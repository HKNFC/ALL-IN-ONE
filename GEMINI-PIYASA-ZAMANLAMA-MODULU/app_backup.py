import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

from config import (
    BIST_TICKERS, SP500_TICKERS, BIST_SECTOR_MAP,
    RISK_PROFILES, REGIME_LABELS, CDS_THRESHOLDS,
)
from utils import (
    signal_color, signal_icon, signal_label,
    format_number, pct_format, score_bar_html,
    indicator_row_html, sub_score_card_html,
)
from data_fetcher import (
    fetch_turkey_cds, fetch_spy_put_call_ratio,
    fetch_index_history, fetch_vix_data, fetch_treasury_yield,
    fetch_dxy_data, fetch_usdtry_data, fetch_multi_ticker_data,
    fetch_sector_data, fetch_relative_strength_data,
    fetch_usa_data_via_twelvedata, generate_mock_data,
    fetch_tcmb_policy_rate, fetch_tcmb_inflation,
)
from indicators import (
    calc_sma, calc_rsi, calc_macd, calc_adx, calc_obv,
    calc_volatility, calc_sma_slope, calc_usdtry_volatility,
)
from market_regime import detect_regime_bist, detect_regime_usa
from scoring_bist import score_bist_macro, score_bist_health, score_bist_timing
from scoring_usa import score_usa_risk, score_usa_internals, score_usa_timing
from decision_engine import decide_bist, decide_usa, get_verdict_style
from backtest import run_backtest

st.set_page_config(
    page_title="Piyasa Zamanlaması Dashboard",
    page_icon="⏱️",
    layout="wide",
)

API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")

MARKETS = {
    "Borsa İstanbul (BIST)": {
        "symbol": "XU100.IS", "display": "BIST 100",
        "currency": "TRY", "source": "yfinance",
    },
    "ABD Borsaları (USA)": {
        "symbol": "SPY", "display": "S&P 500 ETF",
        "currency": "USD", "source": "twelvedata",
    },
}

USA_INDEX_OPTIONS = {"SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF"}

st.sidebar.title("⏱️ Piyasa Zamanlaması")
selected_market = st.sidebar.radio("Piyasa Seçimi", list(MARKETS.keys()))
market_info = MARKETS[selected_market]

if selected_market == "ABD Borsaları (USA)":
    usa_index = st.sidebar.selectbox(
        "Endeks", list(USA_INDEX_OPTIONS.keys()),
        format_func=lambda x: f"{x} — {USA_INDEX_OPTIONS[x]}",
    )
    market_info = {**market_info, "symbol": usa_index, "display": USA_INDEX_OPTIONS[usa_index]}

st.sidebar.markdown("---")
risk_profile = st.sidebar.selectbox(
    "Risk Profili",
    list(RISK_PROFILES.keys()),
    index=1,
    format_func=lambda x: f"{x} — {RISK_PROFILES[x]['desc']}",
)

st.sidebar.markdown("---")
enable_backtest = st.sidebar.checkbox("📊 Backtest Göster", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("Strateji Parametreleri")

cds_trend = None
cds_change = None
cds_change_pct = None
yabanci_oran = None
yabanci_degisim = None

if selected_market == "Borsa İstanbul (BIST)":
    evds_rate = fetch_tcmb_policy_rate()
    evds_inflation = fetch_tcmb_inflation()

    rate_default = evds_rate if evds_rate is not None else 42.50
    infl_default = evds_inflation if evds_inflation is not None else 37.86

    evds_status_parts = []
    if evds_rate is not None:
        evds_status_parts.append(f"Faiz: %{evds_rate:.1f}")
    if evds_inflation is not None:
        evds_status_parts.append(f"Enflasyon: %{evds_inflation:.1f}")
    if evds_status_parts:
        st.sidebar.success(f"TCMB EVDS: {' | '.join(evds_status_parts)}")
    else:
        st.sidebar.caption("EVDS bağlantısı kurulamadı, varsayılan değerler kullanılıyor")

    policy_rate = st.sidebar.number_input("Güncel Politika Faizi (%)", value=rate_default, min_value=0.0, max_value=200.0, step=0.25, format="%.2f")
    annual_inflation = st.sidebar.number_input("Yıllık Enflasyon (%)", value=infl_default, min_value=0.0, max_value=500.0, step=0.1, format="%.2f")
    auto_cds, cds_change, cds_change_pct = fetch_turkey_cds()
    if auto_cds is not None:
        cds_default = int(round(auto_cds))
        change_text = ""
        if cds_change is not None:
            sign = "+" if cds_change > 0 else ""
            change_text = f" | Değişim: {sign}{cds_change:.2f}"
        if cds_change_pct is not None:
            sign = "+" if cds_change_pct > 0 else ""
            change_text += f" ({sign}{cds_change_pct:.2f}%)"
        st.sidebar.success(f"CDS otomatik: {auto_cds:.2f} bps{change_text}")
    else:
        cds_default = 270
        cds_change = None
        cds_change_pct = None
        st.sidebar.warning("CDS verisi çekilemedi, manuel girin")

    cds_trend = None
    if cds_change is not None:
        if cds_change > 3:
            cds_trend = "rising"
        elif cds_change < -3:
            cds_trend = "falling"
        else:
            cds_trend = "flat"

    cds_value = st.sidebar.number_input("5Y CDS Primi (bps)", value=cds_default, min_value=0, max_value=2000, step=5)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Yabancı Yatırımcı Verileri**")
    st.sidebar.caption("Kaynak: [Borsa İstanbul Yabancı İşlem Verileri](https://www.borsaistanbul.com/tr/sayfa/2426/bist-pay-piyasasi-yabanci-islem-verileri)")
    yabanci_oran = st.sidebar.number_input("Yabancı Takas Payı (%)", value=30.0, min_value=0.0, max_value=100.0, step=0.5, format="%.1f")
    yabanci_onceki = st.sidebar.number_input("1 Ay Önceki Yabancı Payı (%)", value=30.0, min_value=0.0, max_value=100.0, step=0.5, format="%.1f")
    yabanci_degisim = yabanci_oran - yabanci_onceki

pc_ratio_val = None
pc_volume_ratio = None
pcr_expiry = None
pcr_details = None

if selected_market == "ABD Borsaları (USA)":
    st.sidebar.markdown("**Put/Call Oranı (SPY Opsiyon)**")
    auto_pcr, auto_pcr_vol, pcr_expiry, pcr_details = fetch_spy_put_call_ratio()
    if auto_pcr is not None:
        st.sidebar.success(f"P/C otomatik: {auto_pcr:.2f} (OI) | Vade: {pcr_expiry}")
        pc_ratio_val = auto_pcr
        pc_volume_ratio = auto_pcr_vol
    else:
        st.sidebar.warning("Opsiyon verisi çekilemedi, manuel girin")
        pc_ratio_val = 0.85
        pc_volume_ratio = None
    pc_ratio_val = st.sidebar.number_input("P/C Oranı (OI)", value=round(pc_ratio_val, 2), min_value=0.0, max_value=5.0, step=0.01, format="%.2f")


@st.cache_data(ttl=300)
def fetch_yf_series(symbol, days=400):
    import yfinance as yf
    end = datetime.today()
    start = end - timedelta(days=days)
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start, end=end)
    if hist.empty:
        return None, "Veri bulunamadı."
    hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
    return hist, None


