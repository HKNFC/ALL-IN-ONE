from __future__ import annotations
import pandas as pd
from indicators import compute_all_indicators, find_divergence_bist, find_divergence_usa, rs_score_bist, rs_score_usa
from data_fetcher import fetch_ohlcv, fetch_multiple
from stock_lists import BIST_STOCKS, USA_STOCKS
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


def _check_bist(symbol: str, df: pd.DataFrame, params: dict = None) -> Optional[dict]:
    p = params or {}
    mfi_min = p.get("mfi_min", 50)
    mfi_max = p.get("mfi_max", 80)
    vol_mult = p.get("vol_mult", 1.3)
    div_lookback = p.get("div_lookback", 15)
    use_divergence = p.get("use_divergence", True)

    if len(df) < 60:
        return None
    df = compute_all_indicators(df)
    last = df.iloc[-1]

    if not (last["Close"] > last["ema21"] and last["ema21"] > last["ema50"]):
        return None

    if not (mfi_min < last["mfi14"] < mfi_max):
        return None

    if not (last["Volume"] > last["vol_avg10"] * vol_mult):
        return None

    if use_divergence and not find_divergence_bist(df["Close"], df["mfi14"], lookback=div_lookback):
        return None

    rs = rs_score_bist(last)
    return {
        "Symbol": symbol,
        "RS Puanı": rs["RS"],
        "Close": round(last["Close"], 2),
        "EMA21": round(last["ema21"], 2),
        "EMA50": round(last["ema50"], 2),
        "MFI(14)": round(last["mfi14"], 1),
        "RSI(14)": round(last["rsi14"], 1),
        "ADX(14)": round(last["adx14"], 1),
        "Volume/Avg": round(last["Volume"] / last["vol_avg10"], 2) if last["vol_avg10"] > 0 else 0,
        "ROC5(%)": round(last.get("roc5", 0), 2),
        "Uyuşmazlık": "Var" if use_divergence else "-",
        "Market": "BIST",
        "_rs_mfi": rs["MFI"],
        "_rs_trend": rs["Trend"],
        "_rs_hacim": rs["Hacim"],
        "_rs_rsi": rs["RSI"],
        "_rs_adx": rs["ADX"],
        "_rs_roc": rs["ROC"],
    }


def _check_usa(symbol: str, df: pd.DataFrame, params: dict = None) -> Optional[dict]:
    p = params or {}
    rsi_min = p.get("rsi_min", 60)
    adx_min = p.get("adx_min", 25)
    use_bb = p.get("use_bb", True)
    use_divergence = p.get("use_divergence", True)

    if len(df) < 210:
        return None
    df = compute_all_indicators(df)
    last = df.iloc[-1]

    if not (last["Close"] > last["ema50"] and last["ema50"] > last["ema200"]):
        return None

    if not (last["rsi14"] > rsi_min and last["adx14"] > adx_min):
        return None

    if use_bb and not (last["bb_width"] < last["bb_width_avg"]):
        return None

    if use_divergence and not find_divergence_usa(df["Close"], df["mfi14"], lookback=20):
        return None

    rs = rs_score_usa(last)
    return {
        "Symbol": symbol,
        "RS Puanı": rs["RS"],
        "Close": round(last["Close"], 2),
        "EMA50": round(last["ema50"], 2),
        "EMA200": round(last["ema200"], 2),
        "RSI(14)": round(last["rsi14"], 1),
        "ADX(14)": round(last["adx14"], 1),
        "MFI(14)": round(last["mfi14"], 1),
        "ROC20(%)": round(last.get("roc20", 0), 2),
        "BB Squeeze": "Var" if use_bb else "-",
        "MFI Div.": "Var" if use_divergence else "-",
        "Market": "USA",
        "_rs_rsi": rs["RSI"],
        "_rs_adx": rs["ADX"],
        "_rs_mfi": rs["MFI"],
        "_rs_trend": rs["Trend"],
        "_rs_bb": rs["BB"],
        "_rs_roc": rs["ROC"],
    }


