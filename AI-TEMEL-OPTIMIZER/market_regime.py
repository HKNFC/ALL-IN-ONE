"""
market_regime.py — Market Regime Filter
========================================
Her rebalance tarihinde piyasa rejimini hesaplar.
USA: SPY, QQQ, VIX  |  BIST: XU100, XBANK, XUSIN

Look-ahead bias: yalnızca rebalance_date <= veri tarihi kullanılır.
"""

from __future__ import annotations
import logging
from typing import Optional
import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Benchmark sembolleri ──────────────────────────────────────────────────────
USA_BENCHMARKS  = ["SPY", "QQQ", "^VIX"]
BIST_BENCHMARKS = ["XU100.IS", "XBANK.IS", "XUSIN.IS"]

_REGIME_CACHE: dict = {}   # (market, date_str) → result dict


def _fetch_bench_history(symbol: str, cutoff: pd.Timestamp) -> Optional[pd.DataFrame]:
    """yfinance'ten cutoff tarihine kadar günlük fiyat geçmişini çeker."""
    try:
        start = (cutoff - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
        end   = (cutoff + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.download(symbol, start=start, end=end,
                         auto_adjust=True, progress=False, timeout=15)
        if df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower()
                      for c in df.columns]
        df = df.rename(columns={"date": "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df[df["datetime"] <= cutoff].sort_values("datetime").reset_index(drop=True)
        return df if len(df) >= 30 else None
    except Exception as e:
        logger.warning(f"_fetch_bench_history({symbol}): {e}")
        return None


def _sma(series: pd.Series, window: int) -> float:
    """Son N değerin basit ortalaması."""
    vals = series.dropna()
    if len(vals) < window:
        return float("nan")
    return float(vals.iloc[-window:].mean())


def _annualized_vol(series: pd.Series, window: int = 20) -> float:
    """Son N günün yıllıklandırılmış volatilitesi."""
    vals = series.dropna()
    if len(vals) < window + 1:
        return float("nan")
    rets = vals.iloc[-window - 1:].pct_change().dropna()
    return float(rets.std() * np.sqrt(252))


def _score_single_bench(df: pd.DataFrame) -> float:
    """
    Tek benchmark için 0-100 arası kısmi skor üretir.
    5 kriter × 20 puan = 100 max.
    """
    if df is None or df.empty or "close" not in df.columns:
        return 50.0  # nötr

    close = df["close"]
    price = float(close.iloc[-1])
    sma50  = _sma(close, 50)
    sma200 = _sma(close, 200)

    if any(np.isnan(v) for v in [price, sma50, sma200]):
        return 50.0

    score = 0.0
    # +20: fiyat > SMA50
    if price > sma50:
        score += 20
    # +20: fiyat > SMA200
    if price > sma200:
        score += 20
    # +20: SMA50 > SMA200
    if sma50 > sma200:
        score += 20

    # +20 / -10: 3 aylık getiri
    if len(close) >= 63:
        ret_3m = (price / float(close.iloc[-63])) - 1
        if ret_3m > 0:
            score += 20
        else:
            score -= 10

    # +20 / -10: volatilite düşüyor mu?
    vol20 = _annualized_vol(close, 20)
    vol60 = _annualized_vol(close, 60)
    if not (np.isnan(vol20) or np.isnan(vol60)):
        if vol20 < vol60:
            score += 20
        else:
            score -= 10

    return max(0.0, min(100.0, score))


def _score_vix(df: Optional[pd.DataFrame]) -> float:
    """VIX yüksekse regime cezası, düşükse bonus."""
    if df is None or df.empty or "close" not in df.columns:
        return 0.0
    vix = float(df["close"].iloc[-1])
    if vix < 15:
        return +10.0
    elif vix < 20:
        return +5.0
    elif vix < 25:
        return 0.0
    elif vix < 30:
        return -10.0
    else:
        return -20.0


def calc_market_regime(rebalance_date: pd.Timestamp, market: str) -> dict:
    """
    market: 'US' veya 'BIST'
    Döndürür:
        regime_score   : float  0-100
        market_exposure: float  0.25 / 0.50 / 0.75 / 1.00
        details        : dict   bileşen detayları
    """
    date_str = rebalance_date.strftime("%Y-%m-%d")
    cache_key = (market.upper(), date_str)
    if cache_key in _REGIME_CACHE:
        return _REGIME_CACHE[cache_key]

    if market.upper() == "US":
        symbols = USA_BENCHMARKS
    else:
        symbols = BIST_BENCHMARKS

    bench_data = {}
    for sym in symbols:
        bench_data[sym] = _fetch_bench_history(sym, rebalance_date)

    # Ağırlıklı ortalama
    if market.upper() == "US":
        spy_score = _score_single_bench(bench_data.get("SPY"))
        qqq_score = _score_single_bench(bench_data.get("QQQ"))
        vix_adj   = _score_vix(bench_data.get("^VIX"))
        regime_score = (spy_score * 0.55 + qqq_score * 0.45) + vix_adj
        details = {
            "SPY_score": round(spy_score, 1),
            "QQQ_score": round(qqq_score, 1),
            "VIX_adjustment": round(vix_adj, 1),
        }
    else:
        xu100_score = _score_single_bench(bench_data.get("XU100.IS"))
        xbank_score = _score_single_bench(bench_data.get("XBANK.IS"))
        xusin_score = _score_single_bench(bench_data.get("XUSIN.IS"))
        regime_score = xu100_score * 0.60 + xbank_score * 0.25 + xusin_score * 0.15
        details = {
            "XU100_score": round(xu100_score, 1),
            "XBANK_score": round(xbank_score, 1),
            "XUSIN_score": round(xusin_score, 1),
        }

    regime_score = max(0.0, min(100.0, regime_score))

    # Market exposure
    if regime_score >= 75:
        exposure = 1.00
    elif regime_score >= 55:
        exposure = 0.75
    elif regime_score >= 40:
        exposure = 0.50
    else:
        exposure = 0.25

    result = {
        "regime_score":    round(regime_score, 1),
        "market_exposure": exposure,
        "details":         details,
        "date":            date_str,
        "market":          market.upper(),
    }
    _REGIME_CACHE[cache_key] = result
    return result