@st.cache_data(ttl=300)
def fetch_td_series(symbol, outputsize=400):
    if not API_KEY:
        return None, "TWELVEDATA_API_KEY bulunamadı."
    try:
        import requests
        r = requests.get(f"https://api.twelvedata.com/time_series", params={
            "symbol": symbol, "interval": "1day", "outputsize": outputsize,
            "order": "ASC", "apikey": API_KEY,
        }, timeout=15)
        data = r.json()
        if data.get("status") == "error":
            return None, data.get("message", "API hatası")
        values = data.get("values")
        if not values:
            return None, "Veri bulunamadı."
        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        return df, None
    except Exception as e:
        return None, str(e)


with st.spinner("Piyasa verileri yükleniyor..."):
    if market_info["source"] == "twelvedata":
        hist, data_err = fetch_td_series(market_info["symbol"], outputsize=400)
    else:
        hist, data_err = fetch_yf_series(market_info["symbol"], days=400)

if data_err:
    st.error(f"Veri alınamadı: {data_err}")
    st.stop()

if hist is None or hist.empty:
    st.warning("Seçilen endeks için veri bulunamadı.")
    st.stop()

close = hist["Close"]
high = hist["High"] if "High" in hist.columns else close
low = hist["Low"] if "Low" in hist.columns else close
volume = hist["Volume"] if "Volume" in hist.columns else None
last_close = close.iloc[-1]
prev_close = close.iloc[-2] if len(close) > 1 else last_close
daily_change_pct = ((last_close - prev_close) / prev_close) * 100

sma50 = calc_sma(close, 50)
sma200 = calc_sma(close, 200)
rsi = calc_rsi(close)
_, _, macd_histogram = calc_macd(close)
adx = calc_adx(high, low, close)
obv = calc_obv(close, volume) if volume is not None else None
volatility = calc_volatility(close)

sma50_val = sma50.dropna().iloc[-1] if sma50 is not None and len(sma50.dropna()) > 0 else None
sma200_val = sma200.dropna().iloc[-1] if sma200 is not None and len(sma200.dropna()) > 0 else None
rsi_val = rsi.dropna().iloc[-1] if rsi is not None and len(rsi.dropna()) > 0 else 50
vol_current = volatility.dropna().iloc[-1] if volatility is not None and len(volatility.dropna()) > 0 else None

hist["SMA50"] = sma50
hist["SMA200"] = sma200
hist["RSI"] = rsi
if obv is not None:
    hist["OBV"] = obv
hist["Volume_SMA_20"] = volume.rolling(20).mean() if volume is not None else None