def _diagnose_bist(symbol: str, df: pd.DataFrame, params: dict = None) -> str:
    p = params or {}
    mfi_min = p.get("mfi_min", 50)
    mfi_max = p.get("mfi_max", 80)
    vol_mult = p.get("vol_mult", 1.3)
    div_lookback = p.get("div_lookback", 15)
    use_divergence = p.get("use_divergence", True)

    if len(df) < 60:
        return "veri_yetersiz"
    df = compute_all_indicators(df)
    last = df.iloc[-1]
    if not (last["Close"] > last["ema21"] and last["ema21"] > last["ema50"]):
        return "trend"
    if not (mfi_min < last["mfi14"] < mfi_max):
        return "mfi"
    if not (last["Volume"] > last["vol_avg10"] * vol_mult):
        return "hacim"
    if use_divergence and not find_divergence_bist(df["Close"], df["mfi14"], lookback=div_lookback):
        return "uyuşmazlık"
    return "geçti"


def _diagnose_usa(symbol: str, df: pd.DataFrame, params: dict = None) -> str:
    p = params or {}
    rsi_min = p.get("rsi_min", 60)
    adx_min = p.get("adx_min", 25)
    use_bb = p.get("use_bb", True)
    use_divergence = p.get("use_divergence", True)

    if len(df) < 210:
        return "veri_yetersiz"
    df = compute_all_indicators(df)
    last = df.iloc[-1]
    if not (last["Close"] > last["ema50"] and last["ema50"] > last["ema200"]):
        return "trend"
    if not (last["rsi14"] > rsi_min and last["adx14"] > adx_min):
        return "momentum"
    if use_bb and not (last["bb_width"] < last["bb_width_avg"]):
        return "bb_daralma"
    if use_divergence and not find_divergence_usa(df["Close"], df["mfi14"], lookback=20):
        return "uyuşmazlık"
    return "geçti"


def screen_bist(progress_callback=None, symbols=None, params=None) -> tuple[pd.DataFrame, dict]:
    results = []
    filter_stats = {"trend": 0, "mfi": 0, "hacim": 0, "uyuşmazlık": 0, "veri_yetersiz": 0, "geçti": 0}
    symbols = symbols if symbols is not None else BIST_STOCKS
    total = len(symbols)

    def process(sym):
        df = fetch_ohlcv(sym, period="6mo")
        result = _check_bist(sym, df, params)
        diag = _diagnose_bist(sym, df, params)
        return result, diag

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process, s): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done / total, futures[future])
            result, diag = future.result()
            filter_stats[diag] = filter_stats.get(diag, 0) + 1
            if result:
                results.append(result)

    df_out = pd.DataFrame(results).sort_values("RS Puanı", ascending=False).reset_index(drop=True) if results else pd.DataFrame()
    return df_out, filter_stats


def screen_usa(progress_callback=None, symbols=None, params=None) -> tuple[pd.DataFrame, dict]:
    results = []
    filter_stats = {"trend": 0, "momentum": 0, "bb_daralma": 0, "uyuşmazlık": 0, "veri_yetersiz": 0, "geçti": 0}
    symbols = symbols if symbols is not None else USA_STOCKS
    total = len(symbols)

    def process(sym):
        df = fetch_ohlcv(sym, period="2y")
        result = _check_usa(sym, df, params)
        diag = _diagnose_usa(sym, df, params)
        return result, diag

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process, s): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done / total, futures[future])
            result, diag = future.result()
            filter_stats[diag] = filter_stats.get(diag, 0) + 1
            if result:
                results.append(result)

    df_out = pd.DataFrame(results).sort_values("RS Puanı", ascending=False).reset_index(drop=True) if results else pd.DataFrame()
    return df_out, filter_stats


def screen_bist_on_date(df_dict: dict, as_of_date, params=None) -> list:
    hits = []
    for sym, full_df in df_dict.items():
        df = full_df[full_df.index <= as_of_date].copy()
        result = _check_bist(sym, df, params)
        if result:
            hits.append((sym, result["RS Puanı"]))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in hits]


def screen_usa_on_date(df_dict: dict, as_of_date, params=None) -> list:
    hits = []
    for sym, full_df in df_dict.items():
        df = full_df[full_df.index <= as_of_date].copy()
        result = _check_usa(sym, df, params)
        if result:
            hits.append((sym, result["RS Puanı"]))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in hits]
