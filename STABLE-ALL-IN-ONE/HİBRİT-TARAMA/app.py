#!/usr/bin/env python3
"""
HİBRİT TARAMA — USA Odaklı  (hızlı batch indirme)
Mark Minervini RS/SEPA  +  QuantumScan Teknik skoru
Port: 8507 (dev) / 8607 (stable)
"""
import sys, os, warnings, logging
warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

MM_DIR = "/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"
QS_DIR = "/Users/hakanficicilar/Documents/Aİ/EMERGENT/backend"
sys.path.insert(0, MM_DIR)
sys.path.insert(0, QS_DIR)

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import json, io
from datetime import datetime, timedelta, date
import plotly.graph_objects as go

st.set_page_config(page_title="Hibrit Tarama — USA", page_icon="⚡",
                   layout="wide", initial_sidebar_state="collapsed")

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "hibrit_history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f: return json.load(f)
        except: pass
    return {"scans": [], "backtests": []}

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, ensure_ascii=False, indent=2, default=str)

try:
    from universal_scanner import UniversalStockScanner
    _MM_OK = True
except Exception as e:
    _MM_OK = False; _MM_ERR = str(e)

try:
    from app.signals import compute_technical_signals
    _QS_OK = True
except Exception as e:
    _QS_OK = False; _QS_ERR = str(e)

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container{padding-top:1rem}
.kpi-box{background:linear-gradient(135deg,#0f1520,#1a2235);border:1px solid #2a3a5c;
 border-radius:12px;padding:18px;text-align:center}
.kpi-val{font-size:2rem;font-weight:800;font-family:monospace}
.kpi-lbl{font-size:.7rem;text-transform:uppercase;color:#6a7a9a;letter-spacing:.1em;margin-top:6px}
</style>""", unsafe_allow_html=True)

st.markdown("## ⚡ Hibrit Tarama — USA")
st.markdown("**Mark Minervini RS** × **QuantumScan Teknik** — iki sistemin güçlü yanlarını birleştir")

if not _MM_OK: st.error(f"MM Scanner: {_MM_ERR}")
if not _QS_OK: st.error(f"QS Signals: {_QS_ERR}")
if not (_MM_OK and _QS_OK): st.stop()

# ── Batch veri indirme ────────────────────────────────────────
def _flatten_cols(df, lowercase=False):
    """MultiIndex veya tuple sutunlari duz stringe cevir."""
    new_cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            new_cols.append(str(col[0]))
        else:
            new_cols.append(str(col))
    df.columns = new_cols
    if lowercase:
        df.columns = [c.lower() for c in df.columns]
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def batch_download(tickers: tuple, start: str, end: str) -> dict:
    """Tum hisseleri tek seferde indir -> {ticker: DataFrame}"""
    try:
        raw = yf.download(list(tickers), start=start, end=end,
                          progress=False, auto_adjust=True, group_by="ticker")
        out = {}
        if len(tickers) == 1:
            tk = tickers[0]
            df = _flatten_cols(raw.copy(), lowercase=True)
            if len(df) >= 30:
                out[tk] = df
        else:
            for tk in tickers:
                try:
                    df = raw[tk].dropna(how="all").copy()
                    df = _flatten_cols(df, lowercase=True)
                    if len(df) >= 30:
                        out[tk] = df
                except: pass
        return out
    except:
        return {}

@st.cache_data(ttl=3600, show_spinner=False)
def get_spy(start: str, end: str):
    df = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
    return _flatten_cols(df, lowercase=True)

# ── Tek hisse hibrit skor ────────────────────────────────────
def score_one(ticker, price_df, spy_df, mm_weight, qs_weight, min_rs, scanner):
    """MM filtresi once calis; gecerse QS hesapla. Boylece yavaslatmaz."""
    try:
        mm = scanner.scan_us_stock(ticker, spy_df, as_of_date=None,
                                   stock_data=price_df)
        if not mm: return None  # scan_us_stock None donerse filtreden gecmedi
        mm_rs = float(mm.get("RS", mm.get("rs_score", 0)))  # RS anahtari
        if mm_rs < min_rs: return None

        # QS sadece MM filtresi gecenler icin - performans
        if qs_weight > 0:
            # QS lowercase sutun bekliyor, MM Title Case - donustur
            qs_df = price_df.copy()
            qs_df.columns = [col.lower() for col in qs_df.columns]
            qs = compute_technical_signals(qs_df)
            qs_tech = float(qs.get("tech_score", 0))
        else:
            qs = {}
            qs_tech = 0.0

        return {
            "ticker":     ticker,
            "mm_rs":      round(mm_rs, 1),
            "qs_tech":    round(qs_tech, 1),
            "hybrid":     round(mm_weight * mm_rs + qs_weight * qs_tech, 1),
            "price":      round(float(mm.get("Price", mm.get("price", 0))), 2),
            "breakout":   round(float(qs.get("breakout", 0)), 1),
            "momentum":   round(float(qs.get("momentum", 0)), 1),
            "money_flow": round(float(qs.get("money_flow", 0)), 1),
            "trend":      round(float(qs.get("trend", 0)), 1),
        }
    except:
        return None

# ════════════════════════════════════════════════════════════
tab_scan, tab_bt, tab_hist = st.tabs(["🔍 Tarama", "📈 Backtest", "📋 Geçmiş"])

# ════════════════════════════════════════════════════════════
# TARAMA
# ════════════════════════════════════════════════════════════
with tab_scan:
    cl, cr = st.columns([1, 3])
    with cl:
        st.markdown("#### Ayarlar")
        sc_today = st.checkbox("Bugün", value=True, key="sc_today")
        sc_date  = st.date_input("Tarama Tarihi", value=date.today()-timedelta(1),
                                  max_value=date.today(), key="sc_dt", disabled=sc_today)
        if sc_today: sc_date = date.today() - timedelta(1)

        universe = st.selectbox("Evren", ["Nasdaq 100", "S&P 500 (ilk 200)", "Özel Liste"], key="sc_univ")
        custom_tickers = ""
        if universe == "Özel Liste":
            custom_tickers = st.text_area("Ticker (virgülle)", "AAPL, NVDA, MSFT", key="sc_cust")

        mm_w_sc = st.slider("MM RS Ağırlığı (%)", 0, 100, 50, key="sc_mmw") / 100
        qs_w_sc = 1 - mm_w_sc
        st.caption(f"MM: %{int(mm_w_sc*100)} · QS: %{int(qs_w_sc*100)}")
        min_rs_sc = st.slider("Min RS", 0, 100, 65, key="sc_minrs")
        top_n_sc  = st.number_input("Top N", 5, 50, 10, key="sc_topn")
        run_sc    = st.button("🔍 Taramayı Başlat", use_container_width=True,
                               type="primary", key="run_sc")

    with cr:
        if run_sc:
            scanner = UniversalStockScanner()
            as_of   = sc_date.strftime("%Y-%m-%d")
            data_start = (sc_date - timedelta(days=400)).strftime("%Y-%m-%d")

            if universe == "Nasdaq 100":
                tickers = tuple(scanner.us_tickers[:150])
            elif universe == "S&P 500 (ilk 200)":
                tickers = tuple(scanner.us_tickers[:200])
            else:
                tickers = tuple(t.strip().upper() for t in custom_tickers.split(",") if t.strip())

            with st.spinner(f"📥 {len(tickers)} hisse indiriliyor (tek seferde)..."):
                price_cache = batch_download(tickers, data_start, as_of)
                spy_df      = get_spy(data_start, as_of)

            results = []
            prog = st.progress(0, text="Skorlar hesaplanıyor...")
            for i, tk in enumerate(tickers):
                prog.progress((i+1)/len(tickers), text=f"Skorlanıyor: {tk}")
                df = price_cache.get(tk)
                if df is None: continue
                r = score_one(tk, df, spy_df, mm_w_sc, qs_w_sc, min_rs_sc, scanner)
                if r: results.append(r)
            prog.empty()

            results.sort(key=lambda x: -x["hybrid"])
            results = results[:int(top_n_sc)]

            h = load_history()
            h["scans"].insert(0, {"date": as_of, "ran_at": datetime.now().isoformat(),
                                   "universe": universe, "mm_weight": mm_w_sc,
                                   "qs_weight": qs_w_sc, "min_rs": min_rs_sc,
                                   "results": results})
            save_history(h)
            st.session_state["last_scan"] = results
            st.success(f"✅ {len(results)} hisse bulundu")

        results = st.session_state.get("last_scan", [])
        if results:
            tbl = [{"Ticker": r["ticker"], "Fiyat": f"${r['price']}",
                    "Hibrit": r["hybrid"], "MM RS": r["mm_rs"],
                    "QS Teknik": r["qs_tech"], "Breakout": r["breakout"],
                    "Momentum": r["momentum"], "Para Akışı": r["money_flow"],
                    "Trend": r["trend"]} for r in results]
            df_sc = pd.DataFrame(tbl)
            st.dataframe(
                df_sc.style.background_gradient(
                    subset=["Hibrit","MM RS","QS Teknik"], cmap="RdYlGn", vmin=0, vmax=100),
                use_container_width=True, hide_index=True)

            tks  = [r["ticker"]  for r in results]
            fig  = go.Figure()
            fig.add_bar(name="MM RS",     x=tks, y=[r["mm_rs"]   for r in results],
                        marker_color="#f97316", opacity=0.7)
            fig.add_bar(name="QS Teknik", x=tks, y=[r["qs_tech"] for r in results],
                        marker_color="#60a5fa", opacity=0.7)
            fig.add_scatter(name="Hibrit", x=tks, y=[r["hybrid"] for r in results],
                            mode="lines+markers",
                            line=dict(color="#4ade80", width=2.5), marker=dict(size=8))
            fig.update_layout(barmode="group", height=320,
                              paper_bgcolor="#0a0e17", plot_bgcolor="#0a0e17",
                              font=dict(color="#aaa"), margin=dict(l=40,r=20,t=20,b=40),
                              legend=dict(bgcolor="#0a0e17"),
                              yaxis=dict(range=[0,110], gridcolor="#1a2235"),
                              xaxis=dict(gridcolor="#1a2235"))
            st.plotly_chart(fig, use_container_width=True)
        elif not run_sc:
            st.info("⬅️ Sol panelden parametreleri ayarlayıp 'Taramayı Başlat' butonuna tıklayın.")

# ════════════════════════════════════════════════════════════
# BACKTEST
# ════════════════════════════════════════════════════════════
with tab_bt:
    st.markdown("#### Hibrit Backtest — USA")
    c1, c2, c3 = st.columns(3)
    with c1:
        bt_start = st.date_input("Başlangıç", value=date(2026,1,1), key="hbt_s")
        bt_end   = st.date_input("Bitiş",     value=date.today(),   key="hbt_e")
    with c2:
        bt_freq  = st.selectbox("Rebalance", ["15 Gün","Aylık","2 Aylık","3 Aylık"], key="hbt_f")
        bt_n     = st.number_input("Portföy Büyüklüğü", 1, 15, 5, key="hbt_n")
    with c3:
        bt_mmw   = st.slider("MM RS Ağırlığı (%)", 0, 100, 50, key="bt_mmw") / 100
        bt_qsw   = 1 - bt_mmw
        st.caption(f"MM: %{int(bt_mmw*100)} · QS: %{int(bt_qsw*100)}")
        bt_minrs = st.slider("Min RS", 0, 100, 55, key="bt_minrs")
        bt_univ  = st.selectbox("Evren", ["Nasdaq 100","S&P 500 (ilk 200)"], key="bt_univ")
        bt_cap   = st.number_input("Sermaye ($)", 10000, 10_000_000, 100000, 10000, key="bt_cap")

    run_bt = st.button("🚀 Backtest Başlat", use_container_width=True,
                        type="primary", key="run_bt")

    if run_bt:
        freq_map  = {"15 Gün":15,"Aylık":30,"2 Aylık":60,"3 Aylık":90}
        freq_days = freq_map[bt_freq]
        start_str = bt_start.strftime("%Y-%m-%d")
        end_str   = bt_end.strftime("%Y-%m-%d")
        data_start = (bt_start - timedelta(days=400)).strftime("%Y-%m-%d")

        rebalance_dates = []
        cur = bt_start
        while cur <= bt_end:
            rebalance_dates.append(cur)
            cur += timedelta(days=freq_days)

        scanner = UniversalStockScanner()
        if bt_univ == "Nasdaq 100":
            universe_tickers = tuple(scanner.us_tickers[:150])
        else:
            universe_tickers = tuple(scanner.us_tickers[:200])

        # ── Tüm veriyi tek seferde indir ──
        with st.spinner(f"📥 {len(universe_tickers)+1} hisse verisi indiriliyor (bir kez)..."):
            price_cache = batch_download(universe_tickers, data_start, end_str)
            spy_df      = get_spy(data_start, end_str)
        st.success(f"✅ {len(price_cache)} hisse verisi hazır. Backtest hesaplanıyor...")

        capital = float(bt_cap)
        equity_curve, periods = [], []
        prog = st.progress(0, "Dönemler hesaplanıyor...")

        for i, rb_date in enumerate(rebalance_dates[:-1]):
            next_rb  = rebalance_dates[i+1]
            rb_str   = rb_date.strftime("%Y-%m-%d")
            next_str = next_rb.strftime("%Y-%m-%d")
            prog.progress((i+1)/max(len(rebalance_dates)-1,1),
                           text=f"Dönem {i+1}/{len(rebalance_dates)-1}: {rb_str}")

            # O dönem için spy ve fiyat verisini kes
            spy_slice = spy_df[spy_df.index <= rb_str]

            cands = []
            for tk in universe_tickers:
                df_all = price_cache.get(tk)
                if df_all is None: continue
                df_slice = df_all[df_all.index <= rb_str]
                if len(df_slice) < 60: continue
                r = score_one(tk, df_slice, spy_slice, bt_mmw, bt_qsw, bt_minrs, scanner)
                if r: cands.append(r)

            cands.sort(key=lambda x: -x["hybrid"])
            sel = cands[:int(bt_n)]
            sel_tickers = [s["ticker"] for s in sel]

            if not sel_tickers:
                equity_curve.append({"date": rb_str, "equity": capital})
                continue

            w = 1.0 / len(sel_tickers)
            period_ret = 0.0
            for tk in sel_tickers:
                df_all = price_cache.get(tk)
                if df_all is None: continue
                df_p = df_all[(df_all.index >= rb_str) & (df_all.index <= next_str)]
                if len(df_p) >= 2:
                    p0 = float(df_p["close"].iloc[0])
                    p1 = float(df_p["close"].iloc[-1])
                    if p0 > 0:
                        period_ret += w * (p1/p0 - 1)

            capital = capital * (1 + period_ret)
            equity_curve.append({"date": rb_str, "equity": capital})
            periods.append({
                "date": rb_str, "tickers": sel_tickers,
                "hyb_scores": [s["hybrid"] for s in sel],
                "mm_scores":  [s["mm_rs"]  for s in sel],
                "qs_scores":  [s["qs_tech"] for s in sel],
                "ret_pct":    round(period_ret*100, 2),
                "equity":     round(capital, 2),
            })

        prog.empty()

        # Benchmark
        try:
            spy_slice = spy_df[(spy_df.index >= start_str) & (spy_df.index <= end_str)]
            bm_ret = float(spy_slice["close"].iloc[-1]/spy_slice["close"].iloc[0] - 1) * 100
        except: bm_ret = 0.0

        total_ret = (capital/bt_cap - 1)*100
        alpha     = total_ret - bm_ret

        # KPI
        k1,k2,k3,k4 = st.columns(4)
        for col, val, lbl, clr in [
            (k1, f"%{total_ret:+.1f}", "Toplam Getiri",  "#4ade80" if total_ret>0 else "#f87171"),
            (k2, f"%{bm_ret:+.1f}",   "SPY Benchmark",  "#60a5fa"),
            (k3, f"%{alpha:+.1f}",    "Alpha (vs SPY)", "#fbbf24" if alpha>0 else "#f87171"),
            (k4, f"${capital:,.0f}",  "Final Değer",    "#a78bfa"),
        ]:
            col.markdown(f'<div class="kpi-box"><div class="kpi-val" style="color:{clr}">{val}</div>'
                         f'<div class="kpi-lbl">{lbl}</div></div>', unsafe_allow_html=True)
        st.markdown("")

        # Equity curve
        if equity_curve:
            eq_df = pd.DataFrame(equity_curve)
            fig = go.Figure()
            try:
                spy_bm = spy_df[(spy_df.index >= start_str) & (spy_df.index <= end_str)]
                spy_norm = (spy_bm["close"] / spy_bm["close"].iloc[0]) * bt_cap
                fig.add_scatter(x=[str(d)[:10] for d in spy_bm.index],
                                y=spy_norm.values,
                                name="SPY", line=dict(color="#60a5fa", width=1.5, dash="dash"))
            except: pass
            fig.add_scatter(x=eq_df["date"], y=eq_df["equity"],
                            name="Hibrit Portföy", mode="lines+markers",
                            line=dict(color="#4ade80", width=2.5),
                            fill="tozeroy", fillcolor="rgba(74,222,128,0.07)")
            fig.add_hline(y=bt_cap, line_dash="dot", line_color="#555", opacity=0.5)
            fig.update_layout(height=340, paper_bgcolor="#0a0e17", plot_bgcolor="#0a0e17",
                              font=dict(color="#aaa",size=11), margin=dict(l=50,r=20,t=30,b=30),
                              yaxis=dict(tickformat="$,.0f", gridcolor="#1a2235"),
                              xaxis=dict(gridcolor="#1a2235"),
                              legend=dict(bgcolor="#0a0e17"))
            st.plotly_chart(fig, use_container_width=True)

        # Dönem tablosu
        if periods:
            st.markdown("##### 📋 Rebalance Geçmişi")
            rows = []
            for p in periods:
                pairs = [f"{t}({h:.0f})" for t,h in zip(p["tickers"],p["hyb_scores"])]
                rows.append({"Tarih": p["date"],
                             "Hisseler (Hibrit Skor)": " · ".join(pairs),
                             "Dönem %": f"%{p['ret_pct']:+.2f}",
                             "Sermaye": f"${p['equity']:,.0f}"})
            df_p = pd.DataFrame(rows)
            st.dataframe(df_p, use_container_width=True, hide_index=True)

            buf = io.BytesIO()
            df_p.to_excel(buf, index=False, engine="openpyxl")
            st.download_button("📥 Excel İndir", buf.getvalue(), "hibrit_backtest.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        h = load_history()
        h["backtests"].insert(0, {
            "ran_at": datetime.now().isoformat(),
            "start": start_str, "end": end_str, "freq": bt_freq,
            "n": int(bt_n), "mm_w": bt_mmw, "qs_w": bt_qsw,
            "universe": bt_univ, "min_rs": bt_minrs,
            "total_ret": round(total_ret,2), "bm_ret": round(bm_ret,2),
            "alpha": round(alpha,2), "final": round(capital,2), "periods": periods,
        })
        save_history(h)

# ════════════════════════════════════════════════════════════
# GEÇMİŞ
# ════════════════════════════════════════════════════════════
with tab_hist:
    h = load_history()
    gc, gb = st.columns(2)
    with gc:
        st.markdown("#### 📋 Tarama Geçmişi")
        for i, sc in enumerate(h.get("scans",[])[:20]):
            label = f"📅 {sc['date']} | {sc['universe']} | MM:{int(sc['mm_weight']*100)}% | {len(sc['results'])} hisse"
            with st.expander(label):
                rows = [{"Ticker":r["ticker"],"Hibrit":r["hybrid"],
                         "MM RS":r["mm_rs"],"QS":r["qs_tech"],"Fiyat":r["price"]}
                        for r in sc["results"]]
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                if st.button("🗑️ Sil", key=f"dsc_{i}"):
                    h["scans"].pop(i); save_history(h); st.rerun()
    with gb:
        st.markdown("#### 📈 Backtest Geçmişi")
        for i, bt in enumerate(h.get("backtests",[])[:20]):
            clr = "🟢" if bt.get("total_ret",0)>0 else "🔴"
            label = (f"{clr} {bt['start']}→{bt['end']} | {bt['freq']} | "
                     f"N={bt['n']} MM:{int(bt['mm_w']*100)}% | "
                     f"%{bt['total_ret']:+.1f} α:{bt['alpha']:+.1f}")
            with st.expander(label):
                st.markdown(f"**Toplam:** %{bt['total_ret']:+.2f} | **SPY:** %{bt['bm_ret']:+.2f} | "
                            f"**Alpha:** %{bt['alpha']:+.2f} | **Final:** ${bt['final']:,.0f}")
                for p in bt.get("periods",[]):
                    st.markdown(f"- `{p['date']}` → {', '.join(p['tickers'])} → **%{p['ret_pct']:+.2f}**")
                if st.button("🗑️ Sil", key=f"dbt_{i}"):
                    h["backtests"].pop(i); save_history(h); st.rerun()
