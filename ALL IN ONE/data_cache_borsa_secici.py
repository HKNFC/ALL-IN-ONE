"""
Veri Çekme Sistemi
==================

Mimari:
  BIST hisseleri  → Twelve Data (gerçek fiyat, Matriks ile uyumlu)
                  → pkl cache (TTL 1 gün)
  ABD hisseleri   → yfinance toplu (100'lük gruplar, rate limit yok)
                  → pkl cache (TTL 1 gün)
  Endeksler       → yfinance tek tek

Canlı Tarama (sadece bugün):
  Yahoo Finance  ↔  Twelve Data çapraz doğrulama
  %3'ten fazla fark → ⚠️ uyarı
"""

import os
import time
import pickle
import logging
import requests
from datetime import datetime, timedelta, date

import pandas as pd

logger = logging.getLogger(__name__)

# ── Sabitler ──────────────────────────────────────────────────────────────────
CACHE_DIR    = os.path.join(os.path.dirname(__file__), ".cache", "prices")
CACHE_TTL    = 86400          # 1 gün (saniye) — hafta içi
CACHE_TTL_WE = 86400 * 3      # 3 gün — hafta sonu cache daha uzun geçerli


def _effective_ttl() -> int:
    """Hafta sonu/tatil günlerinde cache daha uzun geçerli."""
    wd = date.today().weekday()
    return CACHE_TTL_WE if wd >= 5 else CACHE_TTL  # 5=Sat, 6=Sun

TD_API_KEY   = os.environ.get("TWELVEDATA_API_KEY", "e7e92117f1e6465685829ea63688503f")
TD_BASE_URL  = "https://api.twelvedata.com/time_series"
TD_PRICE_URL = "https://api.twelvedata.com/price"
TD_RPM        = 370           # Grow plan: 377 kredi/dk, %98 güvenlik marjı
TD_BATCH_SIZE = 5             # Tek API isteğinde kaç hisse (batch endpoint)
# 5 hisse/istek, 370 kredi/dk → 74 istek/dk → her istek arası ~0.81s
TD_BATCH_SLEEP = 60 / (TD_RPM / TD_BATCH_SIZE)  # ~0.81s

YF_CHUNK     = 100            # yfinance toplu istek başına hisse sayısı
YF_CHUNK_GAP = 3              # gruplar arası bekleme (saniye)

