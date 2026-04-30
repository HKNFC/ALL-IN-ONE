"""
Ensemble Portföy — 3 Model · 9 Hisse · Eşit Ağırlık
Mark Minervini + Portföy Optimizer + Super Investor
"""

import sys, os, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from io import BytesIO

# Path ayarları — diğer modülleri import edebilmek için
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

# Önce Portfolio-Optimizer path'ini ekle (data_cache için)
PO_DIR = os.path.join(AI_DIR, "Portfolio-Optimizer")
sys.path.insert(0, PO_DIR)

# Portföy Optimizer'dan data_cache kullan
try:
    from data_cache import get_price_data, batch_get_price_data
except ImportError as e:
    st.error(f"data_cache yüklenemedi: {e}")
    st.stop()

# Diğer modüller için path ekle
sys.path.insert(0, os.path.join(AI_DIR, "MARK MİNERVİNİ"))
sys.path.insert(0, os.path.join(AI_DIR, "SUPER-INVESTOR-CHATGPT"))

st.set_page_config(page_title="Ensemble Portföy", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# SABİTLER
# ─────────────────────────────────────────────────────────────────────────────

BIST_BENCHMARK = "XU100.IS"
USA_BENCHMARK = "SPY"

# BIST TÜM liste - direkt dosyadan oku (app.py import etmek Streamlit çakışması yapar)
import importlib.util
spec = importlib.util.spec_from_file_location("po_app", "/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/app.py")
po_module = importlib.util.module_from_spec(spec)

# Sadece değişkenleri al, exec_module yerine manual parse et
def get_var_from_file(filepath, varname):
    result = []
    in_var = False
    bracket_count = 0
    import re
    with open(filepath, "r") as f:
        for line in f:
            if not in_var:
                if line.strip().startswith(varname + " =") or line.strip().startswith(varname + "="):
                    in_var = True
                    bracket_count = line.count("[") - line.count("]")
                    result.extend(re.findall(r"""["'](\w+)["']""", line))
            else:
                bracket_count += line.count("[") - line.count("]")
                result.extend(re.findall(r"""["'](\w+)["']""", line))
                if bracket_count <= 0 and "]" in line:
                    break
    return list(set(result))

def _fetch_bist_dynamic():
    """Bigpara'dan BIST listesi çek. Başarısız olursa disk cache kullan."""
    import os, json, time, requests as _req
    cache_file = "/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/data_cache/bist_list_cache.json"
    # Disk cache: 24 saatte bir güncelle
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            if time.time() - cached.get("ts", 0) < 86400 and len(cached.get("tickers", [])) > 200:
                return cached["tickers"]
        except Exception:
            pass
    # Bigpara'dan çek
    try:
        r = _req.get("https://bigpara.hurriyet.com.tr/api/v1/hisse/list",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = r.json().get("data", [])
        tickers = sorted(set(
            x["kod"].strip() for x in data
            if x.get("kod","").strip().isalpha() and 4 <= len(x.get("kod","").strip()) <= 6
        ))
        if len(tickers) > 200:
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, "w") as f:
                    json.dump({"ts": time.time(), "tickers": tickers}, f)
            except Exception:
                pass
            return tickers
    except Exception:
        pass
    return None

_raw_bist       = get_var_from_file("/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/app.py", "BIST_TUM_STOCKS")
_bist100        = get_var_from_file("/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/app.py", "BIST100_STOCKS")
_US_903_TICKERS = get_var_from_file("/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/app.py", "_US_903_TICKERS")
_dynamic_bist   = _fetch_bist_dynamic()
PO_BIST_STOCKS  = sorted(set(_raw_bist) | set(_bist100) | set(_dynamic_bist or []))

if not _US_903_TICKERS:
    _US_903_TICKERS = []
if len(PO_BIST_STOCKS) < 200:
    PO_BIST_STOCKS = []

if not _US_903_TICKERS:
    _US_903_TICKERS = []
if len(PO_BIST_STOCKS) < 200:
    PO_BIST_STOCKS = []


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────

def _last_business_day(d: pd.Timestamp) -> pd.Timestamp:
    """Verilen tarih bugün veya sonrasıysa bir önceki iş gününü döndür."""
    today = pd.Timestamp.today().normalize()
    d = d.normalize()
    if d >= today:
        d = today - pd.Timedelta(days=1)
        while d.weekday() >= 5:
            d -= pd.Timedelta(days=1)
    return d

def get_market_tickers(market: str) -> list:
    """Piyasaya göre ticker listesi döndür."""
    if market == "BIST":
        return [t + ".IS" if not t.endswith(".IS") else t for t in PO_BIST_STOCKS]
    else:  # USA
        return _US_903_TICKERS

def get_benchmark(market: str) -> str:
    return BIST_BENCHMARK if market == "BIST" else USA_BENCHMARK

# ─────────────────────────────────────────────────────────────────────────────
# TARAMA MOTORLARI
# ─────────────────────────────────────────────────────────────────────────────

def screen_minervini_style(tickers: list, cutoff: pd.Timestamp, market: str, top_n: int = 5) -> list:
    """Mark Minervini tarzı tarama."""
    benchmark = get_benchmark(market)
    start_str = (cutoff - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    end_str = cutoff.strftime("%Y-%m-%d")
    
    bench_df = get_price_data(benchmark, start_str, end_str)
    if bench_df is None or bench_df.empty:
        return []
    
    # Index'i datetime'e çevir
    bench_df.index = pd.to_datetime(bench_df.index)
    bench_close = bench_df["Close"]
    
    results = []
    for tk in tickers:
        try:
            df = get_price_data(tk, start_str, end_str)
            if df is None or len(df) < 200:
                continue
            
            # Index'i datetime'e çevir
            df.index = pd.to_datetime(df.index)
            close = df["Close"]
            last = float(close.iloc[-1])
            
            sma50 = float(close.rolling(50).mean().iloc[-1])
            if last < sma50:
                continue
            sma200 = float(close.rolling(200).mean().iloc[-1])
            if sma200 > 0 and last < sma200 * 0.97:
                continue
            
            ret_6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100
            if ret_6m < 0:
                continue
            
            b_now = float(bench_close.iloc[-1])
            b_6m = float(bench_close.iloc[-126])
            b_3m = float(bench_close.iloc[-63])
            b_1m = float(bench_close.iloc[-22])
            b_12m = float(bench_close.iloc[-240]) if len(bench_close) >= 240 else b_6m
            
            p_now = float(close.iloc[-1])
            p_6m = float(close.iloc[-126])
            p_3m = float(close.iloc[-63])
            p_1m = float(close.iloc[-22])
            p_12m = float(close.iloc[-240]) if len(close) >= 240 else p_6m
            
            ex_12m = (p_now/p_12m - b_now/b_12m) * 100
            ex_6m = (p_now/p_6m - b_now/b_6m) * 100
            ex_3m = (p_now/p_3m - b_now/b_3m) * 100
            ex_1m = (p_now/p_1m - b_now/b_1m) * 100
            
            rs_score = ex_12m * 0.30 + ex_6m * 0.30 + ex_3m * 0.25 + ex_1m * 0.15
            
            results.append({"ticker": tk, "score": rs_score, "last_price": last})
        except Exception:
            continue
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

def screen_optimizer_style(tickers: list, cutoff: pd.Timestamp, market: str, top_n: int = 5) -> list:
    """Portföy Optimizer Alfa tarzı tarama."""
    benchmark = get_benchmark(market)
    start_str = (cutoff - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    end_str = cutoff.strftime("%Y-%m-%d")
    
    bench_df = get_price_data(benchmark, start_str, end_str)
    if bench_df is None or bench_df.empty:
        return []
    
    bench_df.index = pd.to_datetime(bench_df.index)
    bench_close = bench_df["Close"]
    
    results = []
    for tk in tickers:
        try:
            df = get_price_data(tk, start_str, end_str)
            if df is None or len(df) < 200:
                continue
            
            df.index = pd.to_datetime(df.index)
            close = df["Close"]
            last = float(close.iloc[-1])
            
            sma50 = float(close.rolling(50).mean().iloc[-1])
            if last < sma50:
                continue
            sma200 = float(close.rolling(200).mean().iloc[-1])
            if sma200 > 0 and last < sma200 * 0.97:
                continue
            
            ret_6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100
            if ret_6m < 0:
                continue
            
            b_now = float(bench_close.iloc[-1])
            b_6m = float(bench_close.iloc[-126])
            b_3m = float(bench_close.iloc[-63])
            b_1m = float(bench_close.iloc[-22])
            
            p_now = float(close.iloc[-1])
            p_6m = float(close.iloc[-126])
            p_3m = float(close.iloc[-63])
            p_1m = float(close.iloc[-22])
            
            ex_6m = (p_now/p_6m - b_now/b_6m) * 100
            ex_3m = (p_now/p_3m - b_now/b_3m) * 100
            ex_1m = (p_now/p_1m - b_now/b_1m) * 100
            
            alfa_score = ex_6m * 0.20 + ex_3m * 0.35 + ex_1m * 0.45
            
            results.append({"ticker": tk, "score": alfa_score, "last_price": last})
        except Exception:
            continue
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

def screen_superinvestor_style(tickers: list, cutoff: pd.Timestamp, market: str, top_n: int = 5,
                               quality: str = "Temel", sort_by: str = "RS Score", profile: str = "standard") -> list:
    """Super Investor tarzı tarama."""
    benchmark = get_benchmark(market)
    start_str = (cutoff - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    end_str = cutoff.strftime("%Y-%m-%d")
    
    bench_df = get_price_data(benchmark, start_str, end_str)
    if bench_df is None or bench_df.empty:
        return []
    
    bench_df.index = pd.to_datetime(bench_df.index)
    bench_close = bench_df["Close"]
    
    results = []
    for tk in tickers:
        try:
            df = get_price_data(tk, start_str, end_str)
            if df is None or len(df) < 200:
                continue
            
            df.index = pd.to_datetime(df.index)
            close = df["Close"]
            last = float(close.iloc[-1])
            
            sma50 = float(close.rolling(50).mean().iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1])
            ret_6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100

            if quality == "Temel":
                if last < sma50 or last < sma200:
                    continue
                if ret_6m < 5:
                    continue
            elif quality == "Sıkı":
                if last < sma50 or last < sma200:
                    continue
                if ret_6m < 10:
                    continue
                # ek: 3ay pozitif
                ret_3m = (float(close.iloc[-1]) / float(close.iloc[-63]) - 1) * 100
                if ret_3m < 3:
                    continue
            # Kapalı: filtre yok
            
            volatility = close.pct_change().std() * np.sqrt(252) * 100
            vol_penalty = min(volatility * 0.5, 10)
            
            b_now = float(bench_close.iloc[-1])
            b_6m = float(bench_close.iloc[-126])
            b_3m = float(bench_close.iloc[-63])
            
            p_now = float(close.iloc[-1])
            p_6m = float(close.iloc[-126])
            p_3m = float(close.iloc[-63])
            
            ex_6m = (p_now/p_6m - b_now/b_6m) * 100
            ex_3m = (p_now/p_3m - b_now/b_3m) * 100
            
            # Profil ağırlıkları (fonksiyon imzasından gelir)
            _pw = {
                "standard":             (0.50, 0.50),
                "quality_compounders":  (0.60, 0.40),
                "growth_leaders":       (0.40, 0.60),
                "smart_money_breakout": (0.35, 0.65),
                "value_confirmation":   (0.55, 0.45),
            }
            _w6, _w3 = _pw.get(profile, (0.50, 0.50))
            si_score = (ex_6m * _w6 + ex_3m * _w3) - vol_penalty
            
            results.append({"ticker": tk, "score": si_score, "last_price": last, "vol": volatility})
        except Exception:
            continue
    
    # Strateji profili ağırlık ayarı
    profile_weights = {
        "standard":             (0.50, 0.50),
        "quality_compounders":  (0.60, 0.40),
        "growth_leaders":       (0.40, 0.60),
        "smart_money_breakout": (0.35, 0.65),
        "value_confirmation":   (0.55, 0.45),
    }
    w6, w3 = profile_weights.get(profile, (0.50, 0.50))

    # Sıralama türü
    if sort_by == "RS Score":
        results.sort(key=lambda x: x["score"], reverse=True)
    elif sort_by in ("Technical Score", "Combined Score", "Selection Score", "Timing Score"):
        # rs_score zaten momentum bazlı — aynı mantık
        results.sort(key=lambda x: x["score"], reverse=True)
    elif sort_by == "Institutional Score":
        # volatilite düşük olanlar öne (düşük vol = kurumsal tercih)
        results.sort(key=lambda x: x.get("vol", 999))
    else:
        results.sort(key=lambda x: x["score"], reverse=True)

    return results[:top_n]

def select_ensemble_portfolio(mm_results: list, po_results: list, si_results: list) -> dict:
    """3 modelden ilk 3'ü seç, örtüşenleri alt sıradan tamamla."""
    selected = {}
    
    for rank in range(3):
        if rank < len(mm_results):
            tk = mm_results[rank]["ticker"]
            if tk not in selected:
                selected[tk] = {"model": "Mark Minervini", "rank": rank + 1, "score": mm_results[rank]["score"]}
        
        if rank < len(po_results):
            tk = po_results[rank]["ticker"]
            if tk not in selected:
                selected[tk] = {"model": "Portföy Optimizer", "rank": rank + 1, "score": po_results[rank]["score"]}
        
        if rank < len(si_results):
            tk = si_results[rank]["ticker"]
            if tk not in selected:
                selected[tk] = {"model": "Super Investor", "rank": rank + 1, "score": si_results[rank]["score"]}
    
    all_results = {"Mark Minervini": mm_results, "Portföy Optimizer": po_results, "Super Investor": si_results}
    
    for model_name, results in all_results.items():
        for rank in range(3, len(results)):
            if len(selected) >= 9:
                break
            tk = results[rank]["ticker"]
            if tk not in selected:
                selected[tk] = {"model": model_name, "rank": rank + 1, "score": results[rank]["score"]}
    
    return selected

def main():
    st.title("🎯 Ensemble Portföy")
    st.caption("Mark Minervini + Portföy Optimizer + Super Investor | 9 Hisse · Eşit Ağırlık")
    
    tab_scan, tab_backtest = st.tabs(["📊 Hisse Tarama", "📈 Backtest"])
    
    with tab_scan:
        st.subheader("Ensemble Tarama")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            market = st.selectbox("Piyasa", ["BIST", "USA"], key="ens_scan_market")
        with col2:
            scan_date = st.date_input("Tarama Tarihi (boş=son iş günü)", value=None, key="ens_scan_date")
        with col3:
            st.write("")
            st.write("")
            run_scan = st.button("🔍 Tarama Yap", use_container_width=True)
        
        # Super Investor parametre seçimleri
        with st.expander("⚙️ Super Investor Parametreleri", expanded=False):
            si_col1, si_col2, si_col3 = st.columns(3)
            with si_col1:
                si_quality = st.selectbox(
                    "Temel Kalite Seviyesi",
                    ["Kapalı", "Temel", "Sıkı"],
                    index=1,
                    key="ens_si_quality"
                )
            with si_col2:
                si_sort = st.selectbox(
                    "Sıralama Türü",
                    ["RS Score", "Technical Score", "Combined Score", "Institutional Score", "Selection Score", "Timing Score"],
                    index=0,
                    key="ens_si_sort"
                )
            with si_col3:
                si_profile = st.selectbox(
                    "Strateji Profili",
                    ["standard", "quality_compounders", "growth_leaders", "smart_money_breakout", "value_confirmation"],
                    format_func=lambda x: {
                        "standard": "Standart",
                        "quality_compounders": "Kalite Bileşikleri",
                        "growth_leaders": "Büyüme Liderleri",
                        "smart_money_breakout": "Akıllı Para Kırılım",
                        "value_confirmation": "Değer+Onay"
                    }[x],
                    index=0,
                    key="ens_si_profile"
                )
        
        st.info(f"💡 Super Investor: {si_quality} | {si_sort} | {si_profile}")
        
        if run_scan:
            with st.spinner("Tarama yapılıyor..."):
                if scan_date:
                    cutoff = _last_business_day(pd.Timestamp(scan_date))
                else:
                    cutoff = _last_business_day(pd.Timestamp.today())
                
                st.info(f"Tarama tarihi: {cutoff.strftime('%Y-%m-%d')}")
                
                tickers = get_market_tickers(market)
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Mark Minervini taranıyor...")
                mm_results = screen_minervini_style(tickers, cutoff, market, top_n=10)
                st.write(f"DEBUG Minervini: {len(mm_results)} sonuç, cutoff={cutoff.date()}")
                if mm_results:
                    st.write(f"İlk 3: {[(r['ticker'], round(r['score'],1)) for r in mm_results[:3]]}")
                    # İlk hissenin detaylı hesaplaması
                    tk = mm_results[0]['ticker']
                    df = get_price_data(tk, (cutoff - pd.Timedelta(days=400)).strftime("%Y-%m-%d"), cutoff.strftime("%Y-%m-%d"))
                    st.write(f"  {tk}: veri son tarih={df.index[-1].date()}, satır={len(df)}")
                progress_bar.progress(33)
                
                status_text.text("Portföy Optimizer taranıyor...")
                po_results = screen_optimizer_style(tickers, cutoff, market, top_n=10)
                st.write(f"DEBUG Optimizer: {len(po_results)} sonuç")
                st.write(f"İlk 5: {[(r['ticker'], round(r['score'],1)) for r in po_results[:5]]}")
                progress_bar.progress(66)
                
                status_text.text("Super Investor taranıyor...")
                si_results = screen_superinvestor_style(tickers, cutoff, market, top_n=10, quality=si_quality, sort_by=si_sort, profile=si_profile)
                st.write(f"DEBUG Super Inv: {len(si_results)} sonuç")
                st.write(f"İlk 5: {[(r['ticker'], round(r['score'],1)) for r in si_results[:5]]}")
                progress_bar.progress(100)
                
                status_text.empty()
                progress_bar.empty()
                
                ensemble = select_ensemble_portfolio(mm_results, po_results, si_results)
                
                st.success(f"{len(ensemble)} hisse seçildi")
                
                ensemble_df = pd.DataFrame([
                    {"Hisse": tk, "Model": info["model"], "Sıra": info["rank"], "Skor": round(info["score"], 2)}
                    for tk, info in ensemble.items()
                ])
                st.dataframe(ensemble_df, use_container_width=True, hide_index=True)
                
                col_mm, col_po, col_si = st.columns(3)
                
                with col_mm:
                    st.markdown("**📊 Mark Minervini (İlk 5)**")
                    if mm_results:
                        mm_df = pd.DataFrame([{"Hisse": r["ticker"], "Skor": round(r["score"], 1)} for r in mm_results[:5]])
                        st.dataframe(mm_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sonuç yok")
                
                with col_po:
                    st.markdown("**🔍 Portföy Optimizer (İlk 5)**")
                    if po_results:
                        po_df = pd.DataFrame([{"Hisse": r["ticker"], "Skor": round(r["score"], 1)} for r in po_results[:5]])
                        st.dataframe(po_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sonuç yok")
                
                with col_si:
                    st.markdown("**🏆 Super Investor (İlk 5)**")
                    if si_results:
                        si_df = pd.DataFrame([{"Hisse": r["ticker"], "Skor": round(r["score"], 1)} for r in si_results[:5]])
                        st.dataframe(si_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sonuç yok")
    
    with tab_backtest:
        st.subheader("Ensemble Backtest")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            bt_market = st.selectbox("Piyasa", ["BIST", "USA"], key="ens_bt_market")
        with col2:
            bt_start = st.date_input("Başlangıç", value=date(2026, 1, 1), key="ens_bt_start")
        with col3:
            bt_end = st.date_input("Bitiş", value=date.today(), key="ens_bt_end")
        with col4:
            bt_period = st.selectbox("Rebalance", ["Aylık", "2 Aylık", "3 Aylık"], key="ens_bt_period")
        
        # Super Investor backtest parametreleri
        with st.expander("⚙️ Super Investor Parametreleri", expanded=False):
            bt_si_col1, bt_si_col2, bt_si_col3 = st.columns(3)
            with bt_si_col1:
                bt_si_quality = st.selectbox(
                    "Temel Kalite Seviyesi",
                    ["Kapalı", "Temel", "Sıkı"],
                    index=1,
                    key="ens_bt_si_quality"
                )
            with bt_si_col2:
                bt_si_sort = st.selectbox(
                    "Sıralama Türü",
                    ["RS Score", "Technical Score", "Combined Score", "Institutional Score", "Selection Score", "Timing Score"],
                    index=0,
                    key="ens_bt_si_sort"
                )
            with bt_si_col3:
                bt_si_profile = st.selectbox(
                    "Strateji Profili",
                    ["standard", "quality_compounders", "growth_leaders", "smart_money_breakout", "value_confirmation"],
                    format_func=lambda x: {
                        "standard": "Standart",
                        "quality_compounders": "Kalite Bileşikleri",
                        "growth_leaders": "Büyüme Liderleri",
                        "smart_money_breakout": "Akıllı Para Kırılım",
                        "value_confirmation": "Değer+Onay"
                    }[x],
                    index=0,
                    key="ens_bt_si_profile"
                )
        
        period_months = {"Aylık": 1, "2 Aylık": 2, "3 Aylık": 3}[bt_period]
        
        run_bt = st.button("📈 Backtest Başlat", use_container_width=True)

        if run_bt:
            st.session_state.pop("ens_bt_result", None)
            st.info(f"🔄 Backtest başlatıldı: {bt_start} → {bt_end} | {bt_market} | {bt_period}")
            with st.spinner("Backtest çalışıyor..."):
                dates = pd.date_range(start=pd.Timestamp(bt_start), end=pd.Timestamp(bt_end), freq=f"{period_months}MS")
                if len(dates) == 0:
                    dates = [pd.Timestamp(bt_start)]
                
                tickers = get_market_tickers(bt_market)
                benchmark = get_benchmark(bt_market)
                
                trades = []
                initial_capital = 100000
                current_value = initial_capital
                
                progress = st.progress(0)
                
                st.write(f"📅 Toplam {len(dates)} periyot | Hisse havuzu: {len(tickers)}")
                for i, rebalance_date in enumerate(dates):
                    cutoff = _last_business_day(rebalance_date)
                    
                    mm_res = screen_minervini_style(tickers, cutoff, bt_market, top_n=5)
                    po_res = screen_optimizer_style(tickers, cutoff, bt_market, top_n=5)
                    si_res = screen_superinvestor_style(tickers, cutoff, bt_market, top_n=5, quality=bt_si_quality, sort_by=bt_si_sort, profile=bt_si_profile)
                    
                    ensemble = select_ensemble_portfolio(mm_res, po_res, si_res)
                    selected_tickers = list(ensemble.keys())
                    
                    if i < len(dates) - 1:
                        next_date = dates[i + 1]
                    else:
                        next_date = pd.Timestamp(bt_end)
                    
                    period_return = 0
                    valid_stocks = 0
                    
                    for tk in selected_tickers:
                        try:
                            df_start = get_price_data(tk, (cutoff - pd.Timedelta(days=5)).strftime("%Y-%m-%d"), cutoff.strftime("%Y-%m-%d"))
                            df_end = get_price_data(tk, (next_date - pd.Timedelta(days=5)).strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d"))
                            
                            if df_start is not None and df_end is not None and len(df_start) > 0 and len(df_end) > 0:
                                p_start = float(df_start["Close"].iloc[-1])
                                p_end = float(df_end["Close"].iloc[-1])
                                stock_return = (p_end / p_start - 1)
                                period_return += stock_return
                                valid_stocks += 1
                        except:
                            continue
                    
                    avg_return = period_return / valid_stocks if valid_stocks > 0 else 0
                    current_value = current_value * (1 + avg_return)
                    
                    try:
                        bench_start = get_price_data(benchmark, (cutoff - pd.Timedelta(days=5)).strftime("%Y-%m-%d"), cutoff.strftime("%Y-%m-%d"))
                        bench_end = get_price_data(benchmark, (next_date - pd.Timedelta(days=5)).strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d"))
                        if bench_start is not None and bench_end is not None:
                            bench_ret = float(bench_end["Close"].iloc[-1]) / float(bench_start["Close"].iloc[-1]) - 1
                        else:
                            bench_ret = 0
                    except:
                        bench_ret = 0
                    
                    st.write(f"  → {cutoff.date()}: MM={len(mm_res)} PO={len(po_res)} SI={len(si_res)} | seçilen={len(selected_tickers)} valid={valid_stocks} getiri={avg_return*100:.1f}%")
                    trades.append({
                        "Tarih": cutoff.strftime("%Y-%m-%d"),
                        "Minervini": ", ".join([r["ticker"] for r in mm_res[:3]]),
                        "Optimizer": ", ".join([r["ticker"] for r in po_res[:3]]),
                        "Super Inv": ", ".join([r["ticker"] for r in si_res[:3]]),
                        "Portföy Değeri": round(current_value, 0),
                        "Dönem Getiri %": round(avg_return * 100, 2),
                        "Benchmark %": round(bench_ret * 100, 2)
                    })
                    
                    progress.progress((i + 1) / len(dates))
                
                progress.empty()
                
                total_return = (current_value / initial_capital - 1) * 100
                st.session_state["ens_bt_result"] = {
                    "trades": trades,
                    "total_return": total_return,
                    "current_value": current_value,
                    "initial_capital": initial_capital,
                    "bt_start": str(bt_start),
                    "bt_end": str(bt_end),
                }


        # Sonuçları her rerun'da göster
        if "ens_bt_result" in st.session_state:
            res = st.session_state["ens_bt_result"]
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.metric("Toplam Getiri", f"%{res['total_return']:.1f}")
            with col_r2:
                st.metric("Başlangıç", f"{res['initial_capital']:,.0f} TL")
            with col_r3:
                st.metric("Bitiş", f"{res['current_value']:,.0f} TL")
            trades_df = pd.DataFrame(res["trades"])
            st.dataframe(trades_df, use_container_width=True, hide_index=True)
            excel_buffer = BytesIO()
            trades_df.to_excel(excel_buffer, index=False, engine="openpyxl")
            st.download_button(
                label="📥 Excel Olarak İndir",
                data=excel_buffer.getvalue(),
                file_name=f"ensemble_backtest_{res['bt_start']}_{res['bt_end']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="ens_bt_download"
            )

if __name__ == "__main__":
    main()
