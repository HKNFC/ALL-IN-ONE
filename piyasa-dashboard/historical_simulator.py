"""
Tarih bazlı geriye dönük simülasyon modülü.
Seçilen tarih aralığında her gün için piyasa kararını hesaplar.
Gerçek işlem yapmaz, sadece rapor üretir.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import RISK_PROFILES, BIST_LAYER_WEIGHTS, USA_LAYER_WEIGHTS, SCORE_SCALE
from data_fetcher import (
    fetch_index_history, fetch_multi_ticker_data, fetch_sector_data,
    fetch_vix_data, fetch_treasury_yield, fetch_dxy_data, fetch_relative_strength_data,
    fetch_usdtry_data, fetch_turkey_cds, fetch_tcmb_policy_rate, fetch_tcmb_inflation,
)
from indicators import (
    calc_sma, calc_rsi, calc_macd, calc_adx, calc_obv,
    calc_volatility, calc_sma_slope, calc_breadth, calc_new_high_low,
    calc_relative_strength, calc_usdtry_volatility, calc_roc,
)
from scoring_bist import (
    score_bist_macro, score_bist_health, score_bist_timing,
    score_bist_money_flow, score_bist_momentum,
)
from scoring_usa import (
    score_usa_risk, score_usa_internals, score_usa_timing,
    score_usa_momentum, score_usa_sentiment,
)
from market_regime import detect_regime_bist, detect_regime_usa
from decision_engine import decide_bist, decide_usa


def simulate_bist_period(start_date, end_date, risk_profile="Dengeli", api_key=""):
    """
    BIST için belirtilen tarih aralığında günlük simülasyon yap.
    
    Returns: DataFrame with columns:
        - date: tarih
        - price: XU100 kapanış
        - verdict: işlem kararı (UYGUN, KADEMELİ ALIM, vb.)
        - hisse_pct: hisse senedi oranı
        - tahvil_pct: tahvil/mevduat oranı  
        - nakit_pct: nakit oranı
        - total_score: toplam skor
        - macro_score, money_flow_score, health_score, timing_score, momentum_score
        - cds: CDS değeri
        - regime: piyasa rejimi
    """
    # Veri çek
    hist = fetch_index_history("XU100.IS", period="5y")
    if hist is None or hist.empty:
        return None, "Veri alınamadı"
    
    # Tarih filtresi - timezone-aware karşılaştırma
    start_ts = pd.Timestamp(start_date).tz_localize(None)
    end_ts = pd.Timestamp(end_date).tz_localize(None)
    hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
    hist = hist[(hist.index >= start_ts) & (hist.index <= end_ts)]
    if len(hist) < 5:
        return None, "Yetersiz veri (min 5 gün)"
    
    # Ek veriler
    usdtry_hist = fetch_usdtry_data(period="5y")
    bist_ticker_data = fetch_multi_ticker_data([
        "THYAO.IS", "ASELS.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS",
        "TUPRS.IS", "SAHOL.IS", "KCHOL.IS", "BIMAS.IS", "SISE.IS",
    ], period="5y")
    
    # TCMB verileri
    policy_rate = fetch_tcmb_policy_rate() or 42.5
    inflation = fetch_tcmb_inflation() or 37.86
    real_rate = policy_rate - inflation
    
    # CDS (mevcut değeri kullan - geçmiş CDS verisi yok)
    cds_value, _, _ = fetch_turkey_cds()
    if cds_value is None:
        cds_value = 270
    
    results = []
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["Dengeli"])
    
    for date in hist.index:
        # O güne kadar olan veriyi al (lookback)
        # İlk 30 günü atla (yeterli veri için)
        lookback = hist.loc[:date]
        if len(lookback) < 30:
            continue
            
        close = lookback["Close"]
        high = lookback["High"] if "High" in lookback.columns else close
        low = lookback["Low"] if "Low" in lookback.columns else close
        volume = lookback["Volume"] if "Volume" in lookback.columns else None
        
        last_close = close.iloc[-1]
        
        # BIST/USD hesapla
        bist_usd_above = None
        if usdtry_hist is not None and not usdtry_hist.empty:
            common_idx = lookback.index.intersection(usdtry_hist.index)
            if len(common_idx) > 50:
                bist_usd_series = lookback.loc[common_idx, "Close"] / usdtry_hist.loc[common_idx, "Close"]
                bist_usd_sma200 = bist_usd_series.rolling(200).mean()
                if len(bist_usd_sma200.dropna()) > 0:
                    bist_usd_above = bist_usd_series.iloc[-1] > bist_usd_sma200.dropna().iloc[-1]
        
        # USDTRY volatilite
        usdtry_vol_current, usdtry_vol_avg = None, None
        if usdtry_hist is not None and not usdtry_hist.empty:
            common_idx = lookback.index.intersection(usdtry_hist.index)
            if len(common_idx) > 20:
                usdtry_vol_current, usdtry_vol_avg = calc_usdtry_volatility(
                    usdtry_hist.loc[common_idx, "Close"]
                )
        
        # Scoring
        macro_score, macro_indicators, macro_max = score_bist_macro(
            cds_value, real_rate, bist_usd_above, usdtry_vol_current, usdtry_vol_avg
        )
        
        # Breadth için ticker verisi (mevcut gün itibariyle)
        health_score, health_indicators, health_max, breadth_pct = score_bist_health(
            {}, {}, hist=lookback  # Sadece endeks verisi kullan
        )
        
        timing_score, timing_indicators, timing_max = score_bist_timing(lookback)
        
        money_flow_score, money_flow_indicators, money_flow_max = score_bist_money_flow(
            lookback, usdtry_hist=usdtry_hist.loc[:date] if usdtry_hist is not None else None,
            cds_value=cds_value, cds_trend=None,
            bist_usd_above=bist_usd_above,
        )
        
        momentum_score, momentum_indicators, momentum_max = score_bist_momentum(lookback)
        
        # Volatilite
        vol = calc_volatility(close)
        vol_current = vol.dropna().iloc[-1] if vol is not None and len(vol.dropna()) > 0 else None
        
        # Regime
        regime, regime_reason = detect_regime_bist(macro_score, breadth_pct, vol_current, cds_value)
        
        # Karar
        verdict, total_score, explanation, allocation, stop_loss = decide_bist(
            macro_score, health_score, timing_score, regime,
            cds_value, real_rate, breadth_pct, bist_usd_above, risk_profile,
            money_flow_score=money_flow_score, momentum_score=momentum_score,
            macro_max=macro_max, health_max=health_max, timing_max=timing_max,
            money_flow_max=money_flow_max, momentum_max=momentum_max,
        )
        
        results.append({
            "date": date.strftime("%Y-%m-%d"),
            "price": round(last_close, 2),
            "verdict": verdict,
            "hisse_pct": allocation.get("hisse", 0),
            "tahvil_pct": allocation.get("tahvil", 30),
            "nakit_pct": allocation.get("nakit", 70),
            "total_score": round(total_score, 2),
            "macro_score": round(macro_score, 2),
            "money_flow_score": round(money_flow_score, 2),
            "health_score": round(health_score, 2),
            "timing_score": round(timing_score, 2),
            "momentum_score": round(momentum_score, 2),
            "cds": cds_value,
            "regime": regime,
        })
    
    return pd.DataFrame(results), None


def simulate_usa_period(start_date, end_date, risk_profile="Dengeli", api_key=""):
    """
    USA için belirtilen tarih aralığında günlük simülasyon yap.
    """
    # Veri çek
    hist = fetch_index_history("SPY", period="5y")
    if hist is None or hist.empty:
        return None, "Veri alınamadı"
    
    # Tarih filtresi - timezone-aware karşılaştırma
    start_ts = pd.Timestamp(start_date).tz_localize(None)
    end_ts = pd.Timestamp(end_date).tz_localize(None)
    hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
    hist = hist[(hist.index >= start_ts) & (hist.index <= end_ts)]
    if len(hist) < 5:
        return None, "Yetersiz veri (min 5 gün)"
    
    # Ek veriler
    vix_current, _, vix_hist = fetch_vix_data()
    treasury_yield = fetch_treasury_yield() or 4.0
    dxy_current, dxy_sma50, dxy_sma200, dxy_hist = fetch_dxy_data()
    rs_data = fetch_relative_strength_data()
    
    results = []
    
    for date in hist.index:
        lookback = hist.loc[:date]
        if len(lookback) < 30:
            continue
            
        close = lookback["Close"]
        last_close = close.iloc[-1]
        
        # SMA200
        sma200 = calc_sma(close, 200)
        sma200_val = sma200.dropna().iloc[-1] if sma200 is not None and len(sma200.dropna()) > 0 else None
        sma200_above = sma200_val is not None and last_close > sma200_val
        
        # Scoring
        risk_score, risk_indicators, risk_max = score_usa_risk(
            vix_current, None, treasury_yield,
            dxy_current, dxy_sma50, dxy_sma200,
        )
        
        internals_score, internals_indicators, internals_max, breadth_pct = score_usa_internals(
            {}, None, None, rs_data
        )
        
        timing_score, timing_indicators, timing_max = score_usa_timing(lookback)
        
        momentum_score, momentum_indicators, momentum_max = score_usa_momentum(lookback, rs_data)
        
        sentiment_score, sentiment_indicators, sentiment_max = score_usa_sentiment(lookback)
        
        # Regime
        dxy_strong = dxy_current > dxy_sma200 if dxy_current and dxy_sma200 else False
        regime, regime_reason = detect_regime_usa(
            vix_current, breadth_pct, treasury_yield, dxy_strong, sma200_above
        )
        
        # Karar
        vix_rising = False
        verdict, total_score, explanation, allocation, stop_loss = decide_usa(
            risk_score, internals_score, timing_score, regime,
            vix_current, vix_rising, breadth_pct, sma200_above, risk_profile,
            momentum_score=momentum_score, sentiment_score=sentiment_score,
            risk_max=risk_max, internals_max=internals_max, timing_max=timing_max,
            momentum_max=momentum_max, sentiment_max=sentiment_max,
        )
        
        results.append({
            "date": date.strftime("%Y-%m-%d"),
            "price": round(last_close, 2),
            "verdict": verdict,
            "hisse_pct": allocation.get("hisse", 0),
            "tahvil_pct": allocation.get("tahvil", 30),
            "nakit_pct": allocation.get("nakit", 70),
            "total_score": round(total_score, 2),
            "risk_score": round(risk_score, 2),
            "breadth_score": round(internals_score, 2),
            "timing_score": round(timing_score, 2),
            "momentum_score": round(momentum_score, 2),
            "sentiment_score": round(sentiment_score, 2),
            "vix": vix_current,
            "regime": regime,
        })
    
    return pd.DataFrame(results), None


def run_simulation(market, start_date, end_date, risk_profile="Dengeli", api_key=""):
    """
    Ana fonksiyon - piyasa seçimine göre simülasyon çalıştır.
    
    Args:
        market: "BIST" veya "USA"
        start_date: "YYYY-MM-DD" formatında başlangıç
        end_date: "YYYY-MM-DD" formatında bitiş
        risk_profile: "Korumacı", "Dengeli", "Agresif", "Fırsatçı"
        api_key: TwelveData API key (USA için)
    
    Returns:
        (DataFrame, error_message)
    """
    if market == "BIST":
        return simulate_bist_period(start_date, end_date, risk_profile, api_key)
    elif market == "USA":
        return simulate_usa_period(start_date, end_date, risk_profile, api_key)
    else:
        return None, f"Bilinmeyen piyasa: {market}"
