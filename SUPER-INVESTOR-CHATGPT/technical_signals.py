"""
Technical Signal Score Engine

Computes a 0-100 Technical Signal Score from pre-computed indicator columns
using five sub-components:

  1) Trend Score (30%) — MA50, MA200, golden cross
  2) Momentum Score (20%) — RSI(14), MACD signals
  3) Breakout Score (20%) — proximity to highs, volume ratio
  4) Volume Flow Score (20%) — MFI, OBV trend/divergence
  5) Risk / Stability Penalty (10%) — ATR-based volatility penalty

When pre-computed indicator columns exist on the DataFrame (from
build_technical_data), they are used directly. Falls back to computing
from price_data when columns are missing.
"""

import numpy as np
import pandas as pd
from typing import Optional


COMBINED_WEIGHT_RS = 0.50
COMBINED_WEIGHT_TECH = 0.50

TREND_WEIGHT = 0.30
MOMENTUM_WEIGHT = 0.20
BREAKOUT_WEIGHT = 0.20
VOLUME_FLOW_WEIGHT = 0.20
RISK_WEIGHT = 0.10

SETUP_LABELS = {
    "strong_buy": "Güçlü Alım Adayı",
    "watchlist": "İzleme",
    "early_setup": "Erken Kurulum",
    "avoid": "Kaçın",
}

PRECOMPUTED_COLS = [
    "ma50", "ma200", "ma50_ratio", "ma200_ratio",
    "rsi", "macd_line", "macd_signal", "macd_histogram",
    "atr", "mfi", "volume_ratio",
    "obv_latest", "obv_trend_positive", "obv_slope",
    "distance_to_52w_high",
]


def _safe_float(val) -> float:
    if val is None:
        return np.nan
    try:
        f = float(val)
        return f if np.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _get_closes(price_data: pd.DataFrame) -> Optional[np.ndarray]:
    if price_data is None or not isinstance(price_data, pd.DataFrame):
        return None
    if price_data.empty or "close" not in price_data.columns:
        return None
    arr = price_data["close"].values.astype(float)
    if len(arr) < 5:
        return None
    return arr


