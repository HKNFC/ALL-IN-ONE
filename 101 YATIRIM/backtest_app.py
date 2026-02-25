"""
BIST Aylık Rebalancing Backtest & Analiz Platformu
Streamlit arayüzü — Sanal Backtest | Stres Testi | Sektörel Dağılım
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import os, io, calendar, time

# ─────────────────────────────────────────────
#  Sayfa Ayarları
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="BIST Backtest Platformu",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {font-size:2rem; font-weight:700; color:#00d4aa; margin-bottom:0.2rem;}
    .sub-header  {font-size:0.95rem; color:#888; margin-bottom:1.5rem;}
    .metric-card {background:#1a1a2e; border-radius:10px; padding:1rem; text-align:center;}
    .metric-val  {font-size:1.6rem; font-weight:700;}
    .pos         {color:#00d4aa;}
    .neg         {color:#ff4b4b;}
    .neu         {color:#ffa64d;}
    div[data-testid="stButton"] > button {
        width:100%; height:3rem; font-size:1rem; font-weight:600;
        border-radius:8px; border:none; cursor:pointer;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Sabitler
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BIST100 = [
    "AKBNK","ARCLK","ASELS","BIMAS","EKGYO","EREGL","FROTO","GARAN",
    "GUBRF","HALKB","ISCTR","KCHOL","KRDMD","MGROS","ODAS","OYAKC",
    "PGSUS","SAHOL","SASA","SISE","SKBNK","TAVHL","TCELL","THYAO",
    "TKFEN","TOASO","TTKOM","TUPRS","VAKBN","VESTL","YKBNK","AKSA",
    "AEFES","ALARK","ANSGR","ASTOR","AVGYO","BERA","BRISA","CCOLA",
    "CIMSA","DOHOL","EKGYO","ENKAI","GESAN","GLYHO","HEKTS","ISGYO",
    "ISMEN","KARSN","KONTR","KONYA","KORDS","LOGO","MAVI","MPARK",
    "OTKAR","PETKM","RYSAS","SOKM","TATGD","TKNSA","TRGYO","TSKB",
    "TURSG","ULKER","VKGYO","YATAS","AGHOL","AKFGY","AKGRT","ALKIM",
    "ALTNY","ARENA","ARTMS","ATAKP","ATATP","AYES","BAGFS","KLNMA",
]

SEKTOR_MAP = {
    "AKBNK":"Bankacılık","GARAN":"Bankacılık","ISCTR":"Bankacılık","HALKB":"Bankacılık",
    "VAKBN":"Bankacılık","YKBNK":"Bankacılık","SKBNK":"Bankacılık","TSKB":"Bankacılık",
    "AKBNK":"Bankacılık","ANSGR":"Sigorta","AKGRT":"Sigorta","TURSG":"Sigorta",
    "THYAO":"Havacılık","PGSUS":"Havacılık","TAVHL":"Havacılık",
    "ASELS":"Savunma","ASTOR":"Enerji","ODAS":"Enerji","AKFGY":"Enerji",
    "TUPRS":"Petrol/Kimya","PETKM":"Petrol/Kimya","SASA":"Kimya","ALKIM":"Kimya",
    "FROTO":"Otomotiv","TOASO":"Otomotiv","ARCLK":"Dayanıklı Tüketim",
    "VESTL":"Dayanıklı Tüketim","BIMAS":"Perakende","MGROS":"Perakende",
    "SOKM":"Perakende","MAVI":"Perakende","TCELL":"Telekomünikasyon",
    "TTKOM":"Telekomünikasyon","SISE":"Cam/İnşaat","EREGL":"Demir/Çelik",
    "KRDMD":"Demir/Çelik","EKGYO":"GYO","ISGYO":"GYO","TRGYO":"GYO",
    "AVGYO":"GYO","VKGYO":"GYO","KCHOL":"Holding","SAHOL":"Holding",
    "DOHOL":"Holding","GLYHO":"Holding","AGHOL":"Holding","NTHOL":"Holding",
    "ENKAI":"İnşaat","TKFEN":"Holding","CCOLA":"İçecek","AEFES":"İçecek",
    "ULKER":"Gıda","TATGD":"Gıda","GUBRF":"Gübre/Tarım","BAGFS":"Gübre/Tarım",
    "LOGO":"Teknoloji","ARENA":"Teknoloji","ALCTL":"Teknoloji",
    "OTKAR":"Savunma/Araç","BRISA":"Otomotiv Yan","KORDS":"Tekstil",
    "ATATP":"Finansal","ATAKP":"Finansal","ALTNY":"Madencilik",
    "ARTMS":"Madencilik","GESAN":"Enerji","TOASO":"Otomotiv","MPARK":"Sağlık",
    "TAVHL":"Havacılık","BERA":"İnşaat","GOLTS":"Madencilik","HEKTS":"İlaç",
    "KONYA":"Çimento","CIMSA":"Çimento","OYAKC":"Çimento","ISMEN":"Finans",
    "KLNMA":"Finans","RYSAS":"Lojistik","TKFEN":"Holding","TKNSA":"Teknoloji",
    "YATAS":"Ev Tekstili","TURSG":"Sigorta","AYES":"Enerji",
}

KOMISYON = 0.001  # %0.1

# ─────────────────────────────────────────────
#  Yardımcı: İlk İş Günleri
# ─────────────────────────────────────────────
def first_biz_days(start_year: int, start_month: int,
                   end_year: int, end_month: int) -> list:
    days = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        d = date(y, m, 1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        days.append(d)
        if m == 12:
            y += 1; m = 1
        else:
            m += 1
    return days

# ─────────────────────────────────────────────
#  Fiyat Verisi Cache
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_prices(tickers_is: tuple, start: str, end: str) -> pd.DataFrame:
    raw = yf.download(
        list(tickers_is), start=start, end=end,
        auto_adjust=True, progress=False, threads=True
    )
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw.xs("Close", axis=1, level=0)
    else:
        closes = raw[["Close"]] if "Close" in raw.columns else raw
    closes.columns = [c.replace(".IS","") for c in closes.columns]
    return closes

@st.cache_data(ttl=3600, show_spinner=False)
def get_bist100_prices(start: str, end: str) -> pd.Series:
    d = yf.download("XU100.IS", start=start, end=end,
                    auto_adjust=True, progress=False)
    if d.empty:
        return pd.Series(dtype=float)
    col = "Close" if "Close" in d.columns else d.columns[0]
    s = d[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s.squeeze()

# ─────────────────────────────────────────────
#  Teknik + Temel Skorlama (hızlı, geçmiş veriye dayalı)
# ─────────────────────────────────────────────
def quick_score_alfa(ticker: str, prices_df: pd.DataFrame,
                     as_of: date) -> float:
    col = ticker
    if col not in prices_df.columns:
        return 0
    sub = prices_df[col].dropna()
    sub = sub[sub.index.date <= as_of]
    if len(sub) < 60:
        return 0
    close = sub
    ema50 = close.ewm(span=50, adjust=False).mean()
    cur = float(close.iloc[-1])
    e50 = float(ema50.iloc[-1])
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    loss = (-delta).clip(lower=0).ewm(com=13, min_periods=14).mean()
    rsi = float(100 - 100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-9)))
    score = 0
    if cur > e50:          score += 30
    if 50 <= rsi <= 65:    score += 30
    elif 40 <= rsi < 50:   score += 15
    # Momentum (3 aylık getiri proxy)
    if len(sub) >= 63:
        ret3m = cur / float(sub.iloc[-63]) - 1
        if ret3m > 0.05:   score += 40
        elif ret3m > 0:    score += 20
    return score

def quick_score_beta(ticker: str, prices_df: pd.DataFrame,
                     as_of: date, bist_ret: float) -> float:
    col = ticker
    if col not in prices_df.columns:
        return 0
    sub = prices_df[col].dropna()
    sub = sub[sub.index.date <= as_of]
    if len(sub) < 30:
        return 0
    cur = float(sub.iloc[-1])
    ema20 = float(sub.ewm(span=20, adjust=False).mean().iloc[-1])
    score = 0
    if cur > ema20:   score += 25
    if len(sub) >= 252:
        ret1y = cur / float(sub.iloc[-252]) - 1
        rel = ret1y * 100 - bist_ret
        if rel > 10:   score += 50
        elif rel > 0:  score += 25
    if len(sub) >= 20:
        # Hacim proxy: fiyat oynaklığı yüksekse hacim de yüksektir
        std5  = float(sub.iloc[-5:].pct_change().std())
        std20 = float(sub.iloc[-20:].pct_change().std())
        if std20 > 0 and std5 >= std20 * 1.3:
            score += 25
    return score

def quick_score_delta(ticker: str, prices_df: pd.DataFrame,
                      as_of: date) -> float:
    col = ticker
    if col not in prices_df.columns:
        return 0
    sub = prices_df[col].dropna()
    sub = sub[sub.index.date <= as_of]
    if len(sub) < 60:
        return 0
    score = 0
    cur = float(sub.iloc[-1])
    # Düşük volatilite proxy olarak beta benzeri ölçüm
    ret = sub.pct_change().dropna()
    if len(ret) >= 60:
        vol = float(ret.iloc[-60:].std()) * np.sqrt(252)
        if vol < 0.35:   score += 40
        elif vol < 0.55: score += 20
    # Fibonacci yakınlığı
    h52 = float(sub.rolling(252).max().iloc[-1])
    l52 = float(sub.rolling(252).min().iloc[-1])
    diff = h52 - l52
    if diff > 0:
        fib382 = l52 + 0.382 * diff
        fib500 = l52 + 0.500 * diff
        tol = diff * 0.03
        if abs(cur - fib382) <= tol or abs(cur - fib500) <= tol:
            score += 60
    return score

# ─────────────────────────────────────────────
#  Backtest Motoru
# ─────────────────────────────────────────────
def run_backtest(start_year: int, start_month: int,
                 end_year: int, end_month: int,
                 baslangiç_sermaye: float,
                 strateji: str,
                 prices_df: pd.DataFrame,
                 bist_prices: pd.Series) -> dict:

    rebalance_dates = first_biz_days(start_year, start_month, end_year, end_month)
    # Son tarih
    end_date = first_biz_days(end_year, end_month,
                               end_year + (1 if end_month == 12 else 0),
                               1 if end_month == 12 else end_month + 1)[0]

    sermaye = baslangiç_sermaye
    portfoy = {}        # {ticker: adet}
    aylik_kayitlar = []
    islem_gecmisi = []

    def en_iyi_hisseler(as_of: date, n=5) -> list:
        bist_ret = 0
        if not bist_prices.empty and len(bist_prices) >= 252:
            sub_b = bist_prices[bist_prices.index.date <= as_of]
            if len(sub_b) >= 252:
                bist_ret = (float(sub_b.iloc[-1]) / float(sub_b.iloc[-252]) - 1) * 100
        scores = {}
        for t in BIST100:
            if t not in prices_df.columns:
                continue
            if strateji == "ALFA":
                s = quick_score_alfa(t, prices_df, as_of)
            elif strateji == "BETA":
                s = quick_score_beta(t, prices_df, as_of, bist_ret)
            else:
                s = quick_score_delta(t, prices_df, as_of)
            if s > 0:
                scores[t] = s
        return sorted(scores, key=scores.get, reverse=True)[:n]

    def guncel_fiyat(ticker: str, d: date) -> float:
        if ticker not in prices_df.columns:
            return 0
        sub = prices_df[ticker].dropna()
        sub = sub[sub.index.date <= d]
        return float(sub.iloc[-1]) if not sub.empty else 0

    # Başlangıç portföyü kur
    hedef = en_iyi_hisseler(rebalance_dates[0])
    if hedef and sermaye > 0:
        pay_basi = sermaye / len(hedef)
        for t in hedef:
            fp = guncel_fiyat(t, rebalance_dates[0])
            if fp > 0:
                adet = int(pay_basi * (1 - KOMISYON) / fp)
                if adet > 0:
                    maliyet = adet * fp * (1 + KOMISYON)
                    portfoy[t] = adet
                    sermaye -= maliyet
                    islem_gecmisi.append({
                        "Tarih": rebalance_dates[0].strftime("%Y-%m-%d"),
                        "İşlem": "ALIŞ",
                        "Hisse": t,
                        "Fiyat": round(fp, 2),
                        "Adet": adet,
                        "Tutar": round(maliyet, 2),
                    })

    for i in range(1, len(rebalance_dates)):
        ay_basi = rebalance_dates[i - 1]
        ay_sonu = rebalance_dates[i] - timedelta(days=1)

        # Ayın kapanışını hesapla
        portfoy_deger = sum(
            portfoy[t] * guncel_fiyat(t, ay_sonu)
            for t in portfoy
        )
        toplam = portfoy_deger + sermaye

        # Aylık getiri
        bist_ay_basi_fiyat = None
        bist_ay_sonu_fiyat = None
        if not bist_prices.empty:
            b_basi = bist_prices[bist_prices.index.date <= ay_basi]
            b_sonu = bist_prices[bist_prices.index.date <= ay_sonu]
            if not b_basi.empty: bist_ay_basi_fiyat = float(b_basi.iloc[-1])
            if not b_sonu.empty: bist_ay_sonu_fiyat = float(b_sonu.iloc[-1])

        bist_ay_getiri = (
            (bist_ay_sonu_fiyat / bist_ay_basi_fiyat - 1) * 100
            if bist_ay_basi_fiyat and bist_ay_sonu_fiyat else 0
        )

        hisse_getiriler = {}
        for t in portfoy:
            fp_basi = guncel_fiyat(t, ay_basi)
            fp_sonu = guncel_fiyat(t, ay_sonu)
            if fp_basi > 0:
                hisse_getiriler[t] = (fp_sonu / fp_basi - 1) * 100

        aylik_kayitlar.append({
            "Ay": ay_basi.strftime("%Y-%m"),
            "Portföy_TL": round(toplam, 2),
            "Ay_Getiri_Pct": round((toplam / baslangiç_sermaye - 1) * 100, 2) if i == 1 else None,
            "BIST100_Ay_Getiri": round(bist_ay_getiri, 2),
            "Hisseler": list(portfoy.keys()),
            "Hisse_Getirileri": hisse_getiriler,
        })

        # Rebalancing
        hedef_yeni = en_iyi_hisseler(rebalance_dates[i])
        çıkan = [t for t in portfoy if t not in hedef_yeni]
        giren = [t for t in hedef_yeni if t not in portfoy]

        for t in çıkan:
            fp = guncel_fiyat(t, rebalance_dates[i])
            if fp > 0:
                gelir = portfoy[t] * fp * (1 - KOMISYON)
                sermaye += gelir
                islem_gecmisi.append({
                    "Tarih": rebalance_dates[i].strftime("%Y-%m-%d"),
                    "İşlem": "SATIŞ",
                    "Hisse": t,
                    "Fiyat": round(fp, 2),
                    "Adet": portfoy[t],
                    "Tutar": round(gelir, 2),
                })
            del portfoy[t]

        kalan = [t for t in portfoy]
        pay_basi = sermaye / len(giren) if giren else 0
        for t in giren:
            fp = guncel_fiyat(t, rebalance_dates[i])
            if fp > 0 and pay_basi > 0:
                adet = int(pay_basi * (1 - KOMISYON) / fp)
                if adet > 0:
                    maliyet = adet * fp * (1 + KOMISYON)
                    portfoy[t] = adet
                    sermaye -= maliyet
                    islem_gecmisi.append({
                        "Tarih": rebalance_dates[i].strftime("%Y-%m-%d"),
                        "İşlem": "ALIŞ",
                        "Hisse": t,
                        "Fiyat": round(fp, 2),
                        "Adet": adet,
                        "Tutar": round(maliyet, 2),
                    })

    # Son değer
    son_tarih = rebalance_dates[-1]
    son_deger = sum(portfoy[t] * guncel_fiyat(t, son_tarih) for t in portfoy) + sermaye

    # Zaman serisi portföy değerleri
    portfoy_serisi = pd.Series(
        [r["Portföy_TL"] for r in aylik_kayitlar],
        index=pd.to_datetime([r["Ay"] for r in aylik_kayitlar])
    )

    return {
        "aylik": aylik_kayitlar,
        "islemler": islem_gecmisi,
        "son_deger": son_deger,
        "son_portfoy": list(portfoy.keys()),
        "portfoy_serisi": portfoy_serisi,
    }

# ─────────────────────────────────────────────
#  Performans Metrikleri
# ─────────────────────────────────────────────
def hesapla_metrikler(portfoy_serisi: pd.Series,
                      bist_prices: pd.Series,
                      baslangiç: float) -> dict:
    if portfoy_serisi.empty:
        return {}

    getiriler = portfoy_serisi.pct_change().dropna()

    # Sharpe (risksiz faiz %45 yıllık BIST ortamı için)
    rf_aylik = (1 + 0.45) ** (1/12) - 1
    fazla_getiri = getiriler - rf_aylik
    sharpe = (fazla_getiri.mean() / getiriler.std() * np.sqrt(12)
              if getiriler.std() > 0 else 0)

    # Maximum Drawdown
    kümülatif = (1 + getiriler).cumprod()
    tepe = kümülatif.cummax()
    drawdown = (kümülatif - tepe) / tepe
    max_dd = float(drawdown.min()) * 100

    # Toplam Getiri
    toplam_getiri = (portfoy_serisi.iloc[-1] / baslangiç - 1) * 100

    # BIST 100 karşılaştırma
    bist_getiri = 0
    if not bist_prices.empty:
        bist_sub = bist_prices[
            (bist_prices.index >= portfoy_serisi.index[0]) &
            (bist_prices.index <= portfoy_serisi.index[-1])
        ]
        if len(bist_sub) >= 2:
            bist_getiri = (float(bist_sub.iloc[-1]) / float(bist_sub.iloc[0]) - 1) * 100

    alfa = toplam_getiri - bist_getiri

    # Başarı oranı (pozitif ay)
    pozitif_aylar = (getiriler > 0).sum()
    basari_orani = pozitif_aylar / len(getiriler) * 100 if len(getiriler) > 0 else 0

    # Yıllık Getiri (CAGR)
    n_yil = len(getiriler) / 12
    cagr = ((portfoy_serisi.iloc[-1] / baslangiç) ** (1 / n_yil) - 1) * 100 if n_yil > 0 else 0

    return {
        "Toplam Getiri (%)":    round(toplam_getiri, 2),
        "BIST100 Getiri (%)":   round(bist_getiri, 2),
        "Alfa (%)":             round(alfa, 2),
        "CAGR (%)":             round(cagr, 2),
        "Sharpe Oranı":         round(sharpe, 3),
        "Max Drawdown (%)":     round(max_dd, 2),
        "Başarı Oranı (%)":     round(basari_orani, 2),
        "Toplam Ay":            len(getiriler),
        "Pozitif Ay":           int(pozitif_aylar),
    }

# ─────────────────────────────────────────────
#  Stres Testi
# ─────────────────────────────────────────────
def stres_testi(portfoy_serisi: pd.Series, bist_prices: pd.Series,
                esik_pct: float = -10.0) -> pd.DataFrame:
    if portfoy_serisi.empty or bist_prices.empty:
        return pd.DataFrame()

    bist_aylik = bist_prices.resample("MS").first().pct_change().dropna() * 100
    port_aylik  = portfoy_serisi.pct_change().dropna() * 100

    stres_aylar = bist_aylik[bist_aylik <= esik_pct]
    satirlar = []
    for dt, bist_ret in stres_aylar.items():
        port_ret = port_aylik.get(dt, np.nan)
        satirlar.append({
            "Ay":                 dt.strftime("%Y-%m"),
            "BIST100 (%)":        round(float(bist_ret), 2),
            "Portföy (%)":        round(float(port_ret), 2) if not np.isnan(port_ret) else "-",
            "Fark (pp)":          round(float(port_ret) - float(bist_ret), 2) if not np.isnan(port_ret) else "-",
            "Defansif mi?":       "✔ Evet" if not np.isnan(port_ret) and port_ret > bist_ret else "✘ Hayır",
        })
    return pd.DataFrame(satirlar)

# ─────────────────────────────────────────────
#  Hayalet Portföy (CSV)
# ─────────────────────────────────────────────
def yukle_referans_portfoy(dosya) -> pd.DataFrame:
    try:
        df = pd.read_csv(dosya)
        return df
    except Exception as e:
        st.error(f"CSV okunamadı: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────
#  Grafik Yardımcıları
# ─────────────────────────────────────────────
def ciz_portfoy_grafigi(portfoy_serisi: pd.Series,
                         bist_prices: pd.Series,
                         baslangiç: float,
                         strateji: str) -> go.Figure:
    fig = make_subplots(rows=2, cols=1,
                        row_heights=[0.7, 0.3],
                        shared_xaxes=True,
                        subplot_titles=["Portföy Değeri (TL)", "Aylık Getiri (%)"])

    fig.add_trace(go.Scatter(
        x=portfoy_serisi.index, y=portfoy_serisi.values,
        name=f"{strateji} Portföy", line=dict(color="#00d4aa", width=2.5)
    ), row=1, col=1)

    fig.add_hline(y=baslangiç, line_dash="dot",
                  line_color="gray", annotation_text="Başlangıç Sermayesi",
                  row=1, col=1)

    if not bist_prices.empty:
        b_sub = bist_prices[bist_prices.index >= portfoy_serisi.index[0]]
        if not b_sub.empty:
            b_endeks = b_sub / float(b_sub.iloc[0]) * baslangiç
            fig.add_trace(go.Scatter(
                x=b_endeks.index, y=b_endeks.values,
                name="BIST100 (Normalize)", line=dict(color="#ffa64d", width=1.8, dash="dash")
            ), row=1, col=1)

    ay_getiri = portfoy_serisi.pct_change().dropna() * 100
    renkler = ["#00d4aa" if v >= 0 else "#ff4b4b" for v in ay_getiri]
    fig.add_trace(go.Bar(
        x=ay_getiri.index, y=ay_getiri.values,
        name="Aylık Getiri", marker_color=renkler, showlegend=False
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=550,
        margin=dict(l=40, r=20, t=50, b=20),
        legend=dict(orientation="h", y=1.02),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
    )
    return fig

def ciz_drawdown(portfoy_serisi: pd.Series) -> go.Figure:
    getiriler = portfoy_serisi.pct_change().dropna()
    kümülatif = (1 + getiriler).cumprod()
    tepe = kümülatif.cummax()
    drawdown = (kümülatif - tepe) / tepe * 100

    fig = go.Figure(go.Scatter(
        x=drawdown.index, y=drawdown.values,
        fill="tozeroy", fillcolor="rgba(255,75,75,0.3)",
        line=dict(color="#ff4b4b", width=1.5),
        name="Drawdown (%)"
    ))
    fig.update_layout(
        template="plotly_dark", height=280,
        title="Maximum Drawdown",
        margin=dict(l=40, r=20, t=40, b=20),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
    )
    return fig

def ciz_sektor_dagilimi(hisseler: list) -> go.Figure:
    sektorler = {SEKTOR_MAP.get(t, "Diğer") for t in hisseler}
    sek_sayac = {}
    for t in hisseler:
        s = SEKTOR_MAP.get(t, "Diğer")
        sek_sayac[s] = sek_sayac.get(s, 0) + 1
    fig = px.pie(
        names=list(sek_sayac.keys()),
        values=list(sek_sayac.values()),
        color_discrete_sequence=px.colors.qualitative.Set3,
        title="Sektörel Dağılım"
    )
    fig.update_layout(
        template="plotly_dark", height=380,
        paper_bgcolor="#0e1117",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig

# ─────────────────────────────────────────────
#  STREAMLIT ARAYÜZ
# ─────────────────────────────────────────────
st.markdown('<div class="main-header">📊 BIST Backtest & Analiz Platformu</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">ALFA · BETA · DELTA Stratejileri | Aylık Rebalancing | Sanal Backtest · Stres Testi · Sektörel Analiz</div>', unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────
with st.sidebar:
    st.header("⚙️ Parametreler")
    strateji = st.selectbox("Strateji", ["ALFA", "BETA", "DELTA"])
    baslangiç_sermaye = st.number_input(
        "Başlangıç Sermayesi (TL)", min_value=10000,
        max_value=10_000_000, value=100_000, step=10_000)
    komisyon_pct = st.number_input(
        "Komisyon (%)", min_value=0.0, max_value=1.0,
        value=0.10, step=0.01, format="%.2f") / 100

    st.divider()
    st.subheader("📅 Backtest Dönemi")
    bugun = date.today()
    bas_yil  = st.number_input("Başlangıç Yılı",  min_value=2020, max_value=bugun.year, value=2023)
    bas_ay   = st.number_input("Başlangıç Ayı",   min_value=1, max_value=12, value=1)
    bit_yil  = st.number_input("Bitiş Yılı",       min_value=2020, max_value=bugun.year, value=bugun.year)
    bit_ay   = st.number_input("Bitiş Ayı",        min_value=1, max_value=12, value=bugun.month)

    st.divider()
    st.subheader("👻 Hayalet Portföy")
    csv_dosya = st.file_uploader(
        "YATIRIM 101 AYLAR.csv yükle", type=["csv"],
        help="Sütunlar: Ay, Hisse1, Hisse2, ... formatında")

    stres_esik = st.slider("Stres Eşiği (BIST % düşüş)", -30, -5, -10)

# ── Ana Panel: 3 Buton ───────────────────────
col_bt, col_st, col_sa = st.columns(3)

bt_tiklandi = col_bt.button("🚀 Sanal Backtest", use_container_width=True)
st_tiklandi = col_st.button("🔥 Stres Testi",    use_container_width=True)
sa_tiklandi = col_sa.button("🏭 Sektörel Dağılım", use_container_width=True)

# Oturum state ile aktif panel
if "panel" not in st.session_state:
    st.session_state.panel = "backtest"
if bt_tiklandi: st.session_state.panel = "backtest"
if st_tiklandi: st.session_state.panel = "stres"
if sa_tiklandi: st.session_state.panel = "sektor"

st.divider()

# ── Veri Yükleme ──────────────────────────────
start_str = f"{int(bas_yil)-1}-01-01"  # biraz öncesinden başla
end_str   = f"{int(bit_yil)+1}-01-01"

with st.spinner("Fiyat verileri indiriliyor (ilk açılış biraz sürebilir)..."):
    tickers_is = tuple(t + ".IS" for t in BIST100)
    prices_df  = get_prices(tickers_is, start_str, end_str)
    bist_prices = get_bist100_prices(start_str, end_str)

if prices_df.empty:
    st.error("Fiyat verisi alınamadı. İnternet bağlantısını kontrol edin.")
    st.stop()

# ── PANEL: SANAL BACKTEST ────────────────────
if st.session_state.panel == "backtest":
    st.subheader(f"🚀 Sanal Backtest — {strateji} Stratejisi")
    st.caption(f"Başlangıç: {bas_yil}/{bas_ay:02d}  →  Bitiş: {bit_yil}/{bit_ay:02d}  |  Sermaye: {baslangiç_sermaye:,.0f} TL  |  Komisyon: %{komisyon_pct*100:.2f}")

    with st.spinner("Backtest çalışıyor..."):
        sonuc = run_backtest(
            int(bas_yil), int(bas_ay), int(bit_yil), int(bit_ay),
            baslangiç_sermaye, strateji, prices_df, bist_prices
        )

    if not sonuc["aylik"]:
        st.warning("Yeterli veri yok. Dönemi genişletmeyi deneyin.")
        st.stop()

    metrikler = hesapla_metrikler(
        sonuc["portfoy_serisi"], bist_prices, baslangiç_sermaye)

    # Metrik kartları
    m_cols = st.columns(5)
    kart_data = [
        ("Toplam Getiri", f"%{metrikler.get('Toplam Getiri (%)',0):+.1f}",
         metrikler.get("Toplam Getiri (%)", 0) >= 0),
        ("vs BIST100 Alfa", f"%{metrikler.get('Alfa (%)',0):+.1f}",
         metrikler.get("Alfa (%)", 0) >= 0),
        ("CAGR", f"%{metrikler.get('CAGR (%)',0):.1f}", True),
        ("Sharpe", f"{metrikler.get('Sharpe Oranı',0):.2f}",
         metrikler.get("Sharpe Oranı", 0) >= 1),
        ("Max Drawdown", f"%{metrikler.get('Max Drawdown (%)',0):.1f}", False),
    ]
    for col, (label, val, pos) in zip(m_cols, kart_data):
        css = "pos" if pos else "neg"
        col.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:0.8rem;color:#aaa">{label}</div>'
            f'<div class="metric-val {css}">{val}</div>'
            f'</div>', unsafe_allow_html=True)

    st.markdown("")

    # Ana grafik
    fig_main = ciz_portfoy_grafigi(
        sonuc["portfoy_serisi"], bist_prices, baslangiç_sermaye, strateji)
    st.plotly_chart(fig_main, use_container_width=True)

    # Drawdown
    st.plotly_chart(
        ciz_drawdown(sonuc["portfoy_serisi"]), use_container_width=True)

    # Aylık tablo
    with st.expander("📋 Aylık Detay Tablosu"):
        rows = []
        prev_val = baslangiç_sermaye
        for r in sonuc["aylik"]:
            curr_val = r["Portföy_TL"]
            ay_get = (curr_val / prev_val - 1) * 100 if prev_val > 0 else 0
            prev_val = curr_val
            rows.append({
                "Ay":              r["Ay"],
                "Portföy (TL)":    f"{curr_val:,.0f}",
                "Ay Getiri (%)":   f"{ay_get:+.2f}",
                "BIST100 (%)":     f"{r['BIST100_Ay_Getiri']:+.2f}",
                "Fark (pp)":       f"{ay_get - r['BIST100_Ay_Getiri']:+.2f}",
                "Hisseler":        ", ".join(r["Hisseler"]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=350)

    # İşlem geçmişi
    with st.expander("🔄 İşlem Geçmişi (Alış/Satış)"):
        if sonuc["islemler"]:
            st.dataframe(pd.DataFrame(sonuc["islemler"]),
                         use_container_width=True, height=300)
        else:
            st.info("İşlem kaydı bulunamadı.")

    # Hayalet portföy karşılaştırması
    if csv_dosya:
        st.subheader("👻 Hayalet Portföy Karşılaştırması")
        ref_df = yukle_referans_portfoy(csv_dosya)
        if not ref_df.empty:
            st.dataframe(ref_df.head(30), use_container_width=True)

            # Korelasyon: AI seçimleri vs referans
            ai_hisseler_set = set()
            for r in sonuc["aylik"]:
                ai_hisseler_set.update(r["Hisseler"])

            ref_hisseler_set = set()
            for col in ref_df.columns:
                if col.lower() != "ay":
                    ref_hisseler_set.update(
                        ref_df[col].dropna().str.upper().tolist())

            ortak = ai_hisseler_set & ref_hisseler_set
            benzerlik = len(ortak) / len(ai_hisseler_set | ref_hisseler_set) * 100 if ai_hisseler_set | ref_hisseler_set else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("AI Seçimi",        len(ai_hisseler_set))
            c2.metric("Referans Seçimi",   len(ref_hisseler_set))
            c3.metric("Örtüşme (Jaccard)", f"%{benzerlik:.1f}")

            if ortak:
                st.success(f"Ortak hisseler: {', '.join(sorted(ortak))}")
            if benzerlik < 30:
                st.warning(
                    "AI seçimleri referanstan %70'den fazla sapıyor. "
                    "Fine-tune önerisi: Momentum eşiğini düşür veya "
                    "sektör kısıtı ekle.")

# ── PANEL: STRES TESTİ ───────────────────────
elif st.session_state.panel == "stres":
    st.subheader("🔥 Stres Testi — Endeks Düştüğünde Ne Oldu?")
    st.caption(f"BIST100 aylık getirisi ≤ %{stres_esik} olan aylar analiz ediliyor")

    with st.spinner("Backtest ve stres analizi çalışıyor..."):
        sonuc = run_backtest(
            int(bas_yil), int(bas_ay), int(bit_yil), int(bit_ay),
            baslangiç_sermaye, strateji, prices_df, bist_prices
        )
        stres_df = stres_testi(sonuc["portfoy_serisi"], bist_prices, stres_esik)

    if stres_df.empty:
        st.info(f"Seçilen dönemde BIST100'ün %{abs(stres_esik)}'den fazla düştüğü ay bulunamadı.")
    else:
        defansif_sayi = (stres_df["Defansif mi?"] == "✔ Evet").sum()
        toplam = len(stres_df)

        c1, c2, c3 = st.columns(3)
        c1.metric("Stres Ayı Sayısı", toplam)
        c2.metric("Defansif Kalan Ay", defansif_sayi)
        c3.metric("Defansif Başarı",   f"%{defansif_sayi/toplam*100:.0f}")

        st.dataframe(
            stres_df.style.applymap(
                lambda v: "color: #00d4aa" if v == "✔ Evet"
                else ("color: #ff4b4b" if v == "✘ Hayır" else ""),
                subset=["Defansif mi?"]
            ),
            use_container_width=True, height=350
        )

        # Bar grafik karşılaştırma
        fig_stres = go.Figure()
        fig_stres.add_trace(go.Bar(
            name="BIST100 (%)", x=stres_df["Ay"],
            y=stres_df["BIST100 (%)"].astype(float),
            marker_color="#ff4b4b"
        ))
        numeric_port = pd.to_numeric(stres_df["Portföy (%)"], errors="coerce")
        fig_stres.add_trace(go.Bar(
            name="Portföy (%)", x=stres_df["Ay"],
            y=numeric_port,
            marker_color="#00d4aa"
        ))
        fig_stres.update_layout(
            barmode="group", template="plotly_dark", height=380,
            title="Stres Aylarında BIST100 vs Portföy",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            margin=dict(l=40, r=20, t=50, b=20),
        )
        st.plotly_chart(fig_stres, use_container_width=True)

        st.info(
            f"**Yorum:** {strateji} stratejisi, endeksin sert düştüğü "
            f"{toplam} ayın {defansif_sayi} tanesinde endeksten daha az kayıp yaşadı. "
            f"Defansif koruma oranı: **%{defansif_sayi/toplam*100:.0f}**"
        )

# ── PANEL: SEKTÖREL DAGILIM ──────────────────
elif st.session_state.panel == "sektor":
    st.subheader("🏭 Sektörel Dağılım Analizi")
    st.caption("Backtest boyunca portföyde yer alan hisselerin sektörel analizi")

    with st.spinner("Backtest çalışıyor..."):
        sonuc = run_backtest(
            int(bas_yil), int(bas_ay), int(bit_yil), int(bit_ay),
            baslangiç_sermaye, strateji, prices_df, bist_prices
        )

    # Tüm hisseler ve görünme sıklıkları
    hisse_sayi = {}
    hisse_getiri_toplam = {}
    hisse_ay_sayi = {}
    prev_val = baslangiç_sermaye

    for r in sonuc["aylik"]:
        curr_val = r["Portföy_TL"]
        ay_get = (curr_val / prev_val - 1) if prev_val > 0 else 0
        prev_val = curr_val
        for t in r["Hisseler"]:
            hisse_sayi[t] = hisse_sayi.get(t, 0) + 1
            hg = r["Hisse_Getirileri"].get(t, 0)
            hisse_getiri_toplam[t] = hisse_getiri_toplam.get(t, 0) + hg
            hisse_ay_sayi[t] = hisse_ay_sayi.get(t, 0) + 1

    tum_hisseler = list(hisse_sayi.keys())

    col_pie, col_bar = st.columns([1, 1])
    with col_pie:
        fig_pie = ciz_sektor_dagilimi(tum_hisseler)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_bar:
        ort_getiriler = {
            t: hisse_getiri_toplam[t] / hisse_ay_sayi[t] * 100
            for t in tum_hisseler if hisse_ay_sayi.get(t, 0) > 0
        }
        sıralı = sorted(ort_getiriler.items(), key=lambda x: x[1], reverse=True)
        hisse_listesi = [x[0] for x in sıralı]
        getiri_listesi = [x[1] for x in sıralı]
        renkler = ["#00d4aa" if g >= 0 else "#ff4b4b" for g in getiri_listesi]

        fig_bar = go.Figure(go.Bar(
            x=hisse_listesi, y=getiri_listesi,
            marker_color=renkler,
            text=[f"{g:.1f}%" for g in getiri_listesi],
            textposition="outside"
        ))
        fig_bar.update_layout(
            template="plotly_dark", height=380,
            title="Hisse Bazlı Ortalama Aylık Getiri (%)",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            margin=dict(l=20, r=20, t=50, b=60),
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # Sektör başarı tablosu
    sek_getiri = {}
    sek_sayi = {}
    for t, g in ort_getiriler.items():
        sek = SEKTOR_MAP.get(t, "Diğer")
        sek_getiri[sek] = sek_getiri.get(sek, 0) + g
        sek_sayi[sek]   = sek_sayi.get(sek, 0) + 1

    sek_ort = {s: sek_getiri[s] / sek_sayi[s] for s in sek_getiri}
    sek_df = pd.DataFrame([
        {"Sektör": s, "Ort. Aylık Getiri (%)": round(g, 2),
         "Hisse Adedi": sek_sayi[s]}
        for s, g in sorted(sek_ort.items(), key=lambda x: x[1], reverse=True)
    ])

    st.subheader("Sektör Bazlı Performans")
    st.dataframe(sek_df, use_container_width=True, height=320)

    en_iyi = sek_df.iloc[0]["Sektör"] if not sek_df.empty else "-"
    st.success(
        f"**{strateji} stratejisinde en başarılı sektör: {en_iyi}**  "
        f"— Bu sektördeki hisseleri önceliklendirerek filtre kriterlerini sektöre özel ince ayar yapabilirsiniz."
    )

st.divider()
st.caption("Veri kaynağı: Yahoo Finance · Gecikmeli veri · Yatırım tavsiyesi değildir.")