if selected_market == "Borsa İstanbul (BIST)":
    real_rate = policy_rate - annual_inflation
    usdtry_hist = fetch_usdtry_data(period="1y")
    bist_usd_above_sma200 = None
    bist_usd = None
    bist_usd_sma200_val = None
    usdtry_vol_current = None
    usdtry_vol_avg = None

    if usdtry_hist is not None and not usdtry_hist.empty:
        usdtry_close = usdtry_hist["Close"]
        usdtry_vol_current, usdtry_vol_avg = calc_usdtry_volatility(usdtry_close)
        common_idx = hist.index.intersection(usdtry_hist.index)
        if len(common_idx) > 0:
            bist_close = hist.loc[common_idx, "Close"]
            usd_close = usdtry_hist.loc[common_idx, "Close"]
            bist_usd_series = bist_close / usd_close
            bist_usd = pd.DataFrame({"BIST_USD": bist_usd_series})
            bist_usd["SMA200"] = bist_usd["BIST_USD"].rolling(200).mean()
            bist_usd_last = bist_usd["BIST_USD"].iloc[-1]
            sma200_bu = bist_usd["SMA200"].dropna()
            if len(sma200_bu) > 0:
                bist_usd_sma200_val = sma200_bu.iloc[-1]
                bist_usd_above_sma200 = bist_usd_last > bist_usd_sma200_val

    with st.spinner("BIST piyasa genişliği hesaplanıyor..."):
        bist_ticker_data = fetch_multi_ticker_data(BIST_TICKERS[:50], period="1y")
        bist_sector_data = fetch_sector_data(BIST_SECTOR_MAP, period="1y")

    macro_score, macro_indicators, macro_max = score_bist_macro(
        cds_value, real_rate, bist_usd_above_sma200, usdtry_vol_current, usdtry_vol_avg,
        cds_trend=cds_trend, yabanci_oran=yabanci_oran, yabanci_degisim=yabanci_degisim,
    )
    health_score, health_indicators, health_max, breadth_pct = score_bist_health(
        bist_ticker_data, bist_sector_data, hist=hist
    )
    timing_score, timing_indicators, timing_max = score_bist_timing(hist)

    regime, regime_reason = detect_regime_bist(macro_score, breadth_pct, vol_current, cds_value)
    verdict, total_score, explanation, allocation, stop_loss = decide_bist(
        macro_score, health_score, timing_score, regime,
        cds_value, real_rate, breadth_pct, bist_usd_above_sma200, risk_profile,
        cds_trend=cds_trend, yabanci_oran=yabanci_oran, yabanci_degisim=yabanci_degisim,
    )

elif selected_market == "ABD Borsaları (USA)":
    vix_current, vix_5d_change, vix_hist = fetch_vix_data()
    treasury_yield = fetch_treasury_yield()
    dxy_current, dxy_sma50, dxy_sma200, dxy_hist = fetch_dxy_data()
    rs_data = fetch_relative_strength_data()

    dxy_strong = None
    if dxy_current is not None and dxy_sma200 is not None:
        dxy_strong = dxy_current > dxy_sma200

    sma200_above = sma200_val is not None and last_close > sma200_val

    with st.spinner("S&P 500 piyasa genişliği hesaplanıyor..."):
        sp500_ticker_data = fetch_multi_ticker_data(SP500_TICKERS[:100], period="1y")

    risk_score, risk_indicators, risk_max = score_usa_risk(
        vix_current, vix_5d_change, treasury_yield,
        dxy_current, dxy_sma50, dxy_sma200,
    )
    internals_score, internals_indicators, internals_max, breadth_pct = score_usa_internals(
        sp500_ticker_data, pc_ratio_val, pc_volume_ratio, rs_data,
    )
    timing_score, timing_indicators, timing_max = score_usa_timing(hist)

    vix_rising = vix_5d_change is not None and vix_5d_change > 0
    regime, regime_reason = detect_regime_usa(
        vix_current, breadth_pct, treasury_yield, dxy_strong, sma200_above,
    )
    verdict, total_score, explanation, allocation, stop_loss = decide_usa(
        risk_score, internals_score, timing_score, regime,
        vix_current, vix_rising, breadth_pct, sma200_above, risk_profile,
    )


regime_info = REGIME_LABELS.get(regime, REGIME_LABELS["neutral"])
verdict_style = get_verdict_style(verdict)

st.markdown(f"""
<div style="display:flex; gap:16px; margin-bottom:20px;">
    <div style="flex:1; background:{regime_info['color']}15; border:2px solid {regime_info['color']}40;
                border-radius:12px; padding:16px; text-align:center;">
        <div style="font-size:12px; color:#6B7280; margin-bottom:4px;">PİYASA REJİMİ</div>
        <div style="font-size:28px; font-weight:800; color:{regime_info['color']};">
            {regime_info['icon']} {regime_info['label']}
        </div>
        <div style="font-size:12px; color:#6B7280; margin-top:4px;">{regime_reason}</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="
    background: {verdict_style['bg']};
    border: 3px solid {verdict_style['border']};
    border-radius: 16px;
    padding: 28px 32px;
    text-align: center;
    margin-bottom: 24px;
">
    <div style="font-size: 18px; color: #6B7280; font-weight: 500; margin-bottom: 4px;">
        {market_info['display']} — İŞLEM KARARI
    </div>
    <div style="font-size: 56px; font-weight: 900; color: {verdict_style['color']}; letter-spacing: 4px;">
        {verdict_style['icon']} {verdict}
    </div>
    <div style="font-size: 16px; color: #4B5563; margin-top: 8px; max-width:800px; margin-left:auto; margin-right:auto;">
        {explanation}
    </div>
    <div style="margin-top:12px; font-size:13px; color:#9CA3AF;">
        Risk Profili: {risk_profile} | Toplam Puan: {total_score:.1f}
    </div>
</div>
""", unsafe_allow_html=True)

