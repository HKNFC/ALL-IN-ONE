import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

logger = logging.getLogger("stock_screener.indicators")

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


def _valid_ohlcv(price_data: pd.DataFrame) -> bool:
    if price_data is None or not isinstance(price_data, pd.DataFrame) or price_data.empty:
        return False
    return "close" in price_data.columns


def _get_closes(price_data: pd.DataFrame) -> np.ndarray:
    return price_data["close"].values.astype(float)


def calc_return(closes: np.ndarray, days: int) -> Optional[float]:
    if closes is None or len(closes) < days + 1:
        return None
    base = closes[-(days + 1)]
    if base == 0 or not np.isfinite(base):
        return None
    current = closes[-1]
    if not np.isfinite(current):
        return None
    return round((current / base - 1) * 100, 2)


def calc_period_returns(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    result = {"return_1m": None, "return_3m": None, "return_6m": None, "return_12m": None}
    if not _valid_ohlcv(price_data):
        return result
    closes = _get_closes(price_data)
    periods = {
        "return_1m": TRADING_DAYS_1M,
        "return_3m": TRADING_DAYS_3M,
        "return_6m": TRADING_DAYS_6M,
        "return_12m": TRADING_DAYS_12M,
    }
    for key, days in periods.items():
        result[key] = calc_return(closes, days)
    return result


def calc_moving_averages(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {
        "ma20": None, "ma50": None, "ma200": None,
        "ma20_ratio": None, "ma50_ratio": None, "ma200_ratio": None,
    }
    if not _valid_ohlcv(price_data):
        return result
    closes = _get_closes(price_data)
    current = closes[-1] if len(closes) > 0 and np.isfinite(closes[-1]) else None
    if current is None:
        return result
    for window, key in [(20, "ma20"), (50, "ma50"), (200, "ma200")]:
        if len(closes) >= window:
            ma = float(np.mean(closes[-window:]))
            if np.isfinite(ma) and ma > 0:
                result[key] = round(ma, 4)
                result[f"{key}_ratio"] = round(current / ma, 4)
    return result


def calc_rsi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    closes = _get_closes(price_data)
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calc_macd(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {
        "macd_line": None, "macd_signal": None, "macd_histogram": None,
    }
    if not _valid_ohlcv(price_data):
        return result
    closes = _get_closes(price_data)
    if len(closes) < 35:
        return result
    alpha12 = 2.0 / 13
    alpha26 = 2.0 / 27
    ema12 = np.empty_like(closes)
    ema26 = np.empty_like(closes)
    ema12[0] = closes[0]
    ema26[0] = closes[0]
    for i in range(1, len(closes)):
        ema12[i] = alpha12 * closes[i] + (1 - alpha12) * ema12[i - 1]
        ema26[i] = alpha26 * closes[i] + (1 - alpha26) * ema26[i - 1]
    macd_line = ema12 - ema26
    alpha9 = 2.0 / 10
    signal = np.empty_like(macd_line)
    signal[0] = macd_line[0]
    for i in range(1, len(macd_line)):
        signal[i] = alpha9 * macd_line[i] + (1 - alpha9) * signal[i - 1]
    result["macd_line"] = round(float(macd_line[-1]), 4)
    result["macd_signal"] = round(float(signal[-1]), 4)
    result["macd_histogram"] = round(float(macd_line[-1] - signal[-1]), 4)
    return result


def calc_atr(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    if not all(c in price_data.columns for c in ["high", "low", "close"]):
        return None
    if len(price_data) < period + 1:
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
    return round(float(np.mean(tr_values[-period:])), 4)


def calc_obv(price_data: pd.DataFrame) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "obv_latest": None, "obv_trend_positive": None, "obv_slope": None,
    }
    if not _valid_ohlcv(price_data):
        return result
    if "volume" not in price_data.columns:
        return result
    close = _get_closes(price_data)
    volume = price_data["volume"].values.astype(float)
    if len(close) < 5:
        return result
    obv = np.zeros(len(close))
    obv[0] = volume[0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    result["obv_latest"] = float(obv[-1])
    lookback = min(20, len(obv) - 1)
    if lookback >= 5:
        slope = obv[-1] - obv[-lookback]
        result["obv_slope"] = float(slope)
        result["obv_trend_positive"] = bool(slope > 0)
    return result


def calc_mfi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    required = ["high", "low", "close", "volume"]
    if not all(c in price_data.columns for c in required):
        return None
    if len(price_data) < period + 1:
        return None
    data = price_data.tail(period + 1)
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
    return round(100.0 - (100.0 / (1.0 + money_ratio)), 2)


def calc_volume_ratio(price_data: pd.DataFrame, window: int = 20) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    if "volume" not in price_data.columns:
        return None
    volumes = price_data["volume"].values.astype(float)
    if len(volumes) < window:
        return None
    avg_vol = float(np.mean(volumes[-window:]))
    if avg_vol <= 0 or not np.isfinite(avg_vol):
        return None
    current_vol = volumes[-1]
    if not np.isfinite(current_vol):
        return None
    return round(float(current_vol / avg_vol), 4)


def calc_distance_to_52w_high(price_data: pd.DataFrame) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    if "high" not in price_data.columns:
        return None
    if len(price_data) < TRADING_DAYS_1M:
        return None
    lookback = min(TRADING_DAYS_12M, len(price_data))
    high_52w = float(price_data["high"].tail(lookback).max())
    current = float(price_data["close"].iloc[-1])
    if not np.isfinite(high_52w) or high_52w <= 0:
        return None
    if not np.isfinite(current):
        return None
    return round((current / high_52w - 1) * 100, 2)


def calc_avg_volume_20d(price_data: pd.DataFrame) -> Optional[float]:
    if not _valid_ohlcv(price_data):
        return None
    if "volume" not in price_data.columns:
        return None
    if len(price_data) < 20:
        return None
    return round(float(price_data["volume"].tail(20).mean()), 0)


def calc_relative_return(
    stock_data: pd.DataFrame,
    benchmark_data: pd.DataFrame,
    days: int = TRADING_DAYS_12M,
) -> Optional[float]:
    if not _valid_ohlcv(stock_data) or not _valid_ohlcv(benchmark_data):
        return None

    if "datetime" in stock_data.columns and "datetime" in benchmark_data.columns:
        s = stock_data[["datetime", "close"]].copy()
        s.columns = ["datetime", "stock_close"]
        b = benchmark_data[["datetime", "close"]].copy()
        b.columns = ["datetime", "bench_close"]
        s["datetime"] = pd.to_datetime(s["datetime"])
        b["datetime"] = pd.to_datetime(b["datetime"])
        merged = pd.merge(s, b, on="datetime", how="inner").sort_values("datetime")
        if len(merged) >= days + 1:
            stock_ret = calc_return(merged["stock_close"].values, days)
            bench_ret = calc_return(merged["bench_close"].values, days)
            if stock_ret is not None and bench_ret is not None:
                return round(stock_ret - bench_ret, 2)

    stock_closes = _get_closes(stock_data)
    bench_closes = _get_closes(benchmark_data)
    stock_ret = calc_return(stock_closes, days)
    bench_ret = calc_return(bench_closes, days)
    if stock_ret is None or bench_ret is None:
        return None
    return round(stock_ret - bench_ret, 2)


def compute_all_indicators(price_data: pd.DataFrame) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    returns = calc_period_returns(price_data)
    result.update(returns)

    mas = calc_moving_averages(price_data)
    result.update(mas)

    result["rsi"] = calc_rsi(price_data)

    macd = calc_macd(price_data)
    result.update(macd)

    result["atr"] = calc_atr(price_data)

    obv = calc_obv(price_data)
    result.update(obv)

    result["mfi"] = calc_mfi(price_data)
    result["volume_ratio"] = calc_volume_ratio(price_data)
    result["distance_to_52w_high"] = calc_distance_to_52w_high(price_data)
    result["avg_volume_20d"] = calc_avg_volume_20d(price_data)

    return result


ALL_INDICATOR_COLUMNS = [
    "return_1m", "return_3m", "return_6m", "return_12m",
    "ma20", "ma50", "ma200",
    "ma20_ratio", "ma50_ratio", "ma200_ratio",
    "rsi",
    "macd_line", "macd_signal", "macd_histogram",
    "atr",
    "obv_latest", "obv_trend_positive", "obv_slope",
    "mfi",
    "volume_ratio",
    "distance_to_52w_high",
    "avg_volume_20d",
]

NUMERIC_INDICATOR_COLUMNS = [
    c for c in ALL_INDICATOR_COLUMNS if c != "obv_trend_positive"
]


def enrich_dataframe_with_indicators(
    df: pd.DataFrame,
    benchmark_history: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    result = df.copy()

    if "price_data" not in result.columns:
        logger.warning("enrich_dataframe_with_indicators: no 'price_data' column — skipping")
        for col in ALL_INDICATOR_COLUMNS:
            result[col] = np.nan
        return result

    all_rows: list[Dict[str, Any]] = []

    for idx, row in result.iterrows():
        price_data = row.get("price_data")

        if not _valid_ohlcv(price_data):
            all_rows.append({col: np.nan for col in ALL_INDICATOR_COLUMNS})
            continue

        if "datetime" in price_data.columns:
            price_data = price_data.sort_values("datetime").reset_index(drop=True)
            result.at[idx, "price_data"] = price_data

        indicators = compute_all_indicators(price_data)

        if benchmark_history is not None:
            rel = calc_relative_return(price_data, benchmark_history)
            indicators["relative_return_vs_index"] = rel

        row_dict = {}
        for col in ALL_INDICATOR_COLUMNS:
            val = indicators.get(col)
            row_dict[col] = val if val is not None else np.nan
        if "relative_return_vs_index" in indicators:
            v = indicators["relative_return_vs_index"]
            row_dict["relative_return_vs_index"] = v if v is not None else np.nan

        all_rows.append(row_dict)

    indicator_df = pd.DataFrame(all_rows, index=result.index)
    for col in indicator_df.columns:
        result[col] = indicator_df[col]

    if "relative_return_vs_index" not in result.columns:
        result["relative_return_vs_index"] = np.nan

    for col in NUMERIC_INDICATOR_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    if "relative_return_vs_index" in result.columns:
        result["relative_return_vs_index"] = pd.to_numeric(
            result["relative_return_vs_index"], errors="coerce"
        )

    return result
