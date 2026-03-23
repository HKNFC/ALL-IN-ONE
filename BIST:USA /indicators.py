import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume
    direction = typical_price.diff()
    positive_flow = raw_money_flow.where(direction > 0, 0)
    negative_flow = raw_money_flow.where(direction <= 0, 0)
    pos_sum = positive_flow.rolling(period).sum()
    neg_sum = negative_flow.rolling(period).sum()
    mfr = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + mfr))


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle.replace(0, np.nan)
    return upper, middle, lower, width


def find_divergence_bist(close: pd.Series, mfi_series: pd.Series, lookback: int = 10) -> bool:
    """
    Bullish divergence: price makes Lower Low AND MFI makes Higher Low in last `lookback` bars.
    We look for at least two local lows within the window.
    """
    if len(close) < lookback + 5:
        return False

    c = close.iloc[-lookback:].values
    m = mfi_series.iloc[-lookback:].values

    price_lows_idx = []
    for i in range(1, len(c) - 1):
        if c[i] < c[i - 1] and c[i] < c[i + 1]:
            price_lows_idx.append(i)

    if len(price_lows_idx) < 2:
        return False

    i1, i2 = price_lows_idx[-2], price_lows_idx[-1]
    price_lower_low = c[i2] < c[i1]
    mfi_higher_low = m[i2] > m[i1]
    return price_lower_low and mfi_higher_low


def find_divergence_usa(close: pd.Series, mfi_series: pd.Series, lookback: int = 20) -> bool:
    """
    Positive MFI divergence: price flat/sideways while MFI rises.
    Price range < 5% over lookback, MFI trend positive.
    """
    if len(close) < lookback + 5:
        return False

    c = close.iloc[-lookback:].values
    m = mfi_series.iloc[-lookback:].values

    price_range_pct = (c.max() - c.min()) / c[0] * 100 if c[0] != 0 else 999

    mfi_slope = np.polyfit(range(len(m)), m, 1)[0]

    return price_range_pct < 8 and mfi_slope > 0


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema21"] = ema(df["Close"], 21)
    df["ema50"] = ema(df["Close"], 50)
    df["ema200"] = ema(df["Close"], 200)
    df["rsi14"] = rsi(df["Close"], 14)
    df["mfi14"] = mfi(df["High"], df["Low"], df["Close"], df["Volume"], 14)
    df["adx14"] = adx(df["High"], df["Low"], df["Close"], 14)
    _, _, _, df["bb_width"] = bollinger_bands(df["Close"], 20)
    df["bb_width_avg"] = df["bb_width"].rolling(20).mean()
    df["vol_avg10"] = df["Volume"].rolling(10).mean()
    df["roc5"] = df["Close"].pct_change(5) * 100
    df["roc20"] = df["Close"].pct_change(20) * 100
    return df


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def rs_score_bist(last: pd.Series) -> dict:
    """
    BIST RS Puanı (0–100). Bileşenler:
      MFI Gücü       25 pt  – para girişi kalitesi
      Trend Gücü     20 pt  – EMA hiyerarşisi ve mesafe
      Hacim Patlaması 20 pt – anlık hacim / 10g ort
      RSI Momentum   15 pt  – 50-80 bandı ideal
      ADX Güç        10 pt  – trend gücü
      Fiyat Momentum 10 pt  – ROC 5g
    """
    scores = {}

    # MFI Gücü (25 pt): 50-80 arası ideal; 65 civarı tam puan
    mfi_val = float(last.get("mfi14", 50))
    if 50 <= mfi_val <= 80:
        scores["MFI"] = 25 * (1 - abs(mfi_val - 65) / 30)
    elif mfi_val < 50:
        scores["MFI"] = _clamp(25 * (mfi_val - 30) / 20, 0, 12)
    else:
        scores["MFI"] = _clamp(25 * (95 - mfi_val) / 15, 0, 12)

    # Trend Gücü (20 pt): EMA21 > EMA50 ve fiyatın EMA21 üstünde olma mesafesi
    c = float(last.get("Close", 0))
    e21 = float(last.get("ema21", c))
    e50 = float(last.get("ema50", e21))
    if c > e21 > e50 and e21 > 0:
        dist_pct = (c - e21) / e21 * 100
        ema_sep = (e21 - e50) / e50 * 100 if e50 > 0 else 0
        scores["Trend"] = _clamp(10 + dist_pct * 2 + ema_sep * 2, 0, 20)
    else:
        scores["Trend"] = 0

    # Hacim (20 pt): vol / vol_avg10
    vol = float(last.get("Volume", 0))
    vol_avg = float(last.get("vol_avg10", 1))
    vol_ratio = vol / vol_avg if vol_avg > 0 else 0
    scores["Hacim"] = _clamp((vol_ratio - 1.0) / 2.0 * 20, 0, 20)

    # RSI Momentum (15 pt): 50-75 arası ideal
    rsi_val = float(last.get("rsi14", 50))
    if 50 <= rsi_val <= 75:
        scores["RSI"] = 15 * (1 - abs(rsi_val - 62.5) / 25)
    else:
        scores["RSI"] = _clamp(15 * (rsi_val - 40) / 15, 0, 7) if rsi_val < 50 else _clamp(15 * (85 - rsi_val) / 10, 0, 7)

    # ADX Güç (10 pt)
    adx_val = float(last.get("adx14", 0))
    scores["ADX"] = _clamp((adx_val - 15) / 35 * 10, 0, 10)

    # Fiyat Momentum ROC5 (10 pt)
    roc5 = float(last.get("roc5", 0))
    scores["ROC"] = _clamp(roc5 / 5 * 10, 0, 10)

    total = sum(scores.values())
    return {"RS": round(total, 1), **{k: round(v, 1) for k, v in scores.items()}}


