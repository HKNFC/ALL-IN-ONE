"""
BIST Hisse Tarama Uygulaması
ALFA, BETA, DELTA portföy kriterlerine göre hisse tarama
"""

import json
import os
import streamlit as st
import pandas as pd

# Backtest geçmişi dosyası - sayfa yenilense bile saklanır
BACKTEST_GECMISI_DOSYA = "data/backtest_gecmisi.json"
TARAMA_GECMISI_DOSYA = "data/tarama_gecmisi.json"


def _backtest_gecmisi_yukle():
    """Dosyadan backtest geçmişini yükler."""
    if os.path.exists(BACKTEST_GECMISI_DOSYA):
        try:
            with open(BACKTEST_GECMISI_DOSYA, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _backtest_gecmisi_kaydet(gecmis: list):
    """Backtest geçmişini dosyaya yazar."""
    os.makedirs(os.path.dirname(BACKTEST_GECMISI_DOSYA), exist_ok=True)
    with open(BACKTEST_GECMISI_DOSYA, "w", encoding="utf-8") as f:
        json.dump(gecmis, f, ensure_ascii=False, indent=2)


def _backtest_sonuc_serialize(sonuc: dict) -> dict:
    """Backtest sonucunu JSON'a kaydetmek için serileştirir (tarih objeleri stringe çevrilir)."""
    equity_curve = [{"tarih": str(e.get("tarih", ""))[:10], "equity": float(e.get("equity", 0))} for e in sonuc.get("equity_curve", [])]
    return {
        "portfoy": sonuc.get("portfoy"),
        "periyod": sonuc.get("periyod"),
        "baslangic_sermaye": sonuc.get("baslangic_sermaye"),
        "son_deger": sonuc.get("son_deger"),
        "toplam_getiri_pct": sonuc.get("toplam_getiri_pct"),
        "cagr_pct": sonuc.get("cagr_pct"),
        "max_drawdown_pct": sonuc.get("max_drawdown_pct"),
        "rebalans_sayisi": sonuc.get("rebalans_sayisi"),
        "analiz_edilen_hisse": sonuc.get("analiz_edilen_hisse"),
        "baslangic_tarih": sonuc.get("baslangic_tarih"),
        "bitis_tarih": sonuc.get("bitis_tarih"),
        "equity_curve": equity_curve,
        "islemler": sonuc.get("islemler", []),
    }


def _tarama_gecmisi_yukle():
    """Dosyadan tarama geçmişini yükler."""
    if os.path.exists(TARAMA_GECMISI_DOSYA):
        try:
            with open(TARAMA_GECMISI_DOSYA, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _tarama_gecmisi_kaydet(gecmis: list):
    """Tarama geçmişini dosyaya yazar."""
    os.makedirs(os.path.dirname(TARAMA_GECMISI_DOSYA), exist_ok=True)
    with open(TARAMA_GECMISI_DOSYA, "w", encoding="utf-8") as f:
        json.dump(gecmis, f, ensure_ascii=False, indent=2)


from src.bist_screener import hisse_tara, toplu_tara, portfoy_backtest, get_havuz, hisse_verisi_cek, teknik_gostergeler
import plotly.graph_objects as go


@st.cache_data(ttl=3600)
def _backtest_cached(portfoy: str, baslangic: str, bitis: str, sermaye: float, periyod: str, borsa: str, bist_indeks: str):
    """Aynı parametrelerle 1 saat boyunca RAM'den döner (sayfa yenilemesinde yeniden hesaplama yok)."""
    return portfoy_backtest(portfoy, baslangic, bitis, sermaye, hisse_havuzu=None, periyod=periyod,
                           progress_callback=None, borsa=borsa, bist_indeks=bist_indeks)
from plotly.subplots import make_subplots

st.set_page_config(page_title="BIST Hisse Tarayıcı", page_icon="📈", layout="wide")

# Session state
if "tarama_top5" not in st.session_state:
    st.session_state.tarama_top5 = None
if "tarama_portfoy" not in st.session_state:
    st.session_state.tarama_portfoy = None
if "tarama_borsa" not in st.session_state:
    st.session_state.tarama_borsa = None
# Seçili strateji: backtest sonucuna göre (portföy + periyod) - Tarama bu stratejiyi kullanır
if "secilen_strateji" not in st.session_state:
    st.session_state.secilen_strateji = None  # {"portfoy": "ALFA", "periyod": "15_gun", "periyod_gun": 15}
# Backtest geçmişi: dosyadan yüklenir, sayfa yenilense bile kalıcı
if "backtest_gecmisi" not in st.session_state:
    st.session_state.backtest_gecmisi = _backtest_gecmisi_yukle()
# Tarama geçmişi: Güncel Tarama'da yapılan taramalar
if "tarama_gecmisi" not in st.session_state:
    st.session_state.tarama_gecmisi = _tarama_gecmisi_yukle()

# Özel stil
st.markdown("""
<style>
    .portfoy-alfa { background: linear-gradient(90deg, #00c85322, transparent); padding: 1rem; border-radius: 8px; border-left: 4px solid #00c853; }
    .portfoy-beta { background: linear-gradient(90deg, #2196f322, transparent); padding: 1rem; border-radius: 8px; border-left: 4px solid #2196f3; }
    .portfoy-delta { background: linear-gradient(90deg, #9c27b022, transparent); padding: 1rem; border-radius: 8px; border-left: 4px solid #9c27b0; }
    .skor-yuksek { color: #00c853; font-weight: bold; }
    .skor-orta { color: #ff9800; }
</style>
""", unsafe_allow_html=True)

st.title("📈 BIST Hisse Tarayıcı")
st.caption("ALFA (Momentum) • BETA (Değer) • DELTA (Defansif) portföy kriterlerine göre hisse tarama")

# Sidebar
with st.sidebar:
    st.header("⚙️ Ayarlar")
    borsa_secim = st.radio("Borsa", ["BIST", "USA"], horizontal=True, help="Tarama ve backtest için borsa seçin")
    bist_indeks_secim = None
    if borsa_secim == "BIST":
        bist_indeks_secim = st.selectbox(
            "BIST İndeks",
            ["BIST_TUM", "BIST_100", "BIST_30", "BIST_50", "BIST_100_DISI"],
            format_func=lambda x: {"BIST_TUM": "BIST Tüm", "BIST_100": "BIST 100", "BIST_30": "BIST 30", "BIST_50": "BIST 50", "BIST_100_DISI": "BIST 100 Dışı"}[x],
            index=1,
            help="BIST hisse havuzu"
        )
    
    st.markdown("---")
    portfoy_secim = st.radio(
        "Portföy Tipi",
        ["ALFA", "BETA", "DELTA"],
        help="ALFA: Momentum/Büyüme | BETA: Değer | DELTA: Defansif"
    )
    
    st.markdown("---")
    st.markdown("**Portföy Özellikleri**")
    if portfoy_secim == "ALFA":
        st.info("""
        • Fiyat > 50 günlük MA  
        • RSI 40-70  
        • MACD pozitif  
        • Hacim ilgisi
        """)
    elif portfoy_secim == "BETA":
        st.info("""
        • Fiyat ~ 200 günlük MA  
        • RSI 30-55  
        • Düzeltme sonrası  
        • Değer girişi
        """)
    else:
        st.info("""
        • Fiyat > 200 günlük MA  
        • RSI 35-60  
        • Düşük volatilite  
        • İstikrarlı trend
        """)

# Ana içerik - İş akışı: 1) Backtest ile strateji belirle 2) Tarama ile bugün alınacak hisseleri bul
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1️⃣ Strateji Belirleme", "2️⃣ Güncel Tarama", "📊 Tek Hisse", "🔄 Backtest Detay", "📋 Referans"
])

