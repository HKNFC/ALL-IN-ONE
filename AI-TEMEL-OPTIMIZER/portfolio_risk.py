"""
portfolio_risk.py — Portfolio Risk Control
============================================
Volatiliteye göre pozisyon büyüklüğü ayarlaması,
maksimum hisse/sektör kısıtları ve çıkış sinyalleri.
"""

from __future__ import annotations
import logging
import math
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_SINGLE_WEIGHT = 0.10   # Tek hisse maks %10
MAX_SECTOR_WEIGHT = 0.30   # Tek sektör maks %30


def _safe(v, default=0.0) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        return float(v)
    except Exception:
        return default


def _ann_vol(price_series: pd.Series, window: int = 60) -> float:
    """Yıllıklandırılmış volatilite."""
    vals = price_series.dropna()
    if len(vals) < window + 1:
        return float("nan")
    rets = vals.pct_change().dropna().iloc[-window:]
    return float(rets.std() * np.sqrt(252))


def calc_position_sizes(
    selected: List[Dict],
    bench_vol: float,
    stock_vols: Dict[str, float],
    sector_map: Dict[str, str],
) -> Dict[str, float]:
    """
    Volatilite ayarlı pozisyon büyüklükleri hesaplar.

    Parametreler:
        selected   : [{"ticker": ..., "adjusted_final_score": ...}, ...]
        bench_vol  : Benchmark yıllıklandırılmış volatilite
        stock_vols : {ticker: ann_vol}
        sector_map : {ticker: sector}

    Döndürür: {ticker: weight (0-1 arası)}
    """
    if not selected:
        return {}

    tickers = [s["ticker"] for s in selected]
    n = len(tickers)

    # Başlangıç: eşit ağırlık
    base_weight = 1.0 / n

    weights: Dict[str, float] = {}
    for ticker in tickers:
        svol = _safe(stock_vols.get(ticker, bench_vol), bench_vol)
        bvol = _safe(bench_vol, svol) if bench_vol and not math.isnan(bench_vol) else svol

        if bvol > 0:
            ratio = svol / bvol
        else:
            ratio = 1.0

        w = base_weight
        if ratio > 2.5:
            w *= 0.60
        elif ratio > 2.0:
            w *= 0.75
        elif ratio > 1.5:
            w *= 0.90

        # Tek hisse maks %10
        w = min(w, MAX_SINGLE_WEIGHT)
        weights[ticker] = w

    # Sektör kısıtı
    sector_totals: Dict[str, float] = {}
    for ticker, w in weights.items():
        sector = sector_map.get(ticker, "Unknown")
        sector_totals[sector] = sector_totals.get(sector, 0) + w

    # Aşan sektörleri oransal düşür
    for sector, total in sector_totals.items():
        if total > MAX_SECTOR_WEIGHT:
            scale = MAX_SECTOR_WEIGHT / total
            for ticker in tickers:
                if sector_map.get(ticker, "Unknown") == sector:
                    weights[ticker] *= scale

    # Normalize et → toplam 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {t: w / total for t, w in weights.items()}

    return {t: round(w, 4) for t, w in weights.items()}


def get_exit_signals(
    ticker: str,
    price_data: pd.DataFrame,
    bench_vol: float,
    excess_3m: float,
    excess_6m: float,
) -> Dict[str, str]:
    """
    Çıkış ve uyarı sinyalleri üretir.

    Döndürür:
        {"signal": "EXIT" | "WARNING" | "HOLD", "reason": str}
    """
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return {"signal": "HOLD", "reason": "Yeterli veri yok"}

    close = price_data["close"].dropna()
    if len(close) < 50:
        return {"signal": "HOLD", "reason": "Yetersiz fiyat geçmişi"}

    price = float(close.iloc[-1])

    # SMA hesapları
    sma50  = float(close.iloc[-50:].mean()) if len(close) >= 50  else float("nan")
    sma200 = float(close.iloc[-200:].mean()) if len(close) >= 200 else float("nan")

    # ADX proxy: 14 günlük fiyat salınımı
    adx_proxy = None
    if len(close) >= 28:
        recent_range   = close.iloc[-14:].max() - close.iloc[-14:].min()
        previous_range = close.iloc[-28:-14].max() - close.iloc[-28:-14].min()
        adx_proxy = recent_range < previous_range * 0.8  # daralan trend = True

    # Hacim zayıflıyor mu?
    vol_weakening = False
    if "volume" in price_data.columns:
        vol = price_data["volume"].dropna()
        if len(vol) >= 20:
            v5  = float(vol.iloc[-5:].mean())
            v20 = float(vol.iloc[-20:].mean())
            vol_weakening = v5 < v20 * 0.70

    # ── EXIT kriterleri ──────────────────────────────────────────────────────
    if not math.isnan(sma200) and price < sma200 * 0.97:
        return {"signal": "EXIT", "reason": f"Fiyat SMA200×0.97 altında ({price:.2f} < {sma200*0.97:.2f})"}

    if excess_3m < -0.05 and excess_6m < -0.10:
        return {"signal": "EXIT", "reason": f"Çift momentum filtresi: 3A={excess_3m*100:.1f}%, 6A={excess_6m*100:.1f}%"}

    # ── WARNING kriterleri ───────────────────────────────────────────────────
    reasons = []
    if not math.isnan(sma50) and price < sma50:
        reasons.append(f"Fiyat SMA50 altında")
    if adx_proxy and vol_weakening:
        reasons.append("ADX daralıyor + hacim zayıflıyor")

    if reasons:
        return {"signal": "WARNING", "reason": " | ".join(reasons)}

    return {"signal": "HOLD", "reason": "Pozisyon devam"}


def calc_sector_exposure(
    weights: Dict[str, float],
    sector_map: Dict[str, str],
) -> Dict[str, float]:
    """Sektör bazlı ağırlık dağılımı döndürür."""
    exposure: Dict[str, float] = {}
    for ticker, w in weights.items():
        sector = sector_map.get(ticker, "Unknown")
        exposure[sector] = round(exposure.get(sector, 0.0) + w, 4)
    return exposure
