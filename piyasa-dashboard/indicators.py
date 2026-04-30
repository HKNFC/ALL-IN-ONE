import pandas as pd
import numpy as np


def calc_sma(series, period):
    if series is None or len(series) < period:
        return None
    return series.rolling(period).mean()


def calc_rsi(series, period=14):
    if series is None or len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series, fast=12, slow=26, signal=9):
    if series is None or len(series) < slow + signal:
        return None, None, None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_adx(high, low, close, period=14):
    if high is None or len(high) < period * 2:
        return None
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        adx = dx.rolling(period).mean()
        return adx
    except Exception:
        return None


def calc_obv(close, volume):
    if close is None or volume is None or len(close) < 2:
        return None
    direction = np.sign(close.diff())
    obv = (direction * volume).fillna(0).cumsum()
    return obv


def calc_volatility(close, period=20):
    if close is None or len(close) < period + 1:
        return None
    return close.pct_change().rolling(period).std() * np.sqrt(252) * 100


def calc_sma_slope(sma_series, lookback=5):
    if sma_series is None or len(sma_series.dropna()) < lookback + 1:
        return None
    recent = sma_series.dropna()
    slope = (recent.iloc[-1] - recent.iloc[-lookback]) / recent.iloc[-lookback] * 100
    return slope


def calc_breadth(tickers_data, sma_period=50):
    above = 0
    total = 0
    for ticker, close_series in tickers_data.items():
        try:
            if close_series is None or len(close_series.dropna()) < sma_period:
                continue
            close = close_series.dropna()
            sma = close.rolling(sma_period).mean().iloc[-1]
            if close.iloc[-1] > sma:
                above += 1
            total += 1
        except Exception:
            continue
    if total == 0:
        return None, 0, 0
    return (above / total) * 100, above, total


def calc_new_high_low(tickers_data, lookback=52 * 5):
    new_highs = 0
    new_lows = 0
    total = 0
    for ticker, close_series in tickers_data.items():
        try:
            if close_series is None or len(close_series.dropna()) < lookback:
                continue
            close = close_series.dropna()
            high_52w = close.iloc[-lookback:].max()
            low_52w = close.iloc[-lookback:].min()
            current = close.iloc[-1]
            if current >= high_52w * 0.97:
                new_highs += 1
            if current <= low_52w * 1.03:
                new_lows += 1
            total += 1
        except Exception:
            continue
    if total == 0:
        return None, 0, 0
    ratio = new_highs / max(new_lows, 1)
    return ratio, new_highs, new_lows


def calc_sector_breadth(sector_data):
    sector_scores = {}
    strong_sectors = 0
    total_sectors = 0
    for sector_name, tickers_close in sector_data.items():
        above = 0
        total = 0
        for ticker, close in tickers_close.items():
            try:
                if close is None or len(close.dropna()) < 50:
                    continue
                c = close.dropna()
                sma50 = c.rolling(50).mean().iloc[-1]
                if c.iloc[-1] > sma50:
                    above += 1
                total += 1
            except Exception:
                continue
        if total > 0:
            pct = above / total * 100
            sector_scores[sector_name] = pct
            if pct > 60:
                strong_sectors += 1
            total_sectors += 1
    return sector_scores, strong_sectors, total_sectors


def calc_relative_strength(series_a, series_b, period=20):
    if series_a is None or series_b is None:
        return None
    if len(series_a) < period or len(series_b) < period:
        return None
    try:
        common = series_a.index.intersection(series_b.index)
        if len(common) < period:
            return None
        ratio = series_a.loc[common] / series_b.loc[common]
        sma = ratio.rolling(period).mean()
        if len(sma.dropna()) < 2:
            return None
        current = ratio.iloc[-1]
        avg = sma.dropna().iloc[-1]
        return (current / avg - 1) * 100
    except Exception:
        return None


def calc_usdtry_volatility(usdtry_close, period=20):
    if usdtry_close is None or len(usdtry_close) < period + 1:
        return None, None
    vol = usdtry_close.pct_change().rolling(period).std() * np.sqrt(252) * 100
    current_vol = vol.dropna().iloc[-1] if len(vol.dropna()) > 0 else None
    avg_vol = vol.dropna().mean() if len(vol.dropna()) > 0 else None
    return current_vol, avg_vol


def calc_roc(series, period=10):
    """Rate of Change: (current - n_periods_ago) / n_periods_ago * 100"""
    if series is None or len(series) < period + 1:
        return None
    return series.pct_change(period) * 100
