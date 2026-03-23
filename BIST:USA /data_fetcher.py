import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, date
import os
import pickle
import hashlib

CACHE_DIR = ".cache"
CACHE_TTL_HOURS = 4

def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.pkl")

def _load_cache(key: str):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            ts, data = pickle.load(f)
        if datetime.now() - ts < timedelta(hours=CACHE_TTL_HOURS):
            return data
    except Exception:
        pass
    return None

def _save_cache(key: str, data):
    path = _cache_path(key)
    with open(path, "wb") as f:
        pickle.dump((datetime.now(), data), f)

def _drop_incomplete_today(df: pd.DataFrame) -> pd.DataFrame:
    """Remove today's bar if the session is still open (incomplete volume)."""
    if df.empty:
        return df
    today = pd.Timestamp(date.today())
    if df.index[-1].normalize() >= today:
        df = df.iloc[:-1]
    return df

def fetch_ohlcv(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    key = f"{symbol}_{period}_{interval}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = _drop_incomplete_today(df)
        _save_cache(key, df)
        return df
    except Exception:
        return pd.DataFrame()

def fetch_ohlcv_range(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    key = f"{symbol}_{start}_{end}_{interval}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        _save_cache(key, df)
        return df
    except Exception:
        return pd.DataFrame()

def fetch_multiple(symbols: list, period: str = "1y", interval: str = "1d") -> dict:
    result = {}
    for sym in symbols:
        df = fetch_ohlcv(sym, period=period, interval=interval)
        if not df.empty and len(df) >= 50:
            result[sym] = df
    return result
