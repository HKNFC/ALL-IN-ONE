"""
ai_score.py — AI News / Narrative Score
=========================================
Gerçek haber API'si olmadığından FMP tarihsel temel verilerinden
proxy metrikler ile 0-100 arası ai_score üretilir.

Tüm veriler fillingDate <= rebalance_date kuralına uyar (look-ahead bias yok).
"""

from __future__ import annotations
import logging
import math
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _safe(v, default=0.0) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        return float(v)
    except Exception:
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _to100(v: float, lo: float, hi: float) -> float:
    """v'yi [lo, hi] aralığından [0, 100]'e normalize eder."""
    if hi == lo:
        return 50.0
    return _clamp((v - lo) / (hi - lo) * 100, 0.0, 100.0)


# ── Bileşen hesaplamaları ─────────────────────────────────────────────────────

def _news_sentiment_score(curr: dict, prev: dict) -> Optional[float]:
    """
    Proxy: EPS momentum — son 2 çeyrek EPS büyüme eğimi.
    EPS büyümesi ivme kazanıyorsa yüksek puan.
    """
    eps_curr = _safe(curr.get("eps_growth"))
    eps_prev = _safe(prev.get("eps_growth")) if prev else None

    if eps_prev is None:
        # Sadece mevcut döneme bak
        if eps_curr > 0.30:
            return 80.0
        elif eps_curr > 0.15:
            return 65.0
        elif eps_curr > 0.0:
            return 50.0
        else:
            return 25.0

    # İvme: mevcut - önceki
    acceleration = eps_curr - eps_prev
    base = _to100(eps_curr, -0.5, 1.0)
    bonus = _clamp(acceleration * 100, -20, 20)
    return _clamp(base + bonus)


def _earnings_quality_score(curr: dict) -> Optional[float]:
    """
    Proxy: Net marj artışı + FCF pozitifliği.
    """
    net_margin = _safe(curr.get("net_margin"))
    prev_net_margin = _safe(curr.get("net_margin_prev"), None)  # önceki dönem marjı
    fcf = _safe(curr.get("free_cash_flow"))
    revenue = _safe(curr.get("revenue"), 1.0)

    score = _to100(net_margin, -0.1, 0.30)

    # FCF pozitifse bonus
    if revenue > 0:
        fcf_margin = fcf / revenue
        if fcf_margin > 0.15:
            score = _clamp(score + 15)
        elif fcf_margin > 0.05:
            score = _clamp(score + 8)
        elif fcf_margin < 0:
            score = _clamp(score - 15)

    return _clamp(score)


def _guidance_score(curr: dict, prev: dict) -> Optional[float]:
    """
    Proxy: Gelir büyümesi ivmesi.
    """
    rev_curr = _safe(curr.get("revenue_growth"))
    rev_prev = _safe(prev.get("revenue_growth")) if prev else None

    if rev_prev is None:
        return _to100(rev_curr, -0.2, 0.5)

    acceleration = rev_curr - rev_prev
    base = _to100(rev_curr, -0.2, 0.5)
    bonus = _clamp(acceleration * 80, -15, 20)
    return _clamp(base + bonus)


def _management_tone_score(curr: dict, prev: dict) -> Optional[float]:
    """
    Proxy: FCF büyümesi + gross marj genişlemesi.
    """
    gross_curr = _safe(curr.get("gross_margin"))
    gross_prev = _safe(prev.get("gross_margin")) if prev else gross_curr
    fcf_curr   = _safe(curr.get("free_cash_flow"))
    fcf_prev   = _safe(prev.get("free_cash_flow")) if prev else fcf_curr

    margin_trend = gross_curr - gross_prev
    fcf_growth   = (fcf_curr - fcf_prev) / max(abs(fcf_prev), 1e-9) if fcf_prev != 0 else 0.0

    base  = _to100(gross_curr, 0.0, 0.70)
    bonus = _clamp(margin_trend * 200, -15, 15)
    bonus += _clamp(fcf_growth * 20, -10, 10)
    return _clamp(base + bonus)


def _risk_warning_score(curr: dict, prev: dict) -> Optional[float]:
    """
    Proxy: Borç artışı + marj daralması + negatif FCF.
    Yüksek puan = yüksek risk = final skora negatif etki.
    """
    debt_eq_curr  = _safe(curr.get("debt_equity"))
    debt_eq_prev  = _safe(prev.get("debt_equity")) if prev else debt_eq_curr
    net_margin    = _safe(curr.get("net_margin"))
    fcf           = _safe(curr.get("free_cash_flow"))
    revenue       = _safe(curr.get("revenue"), 1.0)

    risk = 0.0

    # Borç artışı
    debt_increase = debt_eq_curr - debt_eq_prev
    if debt_increase > 0.5:
        risk += 30
    elif debt_increase > 0.2:
        risk += 15

    # Yüksek borç/özkaynak
    if debt_eq_curr > 3.0:
        risk += 25
    elif debt_eq_curr > 1.5:
        risk += 10

    # Marj daralması
    if net_margin < 0:
        risk += 30
    elif net_margin < 0.03:
        risk += 15

    # Negatif FCF
    if revenue > 0 and (fcf / revenue) < -0.05:
        risk += 20

    return _clamp(risk)