alloc_cols = st.columns(3)
with alloc_cols[0]:
    hisse_pct = allocation.get("hisse", 0)
    hisse_color = "#10B981" if hisse_pct >= 50 else ("#F59E0B" if hisse_pct >= 20 else "#EF4444")
    st.markdown(f"""
    <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:16px; text-align:center;">
        <div style="font-size:12px; color:#6B7280; margin-bottom:6px;">Hisse Senedi</div>
        <div style="font-size:32px; font-weight:800; color:{hisse_color};">%{hisse_pct}</div>
    </div>
    """, unsafe_allow_html=True)
with alloc_cols[1]:
    tahvil_pct = allocation.get("tahvil", 0)
    st.markdown(f"""
    <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:16px; text-align:center;">
        <div style="font-size:12px; color:#6B7280; margin-bottom:6px;">Tahvil / Mevduat</div>
        <div style="font-size:32px; font-weight:800; color:#3B82F6;">%{tahvil_pct}</div>
    </div>
    """, unsafe_allow_html=True)
with alloc_cols[2]:
    nakit_pct = allocation.get("nakit", 0)
    st.markdown(f"""
    <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:16px; text-align:center;">
        <div style="font-size:12px; color:#6B7280; margin-bottom:6px;">Nakit</div>
        <div style="font-size:32px; font-weight:800; color:#6B7280;">%{nakit_pct}</div>
    </div>
    """, unsafe_allow_html=True)