def rs_score_usa(last: pd.Series) -> dict:
    """
    USA RS Puanı (0–100). Bileşenler:
      RSI Momentum    20 pt  – 60-80 arası güçlü momentum
      ADX Güç         20 pt  – trend gücü / yönlülük
      MFI Gücü        20 pt  – kurumsal para girişi
      Trend Kalitesi  15 pt  – EMA50/200 hiyerarşisi ve mesafe
      BB Pozisyonu    15 pt  – Bollinger daralması + konum
      Fiyat Momentum  10 pt  – ROC20 (orta vade ivme)
    """
    scores = {}

    # RSI (20 pt): 60-80 arası ideal
    rsi_val = float(last.get("rsi14", 50))
    if 60 <= rsi_val <= 80:
        scores["RSI"] = 20 * (1 - abs(rsi_val - 70) / 20)
    else:
        scores["RSI"] = _clamp(20 * (rsi_val - 45) / 15, 0, 10) if rsi_val < 60 else _clamp(20 * (90 - rsi_val) / 10, 0, 10)

    # ADX (20 pt)
    adx_val = float(last.get("adx14", 0))
    scores["ADX"] = _clamp((adx_val - 20) / 30 * 20, 0, 20)

    # MFI (20 pt): 55-80 arası ideal
    mfi_val = float(last.get("mfi14", 50))
    if 55 <= mfi_val <= 80:
        scores["MFI"] = 20 * (1 - abs(mfi_val - 67.5) / 25)
    else:
        scores["MFI"] = _clamp(20 * (mfi_val - 35) / 20, 0, 10) if mfi_val < 55 else _clamp(20 * (90 - mfi_val) / 10, 0, 10)

    # Trend Kalitesi (15 pt)
    c = float(last.get("Close", 0))
    e50 = float(last.get("ema50", c))
    e200 = float(last.get("ema200", e50))
    if c > e50 > e200 and e50 > 0:
        dist_pct = (c - e50) / e50 * 100
        sep_pct = (e50 - e200) / e200 * 100 if e200 > 0 else 0
        scores["Trend"] = _clamp(7 + dist_pct * 1.5 + sep_pct * 1.5, 0, 15)
    else:
        scores["Trend"] = 0

    # BB Pozisyonu (15 pt): daralma + fiyatın üst banda yakınlığı
    bb_w = float(last.get("bb_width", 0.1))
    bb_w_avg = float(last.get("bb_width_avg", 0.1))
    squeeze_score = _clamp((1 - bb_w / bb_w_avg) * 10, 0, 10) if bb_w_avg > 0 else 0
    scores["BB"] = squeeze_score + _clamp(float(last.get("rsi14", 50)) / 100 * 5, 0, 5)

    # ROC20 (10 pt)
    roc20 = float(last.get("roc20", 0))
    scores["ROC"] = _clamp(roc20 / 15 * 10, 0, 10)

    total = sum(scores.values())
    return {"RS": round(total, 1), **{k: round(v, 1) for k, v in scores.items()}}
