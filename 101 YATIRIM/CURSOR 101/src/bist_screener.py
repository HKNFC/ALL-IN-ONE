"""
BIST Hisse Tarama Modülü
ALFA, BETA, DELTA portföy kriterlerine göre hisse filtreleme
USA ve BIST borsalarını destekler.
"""

import json
import os
import pickle
import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable

# Disk cache: .cache/prices/{borsa}/ sembol_start_end.pkl
_CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".cache", "prices"))
_MAX_WORKERS = 8  # Paralel skor hesaplama

# BIST indeks dosya yolları
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_BIST_INDEKS_DOSYA = os.path.join(_DATA_DIR, "bist_indeksler.json")
_BIST_TUM_DOSYA = os.path.join(_DATA_DIR, "bist_tum_601.json")


def _bist_indeksler_yukle():
    """data/bist_indeksler.json dosyasından gerçek BIST endeks bileşenlerini yükler."""
    try:
        with open(_BIST_INDEKS_DOSYA, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "BIST_30": data.get("BIST_30", []),
            "BIST_50": data.get("BIST_50", []),
            "BIST_100": data.get("BIST_100", []),
            "BIST_100_DISI": data.get("BIST_100_DISI", []),
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _bist_tum_yukle():
    """BIST tüm hisseler (600+) - data/bist_tum_601.json"""
    try:
        with open(_BIST_TUM_DOSYA, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("BIST_TUM", [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


_BIST_INDEKSLER = _bist_indeksler_yukle()
_BIST_TUM_LIST = _bist_tum_yukle()

if _BIST_INDEKSLER:
    BIST_30 = _BIST_INDEKSLER["BIST_30"]
    BIST_50 = _BIST_INDEKSLER["BIST_50"]
    BIST_100 = _BIST_INDEKSLER["BIST_100"]
    BIST_TUM = _BIST_TUM_LIST if _BIST_TUM_LIST else list(dict.fromkeys(BIST_100 + _BIST_INDEKSLER.get("BIST_100_DISI", [])))
    # BIST 100 dışı = Tüm liste - BIST 100 (587 hisse)
    _b100_set = set(BIST_100)
    BIST_100_DISI = [s for s in BIST_TUM if s not in _b100_set]
else:
    BIST_30 = []
    BIST_50 = []
    BIST_100 = []
    BIST_TUM = _BIST_TUM_LIST if _BIST_TUM_LIST else []
    BIST_100_DISI = []

BIST_HAVUZ = BIST_100

# USA: Popüler S&P 500 / Nasdaq hisseleri
USA_HAVUZ = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "PG", "UNH", "MA", "HD", "DIS", "BAC", "ADBE", "XOM",
    "CRM", "CSCO", "PEP", "KO", "AVGO", "COST", "NFLX", "CMCSA", "AMD", "ABT",
    "NEE", "TMO", "DHR", "INTC", "LIN", "PM", "WFC", "TXN", "IBM", "ORCL",
    "GE", "QCOM", "HON", "INTU", "RTX", "NOW", "AMGN", "CAT", "SPGI", "LOW",
]


def _ticker_format(sembol: str, borsa: str) -> str:
    """Borsaya göre yfinance ticker formatı: USA=raw, BIST=.IS"""
    s = sembol.upper().strip()
    if borsa.upper() == "USA":
        return s
    return f"{s}.IS"


def _cache_path(sembol: str, borsa: str, start: str, end: str) -> str:
    """Cache dosya yolu: .cache/prices/{borsa}/GARAN_2021-01-01_2025-01-01.pkl"""
    safe = sembol.replace("-", "_").upper()
    dirpath = os.path.join(_CACHE_DIR, borsa.upper())
    os.makedirs(dirpath, exist_ok=True)
    return os.path.join(dirpath, f"{safe}_{start}_{end}.pkl")


def _fiyat_diskten_oku(sembol: str, borsa: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Cache'den fiyat verisi oku. Yoksa None."""
    path = _cache_path(sembol, borsa, start, end)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _fiyat_diskten_yaz(sembol: str, borsa: str, start: str, end: str, df: pd.DataFrame):
    """Fiyat verisini cache'e yaz."""
    path = _cache_path(sembol, borsa, start, end)
    try:
        with open(path, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass


def fiyat_verisi_toplu_cek(
    semboller: List[str],
    start: str,
    end: str,
    borsa: str = "BIST",
    progress_callback: Callable = None,
) -> Dict[str, pd.DataFrame]:
    """
    Hisseler için fiyat verisi toplu çeker: önce disk cache, eksikleri tek API çağrısında indirir.
    Teknik göstergeler eklenmiş DataFrame'ler döner. {sembol: df}
    """
    if not semboller:
        return {}
    semboller = [s.strip().upper() for s in semboller if s and str(s).strip()]
    today = pd.Timestamp.now().normalize()
    end_adj = end
    if pd.to_datetime(end) > today:
        end_adj = today.strftime("%Y-%m-%d")

    veriler = {}
    indirilecek = []
    ticker_to_sembol = {}

    for i, sembol in enumerate(semboller):
        if progress_callback:
            progress_callback((i + 1) / len(semboller), f"Cache kontrol: {sembol}")
        df = _fiyat_diskten_oku(sembol, borsa, start, end_adj)
        if df is not None and len(df) >= 220:
            df = teknik_gostergeler(df)
            if not df.empty and len(df) >= 20:
                veriler[sembol] = df
                continue
        ticker = _ticker_format(sembol, borsa)
        indirilecek.append(ticker)
        ticker_to_sembol[ticker] = sembol

    if not indirilecek:
        return veriler

    # Toplu indirme - tek API çağrısı (~50x daha hızlı)
    end_dl = (pd.to_datetime(end_adj) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # yfinance end eksklusif
    if progress_callback:
        progress_callback(0.95, f"{len(indirilecek)} hisse indiriliyor...")
    try:
        df_all = yf.download(
            indirilecek,
            start=start,
            end=end_dl,
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )
    except Exception:
        return veriler

    if df_all.empty or len(df_all) < 50:
        return veriler

    # MultiIndex veya tek sütun parse
    if isinstance(df_all.columns, pd.MultiIndex):
        tickers_in_result = df_all.columns.get_level_values(0).unique()
        for ticker in tickers_in_result:
            if ticker not in ticker_to_sembol:
                continue
            sembol = ticker_to_sembol[ticker]
            try:
                sub = df_all[ticker].copy()
                if sub is None or sub.empty:
                    continue
                if isinstance(sub, pd.Series):
                    continue
                sub.columns = [c.lower() if isinstance(c, str) else c for c in sub.columns]
                if "adj close" in sub.columns and "close" not in sub.columns:
                    sub = sub.rename(columns={"adj close": "close"})
                req = ["open", "high", "low", "close", "volume"]
                if not all(c in sub.columns for c in req):
                    continue
                sub = sub[req].dropna()
                sub.columns = [c.lower() for c in sub.columns]
                if len(sub) < 220:
                    continue
                _fiyat_diskten_yaz(sembol, borsa, start, end_adj, sub.copy())
                sub = teknik_gostergeler(sub)
                if not sub.empty and len(sub) >= 20:
                    veriler[sembol] = sub
            except Exception:
                continue
    else:
        # Tek hisse - yfinance bazen MultiIndex yapmıyor
        if len(indirilecek) == 1:
            ticker = indirilecek[0]
            sembol = ticker_to_sembol.get(ticker)
            if sembol:
                sub = df_all.copy()
                if "Adj Close" in sub.columns and "Close" not in sub.columns:
                    sub = sub.rename(columns={"Adj Close": "Close"})
                sub = sub[["Open", "High", "Low", "Close", "Volume"]].dropna()
                sub.columns = [c.lower() for c in sub.columns]
                if len(sub) >= 220:
                    _fiyat_diskten_yaz(sembol, borsa, start, end_adj, sub.copy())
                    sub = teknik_gostergeler(sub)
                    if not sub.empty and len(sub) >= 20:
                        veriler[sembol] = sub

    return veriler


def get_havuz(borsa: str, bist_indeks: str = None) -> list:
    """Borsa ve (BIST için) indeks seçimine göre hisse havuzu döner."""
    if borsa.upper() == "USA":
        return USA_HAVUZ.copy()
    # BIST
    indeks_map = {
        "BIST_TUM": BIST_TUM,
        "BIST_100": BIST_100,
        "BIST_30": BIST_30,
        "BIST_50": BIST_50,
        "BIST_100_DISI": BIST_100_DISI,
    }
    key = (bist_indeks or "BIST_100").upper()
    return indeks_map.get(key, BIST_100).copy()


def hisse_verisi_cek(sembol: str, gun: int = 365, start: str = None, end: str = None, borsa: str = "BIST") -> Optional[pd.DataFrame]:
    """Hisse fiyat verisi çeker. borsa: BIST (.IS) veya USA"""
    try:
        ticker = _ticker_format(sembol, borsa)
        today = pd.Timestamp.now().normalize()
        if start and end:
            end_ts = pd.to_datetime(end)
            if end_ts > today:
                end = today.strftime("%Y-%m-%d")
            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, threads=False)
            if df.empty or len(df) < 250:
                df = yf.download(ticker, period="730d", auto_adjust=True, progress=False, threads=False)
                if len(df) > 0 and start:
                    bas_t = pd.to_datetime(start)
                    df = df[df.index >= bas_t]
        else:
            df = yf.download(ticker, period=f"{gun}d", auto_adjust=True, progress=False, threads=False)
        if df.empty or len(df) < 50:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if "Adj Close" in df.columns and "Close" not in df.columns:
            df = df.rename(columns={"Adj Close": "Close"})
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception:
        return None


def rsi_hesapla(seri: pd.Series, periyot: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) hesaplar"""
    delta = seri.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/periyot, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/periyot, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    return 100 - (100 / (1 + rs))


def macd_hesapla(seri: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD, sinyal ve histogram hesaplar"""
    ema_fast = seri.ewm(span=fast, adjust=False).mean()
    ema_slow = seri.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def adx_hesapla(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ADX (Average Directional Index) - trend gücü (0-100). 25 üzeri güçlü trend."""
    prev_c = close.shift(1)
    prev_h = high.shift(1)
    prev_l = low.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_c).abs(),
        (low - prev_c).abs()
    ], axis=1).max(axis=1)
    up_move = high - prev_h
    down_move = prev_l - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=close.index)
    minus_dm = pd.Series(minus_dm, index=close.index)
    # Wilder smoothing (alpha=1/period)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx


def teknik_gostergeler(df: pd.DataFrame) -> pd.DataFrame:
    """Fiyat verisine teknik göstergeler ekler"""
    close = df["close"]
    high, low = df["high"], df["low"]
    
    df = df.copy()
    df["ma_20"] = close.rolling(20).mean()
    df["ma_50"] = close.rolling(50).mean()
    df["ma_200"] = close.rolling(200).mean()
    df["rsi"] = rsi_hesapla(close, 14)
    
    macd_line, signal_line, hist = macd_hesapla(close)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_histogram"] = hist
    
    df["vol_hacim_20"] = df["volume"].rolling(20).mean()
    # True Range (Wilder) -> ATR
    prev_c = close.shift(1)
    tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
    df["atr_14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    df["adx_14"] = adx_hesapla(high, low, close, 14)
    df["ret_20"] = (close / close.shift(20) - 1) * 100  # 20 günlük getiri %
    
    return df.dropna()


def alfa_kriterleri(df: pd.DataFrame) -> dict:
    """
    ALFA (Momentum) - Araştırma temelli kriterler:
    - Fiyat trendde (MA50, MA200), RSI makul, MACD pozitif
    - Hacim onayı, 20g getiri pozitif, ADX>25 (güçlü trend)
    """
    son = df.iloc[-1]
    vol_ok = son["volume"] >= son["vol_hacim_20"] * 0.8 if son["vol_hacim_20"] > 0 else True
    ret_ok = son.get("ret_20", 0) > 0
    adx_ok = son.get("adx_14", 0) > 25
    kriterler = {
        "fiyat_ma50_ust": son["close"] > son["ma_50"],
        "fiyat_ma200_ust": son["close"] > son["ma_200"],
        "rsi_35_75": 35 <= son["rsi"] <= 75,
        "macd_sinyal_ust": son["macd"] > son["macd_signal"],
        "hacim_onayi": vol_ok,
        "momentum_20g": ret_ok,
        "adx_trend": adx_ok,
    }
    return kriterler


def beta_kriterleri(df: pd.DataFrame) -> dict:
    """
    BETA (Değer) - Destek bölgesinde giriş, dip alımına uygun:
    - MA200 civarı (düzeltme sonrası), RSI aşırı satımdan toparlanma
    - Trend filtresi yok: değer stratejisi dip alır
    """
    son = df.iloc[-1]
    kriterler = {
        "fiyat_ma200_destek": son["close"] > son["ma_200"] * 0.90,
        "asiri_deger_yok": son["close"] <= son["ma_200"] * 1.25,
        "rsi_20_60": 20 <= son["rsi"] <= 60,
        "hacim_likidite": son["volume"] >= son["vol_hacim_20"] * 0.4 if son["vol_hacim_20"] > 0 else True,
    }
    return kriterler


def delta_kriterleri(df: pd.DataFrame) -> dict:
    """
    DELTA (Defansif) - Düşük volatilite, düzeltmede de çalışır:
    - Fiyat > MA200, ATR% düşük. MA50>MA200 skor için (zorunlu değil)
    """
    son = df.iloc[-1]
    atr_pct = (son["atr_14"] / son["close"]) * 100 if son["close"] > 0 else 100
    ma_uptrend = son["ma_50"] > son["ma_200"]
    kriterler = {
        "fiyat_ma200_ust": son["close"] > son["ma_200"],
        "rsi_28_68": 28 <= son["rsi"] <= 68,
        "dusuk_volatilite": atr_pct <= 5.5,
        "ma_altin_kesişim": ma_uptrend,
        "hacim_istikrar": son["volume"] >= son["vol_hacim_20"] * 0.25 if son["vol_hacim_20"] > 0 else True,
    }
    return kriterler


def hisse_tara(sembol: str, portfoy_tipi: str = "ALFA", borsa: str = "BIST", tarih: str = None) -> Optional[dict]:
    """
    Tek hisse için tarama yapar.
    portfoy_tipi: ALFA, BETA, DELTA
    borsa: BIST veya USA
    tarih: "YYYY-MM-DD" - bu tarihte tarama (None = bugün)
    """
    if tarih:
        t = pd.to_datetime(tarih)
        start = (t - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
        end = (t + pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # yfinance end eksklusif
        df = hisse_verisi_cek(sembol, gun=400, start=start, end=end, borsa=borsa)
    else:
        df = hisse_verisi_cek(sembol, borsa=borsa)
    if df is None or len(df) < 100:
        return None
    
    df = teknik_gostergeler(df)
    if df.empty:
        return None
    
    son = df.iloc[-1]
    
    if portfoy_tipi == "ALFA":
        kriterler = alfa_kriterleri(df)
    elif portfoy_tipi == "BETA":
        kriterler = beta_kriterleri(df)
    elif portfoy_tipi == "DELTA":
        kriterler = delta_kriterleri(df)
    else:
        return None
    
    gecen = sum(kriterler.values())
    toplam = len(kriterler)
    # Backtest ile aynı puanlama: her kriter için ağırlıklı puan (sıralama için)
    idx_son = len(df) - 1
    puan = _kriter_skor_satir(df, idx_son, portfoy_tipi)
    if puan < 0:
        puan = 0
    
    return {
        "sembol": sembol,
        "portfoy": portfoy_tipi,
        "son_fiyat": round(son["close"], 2),
        "rsi": round(son["rsi"], 1),
        "ma_20": round(son["ma_20"], 2),
        "ma_50": round(son["ma_50"], 2),
        "ma_200": round(son["ma_200"], 2),
        "macd": round(son["macd"], 4),
        "skor": puan,
        "gecen_kriter": gecen,
        "toplam_kriter": toplam,
        "kriterler": kriterler,
    }


def _tarama_tek_hisse(args) -> Optional[dict]:
    """Paralel tarama için tek hisse skorlama."""
    sembol, df, portfoy_tipi = args
    if df is None or len(df) < 100:
        return None
    try:
        son = df.iloc[-1]
        if portfoy_tipi == "ALFA":
            kriterler = alfa_kriterleri(df)
        elif portfoy_tipi == "BETA":
            kriterler = beta_kriterleri(df)
        elif portfoy_tipi == "DELTA":
            kriterler = delta_kriterleri(df)
        else:
            return None
        idx_son = len(df) - 1
        puan = _kriter_skor_satir(df, idx_son, portfoy_tipi)
        if puan < 0:
            puan = 0
        return {
            "sembol": sembol,
            "portfoy": portfoy_tipi,
            "son_fiyat": round(son["close"], 2),
            "rsi": round(son["rsi"], 1),
            "ma_20": round(son["ma_20"], 2),
            "ma_50": round(son["ma_50"], 2),
            "ma_200": round(son["ma_200"], 2),
            "macd": round(son["macd"], 4),
            "skor": puan,
            "gecen_kriter": sum(kriterler.values()),
            "toplam_kriter": len(kriterler),
            "kriterler": kriterler,
        }
    except Exception:
        return None


def toplu_tara(hisse_listesi: list, portfoy_tipi: str = "ALFA", borsa: str = "BIST", tarih: str = None) -> pd.DataFrame:
    """Hisse listesini tarar: toplu veri çekme + paralel skor hesaplama."""
    hisse_listesi = [s.strip().upper() for s in hisse_listesi if s and str(s).strip()]
    if not hisse_listesi:
        return pd.DataFrame()

    if tarih:
        t = pd.to_datetime(tarih)
        start = (t - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
        end = (t + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        end = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=420)).strftime("%Y-%m-%d")

    veriler = fiyat_verisi_toplu_cek(hisse_listesi, start, end, borsa=borsa)
    if not veriler:
        return pd.DataFrame()

    args_list = [(s, df, portfoy_tipi) for s, df in veriler.items()]
    sonuclar = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = [ex.submit(_tarama_tek_hisse, a) for a in args_list]
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if r is not None:
                    sonuclar.append(r)
            except Exception:
                pass

    if not sonuclar:
        return pd.DataFrame()
    df_out = pd.DataFrame(sonuclar)
    df_out = df_out.sort_values(["skor", "gecen_kriter"], ascending=[False, False]).reset_index(drop=True)
    return df_out


# ============ BACKTEST ============

def _kriter_kontrol_satir(df: pd.DataFrame, idx: int, portfoy_tipi: str) -> bool:
    """Belirli bir tarih (idx) için kriterlerin geçilip geçilmediğini kontrol eder."""
    if idx < 0 or idx >= len(df):
        return False
    satir = df.iloc[idx]
    try:
        if portfoy_tipi == "ALFA":
            ma50_ust = satir["close"] > satir["ma_50"]
            ma200_ust = satir["close"] > satir["ma_200"]
            rsi_ok = 35 <= satir["rsi"] <= 75
            macd_ok = satir["macd"] > satir["macd_signal"]
            kosullar = [ma50_ust, ma200_ust, rsi_ok, macd_ok]
            return bool(sum(kosullar) >= 3)
        elif portfoy_tipi == "BETA":
            ma200_ust = satir["close"] > satir["ma_200"] * 0.90
            asiri_deger_yok = satir["close"] <= satir["ma_200"] * 1.25
            rsi_ok = 20 <= satir["rsi"] <= 60
            vol_ok = satir["volume"] >= satir["vol_hacim_20"] * 0.4 if satir["vol_hacim_20"] > 0 else True
            return bool(ma200_ust and asiri_deger_yok and rsi_ok and vol_ok)
        elif portfoy_tipi == "DELTA":
            ma200_ust = satir["close"] > satir["ma_200"]
            rsi_ok = 28 <= satir["rsi"] <= 68
            atr_pct = (satir["atr_14"] / satir["close"]) * 100 if satir["close"] > 0 else 100
            vol_ok = atr_pct <= 5.5
            vol_istikrar = satir["volume"] >= satir["vol_hacim_20"] * 0.25 if satir["vol_hacim_20"] > 0 else True
            return bool(ma200_ust and rsi_ok and vol_ok and vol_istikrar)
    except (KeyError, TypeError):
        pass
    return False


def _kriter_skor_satir(df: pd.DataFrame, idx: int, portfoy_tipi: str) -> float:
    """Kriterlere uyan hisseleri sıralamak için skor (yüksek = daha iyi)."""
    if idx < 0 or idx >= len(df):
        return -999
    satir = df.iloc[idx]
    try:
        if portfoy_tipi == "ALFA":
            s = 0
            s += 8 if satir["close"] > satir["ma_50"] else 0
            s += 8 if satir["close"] > satir["ma_200"] else 0
            s += 8 if 35 <= satir["rsi"] <= 75 else 0
            s += 8 if satir["macd"] > satir["macd_signal"] else 0
            s += 8 if satir["volume"] >= satir["vol_hacim_20"] * 0.8 else 0
            s += 15 if satir.get("ret_20", 0) > 0 else 0
            s += 15 if satir.get("adx_14", 0) > 25 else 0
            return s
        elif portfoy_tipi == "BETA":
            s = 0
            s += 20 if satir["close"] > satir["ma_200"] * 0.90 else 0
            s += 15 if satir["close"] <= satir["ma_200"] * 1.25 else 0
            s += 25 if 20 <= satir["rsi"] <= 60 else 0
            s += 20 if satir["volume"] >= satir["vol_hacim_20"] * 0.4 else 0
            return s
        elif portfoy_tipi == "DELTA":
            s = 0
            s += 18 if satir["close"] > satir["ma_200"] else 0
            s += 12 if satir["ma_50"] > satir["ma_200"] else 0
            s += 18 if 28 <= satir["rsi"] <= 68 else 0
            atr_pct = (satir["atr_14"] / satir["close"]) * 100 if satir["close"] > 0 else 100
            s += 22 if atr_pct <= 5.5 else 0
            s += 8 if satir["volume"] >= satir["vol_hacim_20"] * 0.25 else 0
            return s
    except (KeyError, TypeError):
        pass
    return -999


PERIYOD_GUN = {"1_ay": 30, "15_gun": 15, "1_hafta": 7}


def portfoy_backtest(
    portfoy_tipi: str,
    baslangic_tarih: str,
    bitis_tarih: str,
    baslangic_sermaye: float = 100_000,
    hisse_havuzu: list = None,
    periyod: str = "1_ay",
    progress_callback=None,
    borsa: str = "BIST",
    bist_indeks: str = "BIST_100",
) -> Optional[dict]:
    """
    Seçilen portföyün (ALFA/BETA/DELTA) kriterlerine göre backtest.
    periyod: "1_ay", "15_gun", "1_hafta" - tarama/rebalans sıklığı
    borsa: BIST veya USA
    """
    from datetime import datetime as dt
    
    havuz = hisse_havuzu or get_havuz(borsa, bist_indeks)
    # MA200 için ~300 iş günü (14 ay) öncesi gerekli
    fetch_start = (pd.to_datetime(baslangic_tarih) - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    fetch_end = (pd.to_datetime(bitis_tarih) + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    
    # Toplu veri çekme: disk cache + tek API çağrısı
    veriler = fiyat_verisi_toplu_cek(havuz, fetch_start, fetch_end, borsa=borsa, progress_callback=progress_callback)
    
    if not veriler:
        return None
    
    # Tüm tarihler (en geniş ortak tarih aralığı)
    tum_tarihler = pd.DatetimeIndex(
        sorted(set().union(*[set(v.index) for v in veriler.values()]))
    )
    bas_t = pd.to_datetime(baslangic_tarih)
    bit_t = pd.to_datetime(bitis_tarih)
    tarihler = tum_tarihler[(tum_tarihler >= bas_t) & (tum_tarihler <= bit_t)]
    
    if len(tarihler) < 20:
        return None
    
    # Rebalans tarihleri: seçilen periyoda göre (1 ay, 15 gün, 1 hafta)
    periyod_gun = PERIYOD_GUN.get(periyod, 30)
    rebalans_tarihleri = []
    simdi = pd.Timestamp(bas_t)
    bit_ts = pd.Timestamp(bit_t)
    while simdi <= bit_ts:
        sonraki = tarihler[tarihler >= simdi]
        if len(sonraki) > 0:
            rebalans_tarihleri.append(sonraki[0])
        simdi = simdi + pd.Timedelta(days=periyod_gun)
    rebalans_tarihleri = sorted(set(rebalans_tarihleri))
    
    positions = {}
    equity_curve = []
    islemler = []
    
    def _portfoy_degeri(poss, tarih_noktasi):
        """Verilen tarihte portföy değerini hesapla"""
        if not poss:
            return baslangic_sermaye
        deger = 0
        for s, adet in poss.items():
            if s not in veriler:
                continue
            df = veriler[s]
            gecm = df.index[df.index <= tarih_noktasi]
            if len(gecm) > 0:
                son_fiyat = df.loc[gecm[-1], "close"]
                deger += adet * son_fiyat
        return deger
    
    def _tek_hisse_skor(args):
        """Paralel skor hesaplama için helper."""
        s, df, reb_tarih = args
        if hisse_havuzu is not None and s not in hisse_havuzu:
            return None
        gecm = df.index[df.index <= reb_tarih]
        if len(gecm) < 1:
            return None
        idx = df.index.get_loc(gecm[-1])
        if not _kriter_kontrol_satir(df, idx, portfoy_tipi):
            return None
        skor = _kriter_skor_satir(df, idx, portfoy_tipi)
        return (s, skor)

    for ridx, reb_tarih in enumerate(rebalans_tarihleri):
        deger = _portfoy_degeri(positions, reb_tarih) if positions else baslangic_sermaye
        
        # Kriterlere uyan hisseleri paralel tara (ThreadPoolExecutor)
        uyanlar = []
        args_list = [(s, df, reb_tarih) for s, df in veriler.items()]
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = [ex.submit(_tek_hisse_skor, a) for a in args_list]
            for fut in as_completed(futures):
                try:
                    r = fut.result()
                    if r is not None:
                        uyanlar.append(r)
                except Exception:
                    pass
        uyanlar = sorted(uyanlar, key=lambda x: x[1], reverse=True)[:5]
        uyanlar = [s for s, _ in uyanlar]
        
        positions = {}
        if uyanlar:
            parcabasi = deger / len(uyanlar)
            for s in uyanlar:
                df = veriler[s]
                gecm = df.index[df.index <= reb_tarih]
                if len(gecm) > 0:
                    fiyat = df.loc[gecm[-1], "close"]
                    if fiyat > 0:
                        positions[s] = parcabasi / fiyat
        islemler.append({"tarih": str(reb_tarih)[:10], "hisseler": list(positions.keys()), "deger": _portfoy_degeri(positions, reb_tarih)})
        
        # Günlük değer: bu rebalanstan sonrakine kadar (tarih tekrarsız)
        bitis_gun = rebalans_tarihleri[ridx + 1] if ridx + 1 < len(rebalans_tarihleri) else tarihler.max()
        gunler = tarihler[(tarihler >= reb_tarih) & (tarihler <= bitis_gun)]
        for g in gunler:
            equity_curve.append({"tarih": pd.Timestamp(g), "equity": _portfoy_degeri(positions, g)})
    
    # Tarih tekrarlarını kaldır (aynı günde son hesaplanan değer geçerli)
    eq_dict = {str(e["tarih"])[:10]: e for e in equity_curve}
    equity_curve = [{"tarih": pd.to_datetime(k), "equity": v["equity"]} for k, v in sorted(eq_dict.items())]
    
    if not equity_curve:
        return None
    
    eq_df = pd.DataFrame(equity_curve)
    son_deger = eq_df["equity"].iloc[-1]
    toplam_getiri = (son_deger - baslangic_sermaye) / baslangic_sermaye * 100
    
    eq_df["peak"] = eq_df["equity"].cummax()
    eq_df["drawdown"] = (eq_df["equity"] - eq_df["peak"]) / eq_df["peak"].replace(0, np.nan) * 100
    max_drawdown = eq_df["drawdown"].min() if eq_df["drawdown"].notna().any() else 0
    
    gun_sayisi = (pd.to_datetime(eq_df["tarih"].iloc[-1]) - pd.to_datetime(eq_df["tarih"].iloc[0])).days
    yil = gun_sayisi / 365.25 if gun_sayisi > 0 else 1
    cagr = ((son_deger / baslangic_sermaye) ** (1 / yil) - 1) * 100 if yil > 0 else 0
    
    periyod_etiket = {"1_ay": "1 Ay", "15_gun": "15 Gün", "1_hafta": "1 Hafta"}.get(periyod, periyod)
    return {
        "portfoy": portfoy_tipi,
        "periyod": periyod_etiket,
        "baslangic_sermaye": baslangic_sermaye,
        "son_deger": son_deger,
        "toplam_getiri_pct": toplam_getiri,
        "cagr_pct": cagr,
        "max_drawdown_pct": max_drawdown,
        "rebalans_sayisi": len(rebalans_tarihleri),
        "analiz_edilen_hisse": len(veriler),
        "islemler": islemler,
        "equity_curve": equity_curve,
        "baslangic_tarih": str(eq_df["tarih"].iloc[0])[:10],
        "bitis_tarih": str(eq_df["tarih"].iloc[-1])[:10],
    }


def backtest_calistir(sembol: str, portfoy_tipi: str = "ALFA", baslangic_sermaye: float = 100_000, borsa: str = "BIST") -> Optional[dict]:
    """
    Tek hisse için portföy kriterlerine göre backtest (eski API - geriye uyumluluk).
    """
    df = hisse_verisi_cek(sembol, gun=730, borsa=borsa)
    if df is None or len(df) < 250:
        return None
    
    df = teknik_gostergeler(df)
    if df.empty or len(df) < 250:
        return None
    
    sermaye = baslangic_sermaye
    pozisyon, giris_fiyat = 0.0, 0.0
    islemler, equity_curve = [], []
    
    for i in range(200, len(df)):
        tarih, fiyat = df.index[i], df["close"].iloc[i]
        kriter_ok = _kriter_kontrol_satir(df, i, portfoy_tipi)
        
        if kriter_ok and pozisyon == 0:
            pozisyon, giris_fiyat = sermaye / fiyat, fiyat
            sermaye = 0
            islemler.append({"tarih": tarih, "islem": "AL", "fiyat": fiyat, "adet": pozisyon})
        elif not kriter_ok and pozisyon > 0:
            sermaye = pozisyon * fiyat
            kar = (fiyat - giris_fiyat) / giris_fiyat * 100
            islemler.append({"tarih": tarih, "islem": "SAT", "fiyat": fiyat, "adet": pozisyon, "kar_pct": kar})
            pozisyon, giris_fiyat = 0, 0
        
        equity_curve.append({"tarih": tarih, "equity": sermaye + pozisyon * fiyat})
    
    if pozisyon > 0:
        son_fiyat = df["close"].iloc[-1]
        sermaye = pozisyon * son_fiyat
        islemler.append({"tarih": df.index[-1], "islem": "SAT", "fiyat": son_fiyat, "adet": pozisyon, "kar_pct": (son_fiyat - giris_fiyat) / giris_fiyat * 100})
    
    son_deger = sermaye + (pozisyon * df["close"].iloc[-1] if pozisyon > 0 else 0)
    eq_df = pd.DataFrame(equity_curve)
    eq_df["peak"], eq_df["drawdown"] = eq_df["equity"].cummax(), (eq_df["equity"] - eq_df["equity"].cummax()) / eq_df["equity"].cummax() * 100
    karlar = [x["kar_pct"] for x in islemler if x["islem"] == "SAT" and "kar_pct" in x]
    yil = (eq_df["tarih"].iloc[-1] - eq_df["tarih"].iloc[0]).days / 365.25
    
    return {
        "sembol": sembol, "portfoy": portfoy_tipi, "baslangic_sermaye": baslangic_sermaye, "son_deger": son_deger,
        "toplam_getiri_pct": (son_deger - baslangic_sermaye) / baslangic_sermaye * 100,
        "cagr_pct": ((son_deger / baslangic_sermaye) ** (1 / yil) - 1) * 100 if yil > 0 else 0,
        "max_drawdown_pct": eq_df["drawdown"].min(),
        "islem_sayisi": len([i for i in islemler if i["islem"] == "AL"]),
        "win_rate_pct": sum(1 for k in karlar if k > 0) / len(karlar) * 100 if karlar else 0,
        "islemler": islemler, "equity_curve": equity_curve,
        "baslangic_tarih": str(eq_df["tarih"].iloc[0])[:10], "bitis_tarih": str(eq_df["tarih"].iloc[-1])[:10],
    }