# ==================== TAB 1: STRATEJİ BELİRLEME (Backtest Karşılaştırma) ====================
with tab1:
    st.subheader("1️⃣ Strateji Belirleme")
    st.markdown("""
    **Amaç:** Hangi portföyde ve hangi periyotta çalışacağınızı backtest ile belirleyin.
    Farklı portföy + periyot kombinasyonlarını test edip en iyi sonucu veren stratejiyi seçin.
    """)
    
    # Karşılaştırma parametreleri
    st.markdown("### Karşılaştırılacak Stratejiler")
    strat_col1, strat_col2 = st.columns(2)
    with strat_col1:
        kars_portfoyler = st.multiselect("Portföyler", ["ALFA", "BETA", "DELTA"], default=["ALFA", "BETA", "DELTA"], key="kars_portfoy")
        kars_baslangic = st.date_input("Başlangıç", value=pd.Timestamp("2023-01-01"), key="kars_bas",
            help="2022–2024 aralığı daha güvenilir. 2025+ için Yahoo Finance verisi eksik olabilir.")
        kars_bitis = st.date_input("Bitiş", value=pd.Timestamp.now().date(), key="kars_bit")
    with strat_col2:
        _periyot_opts = {"1_ay": "1 Ay", "15_gun": "15 Gün", "1_hafta": "1 Hafta"}
        kars_periyotlar = st.multiselect("Periyotlar", list(_periyot_opts.keys()), default=list(_periyot_opts.keys()),
            format_func=lambda k: _periyot_opts[k], key="kars_periyot")
        kars_sermaye = st.number_input("Sermaye (₺)", value=100000, key="kars_sermaye")
    
    kars_btn = st.button("▶ Tüm Stratejileri Karşılaştır", type="primary", key="kars_btn")
    
    if kars_btn and kars_portfoyler and kars_periyotlar:
        if kars_baslangic >= kars_bitis:
            st.error("Bitiş tarihi başlangıçtan sonra olmalı.")
        else:
            bas_str = kars_baslangic.strftime("%Y-%m-%d")
            bit_str = kars_bitis.strftime("%Y-%m-%d")
            sonuclar = []
            total = len(kars_portfoyler) * len(kars_periyotlar)
            prog = st.progress(0)
            for pi, portfoy in enumerate(kars_portfoyler):
                for pe, periyod_key in enumerate(kars_periyotlar):
                    idx = pi * len(kars_periyotlar) + pe
                    periyod_label = _periyot_opts.get(periyod_key, periyod_key)
                    prog.progress((idx + 1) / total, text=f"{portfoy} / {periyod_label}")
                    havuz = get_havuz(borsa_secim, bist_indeks_secim or "BIST_100")
                    r = portfoy_backtest(portfoy, bas_str, bit_str, kars_sermaye, hisse_havuzu=havuz, periyod=periyod_key, borsa=borsa_secim, bist_indeks=bist_indeks_secim or "BIST_100")
                    if r:
                        sonuclar.append({
                            "Portföy": portfoy,
                            "Periyot": periyod_label,
                            "Getiri %": round(r["toplam_getiri_pct"], 1),
                            "CAGR %": round(r["cagr_pct"], 1),
                            "Max DD %": round(r["max_drawdown_pct"], 1),
                            "Rebalans": r["rebalans_sayisi"],
                            "_portfoy": portfoy,
                            "_periyod": periyod_key,
                        })
            prog.empty()
            
            if sonuclar:
                sonuclar = sorted(sonuclar, key=lambda x: x["Getiri %"], reverse=True)
                kars_df = pd.DataFrame(sonuclar)
                st.success(f"{len(sonuclar)} strateji karşılaştırıldı.")
                st.dataframe(kars_df[["Portföy", "Periyot", "Getiri %", "CAGR %", "Max DD %", "Rebalans"]], use_container_width=True, hide_index=True)
                
                # Strateji seçimi
                st.markdown("### 🏆 Strateji Seçin")
                secim_opts = [f"{s['Portföy']} + {s['Periyot']} (%{s['Getiri %']} getiri)" for s in sonuclar]
                secilen_idx = st.radio("Kullanmak istediğiniz strateji:", range(len(sonuclar)), 
                    format_func=lambda i: secim_opts[i], key="strateji_secim")
                secilen = sonuclar[secilen_idx]
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.metric(f"{secilen['Portföy']} + {secilen['Periyot']}", 
                        f"%{secilen['Getiri %']} getiri", f"CAGR: %{secilen['CAGR %']} | Max DD: %{secilen['Max DD %']}")
                with c2:
                    if st.button("✓ Bu stratejiyi seç", key="sec_strateji"):
                        st.session_state.secilen_strateji = {
                            "portfoy": secilen["_portfoy"],
                            "periyod": secilen["_periyod"],
                            "periyod_gun": {"1_ay": 30, "15_gun": 15, "1_hafta": 7}[secilen["_periyod"]],
                            "periyod_label": secilen["Periyot"],
                        }
                        st.success("Strateji kaydedildi! 2️⃣ Güncel Tarama sekmesine geçin.")
                        st.rerun()
            else:
                st.warning("""
                **Sonuç alınamadı.** Olası nedenler:
                - Yahoo Finance BIST verisi bazen gecikmeli/eksik olabilir
                - 2022–2024 aralığı genelde daha stabil çalışır
                - İnternet/proxy bağlantı sorunları
                
                **Öneri:** Başlangıç tarihi olarak **2022-01-01** veya **2023-01-01** deneyin.
                """)
    
    if st.session_state.secilen_strateji:
        s = st.session_state.secilen_strateji
        st.info(f"**Seçili strateji:** {s['portfoy']} portföyü, {s['periyod_label']} periyot — Tarama bu stratejiyi kullanacak.")