# ── Ana fonksiyon ─────────────────────────────────────────────────────────────

def calc_ai_score(
    fund_data: Optional[dict],
    fund_prev: Optional[dict] = None,
) -> Tuple[float, dict]:
    """
    FMP tarihsel temel verilerinden AI proxy skoru hesaplar.

    Parametreler:
        fund_data : get_fundamentals_as_of(ticker, rebalance_date) → mevcut dönem
        fund_prev : get_fundamentals_as_of(ticker, rebalance_date-90gün) → önceki dönem

    Döndürür:
        (ai_score: float 0-100, breakdown: dict)
    """
    if not fund_data:
        return 50.0, {"note": "Temel veri yok — nötr skor kullanıldı"}

    breakdown = {}
    weights   = {}

    # Bileşen 1: News Sentiment (proxy: EPS momentum)
    try:
        v = _news_sentiment_score(fund_data, fund_prev)
        if v is not None:
            breakdown["news_sentiment_score"] = round(v, 1)
            weights["news_sentiment_score"] = 0.25
    except Exception as e:
        logger.debug(f"news_sentiment_score hata: {e}")

    # Bileşen 2: Earnings Quality
    try:
        v = _earnings_quality_score(fund_data)
        if v is not None:
            breakdown["earnings_quality_score"] = round(v, 1)
            weights["earnings_quality_score"] = 0.25
    except Exception as e:
        logger.debug(f"earnings_quality_score hata: {e}")

    # Bileşen 3: Guidance (proxy: gelir büyümesi ivmesi)
    try:
        v = _guidance_score(fund_data, fund_prev)
        if v is not None:
            breakdown["guidance_score"] = round(v, 1)
            weights["guidance_score"] = 0.20
    except Exception as e:
        logger.debug(f"guidance_score hata: {e}")

    # Bileşen 4: Management Tone (proxy: FCF + marj genişlemesi)
    try:
        v = _management_tone_score(fund_data, fund_prev)
        if v is not None:
            breakdown["management_tone_score"] = round(v, 1)
            weights["management_tone_score"] = 0.15
    except Exception as e:
        logger.debug(f"management_tone_score hata: {e}")

    # Bileşen 5: Risk Warning (negatif etki)
    try:
        v = _risk_warning_score(fund_data, fund_prev)
        if v is not None:
            breakdown["risk_warning_score"] = round(v, 1)
            weights["risk_warning_score"] = -0.15   # negatif ağırlık
    except Exception as e:
        logger.debug(f"risk_warning_score hata: {e}")

    if not breakdown:
        return 50.0, {"note": "Hiçbir bileşen hesaplanamadı — nötr skor"}

    # Ağırlıkları normalize et (eksik bileşenler için)
    pos_total = sum(w for w in weights.values() if w > 0)
    neg_total = sum(w for w in weights.values() if w < 0)

    ai_score = 0.0
    for key, w in weights.items():
        val = breakdown.get(key, 50.0)
        if w > 0 and pos_total > 0:
            ai_score += val * (w / pos_total) * abs(w) / (
                sum(abs(x) for x in weights.values() if x > 0)
            ) * (sum(abs(x) for x in weights.values() if x > 0))
        else:
            ai_score += val * w

    # Daha temiz hesap: toplam pozitif ağırlık 0.85, negatif -0.15
    pos_keys = [k for k, w in weights.items() if w > 0]
    neg_keys = [k for k, w in weights.items() if w < 0]

    pos_sum = sum(weights[k] for k in pos_keys)
    pos_score = sum(breakdown[k] * weights[k] for k in pos_keys)
    if pos_sum > 0:
        # Her pozitif bileşen kendi ağırlığı ile katılır;
        # eksik bileşen varsa kalan ağırlık diğerlerine oransal dağıtılır
        pos_score = sum(
            breakdown[k] * (weights[k] / pos_sum) * 0.85
            for k in pos_keys
        )
    else:
        pos_score = 50.0 * 0.85

    neg_score = sum(breakdown[k] * abs(weights[k]) for k in neg_keys)
    # neg_score: 0-100 arası risk → 0-0.15 arası negatif etki
    neg_impact = neg_score * (abs(neg_total) / (len(neg_keys) if neg_keys else 1) / 100)

    ai_score = _clamp(pos_score - neg_impact * 100)

    breakdown["ai_score_final"] = round(ai_score, 1)
    if not pos_keys:
        breakdown["note"] = "Pozitif bileşen yok — nötr"

    return round(ai_score, 1), breakdown