if stop_loss is not None:
    sl_tip = stop_loss.get("tip", "")
    sl_yuzde = stop_loss.get("yuzde", 0)
    st.markdown(f"""
    <div style="background:#FEF3C7; border:1px solid #FCD34D; border-radius:10px; padding:12px 20px; margin-top:8px; margin-bottom:16px; display:flex; align-items:center; gap:12px;">
        <div style="font-size:20px;">🛡️</div>
        <div>
            <span style="font-weight:700; color:#92400E;">Stop-Loss Önerisi:</span>
            <span style="color:#78350F;"> {sl_tip} — Maksimum %{sl_yuzde} zarar toleransı ({risk_profile} profil)</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div style="background:#FEE2E2; border:1px solid #FCA5A5; border-radius:10px; padding:12px 20px; margin-top:8px; margin-bottom:16px; display:flex; align-items:center; gap:12px;">
        <div style="font-size:20px;">⛔</div>
        <div>
            <span style="font-weight:700; color:#991B1B;">İşlem Önerilmez:</span>
            <span style="color:#7F1D1D;"> Mevcut koşullarda pozisyon açmayın. Nakit ve güvenli limanlarda kalın.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

if selected_market == "Borsa İstanbul (BIST)":
    sub_labels = [("Makro", macro_score, "🏛️"), ("Piyasa Sağlığı", health_score, "🏥"), ("Zamanlama", timing_score, "⏱️")]
    all_indicators = [("Makro Göstergeler", macro_indicators), ("Piyasa Sağlığı", health_indicators), ("Zamanlama", timing_indicators)]
else:
    sub_labels = [("Risk Ortamı", risk_score, "🛡️"), ("Piyasa İç Yapısı", internals_score, "📊"), ("Zamanlama", timing_score, "⏱️")]
    all_indicators = [("Risk Ortamı", risk_indicators), ("Piyasa İç Yapısı", internals_indicators), ("Zamanlama", timing_indicators)]

score_cols = st.columns(len(sub_labels))
for idx, (label, score, icon) in enumerate(sub_labels):
    with score_cols[idx]:
        s_color = signal_color(score)
        s_sign = "+" if score > 0 else ""
        st.markdown(f"""
        <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:14px; text-align:center;">
            <div style="font-size:12px; color:#6B7280; margin-bottom:4px;">{icon} {label}</div>
            <div style="font-size:24px; font-weight:800; color:{s_color};">{s_sign}{score:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

price_cols = st.columns(5 if selected_market == "ABD Borsaları (USA)" and vix_current is not None else 4)
with price_cols[0]:
    st.metric("Son Fiyat", f"{last_close:,.2f} {market_info['currency']}")
with price_cols[1]:
    st.metric("Günlük Değişim", f"{daily_change_pct:+.2f}%", delta=f"{daily_change_pct:+.2f}%")
with price_cols[2]:
    st.metric("RSI (14)", f"{rsi_val:.1f}")
with price_cols[3]:
    if vol_current is not None:
        st.metric("Volatilite (20G)", f"{vol_current:.1f}%")
if selected_market == "ABD Borsaları (USA)" and vix_current is not None:
    with price_cols[4]:
        vix_delta = f"{vix_5d_change:+.2f}" if vix_5d_change is not None else None
        st.metric("VIX Korku", f"{vix_current:.2f}", delta=vix_delta, delta_color="inverse")

display_cutoff = pd.Timestamp(datetime.today() - timedelta(days=250))
hist_display = hist[hist.index >= display_cutoff]

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    vertical_spacing=0.06, row_heights=[0.75, 0.25],
    subplot_titles=("", "RSI (14)"),
)

fig.add_trace(go.Scatter(
    x=hist_display.index, y=hist_display["Close"],
    mode="lines", name="Fiyat",
    line=dict(color="#1f77b4", width=2.5),
    fill="tozeroy", fillcolor="rgba(31,119,180,0.08)",
), row=1, col=1)

if sma50 is not None:
    fig.add_trace(go.Scatter(
        x=hist_display.index, y=hist_display["SMA50"],
        mode="lines", name="SMA 50",
        line=dict(color="#F59E0B", width=2, dash="dash"),
    ), row=1, col=1)

if sma200 is not None:
    fig.add_trace(go.Scatter(
        x=hist_display.index, y=hist_display["SMA200"],
        mode="lines", name="SMA 200",
        line=dict(color="#EF4444", width=2, dash="dot"),
    ), row=1, col=1)

if rsi is not None:
    fig.add_trace(go.Scatter(
        x=hist_display.index, y=hist_display["RSI"],
        mode="lines", name="RSI",
        line=dict(color="#8B5CF6", width=1.5),
    ), row=2, col=1)

fig.add_hline(y=70, line_dash="dash", line_color="red", line_width=1, row=2, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="green", line_width=1, row=2, col=1)

fig.update_layout(
    template="plotly_white", height=600,
    margin=dict(l=40, r=40, t=20, b=40),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
fig.update_yaxes(title_text=f"Fiyat ({market_info['currency']})", row=1, col=1)
fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

st.plotly_chart(fig, width="stretch")

st.markdown("---")
st.subheader("Hacim Analizi & Para Akışı (OBV)")

vol_sma20 = hist["Volume_SMA_20"] if "Volume_SMA_20" in hist.columns else None
last_volume = volume.iloc[-1] if volume is not None else 0
vol_sma20_val = vol_sma20.dropna().iloc[-1] if vol_sma20 is not None and len(vol_sma20.dropna()) > 0 else None
hacim_onayi = vol_sma20_val is not None and last_volume > vol_sma20_val

obv_trend_pozitif = None
if obv is not None and len(obv.dropna()) >= 6:
    obv_5d_change = obv.dropna().iloc[-1] - obv.dropna().iloc[-6]
    obv_trend_pozitif = obv_5d_change > 0

vol_fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    vertical_spacing=0.08, row_heights=[0.5, 0.5],
    subplot_titles=("İşlem Hacmi & 20 Günlük Ortalama", "OBV (On-Balance Volume)"),
)

if volume is not None:
    vol_colors = ["#10B981" if hist_display["Close"].iloc[i] >= hist_display["Close"].iloc[i-1] else "#EF4444"
                  for i in range(1, len(hist_display))]
    vol_colors.insert(0, "#6B7280")

    vol_fig.add_trace(go.Bar(
        x=hist_display.index, y=hist_display["Volume"],
        name="Hacim", marker_color=vol_colors, opacity=0.6,
    ), row=1, col=1)

    if vol_sma20 is not None:
        vol_fig.add_trace(go.Scatter(
            x=hist_display.index, y=vol_sma20[hist_display.index] if hasattr(vol_sma20, 'loc') else None,
            name="Hacim SMA 20", line=dict(color="#F59E0B", width=2),
        ), row=1, col=1)

if obv is not None:
    obv_color = "#10B981" if obv_trend_pozitif else "#EF4444" if obv_trend_pozitif is not None else "#6B7280"
    vol_fig.add_trace(go.Scatter(
        x=hist_display.index, y=obv[hist_display.index] if hasattr(obv, 'loc') else hist_display.get("OBV"),
        name="OBV", line=dict(color=obv_color, width=2),
        fill="tozeroy",
        fillcolor=f"rgba({16 if obv_trend_pozitif else 239},{185 if obv_trend_pozitif else 68},{129 if obv_trend_pozitif else 68},0.08)",
    ), row=2, col=1)

vol_fig.update_layout(
    template="plotly_white", height=500,
    margin=dict(l=40, r=40, t=30, b=40),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
vol_fig.update_yaxes(title_text="Hacim", row=1, col=1)
vol_fig.update_yaxes(title_text="OBV", row=2, col=1)

st.plotly_chart(vol_fig, width="stretch")

hacim_cols = st.columns(3)
with hacim_cols[0]:
    vol_ratio = (last_volume / vol_sma20_val * 100) if vol_sma20_val and vol_sma20_val > 0 else 0
    st.metric("Güncel Hacim / Ort.", f"{vol_ratio:.0f}%",
              delta="Ortalamanın üzerinde" if hacim_onayi else "Ortalamanın altında",
              delta_color="normal" if hacim_onayi else "inverse")
with hacim_cols[1]:
    obv_trend_label = "Pozitif (Para Girişi)" if obv_trend_pozitif else ("Negatif (Para Çıkışı)" if obv_trend_pozitif is not None else "Belirsiz")
    st.metric("OBV 5G Trend", obv_trend_label)
with hacim_cols[2]:
    hacim_puan = 0
    if sma50_val is not None:
        if last_close > sma50_val and hacim_onayi:
            hacim_puan = 2
        elif last_close > sma50_val:
            hacim_puan = 1
    if obv_trend_pozitif is not None and not obv_trend_pozitif:
        hacim_puan -= 1
    puan_desc = "Güçlü" if hacim_puan >= 2 else ("Zayıf" if hacim_puan == 1 else ("Nötr" if hacim_puan == 0 else "Dikkat"))
    st.metric("Hacim Skoru", f"{puan_desc} ({hacim_puan:+d})")


st.markdown("---")
st.subheader("📋 Gösterge Detay Tablosu")

for section_name, indicators_list in all_indicators:
    if not indicators_list:
        continue
    rows_html = ""
    for ind in indicators_list:
        rows_html += indicator_row_html(
            ind["name"], ind["value"], ind["threshold"],
            ind["signal"], ind["points"], ind["desc"],
        )

    st.markdown(f"""
    <div style="margin-bottom:20px;">
        <div style="font-size:15px; font-weight:700; color:#374151; margin-bottom:8px; padding:8px 12px;
                    background:#F3F4F6; border-radius:8px;">{section_name}</div>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <thead>
                <tr style="background:#F9FAFB; border-bottom:2px solid #E5E7EB;">
                    <th style="padding:8px 12px; text-align:left; color:#6B7280;">Gösterge</th>
                    <th style="padding:8px 12px; text-align:left; color:#6B7280;">Değer</th>
                    <th style="padding:8px 12px; text-align:left; color:#6B7280;">Eşik</th>
                    <th style="padding:8px 12px; text-align:left; color:#6B7280;">Puan</th>
                    <th style="padding:8px 12px; text-align:left; color:#6B7280;">Açıklama</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)


if selected_market == "Borsa İstanbul (BIST)":
    st.markdown("---")
    st.subheader("CDS Risk Primi & Dolar Bazlı BIST")

    cds_col1, cds_col2 = st.columns(2)

    with cds_col1:
        cds_trend_label = ""
        if cds_trend == "rising":
            cds_trend_label = " ↗️ Yükseliyor"
        elif cds_trend == "falling":
            cds_trend_label = " ↘️ Düşüyor"
        elif cds_trend == "flat":
            cds_trend_label = " → Yatay"
        st.markdown(f"##### 🛡️ CDS Primi (5 Yıllık){cds_trend_label}")

        if cds_value < CDS_THRESHOLDS["guclu_giris"]:
            cds_color, cds_zone = "#10B981", "Güçlü Giriş"
        elif cds_value < CDS_THRESHOLDS["ilimli_giris"]:
            cds_color, cds_zone = "#84CC16", "Ilımlı Giriş"
        elif cds_value < CDS_THRESHOLDS["zayif_ilgi"]:
            cds_color, cds_zone = "#F59E0B", "Zayıf İlgi"
        elif cds_value < CDS_THRESHOLDS["sert_cikis"]:
            cds_color, cds_zone = "#EF4444", "Sert Çıkış"
        else:
            cds_color, cds_zone = "#991B1B", "Sistem Kapalı"

        cds_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=cds_value,
            number=dict(suffix=" bps", font=dict(size=28)),
            gauge=dict(
                axis=dict(range=[0, 800]),
                bar=dict(color=cds_color),
                steps=[
                    dict(range=[0, 200], color="rgba(16,185,129,0.15)"),
                    dict(range=[200, 300], color="rgba(132,204,22,0.15)"),
                    dict(range=[300, 400], color="rgba(245,158,11,0.15)"),
                    dict(range=[400, 500], color="rgba(239,68,68,0.15)"),
                    dict(range=[500, 800], color="rgba(153,27,27,0.15)"),
                ],
                threshold=dict(line=dict(color="#DC2626", width=3), thickness=0.8, value=500),
            ),
            title=dict(text=cds_zone, font=dict(size=16, color=cds_color)),
        ))
        cds_gauge.update_layout(height=250, margin=dict(l=30, r=30, t=40, b=20))
        st.plotly_chart(cds_gauge, width='stretch')

    with cds_col2:
        st.markdown("##### 💵 BIST 100 / USD")
        if bist_usd is not None and not bist_usd.empty:
            bist_usd_fig = go.Figure()
            bist_usd_fig.add_trace(go.Scatter(
                x=bist_usd.index, y=bist_usd["BIST_USD"],
                name="BIST/USD", line=dict(color="#2563EB", width=2),
            ))
            bist_usd_fig.add_trace(go.Scatter(
                x=bist_usd.index, y=bist_usd["SMA200"],
                name="SMA 200", line=dict(color="#EF4444", width=1.5, dash="dot"),
            ))
            if bist_usd_above_sma200 is not None:
                marker_color = "#10B981" if bist_usd_above_sma200 else "#EF4444"
                bist_usd_fig.add_trace(go.Scatter(
                    x=[bist_usd.index[-1]], y=[bist_usd["BIST_USD"].iloc[-1]],
                    mode="markers+text", marker=dict(size=10, color=marker_color, symbol="diamond"),
                    text=[f"  {bist_usd['BIST_USD'].iloc[-1]:.2f}"],
                    textposition="middle right", textfont=dict(size=11, color=marker_color),
                    showlegend=False,
                ))
            bist_usd_fig.update_layout(
                template="plotly_white", height=250,
                margin=dict(l=40, r=40, t=20, b=40),
                hovermode="x unified", yaxis_title="BIST/USD",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(bist_usd_fig, width='stretch')

            if bist_usd_above_sma200:
                st.markdown("""
                <div style="background:#ECFDF5; border-left:4px solid #10B981; padding:12px 16px; border-radius:8px;">
                    <b style="color:#065F46;">✅ Dolar Bazında Yükseliş Trendinde</b><br>
                    <span style="color:#374151; font-size:13px;">BIST/USD, SMA 200 üzerinde. TL bazlı yükseliş dolar bazında doğrulanıyor.</span>
                </div>
                """, unsafe_allow_html=True)
            elif bist_usd_above_sma200 is not None:
                st.markdown("""
                <div style="background:#FEF2F2; border-left:4px solid #EF4444; padding:12px 16px; border-radius:8px;">
                    <b style="color:#991B1B;">⚠️ Dolar Bazında Düşüş Trendinde</b><br>
                    <span style="color:#374151; font-size:13px;">BIST/USD, SMA 200 altında. TL bazlı rekorlar yanıltıcı olabilir.</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("BIST/USD verisi hesaplanamadı.")


if selected_market == "ABD Borsaları (USA)":
    if vix_current is not None and vix_hist is not None and not vix_hist.empty:
        st.markdown("---")
        st.subheader("VIX Korku Endeksi")

        vix_close = vix_hist["Close"]
        vix_sma50 = vix_close.rolling(50).mean()
        vix_sma200 = vix_close.rolling(200).mean()

        vix_fig = go.Figure()
        vix_fig.add_trace(go.Scatter(x=vix_hist.index, y=vix_close, name="VIX", line=dict(color="#7C3AED", width=2)))
        vix_fig.add_trace(go.Scatter(x=vix_hist.index, y=vix_sma50, name="SMA 50", line=dict(color="#F59E0B", width=1.5, dash="dash")))
        vix_fig.add_trace(go.Scatter(x=vix_hist.index, y=vix_sma200, name="SMA 200", line=dict(color="#EF4444", width=1.5, dash="dot")))
        vix_fig.add_hline(y=25, line_dash="solid", line_color="#DC2626", line_width=1.5,
                          annotation_text="Yüksek Korku (25)", annotation_position="top left",
                          annotation_font_color="#DC2626", annotation_font_size=11)
        vix_fig.add_hline(y=15, line_dash="solid", line_color="#059669", line_width=1.5,
                          annotation_text="Düşük Korku (15)", annotation_position="bottom left",
                          annotation_font_color="#059669", annotation_font_size=11)
        vix_fig.add_hrect(y0=25, y1=max(vix_close.max() * 1.1, 40), fillcolor="rgba(220,38,38,0.07)", line_width=0)
        vix_fig.add_hrect(y0=0, y1=15, fillcolor="rgba(5,150,105,0.07)", line_width=0)

        vix_fig.add_trace(go.Scatter(
            x=[vix_hist.index[-1]], y=[vix_current],
            mode="markers+text", marker=dict(size=10, color="#7C3AED", symbol="diamond"),
            text=[f"  {vix_current:.1f}"], textposition="middle right",
            textfont=dict(size=12, color="#7C3AED"), showlegend=False,
        ))

        vix_fig.update_layout(
            template="plotly_white", height=350,
            margin=dict(l=40, r=40, t=20, b=40),
            hovermode="x unified", yaxis_title="VIX",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(vix_fig, width="stretch")

    st.markdown("---")
    st.subheader("Put/Call Oranı & DXY (Dolar Endeksi)")

    usa_col1, usa_col2 = st.columns(2)

    with usa_col1:
        st.markdown("##### 📊 Put/Call Oranları")
        if pc_ratio_val is not None:
            if pc_ratio_val > 1.0:
                pc_color, pc_zone = "#10B981", "Aşırı Korku (Alım Fırsatı)"
            elif pc_ratio_val > 0.7:
                pc_color, pc_zone = "#F59E0B", "Normal"
            elif pc_ratio_val > 0.5:
                pc_color, pc_zone = "#F97316", "Düşük Korku"
            else:
                pc_color, pc_zone = "#EF4444", "Aşırı Coşku (Satış Sinyali)"

            pc_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=pc_ratio_val,
                number=dict(font=dict(size=24)),
                gauge=dict(
                    axis=dict(range=[0, 2.0]),
                    bar=dict(color=pc_color),
                    steps=[
                        dict(range=[0, 0.5], color="rgba(239,68,68,0.15)"),
                        dict(range=[0.5, 0.7], color="rgba(249,115,22,0.15)"),
                        dict(range=[0.7, 1.0], color="rgba(245,158,11,0.15)"),
                        dict(range=[1.0, 2.0], color="rgba(16,185,129,0.15)"),
                    ],
                    threshold=dict(line=dict(color="#DC2626", width=3), thickness=0.8, value=1.0),
                ),
                title=dict(text=pc_zone, font=dict(size=14, color=pc_color)),
            ))
            pc_gauge.update_layout(height=220, margin=dict(l=30, r=30, t=40, b=10))
            st.plotly_chart(pc_gauge, width='stretch')

            if pcr_details is not None:
                put_oi = pcr_details["put_oi"]
                call_oi = pcr_details["call_oi"]
                vol_text = f"{pc_volume_ratio:.2f}" if pc_volume_ratio is not None else "N/A"
                st.markdown(f"""
                <div style="display:flex; gap:12px; margin-bottom:10px;">
                    <div style="flex:1; background:#F9FAFB; border-radius:8px; padding:10px 14px; text-align:center;">
                        <div style="font-size:11px; color:#6B7280;">Put OI</div>
                        <div style="font-size:18px; font-weight:700; color:#EF4444;">{put_oi:,}</div>
                    </div>
                    <div style="flex:1; background:#F9FAFB; border-radius:8px; padding:10px 14px; text-align:center;">
                        <div style="font-size:11px; color:#6B7280;">Call OI</div>
                        <div style="font-size:18px; font-weight:700; color:#10B981;">{call_oi:,}</div>
                    </div>
                    <div style="flex:1; background:#F9FAFB; border-radius:8px; padding:10px 14px; text-align:center;">
                        <div style="font-size:11px; color:#6B7280;">Volume P/C</div>
                        <div style="font-size:18px; font-weight:700;">{vol_text}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with usa_col2:
        st.markdown("##### 💲 DXY (Dolar Endeksi)")
        if dxy_hist is not None and not dxy_hist.empty:
            dxy_fig = go.Figure()
            dxy_close = dxy_hist["Close"]
            dxy_s50 = dxy_close.rolling(50).mean()
            dxy_s200 = dxy_close.rolling(200).mean()

            dxy_fig.add_trace(go.Scatter(x=dxy_hist.index, y=dxy_close, name="DXY", line=dict(color="#059669", width=2)))
            dxy_fig.add_trace(go.Scatter(x=dxy_hist.index, y=dxy_s50, name="SMA 50", line=dict(color="#F59E0B", width=1.5, dash="dash")))
            dxy_fig.add_trace(go.Scatter(x=dxy_hist.index, y=dxy_s200, name="SMA 200", line=dict(color="#EF4444", width=1.5, dash="dot")))

            if dxy_current is not None:
                dxy_above = dxy_strong if dxy_strong is not None else False
                mc = "#EF4444" if dxy_above else "#10B981"
                dxy_fig.add_trace(go.Scatter(
                    x=[dxy_hist.index[-1]], y=[dxy_current],
                    mode="markers+text", marker=dict(size=10, color=mc, symbol="diamond"),
                    text=[f"  {dxy_current:.2f}"], textposition="middle right",
                    textfont=dict(size=11, color=mc), showlegend=False,
                ))

            dxy_fig.update_layout(
                template="plotly_white", height=250,
                margin=dict(l=40, r=40, t=20, b=40),
                hovermode="x unified", yaxis_title="DXY",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(dxy_fig, width='stretch')

            if dxy_strong:
                st.markdown("""
                <div style="background:#FEF2F2; border-left:4px solid #EF4444; padding:12px 16px; border-radius:8px;">
                    <b style="color:#991B1B;">⚠️ Güçlü Dolar — Hisseler Baskı Altında</b>
                </div>
                """, unsafe_allow_html=True)
            elif dxy_strong is not None and not dxy_strong:
                st.markdown("""
                <div style="background:#ECFDF5; border-left:4px solid #10B981; padding:12px 16px; border-radius:8px;">
                    <b style="color:#065F46;">✅ Zayıf Dolar — Hisseler İçin Olumlu</b>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("DXY verisi alınamadı")


if enable_backtest:
    st.markdown("---")
    st.subheader("📊 Backtest Sonuçları")

    bt_market = "BIST" if selected_market == "Borsa İstanbul (BIST)" else "USA"
    bt_result = run_backtest(hist, market=bt_market)

    if bt_result is not None:
        stats = bt_result["stats"]
        signals_df = bt_result["signals"]

        bt_cols = st.columns(4)
        with bt_cols[0]:
            st.metric("Strateji Getiri", f"%{stats['strat_total_return']:.1f}",
                       delta=f"vs Al-Tut: %{stats['bh_total_return']:.1f}")
        with bt_cols[1]:
            st.metric("Sharpe Oranı", f"{stats['strat_sharpe']:.2f}",
                       delta=f"vs Al-Tut: {stats['bh_sharpe']:.2f}")
        with bt_cols[2]:
            st.metric("Max Drawdown", f"%{stats['strat_max_dd']:.1f}",
                       delta=f"vs Al-Tut: %{stats['bh_max_dd']:.1f}", delta_color="inverse")
        with bt_cols[3]:
            st.metric("Piyasada Kalma", f"%{stats['in_market_pct']:.0f}",
                       delta=f"{stats['total_trades']} işlem")

        eq_fig = go.Figure()
        eq_fig.add_trace(go.Scatter(
            x=signals_df.index, y=signals_df["strategy_equity"],
            name="Strateji", line=dict(color="#10B981", width=2),
            fill="tozeroy", fillcolor="rgba(16,185,129,0.08)",
        ))
        eq_fig.add_trace(go.Scatter(
            x=signals_df.index, y=signals_df["buy_hold_equity"],
            name="Al & Tut", line=dict(color="#6B7280", width=1.5, dash="dash"),
        ))
        eq_fig.update_layout(
            template="plotly_white", height=350,
            margin=dict(l=40, r=40, t=20, b=40),
            hovermode="x unified", yaxis_title="Equity (1.0 = Başlangıç)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(eq_fig, width="stretch")

        st.markdown(f"""
        <div style="background:#EFF6FF; border-left:4px solid #3B82F6; padding:14px 18px; border-radius:8px; margin-top:8px;">
            <div style="font-size:12px; font-weight:600; color:#1E40AF; margin-bottom:3px;">📝 Backtest Notu</div>
            <div style="font-size:13px; color:#1E3A5F; line-height:1.5;">
                Bu backtest geçmiş veriler üzerinde çalıştırılmıştır. Gelecek performansı garanti etmez.
                Strateji SMA50/200, RSI, MACD sinyallerine dayanmaktadır.
                İşlem maliyetleri ve slippage dahil değildir.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("Backtest için yeterli veri yok (en az 252 gün gerekli).")