# ==================== TAB 2: GÜNCEL TARAMA ====================
with tab2:
    st.subheader("2️⃣ Güncel Tarama")
    
    # Tarama geçmişi listesi (dosyadan yüklü, kalıcı)
    if st.session_state.tarama_gecmisi:
        st.markdown("### 📋 Tarama Geçmişi")
        tarama_silinecek_idx = None
        for i, tr in enumerate(st.session_state.tarama_gecmisi):
            col_bilgi, col_sil = st.columns([6, 0.4])
            with col_bilgi:
                hr = tr.get("hisseler", [])
                hisse_str = ", ".join(hr[:5]) if hr else "(sonuç yok)"
                st.write(f"**{tr['tarih']}** · **{tr['portfoy']}** · {hisse_str or '(sonuç yok)'}")
            with col_sil:
                if st.button("🗑️", key=f"tarama_sil_{i}", help="Bu taramayı sil"):
                    tarama_silinecek_idx = i
        if tarama_silinecek_idx is not None:
            st.session_state.tarama_gecmisi.pop(tarama_silinecek_idx)
            _tarama_gecmisi_kaydet(st.session_state.tarama_gecmisi)
            st.success("Tarama silindi.")
            st.rerun()
        st.markdown("---")
    
    st.markdown("""
    İstediğiniz portföy ve tarihte tarama yapın. Geçmiş bir tarih seçerseniz, o günün verilerine göre tarama sonucu elde edersiniz.
    """)
    
    # Portföy ve tarih seçimi
    tarama_col1, tarama_col2, tarama_col3 = st.columns(3)
    with tarama_col1:
        tarama_portfoy = st.selectbox("Portföy", ["ALFA", "BETA", "DELTA"], key="tarama_portfoy_secim",
            help="Hangi portföy kriterlerine göre tarama yapılacak")
    with tarama_col2:
        tarama_tarih = st.date_input("Tarama tarihi", value=pd.Timestamp.now().date(), key="tarama_tarih_secim",
            help="Bu tarihteki verilere göre tarama yapılır (geçmiş tarih seçebilirsiniz)")
    with tarama_col3:
        st.write("")  # hizalama için
    
    # Seçili strateji varsa sonraki rebalans bilgisi
    if st.session_state.secilen_strateji:
        from datetime import timedelta
        ss = st.session_state.secilen_strateji
        bugun = pd.Timestamp.now().date()
        sonraki_rebalans = bugun + timedelta(days=ss["periyod_gun"])
        st.info(f"**Sonraki rebalans tarihi (seçili strateji):** {sonraki_rebalans.strftime('%Y-%m-%d')}")
    
    varsayilan_havuz = get_havuz(borsa_secim, bist_indeks_secim or "BIST_100")
    if borsa_secim == "USA":
        havuz_bilgi = f"USA (S&P/Nasdaq benzeri, {len(varsayilan_havuz)} hisse)"
    else:
        indeks_etiket = {"BIST_TUM": "BIST Tüm", "BIST_100": "BIST 100", "BIST_30": "BIST 30", "BIST_50": "BIST 50", "BIST_100_DISI": "BIST 100 Dışı"}.get(bist_indeks_secim or "BIST_100", "BIST 100")
        havuz_bilgi = f"{indeks_etiket} ({len(varsayilan_havuz)} hisse)"
    st.info(f"**Veri havuzu:** {havuz_bilgi}. Özel liste için aşağıya hisse kodları yazabilirsiniz.")
    custom_havuz = st.text_input("Tarama Havuzu (boş = yukarıdaki indeks)", value="", 
        placeholder="THYAO, GARAN, EREGL, ..." if borsa_secim == "BIST" else "AAPL, MSFT, GOOGL, ...", key="guncel_havuz")
    tara_btn = st.button("✅ Taramayı Çalıştır", type="primary", key="guncel_tara")
    
    if tara_btn:
        havuz = [h.strip().upper() for h in custom_havuz.replace("\n", ",").split(",") if h.strip()] if custom_havuz.strip() else varsayilan_havuz
        tarih_str = tarama_tarih.strftime("%Y-%m-%d")
        with st.spinner(f"Hisse verileri çekiliyor ({tarama_tarih} tarihi için)..."):
            sonuc_df = toplu_tara(havuz, tarama_portfoy, borsa=borsa_secim, tarih=tarih_str)
        
        if sonuc_df.empty:
            st.warning("Veri çekilebilen hisse bulunamadı.")
        else:
            sonuc_df = sonuc_df.sort_values("skor", ascending=False).reset_index(drop=True)
            bulunan_hisseler = sonuc_df["sembol"].tolist()
            st.session_state.tarama_top5 = bulunan_hisseler[:5]
            st.session_state.tarama_portfoy = tarama_portfoy
            st.session_state.tarama_borsa = borsa_secim
            
            # Tarama geçmişine ekle (en yeni en üstte, en iyi 50 hisse saklanır)
            st.session_state.tarama_gecmisi.insert(0, {
                "tarih": tarih_str,
                "portfoy": tarama_portfoy,
                "hisseler": bulunan_hisseler[:50],
            })
            _tarama_gecmisi_kaydet(st.session_state.tarama_gecmisi)
            
            st.success(f"**{tarama_portfoy}** portföyüne göre **{tarama_tarih}** tarihinde almanız gereken hisseler:")
            ust_5 = sonuc_df.head(5)
            cols = st.columns(5)
            for i, row in enumerate(ust_5.itertuples()):
                with cols[i]:
                    st.metric(f"#{i+1} {row.sembol}", f"{row.skor:.0f} puan", f"₺{row.son_fiyat:,.0f} | RSI: {row.rsi:.0f} | {row.gecen_kriter}/{row.toplam_kriter} kriter")
            
            st.markdown("---")
            st.markdown("### Tüm sonuçlar (iyiden kötüye)")
            goster = sonuc_df[["sembol", "son_fiyat", "rsi", "ma_50", "ma_200", "gecen_kriter", "skor"]].copy()
            goster.columns = ["Sembol", "Fiyat", "RSI", "MA50", "MA200", "Geçen Kriter", "Puan"]
            st.dataframe(goster, use_container_width=True, hide_index=True)
            
            if st.session_state.secilen_strateji:
                ss = st.session_state.secilen_strateji
                from datetime import timedelta
                sonraki = tarama_tarih + timedelta(days=ss["periyod_gun"])
                st.caption(f"⏰ Sonraki rebalans: {sonraki.strftime('%Y-%m-%d')} — **{ss['periyod_label']}** sonra tekrar tarama yapın.")

