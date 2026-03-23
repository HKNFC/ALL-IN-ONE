import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from scan_history import load_history, add_scan_record, delete_record, clear_all

st.set_page_config(
    page_title="BIST & USA Hisse Tarayıcı",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1f77b4; margin-bottom: 0.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 24px; border-radius: 6px 6px 0 0; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">BIST & USA Hisse Tarayıcı + Backtest</div>', unsafe_allow_html=True)
st.markdown("**BIST:** Hacim & Trend Takibi &nbsp;|&nbsp; **USA:** Momentum & Kurumsal Güç")
st.divider()

tab_screener, tab_backtest, tab_history = st.tabs(["Tarayıcı", "Backtest", "Tarama Geçmişi"])


# ─── SCREENER TAB ─────────────────────────────────────────────────────────────
with tab_screener:
    col_left, col_right = st.columns([1, 3])

    with col_left:
        st.subheader("Borsa & Endeks")
        market_choice = st.selectbox("Borsa", ["BIST", "USA", "Her İkisi"])
        bist_index_choice = None
        if market_choice in ["BIST", "Her İkisi"]:
            bist_index_choice = st.selectbox(
                "BIST Endeksi",
                ["BIST 50", "BIST 100", "BIST TÜM", "BIST 100 Dışı"],
                index=1,
            )

        # ── BIST parametreleri ────────────────────────────────────────
        if market_choice in ["BIST", "Her İkisi"]:
            st.markdown("---")
            st.markdown("**BIST Filtre Eşikleri**")
            bist_mfi_min = st.slider("MFI Alt Sınır", 20, 60, 50, key="bist_mfi_min")
            bist_mfi_max = st.slider("MFI Üst Sınır", 60, 95, 80, key="bist_mfi_max")
            bist_vol_mult = st.slider("Hacim Çarpanı (×ort)", 1.0, 3.0, 1.3, 0.1, key="bist_vol")
            bist_div_lookback = st.slider("Uyuşmazlık Lookback (bar)", 5, 30, 15, key="bist_div_lb")
            bist_use_div = st.checkbox("Uyuşmazlık filtresi", value=True, key="bist_use_div")

        # ── USA parametreleri ─────────────────────────────────────────
        if market_choice in ["USA", "Her İkisi"]:
            st.markdown("---")
            st.markdown("**USA Filtre Eşikleri**")
            usa_rsi_min = st.slider("RSI Alt Sınır", 40, 75, 60, key="usa_rsi")
            usa_adx_min = st.slider("ADX Alt Sınır", 15, 40, 25, key="usa_adx")
            usa_use_bb = st.checkbox("BB Daralması (VCP)", value=True, key="usa_bb")
            usa_use_div = st.checkbox("MFI Uyuşmazlığı", value=True, key="usa_div")

        st.markdown("---")
        run_btn = st.button("Tara", type="primary", use_container_width=True)

    with col_right:
        if run_btn:
            from screener import screen_bist, screen_usa
            from stock_lists import BIST_INDEX_MAP

            bist_results = pd.DataFrame()
            usa_results = pd.DataFrame()
            bist_stats = {}
            usa_stats = {}

            bist_params = {}
            usa_params = {}
            if market_choice in ["BIST", "Her İkisi"]:
                bist_params = {
                    "mfi_min": bist_mfi_min,
                    "mfi_max": bist_mfi_max,
                    "vol_mult": bist_vol_mult,
                    "div_lookback": bist_div_lookback,
                    "use_divergence": bist_use_div,
                }
            if market_choice in ["USA", "Her İkisi"]:
                usa_params = {
                    "rsi_min": usa_rsi_min,
                    "adx_min": usa_adx_min,
                    "use_bb": usa_use_bb,
                    "use_divergence": usa_use_div,
                }

            if market_choice in ["BIST", "Her İkisi"]:
                selected_symbols = BIST_INDEX_MAP.get(bist_index_choice, BIST_INDEX_MAP["BIST 100"])
                pb = st.progress(0, text="BIST taranıyor...")

                def bist_progress(pct, sym):
                    pb.progress(min(pct, 1.0), text=f"BIST: {sym}")

                bist_results, bist_stats = screen_bist(
                    progress_callback=bist_progress,
                    symbols=selected_symbols,
                    params=bist_params,
                )
                pb.empty()

            if market_choice in ["USA", "Her İkisi"]:
                pb2 = st.progress(0, text="USA taranıyor...")

                def usa_progress(pct, sym):
                    pb2.progress(min(pct, 1.0), text=f"USA: {sym}")

                usa_results, usa_stats = screen_usa(
                    progress_callback=usa_progress,
                    params=usa_params,
                )
                pb2.empty()

            total_hits = len(bist_results) + len(usa_results)
            if total_hits > 0:
                st.success(f"Tarama tamamlandı — {total_hits} hisse bulundu.")
            else:
                st.warning("Kriterlere uyan hisse bulunamadı.")

            # ── Geçmişe kaydet ─────────────────────────────────────────
            if market_choice in ["BIST", "Her İkisi"] and not bist_results.empty:
                add_scan_record(
                    market="BIST",
                    index_name=bist_index_choice,
                    params=bist_params,
                    results_df=bist_results,
                )
            if market_choice in ["USA", "Her İkisi"] and not usa_results.empty:
                add_scan_record(
                    market="USA",
                    index_name="USA",
                    params=usa_params,
                    results_df=usa_results,
                )

            # ── Filtre İstatistikleri ──────────────────────────────────
            if bist_stats or usa_stats:
                with st.expander("Filtre İstatistikleri — kaç hisse hangi adımda elendi?", expanded=(total_hits == 0)):
                    stat_cols = st.columns(2)
                    if bist_stats and market_choice in ["BIST", "Her İkisi"]:
                        with stat_cols[0]:
                            st.markdown(f"**BIST — {bist_index_choice}**")
                            label_map = {
                                "trend": "Trend (Fiyat > EMA21 > EMA50)",
                                "mfi": f"MFI ({bist_mfi_min}–{bist_mfi_max})",
                                "hacim": f"Hacim (>{bist_vol_mult}× ort)",
                                "uyuşmazlık": "Uyuşmazlık",
                                "veri_yetersiz": "Veri yetersiz",
                                "geçti": "Geçti",
                            }
                            rows = [{"Filtre": label_map.get(k, k), "Elenen": v}
                                    for k, v in bist_stats.items() if k != "geçti"]
                            rows.append({"Filtre": "Geçti", "Elenen": bist_stats.get("geçti", 0)})
                            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    if usa_stats and market_choice in ["USA", "Her İkisi"]:
                        with stat_cols[1]:
                            st.markdown("**USA**")
                            label_map_usa = {
                                "trend": "Trend (Fiyat > EMA50 > EMA200)",
                                "momentum": f"Momentum (RSI>{usa_rsi_min} & ADX>{usa_adx_min})",
                                "bb_daralma": "BB Daralması",
                                "uyuşmazlık": "MFI Uyuşmazlığı",
                                "veri_yetersiz": "Veri yetersiz",
                                "geçti": "Geçti",
                            }
                            rows_usa = [{"Filtre": label_map_usa.get(k, k), "Elenen": v}
                                        for k, v in usa_stats.items() if k != "geçti"]
                            rows_usa.append({"Filtre": "Geçti", "Elenen": usa_stats.get("geçti", 0)})
                            st.dataframe(pd.DataFrame(rows_usa), hide_index=True, use_container_width=True)

            # ── Sonuç tabloları ────────────────────────────────────────
            if not bist_results.empty:
                st.subheader(f"BIST Sonuçları — {bist_index_choice} ({len(bist_results)} hisse)")

                display_cols = ["Symbol", "RS Puanı", "Close", "EMA21", "EMA50",
                                "MFI(14)", "RSI(14)", "ADX(14)", "Volume/Avg", "ROC5(%)", "Uyuşmazlık"]
                score_cols = ["_rs_mfi", "_rs_trend", "_rs_hacim", "_rs_rsi", "_rs_adx", "_rs_roc"]
                df_display = bist_results[[c for c in display_cols if c in bist_results.columns]].copy()

                st.dataframe(
                    df_display.style
                        .format({"Close": "{:.2f}", "EMA21": "{:.2f}", "EMA50": "{:.2f}",
                                 "MFI(14)": "{:.1f}", "RSI(14)": "{:.1f}", "ADX(14)": "{:.1f}",
                                 "Volume/Avg": "{:.2f}", "ROC5(%)": "{:+.2f}", "RS Puanı": "{:.1f}"})
                        .background_gradient(subset=["RS Puanı"], cmap="RdYlGn", vmin=0, vmax=100),
                    use_container_width=True, hide_index=True,
                )

                with st.expander("RS Puan Dökümü (bileşen bazlı)"):
                    rs_breakdown = bist_results[["Symbol", "RS Puanı"] + [c for c in score_cols if c in bist_results.columns]].copy()
                    rs_breakdown.columns = [c.replace("_rs_", "").upper() if c.startswith("_rs_") else c for c in rs_breakdown.columns]
                    rs_breakdown.rename(columns={"HACIM": "HACİM", "TREND": "TREND", "MFI": "MFI",
                                                  "RSI": "RSI", "ADX": "ADX", "ROC": "ROC(5g)"}, inplace=True)
                    st.dataframe(rs_breakdown.style.background_gradient(cmap="Blues", subset=rs_breakdown.columns[2:]),
                                 use_container_width=True, hide_index=True)

                    fig_rs = px.bar(bist_results.head(20), x="Symbol", y="RS Puanı",
                                    color="RS Puanı", color_continuous_scale="RdYlGn",
                                    range_color=[0, 100], title="RS Puanı Karşılaştırması")
                    fig_rs.update_layout(height=300, showlegend=False)
                    st.plotly_chart(fig_rs, use_container_width=True)

            if not usa_results.empty:
                st.subheader(f"USA Sonuçları ({len(usa_results)} hisse)")

                display_cols_usa = ["Symbol", "RS Puanı", "Close", "EMA50", "EMA200",
                                    "RSI(14)", "ADX(14)", "MFI(14)", "ROC20(%)", "BB Squeeze", "MFI Div."]
                score_cols_usa = ["_rs_rsi", "_rs_adx", "_rs_mfi", "_rs_trend", "_rs_bb", "_rs_roc"]
                df_display_usa = usa_results[[c for c in display_cols_usa if c in usa_results.columns]].copy()

                st.dataframe(
                    df_display_usa.style
                        .format({"Close": "{:.2f}", "EMA50": "{:.2f}", "EMA200": "{:.2f}",
                                 "RSI(14)": "{:.1f}", "ADX(14)": "{:.1f}", "MFI(14)": "{:.1f}",
                                 "ROC20(%)": "{:+.2f}", "RS Puanı": "{:.1f}"})
                        .background_gradient(subset=["RS Puanı"], cmap="RdYlGn", vmin=0, vmax=100),
                    use_container_width=True, hide_index=True,
                )

                with st.expander("RS Puan Dökümü (bileşen bazlı)"):
                    rs_breakdown_usa = usa_results[["Symbol", "RS Puanı"] + [c for c in score_cols_usa if c in usa_results.columns]].copy()
                    rs_breakdown_usa.columns = [c.replace("_rs_", "").upper() if c.startswith("_rs_") else c for c in rs_breakdown_usa.columns]
                    st.dataframe(rs_breakdown_usa.style.background_gradient(cmap="Blues", subset=rs_breakdown_usa.columns[2:]),
                                 use_container_width=True, hide_index=True)

                    fig_rs_usa = px.bar(usa_results.head(20), x="Symbol", y="RS Puanı",
                                        color="RS Puanı", color_continuous_scale="RdYlGn",
                                        range_color=[0, 100], title="RS Puanı Karşılaştırması")
                    fig_rs_usa.update_layout(height=300, showlegend=False)
                    st.plotly_chart(fig_rs_usa, use_container_width=True)
        else:
            st.info("Taramayı başlatmak için sol panelden ayarları yapıp 'Tara' butonuna tıklayın.")


# ─── BACKTEST TAB ─────────────────────────────────────────────────────────────
with tab_backtest:
    col_bl, col_br = st.columns([1, 3])

    with col_bl:
        st.subheader("Backtest Ayarları")
        bt_market = st.selectbox("Borsa", ["BIST", "USA"], key="bt_market")
        bt_bist_index = None
        if bt_market == "BIST":
            bt_bist_index = st.selectbox(
                "BIST Endeksi",
                ["BIST 50", "BIST 100", "BIST TÜM", "BIST 100 Dışı"],
                index=1,
                key="bt_bist_index",
            )
        bt_interval = st.selectbox("Rebalance Aralığı", ["1 Hafta", "15 Gün", "1 Ay"])

        default_end = datetime.today()
        default_start = default_end - timedelta(days=365)
        bt_start = st.date_input("Başlangıç Tarihi", value=default_start)
        bt_end = st.date_input("Bitiş Tarihi", value=default_end)
        bt_capital = st.number_input("Başlangıç Sermayesi", min_value=1000, value=100000, step=1000)

        bt_run_btn = st.button("Backtesti Çalıştır", type="primary", use_container_width=True)

        st.markdown("---")
        st.markdown("""
**Nasıl çalışır?**  
Her rebalance tarihinde mevcut portföy satılır,
o günkü tarama kriterleri geçen hisseler eşit ağırlıkta satın alınır.

**Benchmark:**  
BIST → XU100 | USA → SPY
""")

    with col_br:
        if bt_run_btn:
            if bt_start >= bt_end:
                st.error("Başlangıç tarihi bitiş tarihinden önce olmalıdır.")
            else:
                from backtest_engine import run_backtest

                progress_container = st.empty()
                progress_bar = progress_container.progress(0, text="Başlıyor...")

                def bt_progress(pct, msg):
                    progress_bar.progress(min(pct, 1.0), text=str(msg))

                with st.spinner("Backtest çalışıyor, lütfen bekleyin..."):
                    from stock_lists import BIST_INDEX_MAP
                    bt_symbols = BIST_INDEX_MAP.get(bt_bist_index) if bt_market == "BIST" and bt_bist_index else None
                    result = run_backtest(
                        market=bt_market,
                        start_date=bt_start.strftime("%Y-%m-%d"),
                        end_date=bt_end.strftime("%Y-%m-%d"),
                        interval_label=bt_interval,
                        initial_capital=float(bt_capital),
                        progress_callback=bt_progress,
                        symbols=bt_symbols,
                    )

                progress_container.empty()
                index_label = f" — {bt_bist_index}" if bt_bist_index else ""
                st.success(f"Backtest tamamlandı! ({bt_market}{index_label})")

                m1, m2, m3, m4, m5, m6 = st.columns(6)
                ret = result["total_return_pct"]
                bench = result["benchmark_return_pct"]
                alpha = result["alpha_pct"]

                m1.metric("Toplam Getiri", f"%{ret:+.1f}")
                m2.metric("CAGR", f"%{result['cagr_pct']:+.1f}")
                m3.metric("Sharpe Oranı", f"{result['sharpe_ratio']:.2f}")
                m4.metric("Maks. Düşüş", f"%{result['max_drawdown_pct']:.1f}")
                m5.metric("Benchmark", f"%{bench:+.1f}", help="XU100 / SPY")
                m6.metric("Alpha", f"%{alpha:+.1f}")

                ph = result["portfolio_history"]
                if not ph.empty:
                    st.subheader("Portföy Değeri")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=ph["Date"], y=ph["Portfolio Value"],
                        mode="lines+markers", name="Portföy",
                        line=dict(color="#1f77b4", width=2), marker=dict(size=5),
                    ))

                    bench_sym = "XU100.IS" if bt_market == "BIST" else "SPY"
                    from data_fetcher import fetch_ohlcv_range
                    bench_df = fetch_ohlcv_range(bench_sym, start=bt_start.strftime("%Y-%m-%d"), end=bt_end.strftime("%Y-%m-%d"))
                    if not bench_df.empty:
                        bench_norm = bench_df["Close"] / bench_df.iloc[0]["Close"] * float(bt_capital)
                        fig.add_trace(go.Scatter(
                            x=bench_norm.index, y=bench_norm.values,
                            mode="lines", name=bench_sym,
                            line=dict(color="#ff7f0e", width=1.5, dash="dash"),
                        ))

                    fig.update_layout(
                        xaxis_title="Tarih", yaxis_title="Portföy Değeri",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        height=400, hovermode="x unified",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                if not ph.empty and "Holdings" in ph.columns:
                    fig2 = px.bar(ph, x="Date", y="Holdings",
                                  title="Her Rebalance'ta Seçilen Hisse Sayısı",
                                  color_discrete_sequence=["#2ca02c"])
                    fig2.update_layout(height=250)
                    st.plotly_chart(fig2, use_container_width=True)

                if not result["trades_log"].empty:
                    with st.expander("İşlem Geçmişi", expanded=False):
                        st.dataframe(result["trades_log"], use_container_width=True, hide_index=True)
                        trades_csv = result["trades_log"].to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "CSV İndir",
                            data=trades_csv,
                            file_name=f"backtest_{bt_market}_{bt_interval.replace(' ', '_')}.csv",
                            mime="text/csv",
                        )
        else:
            st.info("Backtest başlatmak için sol panelden ayarları yapıp 'Backtesti Çalıştır' butonuna tıklayın.")