def _calc_sma(closes: np.ndarray, window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return float(np.mean(closes[-window:]))


def _calc_ema(closes: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1)
    ema = np.empty_like(closes)
    ema[0] = closes[0]
    for i in range(1, len(closes)):
        ema[i] = alpha * closes[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calc_rsi(closes: np.ndarray, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _calc_macd(closes: np.ndarray):
    if len(closes) < 35:
        return None, None, None
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = _calc_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])


def _calc_atr(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or len(price_data) < period + 1:
        return None
    if not all(c in price_data.columns for c in ["high", "low", "close"]):
        return None
    high = price_data["high"].values.astype(float)
    low = price_data["low"].values.astype(float)
    close = price_data["close"].values.astype(float)
    tr_values = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        tr_values.append(tr)
    if len(tr_values) < period:
        return None
    return float(np.mean(tr_values[-period:]))


def _calc_mfi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or len(price_data) < period + 1:
        return None
    required = ["high", "low", "close", "volume"]
    if not all(c in price_data.columns for c in required):
        return None
    data = price_data.tail(period + 1).copy()
    high = data["high"].values.astype(float)
    low = data["low"].values.astype(float)
    close = data["close"].values.astype(float)
    volume = data["volume"].values.astype(float)
    typical_price = (high + low + close) / 3.0
    raw_money_flow = typical_price * volume
    pos_flow = 0.0
    neg_flow = 0.0
    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i - 1]:
            pos_flow += raw_money_flow[i]
        elif typical_price[i] < typical_price[i - 1]:
            neg_flow += raw_money_flow[i]
    if neg_flow == 0:
        return 100.0
    money_ratio = pos_flow / neg_flow
    mfi = 100.0 - (100.0 / (1.0 + money_ratio))
    return round(mfi, 2)


def _calc_obv(price_data: pd.DataFrame) -> Optional[np.ndarray]:
    if price_data is None or len(price_data) < 5:
        return None
    if "close" not in price_data.columns or "volume" not in price_data.columns:
        return None
    close = price_data["close"].values.astype(float)
    volume = price_data["volume"].values.astype(float)
    obv = np.zeros(len(close))
    obv[0] = volume[0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def _has_precomputed(row) -> bool:
    for col in ["ma50", "rsi", "mfi"]:
        val = row.get(col)
        if val is None:
            continue
        try:
            if pd.isna(val):
                continue
        except (TypeError, ValueError):
            continue
        return True
    return False


def compute_trend_score_from_row(row) -> float:
    current = _safe_float(row.get("close") or (row.get("price_data").iloc[-1]["close"] if isinstance(row.get("price_data"), pd.DataFrame) and not row.get("price_data").empty else np.nan))
    if np.isnan(current) or current <= 0:
        return 50.0

    score = 0.0
    n_signals = 0

    ma50 = _safe_float(row.get("ma50"))
    if not np.isnan(ma50) and ma50 > 0:
        n_signals += 1
        if current > ma50:
            score += 25
            proximity = min((current / ma50 - 1) * 100, 10)
            score += proximity

    ma200 = _safe_float(row.get("ma200"))
    if not np.isnan(ma200) and ma200 > 0:
        n_signals += 1
        if current > ma200:
            score += 25
            proximity = min((current / ma200 - 1) * 100, 10)
            score += proximity

    if not np.isnan(ma50) and not np.isnan(ma200) and ma50 > 0 and ma200 > 0:
        n_signals += 1
        if ma50 > ma200:
            score += 20

    if n_signals == 0:
        return 50.0
    return min(score, 100.0)


def compute_momentum_score_from_row(row) -> float:
    components = []

    rsi = _safe_float(row.get("rsi"))
    if not np.isnan(rsi):
        if 40 <= rsi <= 70:
            rsi_score = 60 + (rsi - 40) * (40.0 / 30.0)
        elif rsi > 70:
            rsi_score = max(100 - (rsi - 70) * 2, 50)
        elif rsi < 30:
            rsi_score = rsi
        else:
            rsi_score = 30 + (rsi - 30) * (30.0 / 10.0)
        components.append(rsi_score)

    macd_line = _safe_float(row.get("macd_line"))
    macd_signal = _safe_float(row.get("macd_signal"))
    macd_histogram = _safe_float(row.get("macd_histogram"))
    if not np.isnan(macd_line) and not np.isnan(macd_signal):
        macd_score = 0.0
        if macd_line > macd_signal:
            macd_score += 50
        if not np.isnan(macd_histogram) and macd_histogram > 0:
            macd_score += 30
        if macd_line > 0:
            macd_score += 20
        components.append(macd_score)

    if not components:
        return 50.0
    return min(float(np.mean(components)), 100.0)


def compute_breakout_score_from_row(row) -> float:
    components = []

    vol_ratio = _safe_float(row.get("volume_ratio"))
    if not np.isnan(vol_ratio):
        vol_score = min(vol_ratio * 50, 100.0)
        components.append(vol_score)

    d52 = _safe_float(row.get("distance_to_52w_high"))
    if not np.isnan(d52):
        proximity_52w = 100.0 + d52
        components.append(min(max(proximity_52w, 0.0), 100.0))

    if not components:
        return 50.0
    return min(float(np.mean(components)), 100.0)


def _score_mfi(mfi: float) -> float:
    if 55 <= mfi <= 75:
        return 85 + (mfi - 55) * (15.0 / 20.0)
    elif 50 <= mfi < 55:
        return 60 + (mfi - 50) * (25.0 / 5.0)
    elif 45 <= mfi < 50:
        return 40 + (mfi - 45) * (20.0 / 5.0)
    elif mfi > 80:
        return max(50 - (mfi - 80) * 3, 10)
    elif mfi > 75:
        return max(85 - (mfi - 75) * 7, 50)
    elif mfi < 30:
        return max(mfi, 5)
    elif mfi < 45:
        return 20 + (mfi - 30) * (20.0 / 15.0)
    return 50.0


def compute_volume_flow_score_from_row(row) -> tuple:
    components = []
    divergence_bonus = 0.0

    mfi = _safe_float(row.get("mfi"))
    if not np.isnan(mfi):
        components.append(_score_mfi(mfi))

    obv_slope = _safe_float(row.get("obv_slope"))
    obv_trend = row.get("obv_trend_positive")

    if not np.isnan(obv_slope):
        obv_latest = _safe_float(row.get("obv_latest"))
        obv_mean = abs(obv_latest) if not np.isnan(obv_latest) and obv_latest != 0 else 1.0
        obv_trend_pct = obv_slope / obv_mean if obv_mean > 0 else 0.0

        obv_score = 50.0
        if obv_trend_pct > 0.1:
            obv_score = 70 + min(obv_trend_pct * 100, 30)
        elif obv_trend_pct > 0:
            obv_score = 50 + obv_trend_pct * 200
        elif obv_trend_pct < -0.1:
            obv_score = max(30 - abs(obv_trend_pct) * 100, 5)
        else:
            obv_score = 50 + obv_trend_pct * 200
        components.append(min(max(obv_score, 0.0), 100.0))

        d52 = _safe_float(row.get("distance_to_52w_high"))
        if not np.isnan(d52):
            price_change_pct = d52 / 100.0
            if price_change_pct > 0.02 and obv_trend_pct < -0.05:
                divergence_bonus = -15.0
            if abs(price_change_pct) < 0.02 and obv_trend_pct > 0.1:
                divergence_bonus = 10.0

    if not components:
        return 50.0, 0.0

    base_score = min(float(np.mean(components)), 100.0)
    return max(min(base_score, 100.0), 0.0), divergence_bonus


def compute_risk_score_from_row(row) -> float:
    atr = _safe_float(row.get("atr"))
    if np.isnan(atr):
        return 50.0

    current = _safe_float(row.get("close") or (row.get("price_data").iloc[-1]["close"] if isinstance(row.get("price_data"), pd.DataFrame) and not row.get("price_data").empty else np.nan))
    if np.isnan(current) or current <= 0:
        return 50.0

    atr_pct = (atr / current) * 100

    if atr_pct <= 1.0:
        return 100.0
    elif atr_pct <= 2.0:
        return 90.0
    elif atr_pct <= 3.0:
        return 75.0
    elif atr_pct <= 5.0:
        return 60.0
    elif atr_pct <= 8.0:
        return 40.0
    else:
        return max(20.0 - (atr_pct - 8.0) * 2, 0.0)


def compute_technical_score_for_row(price_data, row=None) -> float:
    if row is not None and _has_precomputed(row):
        trend = compute_trend_score_from_row(row)
        momentum = compute_momentum_score_from_row(row)
        breakout = compute_breakout_score_from_row(row)
        volume_flow, divergence_bonus = compute_volume_flow_score_from_row(row)
        risk = compute_risk_score_from_row(row)
    else:
        closes = _get_closes(price_data)
        if closes is None:
            return np.nan
        trend = _compute_trend_score_legacy(closes)
        momentum = _compute_momentum_score_legacy(closes)
        breakout = _compute_breakout_score_legacy(closes, price_data)
        volume_flow, divergence_bonus = _compute_volume_flow_score_legacy(closes, price_data)
        risk = _compute_risk_score_legacy(closes, price_data)

    raw = (
        trend * TREND_WEIGHT
        + momentum * MOMENTUM_WEIGHT
        + breakout * BREAKOUT_WEIGHT
        + volume_flow * VOLUME_FLOW_WEIGHT
        + risk * RISK_WEIGHT
        + divergence_bonus
    )
    return round(min(max(raw, 0.0), 100.0), 2)


def _compute_trend_score_legacy(closes: np.ndarray) -> float:
    score = 0.0
    n_signals = 0
    current = closes[-1]

    ma50 = _calc_sma(closes, 50)
    if ma50 is not None:
        n_signals += 1
        if current > ma50:
            score += 25
            proximity = min((current / ma50 - 1) * 100, 10)
            score += proximity

    ma200 = _calc_sma(closes, 200)
    if ma200 is not None:
        n_signals += 1
        if current > ma200:
            score += 25
            proximity = min((current / ma200 - 1) * 100, 10)
            score += proximity

    if ma50 is not None and ma200 is not None:
        n_signals += 1
        if ma50 > ma200:
            score += 20

    if n_signals == 0:
        return 50.0
    return min(score, 100.0)


def _compute_momentum_score_legacy(closes: np.ndarray) -> float:
    components = []

    rsi = _calc_rsi(closes, 14)
    if rsi is not None:
        if 40 <= rsi <= 70:
            rsi_score = 60 + (rsi - 40) * (40.0 / 30.0)
        elif rsi > 70:
            rsi_score = max(100 - (rsi - 70) * 2, 50)
        elif rsi < 30:
            rsi_score = rsi
        else:
            rsi_score = 30 + (rsi - 30) * (30.0 / 10.0)
        components.append(rsi_score)

    macd_line, signal_line, histogram = _calc_macd(closes)
    if macd_line is not None:
        macd_score = 0.0
        if macd_line > signal_line:
            macd_score += 50
        if histogram is not None and histogram > 0:
            macd_score += 30
        if macd_line > 0:
            macd_score += 20
        components.append(macd_score)

    if not components:
        return 50.0
    return min(float(np.mean(components)), 100.0)


def _compute_breakout_score_legacy(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> float:
    components = []

    if len(closes) >= 20:
        high_20d = float(np.max(closes[-20:]))
        if high_20d > 0:
            proximity_20d = (closes[-1] / high_20d) * 100
            components.append(min(proximity_20d, 100.0))

    if len(closes) >= 252:
        high_52w = float(np.max(closes[-252:]))
    elif len(closes) >= 126:
        high_52w = float(np.max(closes))
    else:
        high_52w = None

    if high_52w is not None and high_52w > 0:
        proximity_52w = (closes[-1] / high_52w) * 100
        components.append(min(proximity_52w, 100.0))

    if (price_data is not None and "volume" in price_data.columns
            and len(price_data) >= 20):
        volumes = price_data["volume"].values.astype(float)
        avg_vol = np.mean(volumes[-20:])
        if avg_vol > 0 and np.isfinite(avg_vol):
            current_vol = volumes[-1]
            vol_ratio = current_vol / avg_vol
            vol_score = min(vol_ratio * 50, 100.0)
            components.append(vol_score)

    if not components:
        return 50.0
    return min(float(np.mean(components)), 100.0)


def _score_obv(obv: np.ndarray, closes: np.ndarray) -> tuple:
    lookback = min(20, len(obv) - 1)
    if lookback < 5:
        return 50.0, 0.0

    obv_recent = obv[-lookback:]
    closes_recent = closes[-lookback:]

    obv_slope = (obv_recent[-1] - obv_recent[0])
    obv_mean = np.mean(np.abs(obv_recent))
    if obv_mean > 0:
        obv_trend_pct = obv_slope / obv_mean
    else:
        obv_trend_pct = 0.0

    price_change_pct = 0.0
    if closes_recent[0] > 0:
        price_change_pct = (closes_recent[-1] - closes_recent[0]) / closes_recent[0]

    obv_score = 50.0
    if obv_trend_pct > 0.1:
        obv_score = 70 + min(obv_trend_pct * 100, 30)
    elif obv_trend_pct > 0:
        obv_score = 50 + obv_trend_pct * 200
    elif obv_trend_pct < -0.1:
        obv_score = max(30 - abs(obv_trend_pct) * 100, 5)
    else:
        obv_score = 50 + obv_trend_pct * 200

    divergence_bonus = 0.0

    if price_change_pct > 0.02 and obv_trend_pct < -0.05:
        divergence_bonus = -15.0

    if abs(price_change_pct) < 0.02 and obv_trend_pct > 0.1:
        divergence_bonus = 10.0

    return min(max(obv_score, 0.0), 100.0), divergence_bonus


def _compute_volume_flow_score_legacy(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> tuple:
    components = []
    divergence_bonus = 0.0

    mfi = _calc_mfi(price_data)
    if mfi is not None:
        components.append(_score_mfi(mfi))

    obv = _calc_obv(price_data)
    if obv is not None and len(closes) >= 5:
        obv_s, div_b = _score_obv(obv, closes)
        components.append(obv_s)
        divergence_bonus = div_b

    if not components:
        return 50.0, 0.0

    base_score = min(float(np.mean(components)), 100.0)
    return max(min(base_score, 100.0), 0.0), divergence_bonus


def _compute_risk_score_legacy(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> float:
    atr = _calc_atr(price_data)
    if atr is None or closes[-1] <= 0:
        return 50.0

    atr_pct = (atr / closes[-1]) * 100

    if atr_pct <= 1.0:
        score = 100.0
    elif atr_pct <= 2.0:
        score = 90.0
    elif atr_pct <= 3.0:
        score = 75.0
    elif atr_pct <= 5.0:
        score = 60.0
    elif atr_pct <= 8.0:
        score = 40.0
    else:
        score = max(20.0 - (atr_pct - 8.0) * 2, 0.0)

    return score


def assign_setup_label(rs_score: float, tech_score: float) -> str:
    rs = _safe_float(rs_score)
    tech = _safe_float(tech_score)
    if np.isnan(rs) or np.isnan(tech):
        return "N/A"
    if rs >= 75 and tech >= 70:
        return SETUP_LABELS["strong_buy"]
    if rs >= 70 and 50 <= tech < 70:
        return SETUP_LABELS["watchlist"]
    if rs >= 70 and tech < 50:
        return SETUP_LABELS["early_setup"]
    return SETUP_LABELS["avoid"]


def _compute_volume_indicators(row, price_data) -> dict:
    indicators = {"mfi": np.nan, "obv_trend_positive": False, "volume_ratio": np.nan}

    if _has_precomputed(row):
        mfi = _safe_float(row.get("mfi"))
        if not np.isnan(mfi):
            indicators["mfi"] = mfi
        obv_trend = row.get("obv_trend_positive")
        if obv_trend is not None:
            indicators["obv_trend_positive"] = bool(obv_trend)
        vr = _safe_float(row.get("volume_ratio"))
        if not np.isnan(vr):
            indicators["volume_ratio"] = vr
        return indicators

    closes = _get_closes(price_data)
    if closes is None:
        return indicators

    mfi = _calc_mfi(price_data)
    if mfi is not None:
        indicators["mfi"] = mfi

    obv = _calc_obv(price_data)
    if obv is not None and len(obv) >= 20:
        obv_slope = obv[-1] - obv[-20]
        indicators["obv_trend_positive"] = bool(obv_slope > 0)
    elif obv is not None and len(obv) >= 5:
        obv_slope = obv[-1] - obv[0]
        indicators["obv_trend_positive"] = bool(obv_slope > 0)

    if (price_data is not None and isinstance(price_data, pd.DataFrame)
            and "volume" in price_data.columns and len(price_data) >= 20):
        volumes = price_data["volume"].values.astype(float)
        avg_vol = np.mean(volumes[-20:])
        if avg_vol > 0 and np.isfinite(avg_vol):
            indicators["volume_ratio"] = round(float(volumes[-1] / avg_vol), 4)

    return indicators


def _extract_close_from_row(row) -> float:
    close = row.get("close")
    if close is not None:
        f = _safe_float(close)
        if not np.isnan(f):
            return f
    price_data = row.get("price_data")
    if isinstance(price_data, pd.DataFrame) and not price_data.empty and "close" in price_data.columns:
        return float(price_data["close"].iloc[-1])
    return np.nan


def append_technical_scores(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    has_precomputed = all(col in result.columns for col in ["ma50", "rsi", "mfi"])

    if not has_precomputed and "close" not in result.columns:
        close_vals = []
        for _, row in result.iterrows():
            close_vals.append(_extract_close_from_row(row))
        result["close"] = close_vals

    tech_scores = []
    mfi_vals = []
    obv_trend_vals = []
    vol_ratio_vals = []

    for _, row in result.iterrows():
        price_data = row.get("price_data")
        tech_scores.append(compute_technical_score_for_row(price_data, row=row))
        vi = _compute_volume_indicators(row, price_data)
        mfi_vals.append(vi["mfi"])
        obv_trend_vals.append(vi["obv_trend_positive"])
        vol_ratio_vals.append(vi["volume_ratio"])

    result["technical_score"] = tech_scores

    if "mfi" not in result.columns:
        result["mfi"] = mfi_vals
    if "obv_trend_positive" not in result.columns:
        result["obv_trend_positive"] = obv_trend_vals
    if "volume_ratio" not in result.columns:
        result["volume_ratio"] = vol_ratio_vals

    rs_scores = result["rs_score"].values if "rs_score" in result.columns else np.full(len(result), np.nan)
    tech_arr = np.array(tech_scores)

    combined = np.where(
        np.isnan(rs_scores) | np.isnan(tech_arr),
        np.where(np.isnan(rs_scores), tech_arr, rs_scores),
        rs_scores * COMBINED_WEIGHT_RS + tech_arr * COMBINED_WEIGHT_TECH,
    )
    result["combined_score"] = np.round(combined, 2)

    result["setup_label"] = [
        assign_setup_label(rs, tech)
        for rs, tech in zip(rs_scores, tech_arr)
    ]

    return result
