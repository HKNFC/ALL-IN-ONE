"""
FMP (Financial Modeling Prep) Veri Sağlayıcı
USA hisse tarama ve backtest için merkezi veri modülü.
BIST verileri bu modülü KULLANMAZ (yfinance/Twelve Data devam eder).

API: https://financialmodelingprep.com/stable
Plan: Premium (750 req/dk)
"""
import os, json, time, logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
import requests

logger = logging.getLogger(__name__)

FMP_API_KEY  = os.environ.get("FMP_API_KEY") or ""
if not FMP_API_KEY:
    raise EnvironmentError("FMP_API_KEY ortam değişkeni tanımlı değil. .env dosyasına ekleyin.")
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
MAX_WORKERS  = 15          # Eş zamanlı istek (750 req/dk limitine göre güvenli)
CACHE_DIR    = Path(os.path.expanduser("~/.cache/fmp"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_HOURS = 20       # Gün içinde yeniden çekme (piyasa kapandıktan sonra 1x yeterli)


# ─── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _get(endpoint, params=None, timeout=12):
    """FMP stable API'ye GET isteği atar."""
    p = params or {}
    p["apikey"] = FMP_API_KEY
    try:
        r = requests.get(f"{FMP_BASE_URL}/{endpoint}", params=p, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"FMP {endpoint} → {r.status_code}")
    except Exception as e:
        logger.error(f"FMP istek hatası {endpoint}: {e}")
    return None


def _cache_path(key: str):
    safe = key.replace("/", "_").replace("?", "_").replace("&", "_")
    return CACHE_DIR / f"{safe}.json"


def _cache_load(key):
    p = _cache_path(key)
    if not p.exists():
        return None
    age_h = (time.time() - p.stat().st_mtime) / 3600
    if age_h > CACHE_TTL_HOURS:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _cache_save(key: str, data):
    try:
        _cache_path(key).write_text(json.dumps(data, default=str))
    except Exception:
        pass


# ─── Hisse Listeleri ─────────────────────────────────────────────────────────

def get_usa_symbols():
    """
    S&P500 + NASDAQ-100 bileşenlerini döndürür (~580 benzersiz hisse).
    Cache: 20 saat geçerli.
    """
    cache_key = "usa_symbols"
    cached = _cache_load(cache_key)
    if cached:
        return cached

    symbols = set()
    for ep in ("sp500-constituent", "nasdaq-constituent"):
        data = _get(ep)
        if data:
            symbols.update(d["symbol"] for d in data if d.get("symbol"))

    result = sorted(symbols)
    if result:
        _cache_save(cache_key, result)
    return result


# ─── Tarihsel Fiyat Verisi ───────────────────────────────────────────────────

def get_history(symbol, from_date=None, to_date=None):
    """
    Tek hisse tarihsel OHLCV verisi döndürür (split-adjusted close).
    from_date / to_date: 'YYYY-MM-DD' formatında.
    """
    if from_date is None:
        from_date = (datetime.today() - timedelta(days=600)).strftime("%Y-%m-%d")
    if to_date is None:
        to_date = datetime.today().strftime("%Y-%m-%d")

    cache_key = f"hist_{symbol}_{from_date}_{to_date}"
    cached = _cache_load(cache_key)
    if cached:
        df = pd.DataFrame(cached)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df.columns = [c.capitalize() for c in df.columns]
        return df

    data = _get("historical-price-eod/full", {
        "symbol": symbol,
        "from": from_date,
        "to": to_date,
    })
    if not data:
        return None

    _cache_save(cache_key, data)
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df.columns = [c.capitalize() for c in df.columns]
    return df


def get_history_bulk(symbols, from_date=None, to_date=None,
                     progress_callback=None):
    """
    Birden fazla hisse için concurrent tarihsel veri çeker.
    Döndürür: {symbol: DataFrame}
    """
    if from_date is None:
        from_date = (datetime.today() - timedelta(days=600)).strftime("%Y-%m-%d")
    if to_date is None:
        to_date = datetime.today().strftime("%Y-%m-%d")

    results = {}
    total = len(symbols)
    done = 0

    def _fetch(sym):
        return sym, get_history(sym, from_date, to_date)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch, s): s for s in symbols}
        for future in as_completed(futures):
            sym, df = future.result()
            if df is not None and not df.empty:
                results[sym] = df
            done += 1
            if progress_callback and done % 20 == 0:
                progress_callback(done, total)

    return results


# ─── Anlık Fiyat ─────────────────────────────────────────────────────────────

def get_quote(symbol):
    """Tek hisse son fiyat + temel istatistikler."""
    data = _get("profile", {"symbol": symbol})
    if data and isinstance(data, list):
        return data[0]
    return None


def get_last_price(symbol):
    q = get_quote(symbol)
    return q["price"] if q else None


# ─── Hızlı tarama (RS skoru için son N gün kapanışı) ─────────────────────────

def get_close_series(symbol, days=300):
    """Sadece kapanış serisi döndürür (RS hesabı için optimize)."""
    from_date = (datetime.today() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    df = get_history(symbol, from_date=from_date)
    if df is None or df.empty or "Close" not in df.columns:
        return None
    return df["Close"].dropna()