# ==================== TAB 3: TEK HİSSE ====================
with tab3:
    st.subheader("Tek Hisse Detaylı Analiz")
    
    sembol_hint = "THYAO, GARAN" if borsa_secim == "BIST" else "AAPL, MSFT"
    sembol = st.text_input(f"Hisse kodu (örn: {sembol_hint})", value="ISGSY" if borsa_secim == "BIST" else "AAPL", max_chars=10).upper().strip()
    
    if sembol:
        with st.spinner("Veri çekiliyor..."):
            sonuc = hisse_tara(sembol, portfoy_secim, borsa=borsa_secim)
            df_raw = hisse_verisi_cek(sembol, borsa=borsa_secim)
        
        if sonuc is None:
            st.error(f"{sembol} için yeterli veri bulunamadı. Sembolü kontrol edin.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Son Fiyat", f"₺{sonuc['son_fiyat']:,.2f}", "")
            with col2:
                st.metric("RSI", f"{sonuc['rsi']:.1f}", "Aşırı alım >70, Aşırı satım <30" if sonuc['rsi'] > 70 or sonuc['rsi'] < 30 else "Normal bölge")
            with col3:
                st.metric("Puan", f"{sonuc['skor']:.0f}", f"{sonuc['gecen_kriter']}/{sonuc['toplam_kriter']} kriter geçti")
            
            st.markdown("**Kriter Durumu**")
            for kr, gecti in sonuc["kriterler"].items():
                st.write(f"{'✅' if gecti else '❌'} {kr.replace('_', ' ').title()}")
            
            # Grafik
            if df_raw is not None and len(df_raw) >= 50:
                df_tek = teknik_gostergeler(df_raw)
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                    subplot_titles=("Fiyat & Ortalamalar", "RSI", "MACD"),
                                    row_heights=[0.5, 0.25, 0.25])
                
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["close"], name="Fiyat", line=dict(color="#2196f3")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["ma_50"], name="MA 50", line=dict(color="#ff9800", dash="dash")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["ma_200"], name="MA 200", line=dict(color="#9c27b0", dash="dot")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["rsi"], name="RSI", line=dict(color="#00bcd4")), row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=2, col=1)
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["macd"], name="MACD", line=dict(color="#4caf50")), row=3, col=1)
                fig.add_trace(go.Scatter(x=df_tek.index, y=df_tek["macd_signal"], name="Sinyal", line=dict(color="#f44336", dash="dash")), row=3, col=1)
                
                fig.update_layout(height=500, template="plotly_white", showlegend=True, legend=dict(orientation="h"))
                st.plotly_chart(fig, use_container_width=True, key="plotly_tek_hisse")