os.makedirs(CACHE_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sembol yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def _is_bist(ticker: str) -> bool:
    return ticker.endswith(".IS")


def _to_td_symbol(ticker: str):
    """yfinance ticker → Twelve Data sembolü. None → Twelve Data desteklemiyor."""
    if ticker.startswith("^") or ticker in ("XU100.IS", "XU030.IS"):
        return None
    if ticker.endswith(".IS"):
        return ticker[:-3] + ":BIST"
    return ticker   # ABD hisseleri aynen


# ─────────────────────────────────────────────────────────────────────────────
# Disk cache
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(ticker: str) -> str:
    safe = ticker.replace("/", "_").replace(":", "_").replace("^", "_")
    return os.path.join(CACHE_DIR, f"{safe}.pkl")


def _is_cache_valid(ticker: str, start_str: str, end_str: str) -> bool:
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            meta = pickle.load(f)
        cache_start = meta.get("start_str", "")
        cache_end   = meta.get("end_str",   "")
        if not cache_start or not cache_end:
            return False
        # Tarih aralığı: cache istenen başlangıcı karşılamalı
        if cache_start > start_str:
            return False
        # Bitiş: güncel veri isteniyorsa (end_str >= bugün-5 gün), cache_end de yeterince yakın olmalı
        today_str = date.today().strftime("%Y-%m-%d")
        near_today_start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        if end_str >= near_today_start:
            # Güncel veri isteniyor — cache_end en az dünkü olmalı
            if cache_end < near_today_start:
                return False
            # TTL kontrolü — güncel veri için
            if time.time() - meta.get("fetched_at", 0) > _effective_ttl():
                return False
        else:
            # Sadece geçmiş veri isteniyor — cache_end yeterliyse TTL yok
            if cache_end < end_str:
                return False
        return True
    except Exception:
        return False


def _read_cache(ticker: str, start_str: str, end_str: str) -> pd.DataFrame:
    try:
        with open(_cache_path(ticker), "rb") as f:
            meta = pickle.load(f)
        df = meta.get("data", pd.DataFrame())
        if df.empty:
            return pd.DataFrame()
        mask = (df.index >= pd.Timestamp(start_str)) & (df.index <= pd.Timestamp(end_str))
        return df[mask].copy()
    except Exception:
        return pd.DataFrame()


def _write_cache(ticker: str, df: pd.DataFrame, start_str: str, end_str: str):
    if df is None or df.empty:
        return
    try:
        with open(_cache_path(ticker), "wb") as f:
            pickle.dump({
                "data":       df,
                "fetched_at": time.time(),
                "start_str":  start_str,
                "end_str":    end_str,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning(f"Cache write failed for {ticker}: {e}")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex düzelt, sütunları standartlaştır, timezone kaldır."""
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            df[col] = 0.0
        elif isinstance(df[col], pd.DataFrame):
            df[col] = df[col].iloc[:, 0]
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


# ─────────────────────────────────────────────────────────────────────────────
# Twelve Data — BIST birincil kaynak
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_twelvedata_single(td_symbol: str, start_str: str, end_str: str) -> pd.DataFrame:
    """Twelve Data'dan tek hisse verisi çek (gerçek fiyat, düzeltme yok)."""
    params = {
        "symbol":     td_symbol,
        "interval":   "1day",
        "start_date": start_str,
        "end_date":   end_str,
        "outputsize": 5000,
        "order":      "ASC",
        "apikey":     TD_API_KEY,
    }
    try:
        r = requests.get(TD_BASE_URL, params=params, timeout=15)
        data = r.json()
        if data.get("status") == "error" or "values" not in data:
            return pd.DataFrame()
        rows = data["values"]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume"
        })
        return _normalize_df(df)
    except Exception as e:
        logger.warning(f"Twelve Data fetch error for {td_symbol}: {e}")
        return pd.DataFrame()


def _fetch_td_batch(tickers: list, start_str: str, end_str: str,
                    progress_callback=None) -> dict:
    """
    BIST ve ABD hisselerini Twelve Data batch endpoint ile çeker.
    BIST  → sembol:BIST formatı (örn. GARAN:BIST)
    ABD   → sembol doğrudan (örn. AAPL)
    Endeksler (^...) ve desteklenmeyen semboller → atlanır (yfinance fallback'e kalır)
    Başarısız her hisse için yfinance fallback devreye girer.
    """
    result = {}
    total = len(tickers)

    td_map = {}
    for t in tickers:
        sym = _to_td_symbol(t)
        if sym:
            td_map[t] = sym

    if not td_map:
        return result

    items = list(td_map.items())
    chunks = [items[i:i+TD_BATCH_SIZE] for i in range(0, len(items), TD_BATCH_SIZE)]
    fetched_count = 0

    for ci, chunk in enumerate(chunks):
        if progress_callback:
            done = ci * TD_BATCH_SIZE
            bist_in_chunk = sum(1 for yf_tk, _ in chunk if _is_bist(yf_tk))
            label = "BIST" if bist_in_chunk == len(chunk) else ("ABD" if bist_in_chunk == 0 else "BIST+ABD")
            progress_callback(done, total,
                f"Twelve Data {label} ({done+1}-{min(done+TD_BATCH_SIZE,total)}/{total})...")

        symbols_str = ",".join(sym for _, sym in chunk)
        params = {
            "symbol":     symbols_str,
            "interval":   "1day",
            "start_date": start_str,
            "end_date":   end_str,
            "outputsize": 5000,
            "order":      "ASC",
            "apikey":     TD_API_KEY,
        }
        try:
            r = requests.get(TD_BASE_URL, params=params, timeout=20)
            data = r.json()
        except Exception as e:
            logger.warning(f"TD batch fetch error chunk {ci}: {e}")
            data = {}

        if len(chunk) == 1:
            _, td_sym = chunk[0]
            single_data = {td_sym: data} if "values" in data else data
        else:
            single_data = data

        for yf_tk, td_sym in chunk:
            sym_data = single_data.get(td_sym, {})
            if isinstance(sym_data, dict) and sym_data.get("status") != "error" and "values" in sym_data:
                rows = sym_data["values"]
                if rows:
                    try:
                        df = pd.DataFrame(rows)
                        df["datetime"] = pd.to_datetime(df["datetime"])
                        df = df.set_index("datetime").sort_index()
                        for col in ["open", "high", "low", "close", "volume"]:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                        df = df.rename(columns={
                            "open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"
                        })
                        df = _normalize_df(df)
                        if not df.empty:
                            _write_cache(yf_tk, df, start_str, end_str)
                            result[yf_tk] = df
                            fetched_count += 1
                            continue
                    except Exception as e:
                        logger.warning(f"TD parse error {td_sym}: {e}")

            # Twelve Data başarısız → yfinance fallback
            df_yf = _yf_single(yf_tk, start_str, end_str)
            if not df_yf.empty:
                _write_cache(yf_tk, df_yf, start_str, end_str)
                result[yf_tk] = df_yf

        if ci < len(chunks) - 1:
            time.sleep(TD_BATCH_SLEEP)

    return result


# Geriye dönük uyumluluk için alias
_fetch_td_batch_bist = _fetch_td_batch


# ─────────────────────────────────────────────────────────────────────────────
# yfinance — ABD hisseleri ve endeksler
# ─────────────────────────────────────────────────────────────────────────────

def _yf_single(ticker: str, start_str: str, end_str: str) -> pd.DataFrame:
    """yfinance ile tek hisse indir."""
    import yfinance as yf
    end_plus1 = (datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        raw = yf.download(ticker, start=start_str, end=end_plus1,
                          auto_adjust=True, progress=False)
        return _normalize_df(raw)
    except Exception as e:
        logger.warning(f"yfinance single failed for {ticker}: {e}")
        return pd.DataFrame()


def _yf_bulk_download(tickers: list, start_str: str, end_str: str,
                       progress_callback=None) -> dict:
    """
    yfinance toplu indirme — ABD hisseleri için (100'lük gruplar).
    Sonucu pkl cache'e yazar.
    """
    import yfinance as yf
    result = {}
    if not tickers:
        return result

    end_plus1 = (datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    chunks = [tickers[i:i + YF_CHUNK] for i in range(0, len(tickers), YF_CHUNK)]

    for ci, chunk in enumerate(chunks):
        if progress_callback:
            done = ci * YF_CHUNK
            lo = done + 1
            hi = min(done + YF_CHUNK, len(tickers))
            progress_callback(done, len(tickers),
                f"yfinance ABD ({lo}–{hi}/{len(tickers)})...")
        try:
            raw = yf.download(chunk, start=start_str, end=end_plus1,
                              auto_adjust=True, progress=False,
                              group_by="ticker", threads=True)
            if raw is None or raw.empty:
                continue
            for tk in chunk:
                try:
                    if len(chunk) == 1:
                        df = raw.copy()
                    else:
                        lvl = 1 if isinstance(raw.columns, pd.MultiIndex) else 0
                        if tk not in raw.columns.get_level_values(lvl):
                            continue
                        df = raw.xs(tk, axis=1, level=lvl).copy()
                    df = _normalize_df(df)
                    if not df.empty:
                        _write_cache(tk, df, start_str, end_str)
                        result[tk] = df
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"yfinance chunk {ci} failed: {e}")
        if ci < len(chunks) - 1:
            time.sleep(YF_CHUNK_GAP)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Ana API
# ─────────────────────────────────────────────────────────────────────────────

def get_price_data(ticker: str, start_str: str, end_str: str) -> pd.DataFrame:
    """Tek hisse OHLCV: cache → kaynak."""
    today = date.today().strftime("%Y-%m-%d")
    if end_str > today:
        end_str = today

    if _is_cache_valid(ticker, start_str, end_str):
        df = _read_cache(ticker, start_str, end_str)
        if not df.empty:
            return df

    if _is_bist(ticker):
        td_sym = _to_td_symbol(ticker)
        if td_sym:
            df = _fetch_twelvedata_single(td_sym, start_str, end_str)
            if not df.empty:
                _write_cache(ticker, df, start_str, end_str)
                return df
    return _yf_single(ticker, start_str, end_str)


def batch_get_price_data(tickers: list, start_str: str, end_str: str,
                          progress_callback=None) -> dict:
    """
    Çoklu hisse veri çekme:
      BIST  → Twelve Data (gerçek fiyat) → pkl cache
      ABD   → yfinance toplu             → pkl cache
      Endeks → yfinance tek tek          → pkl cache
    """
    today = date.today().strftime("%Y-%m-%d")
    if end_str > today:
        end_str = today

    result  = {}
    missing_bist = []
    missing_us   = []
    missing_idx  = []

    for ticker in tickers:
        if _is_cache_valid(ticker, start_str, end_str):
            df = _read_cache(ticker, start_str, end_str)
            if not df.empty:
                result[ticker] = df
                continue
        td_sym = _to_td_symbol(ticker)
        if td_sym is None:
            missing_idx.append(ticker)
        elif _is_bist(ticker):
            missing_bist.append(ticker)
        else:
            missing_us.append(ticker)

    # Endeksler — yfinance tek tek
    for ticker in missing_idx:
        df = _yf_single(ticker, start_str, end_str)
        if not df.empty:
            _write_cache(ticker, df, start_str, end_str)
            result[ticker] = df

    # BIST + ABD — Twelve Data (birleşik batch)
    missing_td = missing_bist + missing_us
    if missing_td:
        td_result = _fetch_td_batch(
            missing_td, start_str, end_str, progress_callback=progress_callback)
        result.update(td_result)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Canlı fiyat — çapraz doğrulama
# ─────────────────────────────────────────────────────────────────────────────

def _yf_live_price(ticker: str):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        p = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        return float(p) if p else None
    except Exception:
        return None


def _td_live_price(ticker: str):
    td_sym = _to_td_symbol(ticker)
    if not td_sym:
        return None
    try:
        r = requests.get(TD_PRICE_URL,
                         params={"symbol": td_sym, "apikey": TD_API_KEY},
                         timeout=5)
        p = r.json().get("price")
        return float(p) if p else None
    except Exception:
        return None


def get_live_price_with_validation(ticker: str, threshold_pct: float = 3.0):
    yf_price = _yf_live_price(ticker)
    td_price = _td_live_price(ticker)
    warning = None
    if yf_price and td_price:
        diff_pct = abs(yf_price - td_price) / td_price * 100
        if diff_pct > threshold_pct:
            warning = (f"⚠️ Fiyat uyuşmazlığı: Yahoo={yf_price:.2f}, "
                       f"Twelvedata={td_price:.2f} (fark: {diff_pct:.1f}%)")
    return {"price": yf_price or td_price, "yf": yf_price,
            "td": td_price, "warning": warning}


# ─────────────────────────────────────────────────────────────────────────────
# Cache yönetimi & geriye dönük uyumluluk shim'leri
# ─────────────────────────────────────────────────────────────────────────────

def init_price_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_stats() -> dict:
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".pkl")]
    total_size = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files)
    return {"total_tickers": len(files),
            "total_size_mb": round(total_size / 1024 / 1024, 1),
            "cache_dir": CACHE_DIR}


def clear_cache():
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".pkl"):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except Exception:
                pass


def _get_cached_date_range(ticker: str):
    try:
        with open(_cache_path(ticker), "rb") as f:
            meta = pickle.load(f)
        return meta.get("start_str"), meta.get("end_str")
    except Exception:
        return (None, None)


def _load_from_cache(ticker: str, start_str: str, end_str: str) -> pd.DataFrame:
    return _read_cache(ticker, start_str, end_str)


def _save_to_cache(ticker: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    df = _normalize_df(df.copy())
    if df.empty:
        return
    start_str = df.index.min().strftime("%Y-%m-%d")
    end_str   = df.index.max().strftime("%Y-%m-%d")
    _write_cache(ticker, df, start_str, end_str)


def _batch_download_yfinance_bulk(tickers: list, start_str: str, end_str: str,
                                   progress_callback=None) -> dict:
    """Twelve Data birincil, başarısız hisseler için yfinance fallback."""
    result = _fetch_td_batch(tickers, start_str, end_str, progress_callback)
    missing = [t for t in tickers if t not in result]
    if missing:
        result.update(_yf_bulk_download(missing, start_str, end_str))
    return result