# ─── HISTORY TAB ──────────────────────────────────────────────────────────────
with tab_history:
    st.subheader("Tarama Geçmişi")

    history = load_history()

    if not history:
        st.info("Henüz kaydedilmiş tarama yok. Tarayıcı sekmesinden bir tarama yapın.")
    else:
        h_col1, h_col2 = st.columns([4, 1])
        with h_col2:
            if st.button("Tümünü Sil", type="secondary", use_container_width=True):
                clear_all()
                st.rerun()

        for rec in history:
            market_label = rec.get("market", "")
            index_label = rec.get("index", "")
            date_label = rec.get("date", "")
            total_hits = rec.get("total_hits", 0)
            params = rec.get("params", {})
            top5 = rec.get("top5", [])
            rec_id = rec.get("id", "")

            header = f"**{date_label}** — {market_label} / {index_label} — {total_hits} hisse bulundu"

            with st.expander(header, expanded=False):
                info_col, del_col = st.columns([5, 1])

                with del_col:
                    if st.button("Sil", key=f"del_{rec_id}", type="secondary"):
                        delete_record(rec_id)
                        st.rerun()

                with info_col:
                    # Filtre eşikleri
                    st.markdown("**Kullanılan Filtre Eşikleri**")
                    if market_label == "BIST":
                        threshold_items = [
                            f"MFI: {params.get('mfi_min', '-')}–{params.get('mfi_max', '-')}",
                            f"Hacim çarpanı: ×{params.get('vol_mult', '-')}",
                            f"Uyuşmazlık lookback: {params.get('div_lookback', '-')} bar",
                            f"Uyuşmazlık filtresi: {'Açık' if params.get('use_divergence') else 'Kapalı'}",
                        ]
                    else:
                        threshold_items = [
                            f"RSI min: {params.get('rsi_min', '-')}",
                            f"ADX min: {params.get('adx_min', '-')}",
                            f"BB Daralması: {'Açık' if params.get('use_bb') else 'Kapalı'}",
                            f"MFI Uyuşmazlığı: {'Açık' if params.get('use_divergence') else 'Kapalı'}",
                        ]
                    st.markdown("  ".join([f"`{t}`" for t in threshold_items]))

                    # Top 5 tablo
                    if top5:
                        st.markdown("**En Yüksek RS Puanlı 5 Hisse**")
                        df_top5 = pd.DataFrame(top5)
                        df_top5.rename(columns={
                            "symbol": "Sembol", "rs": "RS Puanı",
                            "mfi": "MFI", "rsi": "RSI", "adx": "ADX", "vol": "Vol/Avg",
                        }, inplace=True)
                        cols_to_show = [c for c in ["Sembol", "RS Puanı", "MFI", "RSI", "ADX", "Vol/Avg"] if c in df_top5.columns]
                        st.dataframe(
                            df_top5[cols_to_show].style
                                .format({c: "{:.1f}" for c in ["RS Puanı", "MFI", "RSI", "ADX", "Vol/Avg"] if c in df_top5.columns})
                                .background_gradient(subset=["RS Puanı"], cmap="RdYlGn", vmin=0, vmax=100),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("Bu taramada hiç hisse geçememişti.")