# ==================== TAB 4: BACKTEST DETAY ====================
with tab4:
    st.subheader("🔄 Backtest Detay")
    
    # Backtest geçmişi listesi (dosyadan yüklü, kalıcı) - tıklanınca detaylar gösterilir
    if st.session_state.backtest_gecmisi:
        st.markdown("### 📋 Backtest Geçmişi")
        st.caption("Detayları görmek için satıra tıklayın (genişletin)")
        silinecek_idx = None
        for i, bt in enumerate(st.session_state.backtest_gecmisi):
            ozet = f"**{bt['Portföy']}** · {bt['Periyot']} · {bt['Başlangıç']} → {bt['Bitiş']} · **%{bt['Getiri %']}**"
            with st.expander(ozet, expanded=False):
                detay = bt.get("detay")
                if detay:
                    # Metrikler
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Toplam Getiri", f"%{detay.get('toplam_getiri_pct', 0):.1f}", "")
                    m2.metric("CAGR", f"%{detay.get('cagr_pct', 0):.1f}", "")
                    m3.metric("Max Drawdown", f"%{detay.get('max_drawdown_pct', 0):.1f}", "")
                    m4.metric("Rebalans Sayısı", detay.get("rebalans_sayisi", 0), "")
                    m5.metric("Analiz Edilen Hisse", detay.get("analiz_edilen_hisse", 0), "")
                    st.metric("Son Portföy Değeri", f"₺{detay.get('son_deger', 0):,.0f}",
                              f"Başlangıç: ₺{detay.get('baslangic_sermaye', 0):,.0f}")
                    # Equity curve grafiği
                    eq = detay.get("equity_curve", [])
                    if eq:
                        eq_df = pd.DataFrame(eq)
                        fig_bt = go.Figure()
                        fig_bt.add_trace(go.Scatter(x=eq_df["tarih"], y=eq_df["equity"], name="Portföy Değeri", line=dict(color="#2196f3")))
                        fig_bt.update_layout(title=f"{detay.get('portfoy', '')} Portföy Değeri (Equity Curve)", xaxis_title="Tarih", yaxis_title="Değer (₺)",
                                            template="plotly_white", height=320)
                        st.plotly_chart(fig_bt, use_container_width=True, key=f"plotly_bt_gecmis_{i}")
                    # Rebalans geçmişi
                    islemler = detay.get("islemler", [])
                    if islemler:
                        with st.expander(f"📋 Rebalans Geçmişi ({detay.get('periyod', '')} portföy bileşimi)"):
                            for op in islemler:
                                hisse_str = ", ".join(op.get("hisseler", [])) if op.get("hisseler") else "(kriterleri geçen hisse yok)"
                                st.write(f"**{op.get('tarih', '')}** — {hisse_str} (Değer: ₺{op.get('deger', 0):,.0f})")
                else:
                    st.info("Bu backtest detayları kaydedilmemiş (eski format). Yeni backtest'lerden sonuçları tekrar görebilirsiniz.")
                if st.button("🗑️ Bu backtesti sil", key=f"bt_sil_{i}", help="Bu backtesti geçmişten sil"):
                    silinecek_idx = i
        if silinecek_idx is not None:
            st.session_state.backtest_gecmisi.pop(silinecek_idx)
            _backtest_gecmisi_kaydet(st.session_state.backtest_gecmisi)
            st.success("Backtest silindi.")
            st.rerun()
        st.markdown("---")
    
    st.markdown("Seçili havuzdaki (BIST 100, BIST TUM vb.) **tüm hisseler** ile backtest. Her rebalans tarihinde portföy kriterlerine göre en iyi 5 hisse seçilir ve al/sat simülasyonu yapılır.")
    
    bt_col1, bt_col2, bt_col3, bt_col4, bt_col5 = st.columns([1, 1, 1, 1, 1])
    with bt_col1:
        bt_portfoy = st.selectbox("Portföy", ["ALFA", "BETA", "DELTA"], key="bt_portfoy",
            help="Hangi portföy kriterlerine göre al/sat simülasyonu yapılacak")
    with bt_col2:
        bt_periyod = st.selectbox("Tarama periyodu", ["1_ay", "15_gun", "1_hafta"],
            format_func=lambda x: {"1_ay": "1 Ay", "15_gun": "15 Gün", "1_hafta": "1 Hafta"}[x],
            key="bt_periyod", help="Portföy bu sıklıkta taranır ve al/sat yapılır")
    with bt_col3:
        bt_baslangic = st.date_input("Başlangıç tarihi", value=pd.Timestamp("2023-01-01"), key="bt_baslangic")
    with bt_col4:
        bt_bitis = st.date_input("Bitiş tarihi", value=pd.Timestamp.now().date(), key="bt_bitis")
    with bt_col5:
        bt_sermaye = st.number_input("Başlangıç sermayesi (₺)", value=100000, min_value=1000, step=10000, key="bt_sermaye")
    
    bt_btn = st.button("▶ Backtest Çalıştır", type="primary", key="bt_btn")
    
    if bt_btn:
        bas_str = bt_baslangic.strftime("%Y-%m-%d")
        bit_str = bt_bitis.strftime("%Y-%m-%d")
        if bt_baslangic >= bt_bitis:
            st.error("Bitiş tarihi başlangıçtan sonra olmalı.")
        else:
            with st.spinner("Portföy backtest hesaplanıyor... (ilk seferde veri indirilir, sonrakiler disk cache'den ~saniyeler)"):
                sonuc = _backtest_cached(
                    bt_portfoy, bas_str, bit_str, float(bt_sermaye), bt_periyod,
                    borsa_secim, bist_indeks_secim or "BIST_100"
                )
            
            if sonuc is None:
                st.error("Yeterli veri bulunamadı. Tarih aralığını değiştirmeyi veya daha geniş bir dönem seçmeyi deneyin.")
            else:
                # Backtest geçmişine ekle (detaylar tıklanınca tekrar görüntülenebilir)
                periyod_etiket = {"1_ay": "1 Ay", "15_gun": "15 Gün", "1_hafta": "1 Hafta"}.get(bt_periyod, bt_periyod)
                st.session_state.backtest_gecmisi.insert(0, {
                    "Portföy": bt_portfoy,
                    "Periyot": periyod_etiket,
                    "Başlangıç": bas_str,
                    "Bitiş": bit_str,
                    "Getiri %": round(sonuc["toplam_getiri_pct"], 1),
                    "detay": _backtest_sonuc_serialize(sonuc),
                })
                _backtest_gecmisi_kaydet(st.session_state.backtest_gecmisi)
                periyod_info = f" | Periyod: {sonuc.get('periyod', '1 Ay')}"
                st.success(f"**{sonuc['portfoy']}** portföyü backtest tamamlandı: {sonuc['baslangic_tarih']} → {sonuc['bitis_tarih']}{periyod_info}")
                
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Toplam Getiri", f"%{sonuc['toplam_getiri_pct']:.1f}", "")
                m2.metric("CAGR", f"%{sonuc['cagr_pct']:.1f}", "")
                m3.metric("Max Drawdown", f"%{sonuc['max_drawdown_pct']:.1f}", "")
                m4.metric("Rebalans Sayısı", sonuc["rebalans_sayisi"], "")
                m5.metric("Havuzdaki Hisse", sonuc["analiz_edilen_hisse"], "her rebalansta en iyi 5 seçildi")
                
                st.metric("Son Portföy Değeri", f"₺{sonuc['son_deger']:,.0f}", f"Başlangıç: ₺{sonuc['baslangic_sermaye']:,.0f}")
                
                eq_df = pd.DataFrame(sonuc["equity_curve"])
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Scatter(x=eq_df["tarih"], y=eq_df["equity"], name="Portföy Değeri", line=dict(color="#2196f3")))
                fig_bt.update_layout(title=f"{sonuc['portfoy']} Portföy Değeri (Equity Curve)", xaxis_title="Tarih", yaxis_title="Değer (₺)", 
                                    template="plotly_white", height=350)
                st.plotly_chart(fig_bt, use_container_width=True, key="plotly_bt_sonuc")
                
                if sonuc["islemler"]:
                    periyod_label = sonuc.get("periyod", "Periyod")
                    with st.expander(f"📋 Rebalans Geçmişi ({periyod_label} portföy bileşimi)"):
                        for i in sonuc["islemler"]:
                            hisse_str = ', '.join(i['hisseler']) if i['hisseler'] else "(kriterleri geçen hisse yok)"
                            st.write(f"**{i['tarih']}** — {hisse_str} (Değer: ₺{i['deger']:,.0f})")

# ==================== TAB 5: REFERANS ====================
with tab5:
    st.subheader("Referans Portföy Verileri")
    st.markdown("Analiz edilen yatırımcının aylık portföy bileşimleri:")
    
    ref_df = pd.read_csv("data/portfoy_verisi.csv")
    
    ay_siralama = {
        "Oca.25": 1, "Şub.25": 2, "Mar.25": 3, "Nis.25": 4, "May.25": 5, "Haz.25": 6,
        "Tem.25": 7, "Ağu.25": 8, "Eyl.25": 9, "Eki.25": 10, "Kas.25": 11, "Ara.25": 12,
        "Oca.26": 13, "Şub.26": 14
    }
    ref_df["sira"] = ref_df["ay"].map(ay_siralama)
    ref_df = ref_df.sort_values(["sira", "portfoy", "hisse_kodu"])
    
    st.dataframe(ref_df[["ay", "portfoy", "hisse_kodu"]], use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("Detaylı analiz: `docs/PORTFOY_ANALIZI.md`")
    
