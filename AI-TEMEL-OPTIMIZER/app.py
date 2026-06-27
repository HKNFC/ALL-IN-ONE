"""
AI TEMEL OPTİMİZER
==================
TEMEL OPTİMİZER üzerine inşa edilmiştir.

EK KATMANLAR:
  1. Market Regime Filter  — piyasa rejimi skoru + pozisyon büyüklüğü ayarı
  2. AI Narrative Score    — temel veri değişim hızı / kalite skoru
  3. Portfolio Risk Control — volatilite bazlı pozisyon boyutlandırma + çıkış sinyalleri

BIST: fund_weight = 0.0 — kesinlikle değiştirilmez.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import ta
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import requests, os, sqlite3, json
from io import BytesIO
from typing import Optional, Dict, List, Tuple

# ─── AI Katman importları ─────────────────────────────────────────────────────
from market_regime import calc_market_regime
from ai_score import calc_ai_score
from portfolio_risk import calc_position_sizes, get_exit_signals, calc_sector_exposure

try:
    from data_cache import get_price_data as _dc_get, batch_get_price_data as _dc_batch, init_price_cache as _dc_init
    _dc_init()
    _USE_DATA_CACHE = True
except Exception:
    _USE_DATA_CACHE = False

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

from historical_fundamentals_fmp import (
    get_fundamentals_as_of,
    calc_historical_fund_score,
    prefetch_fundamentals_batch,
    fetch_historical_fundamentals,
)

# ─── Sayfa yapılandırması ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI TEMEL OPTİMİZER | Regime + AI + Risk",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sabitler ─────────────────────────────────────────────────────────────────
DB_PATH        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_temel_optimizer.db")
COMMISSION_RATE = 0.001
SLIPPAGE_BUY   = 1.001
SLIPPAGE_SELL  = 0.999
RANK_WEIGHTS   = {1: 0.40, 2: 0.25, 3: 0.18, 4: 0.10, 5: 0.07}

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE    = "https://financialmodelingprep.com/stable"

# ─── pandas-ta adapter ───────────────────────────────────────────────────────
class _pta:
    @staticmethod
    def sma(series, length=20):   return series.rolling(window=length).mean()
    @staticmethod
    def ema(series, length=20):   return series.ewm(span=length, adjust=False).mean()

pta = _pta()

# ─── Veritabanı ───────────────────────────────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temel_backtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            market TEXT,
            strategy TEXT,
            start_date TEXT,
            end_date TEXT,
            top_n INTEGER,
            rebalance TEXT,
            fund_weight REAL,
            cagr REAL,
            sharpe REAL,
            max_dd REAL,
            total_return REAL,
            params_json TEXT,
            trades_json TEXT,
            period_json TEXT
        )""")
    # Migration: eski DB'lere sütunlar ekle
    for col_def in [
        "ALTER TABLE temel_backtests ADD COLUMN period_json TEXT",
        "ALTER TABLE temel_backtests ADD COLUMN regime_score REAL",
        "ALTER TABLE temel_backtests ADD COLUMN market_exposure REAL",
        "ALTER TABLE temel_backtests ADD COLUMN ai_score REAL",
    ]:
        try:
            conn.execute(col_def)
            conn.commit()
        except Exception:
            pass
    # Tarama geçmişi tablosu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temel_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            scan_date TEXT,
            market TEXT,
            fund_weight REAL,
            top_n INTEGER,
            total_found INTEGER,
            results_json TEXT
        )""")
    conn.commit()
    return conn

def _db_save(rec: dict):
    conn = _get_db()
    conn.execute("""INSERT INTO temel_backtests
        (created_at,market,strategy,start_date,end_date,top_n,rebalance,
         fund_weight,cagr,sharpe,max_dd,total_return,params_json,trades_json,period_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rec.get("market",""), rec.get("strategy",""),
        rec.get("start_date",""), rec.get("end_date",""),
        rec.get("top_n",5), rec.get("rebalance","Aylık"),
        rec.get("fund_weight",0.4),
        rec.get("cagr",0), rec.get("sharpe",0),
        rec.get("max_dd",0), rec.get("total_return",0),
        json.dumps(rec.get("params",{})),
        json.dumps(rec.get("trades",[])),
        json.dumps(rec.get("period_detail",[])),
    ))
    conn.commit()
    conn.close()

def _db_list():
    conn = _get_db()
    rows = conn.execute(
        "SELECT id,created_at,market,strategy,start_date,end_date,top_n,rebalance,fund_weight,cagr,sharpe,max_dd,total_return "
        "FROM temel_backtests ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return rows

def _clean_df_for_display(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Arrow/Streamlit serileştirmesini bozan karışık-tip sütunları düzeltir.
    object dtype sütunlardaki float/int değerler string'e, None/nan → '-'.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda v: "-" if v is None or (isinstance(v, float) and __import__("math").isnan(v))
                else str(v)
            )
    return df

def _db_delete(rid: int):
    conn = _get_db()
    conn.execute("DELETE FROM temel_backtests WHERE id=?", (rid,))
    conn.commit()
    conn.close()

# ── Tarama geçmişi CRUD ───────────────────────────────────────────────────────
def _scan_save(scan_date: str, market: str, fund_weight: float,
               top_n: int, df_results: "pd.DataFrame"):
    conn = _get_db()
    conn.execute("""INSERT INTO temel_scans
        (created_at, scan_date, market, fund_weight, top_n, total_found, results_json)
        VALUES (?,?,?,?,?,?,?)""", (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        scan_date, market, fund_weight, top_n,
        len(df_results),
        df_results.to_json(orient="records", force_ascii=False),
    ))
    conn.commit()
    conn.close()

def _scan_list():
    conn = _get_db()
    rows = conn.execute(
        "SELECT id,created_at,scan_date,market,fund_weight,top_n,total_found "
        "FROM temel_scans ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return rows

def _scan_get(sid: int) -> "pd.DataFrame":
    conn = _get_db()
    row = conn.execute(
        "SELECT results_json FROM temel_scans WHERE id=?", (sid,)
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return pd.DataFrame()
    from io import StringIO as _SIO
    df = pd.read_json(_SIO(row[0]), orient="records")
    return _clean_df_for_display(df)

def _scan_delete(sid: int):
    conn = _get_db()
    conn.execute("DELETE FROM temel_scans WHERE id=?", (sid,))
    conn.commit()
    conn.close()

def _db_get_detail(rid: int) -> dict:
    """Backtest kaydının trades + period_detail verilerini döndürür."""
    conn = _get_db()
    row = conn.execute(
        "SELECT trades_json, period_json FROM temel_backtests WHERE id=?", (rid,)
    ).fetchone()
    conn.close()
    if not row:
        return {"trades": [], "period_detail": []}
    trades  = json.loads(row[0]) if row[0] else []
    periods = json.loads(row[1]) if row[1] else []
    return {"trades": trades, "period_detail": periods}

def _build_period_returns(trades: list, period_detail: list) -> pd.DataFrame:
    """
    Her dönem için hisse bazlı K/Z % tablosu oluşturur.
    SAT kayıtlarından dönem-hisse eşleşmesi yapılır.
    """
    if not trades:
        return pd.DataFrame()
    df_t = pd.DataFrame(trades)
    sat = df_t[df_t["İşlem"] == "SAT"].copy() if "İşlem" in df_t.columns else pd.DataFrame()
    if sat.empty:
        return pd.DataFrame()
    rows = []
    for p in period_detail:
        d_basi = p.get("Dönem Başı","")
        d_sonu = p.get("Dönem Sonu","")
        hisseler = [h.strip() for h in p.get("Seçilen Hisseler","").split(",") if h.strip()]
        for sym in hisseler:
            sym_sat = sat[(sat["Sembol"] == sym) & (sat["Tarih"] >= d_basi) & (sat["Tarih"] <= d_sonu)]
            if not sym_sat.empty:
                kz = sym_sat.iloc[-1]["K/Z (%)"]
                fiyat_alis = sym_sat.iloc[-1].get("Alış Fiyatı", "-")
                fiyat_satis = sym_sat.iloc[-1].get("Fiyat", "-")
            else:
                kz = "—"
                fiyat_alis = "—"
                fiyat_satis = "—"
            rows.append({
                "Dönem Başı": d_basi,
                "Dönem Sonu": d_sonu,
                "Hisse": sym,
                "Alış Fiyatı": fiyat_alis,
                "Satış Fiyatı": fiyat_satis,
                "K/Z (%)": kz,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()

# ─── S&P 500 + MidCap 400 — 913 hisselik statik evren ───────────────────────
_US_913_TICKERS = [
    "A","AA","AAL","AAON","AAPL","ABBV","ABNB","ABT","ACGL","ACI",
    "ACM","ACN","ADBE","ADC","ADI","ADM","ADP","ADSK","AEE","AEIS",
    "AEP","AES","AFG","AFL","AGCO","AHR","AIG","AIT","AIZ","AJG",
    "AKAM","ALB","ALGM","ALGN","ALK","ALL","ALLE","ALLY","ALV","AM",
    "AMAT","AMCR","AMD","AME","AMG","AMGN","AMH","AMKR","AMP","AMT",
    "AMZN","AN","ANET","ANF","AON","AOS","APA","APD","APG","APH",
    "APO","APP","APPF","APTV","AR","ARE","ARES","ARMK","ARW","ARWR",
    "ASB","ASH","ATI","ATO","ATR","AVAV","AVB","AVGO","AVNT","AVT",
    "AVTR","AVY","AWK","AXON","AXP","AXTA","AYI","AZO","BA","BAC",
    "BAH","BALL","BAX","BBWI","BBY","BC","BCO","BDC","BDX","BEN",
    "BF-B","BG","BHF","BIIB","BILL","BIO","BJ","BK","BKH","BKNG",
    "BKR","BLD","BLDR","BLK","BLKB","BMRN","BMY","BR","BRBR","BRK-B",
    "BRKR","BRO","BROS","BRX","BSX","BSY","BURL","BWA","BWXT","BX",
    "BXP","BYD","C","CACI","CAG","CAH","CAR","CARR","CART","CASY",
    "CAT","CAVA","CB","CBOE","CBRE","CBSH","CBT","CCI","CCK","CCL",
    "CDNS","CDP","CDW","CEG","CELH","CF","CFG","CFR","CG","CGNX",
    "CHD","CHDN","CHE","CHH","CHRD","CHRW","CHTR","CHWY","CI","CIEN",
    "CINF","CL","CLF","CLH","CLX","CMC","CMCSA","CME","CMG","CMI",
    "CMS","CNC","CNH","CNM","CNO","CNP","CNX","CNXC","COF","COHR",
    "COIN","COKE","COLB","COLM","COO","COP","COR","COST","COTY","CPAY",
    "CPB","CPRI","CPRT","CPT","CR","CRBG","CRH","CRL","CRM","CROX",
    "CRS","CRUS","CRWD","CSCO","CSGP","CSL","CSX","CTAS","CTRA","CTRE",
    "CTSH","CTVA","CUBE","CUZ","CVLT","CVNA","CVS","CVX","CW","CXT",
    "CYTK","D","DAL","DAR","DASH","DBX","DCI","DD","DDOG","DE",
    "DECK","DELL","DG","DGX","DHI","DHR","DINO","DIS","DKS","DLB",
    "DLR","DLTR","DOC","DOCS","DOCU","DOV","DOW","DPZ","DRI","DT",
    "DTE","DTM","DUK","DUOL","DVA","DVN","DXCM","DY","EA","EBAY",
    "ECL","ED","EEFT","EFX","EG","EGP","EHC","EIX","EL","ELAN",
    "ELF","ELS","ELV","EME","EMR","ENS","ENSG","ENTG","EOG","EPAM",
    "EPR","EQH","EQIX","EQR","EQT","ERIE","ES","ESAB","ESNT","ESS",
    "ETN","ETR","EVR","EVRG","EW","EWBC","EXC","EXE","EXEL","EXLS",
    "EXP","EXPD","EXPE","EXPO","EXR","F","FAF","FANG","FAST","FBIN",
    "FCFS","FCN","FCX","FDS","FDX","FE","FFIN","FFIV","FHI","FHN",
    "FICO","FIS","FISV","FITB","FIVE","FIX","FLEX","FLG","FLO","FLR",
    "FLS","FN","FNB","FND","FNF","FOUR","FOX","FOXA","FR","FRT",
    "FSLR","FTI","FTNT","FTV","G","GAP","GATX","GBCI","GD","GDDY",
    "GE","GEF","GEHC","GEN","GEV","GGG","GHC","GILD","GIS","GL",
    "GLPI","GLW","GM","GME","GMED","GNRC","GNTX","GOOG","GOOGL","GPC",
    "GPK","GPN","GRMN","GS","GT","GTLS","GWRE","GWW","GXO","H",
    "HAE","HAL","HALO","HAS","HBAN","HCA","HD","HGV","HIG","HII",
    "HIMS","HL","HLI","HLNE","HLT","HOG","HOLX","HOMB","HON","HOOD",
    "HPE","HPQ","HQY","HR","HRB","HRL","HSIC","HST","HSY","HUBB",
    "HUM","HWC","HWM","HXL","IBKR","IBM","IBOC","ICE","IDA","IDCC",
    "IDXX","IEX","IFF","ILMN","INCY","INGR","INTC","INTU","INVH","IP",
    "IPGP","IQV","IR","IRM","IRT","ISRG","IT","ITT","ITW","IVZ",
    "J","JAZZ","JBHT","JBL","JCI","JEF","JHG","JKHY","JLL","JNJ",
    "JPM","KBH","KBR","KD","KDP","KEX","KEY","KEYS","KHC","KIM",
    "KKR","KLAC","KMB","KMI","KNF","KNSL","KNX","KO","KR","KRC",
    "KRG","KTOS","KVUE","L","LAD","LAMR","LDOS","LEA","LECO","LEN",
    "LFUS","LH","LHX","LII","LIN","LITE","LIVN","LLY","LMT","LNT",
    "LNTH","LOPE","LOW","LPX","LRCX","LSCC","LSTR","LULU","LUV","LVS",
    "LYB","LYV","M","MA","MAA","MANH","MAR","MAS","MASI","MAT",
    "MCD","MCHP","MCK","MCO","MDLZ","MDT","MEDP","MET","META","MGM",
    "MIDD","MKC","MKSI","MLI","MLM","MMM","MMS","MNST","MO","MOG-A",
    "MORN","MOS","MP","MPC","MPWR","MRK","MRNA","MRSH","MS","MSA",
    "MSCI","MSFT","MSI","MSM","MTB","MTD","MTDR","MTG","MTN","MTSI",
    "MTZ","MU","MUR","MUSA","NBIX","NCLH","NDAQ","NDSN","NEE",
    "NEM","NEU","NFG","NFLX","NI","NJR","NKE","NLY","NNN","NOC",
    "NOV","NOVT","NOW","NRG","NSA","NSC","NTAP","NTNX","NTRS","NUE",
    "NVDA","NVR","NVST","NVT","NWE","NWS","NWSA","NXPI","NXST","NXT",
    "NYT","O","OC","ODFL","OGE","OGS","OHI","OKE","OKTA","OLED",
    "OLLI","OLN","OMC","ON","ONB","ONTO","OPCH","ORA","ORCL","ORI",
    "ORLY","OSK","OTIS","OVV","OXY","OZK","PAG","PANW","PATH","PAYX",
    "PB","PBF","PCAR","PCG","PCTY","PEG","PEGA","PEN","PEP","PFE",
    "PFG","PFGC","PG","PGR","PH","PHM","PII","PINS","PK","PKG",
    "PLD","PLNT","PLTR","PM","PNC","PNFP","PNR","PNW","PODD","POOL",
    "POR","POST","PPC","PPG","PPL","PR","PRI","PRU","PSA","PSKY",
    "PSN","PSTG","PSX","PTC","PVH","PWR","PYPL","Q","QCOM","QLYS",
    "R","RBA","RBC","RCL","REG","REGN","REXR","RF","RGA","RGEN",
    "RGLD","RH","RJF","RL","RLI","RMBS","RMD","RNR","ROIV","ROK",
    "ROL","ROP","ROST","RPM","RRC","RRX","RS","RSG","RTX","RVTY",
    "RYAN","RYN","SAIA","SAIC","SAM","SARO","SATS","SBAC","SBRA","SBUX",
    "SCHW","SCI","SEIC","SF","SFM","SGI","SHC","SHW","SIGI","SITM",
    "SJM","SLAB","SLB","SLGN","SLM","SMCI","SMG","SNA","SNDK","SNPS",
    "SNX","SO","SOLS","SOLV","SON","SPG","SPGI","SPXC","SR","SRE",
    "SSB","SSD","ST","STAG","STE","STLD","STRL","STT","STWD","STX",
    "STZ","SW","SWK","SWKS","SWX","SYF","SYK","SYNA","SYY","T",
    "TAP","TCBI","TDG","TDY","TECH","TEL","TER","TEX","TFC","TGT",
    "THC","THG","THO","TJX","TKO","TKR","TLN","TMHC","TMO","TMUS",
    "TNL","TOL","TPL","TPR","TREX","TRGP","TRMB","TROW","TRU","TRV",
    "TSCO","TSLA","TSN","TT","TTC","TTD","TTEK","TTMI","TTWO","TWLO",
    "TXN","TXNM","TXRH","TXT","TYL","UAL","UBER","UBSI","UDR","UFPI",
    "UGI","UHS","ULS","ULTA","UMBF","UNH","UNM","UNP","UPS","URI",
    "USB","USFD","UTHR","V","VAL","VC","VFC","VICI","VICR","VLO",
    "VLTO","VLY","VMC","VMI","VNO","VNOM","VNT","VOYA","VRSK","VRSN",
    "VRT","VRTX","VST","VTR","VTRS","VVV","VZ","WAB","WAL","WAT",
    "WBD","WBS","WCC","WDAY","WDC","WEC","WELL","WEX","WFC","WFRD",
    "WH","WHR","WING","WLK","WM","WMB","WMG","WMS","WMT","WPC",
    "WRB","WSM","WSO","WST","WTFC","WTRG","WTS","WTW","WWD","WY",
    "WYNN","XEL","XOM","XPO","XRAY","XYL","YETI","YUM","ZBH",
    "ZBRA","ZION","ZTS",
    # Ek Nasdaq/Growth hisseleri (toplam ~913)
    "ADYEY","AFRM","AI","AIOT","AKRO","ALKS","ALNY","AMPL","APPN","ASAN",
    "ASGN","ATMU","ATOM","AZEK","BCPC","BFAM","BGFV","BJRI","BOWL","BRZE",
]

# ─── Hisse evrenini getir ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _get_sp500():
    """Wikipedia'dan S&P 500 listesi çeker; hata durumunda 913 hisselik statik listeyi döndürür."""
    try:
        df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        return [t.replace(".", "-") for t in df["Symbol"].tolist()]
    except Exception:
        return _US_913_TICKERS

@st.cache_data(ttl=3600)
def _get_bist():
    try:
        url = f"{FMP_BASE}/stock/list?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        all_stocks = r.json()
        return [s["symbol"] for s in all_stocks if s.get("symbol","").endswith(".IS")]
    except Exception:
        return ["GARAN.IS","AKBNK.IS","ISCTR.IS","THYAO.IS","BIMAS.IS","ASELS.IS","KCHOL.IS","EREGL.IS"]

def _get_universe(market: str) -> list:
    if "BIST" in market:
        return _get_bist()
    return list(_US_913_TICKERS)

# ─── Sütun adlarını normalize et ─────────────────────────────────────────────
def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex veya büyük-küçük harf farklarını normalize eder."""
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]).lower().strip() for c in df.columns]
    else:
        df.columns = [str(c).lower().strip() for c in df.columns]
    if "adj close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"adj close": "close"})
    return df

# ─── Fiyat verisi ─────────────────────────────────────────────────────────────
def _get_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    if _USE_DATA_CACHE:
        try:
            df = _dc_get(ticker, start, end)
            if df is not None and not df.empty:
                return _normalize_cols(df)
        except Exception:
            pass
    try:
        df = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True, actions=False)
        if df.empty:
            return pd.DataFrame()
        df = _normalize_cols(df)
        return df
    except Exception:
        return pd.DataFrame()

def _batch_prices(tickers: list, start: str, end: str,
                  progress_cb=None) -> dict:
    result = {}
    if _USE_DATA_CACHE:
        try:
            raw_dc = _dc_batch(tickers, start, end, progress_callback=progress_cb)
            for k, v in raw_dc.items():
                if v is not None and not v.empty:
                    result[k] = _normalize_cols(v.copy())
            if result:
                return result
        except Exception:
            pass
    chunk = 100
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i+chunk]
        try:
            raw = yf.download(" ".join(batch), start=start, end=end,
                              progress=False, auto_adjust=True,
                              actions=False, group_by="ticker")
            for t in batch:
                try:
                    if len(batch) > 1:
                        df = raw[t].dropna(how="all") if t in raw.columns.get_level_values(0) else pd.DataFrame()
                    else:
                        df = raw.dropna(how="all")
                    if not df.empty:
                        df = _normalize_cols(df.copy())
                        result[t] = df
                except Exception:
                    pass
        except Exception:
            pass
        if progress_cb:
            progress_cb(min(1.0, (i + chunk) / len(tickers)), f"Fiyat verisi indiriliyor ({i+chunk}/{len(tickers)})")
    return result

# ─── Rebalance tarihleri ──────────────────────────────────────────────────────
def _rebalance_dates(start: datetime, end: datetime, freq: str) -> list:
    dates = []
    d = start
    if freq == "15 Günlük":
        while d <= end:
            dates.append(d)
            d += timedelta(days=15)
    elif freq == "Çeyreklik":
        while d <= end:
            dates.append(d)
            d += timedelta(days=91)
    else:  # Aylık
        while d <= end:
            dates.append(d)
            m, y = d.month + 1, d.year
            if m > 12:
                m, y = 1, y + 1
            d = d.replace(year=y, month=m)
    if not dates or dates[-1] < end:
        dates.append(end)
    return dates

# ─── Teknik skor ──────────────────────────────────────────────────────────────
def _calc_tech_score(ticker: str, df: pd.DataFrame,
                     bench_close: pd.Series,
                     bench_ann_vol: float = None) -> Optional[Dict]:
    try:
        close  = df["close"].astype(float)
        volume = df.get("volume", pd.Series(dtype=float)).astype(float)
    except Exception:
        return None

    if len(close) < 130:
        return None

    last_price = float(close.iloc[-1])

    sma50  = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if last_price < sma50:
        return None
    if sma200 and last_price < sma200 * 0.97:
        return None

    def _excess(n):
        if len(close) <= n or len(bench_close) <= n:
            return 0.0
        stock_r = float(close.iloc[-1] / close.iloc[-n] - 1) * 100
        bench_r = float(bench_close.iloc[-1] / bench_close.iloc[-n] - 1) * 100
        return stock_r - bench_r

    e1m, e3m, e6m, e12m = _excess(21), _excess(63), _excess(126), _excess(252)

    if len(close) > 126:
        ret6m_abs = float(close.iloc[-1] / close.iloc[-126] - 1) * 100
        if ret6m_abs <= 0:
            return None

    if e3m < -5 and e6m < -10:
        return None

    if len(volume) >= 20:
        avg_vol20 = float(volume.iloc[-20:].mean())
        min_vol = 10000 if ticker.endswith(".IS") else 200000
        if avg_vol20 < min_vol:
            return None

    adx_bonus = 0.0
    try:
        hi = close.values; lo = close.values; cl = close.values
        if "high" in df.columns and "low" in df.columns:
            hi = df["high"].astype(float).values
            lo = df["low"].astype(float).values
        tr = np.maximum(hi[1:] - lo[1:],
             np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
        atr14 = pd.Series(tr).ewm(span=14, adjust=False).mean()
        dm_pos = np.where((hi[1:]-hi[:-1]) > (lo[:-1]-lo[1:]), np.maximum(hi[1:]-hi[:-1],0), 0)
        dm_neg = np.where((lo[:-1]-lo[1:]) > (hi[1:]-hi[:-1]), np.maximum(lo[:-1]-lo[1:],0), 0)
        di_pos = pd.Series(dm_pos).ewm(span=14,adjust=False).mean() / (atr14+1e-9) * 100
        di_neg = pd.Series(dm_neg).ewm(span=14,adjust=False).mean() / (atr14+1e-9) * 100
        dx     = np.abs(di_pos-di_neg) / (di_pos+di_neg+1e-9) * 100
        adx    = float(pd.Series(dx).ewm(span=14,adjust=False).mean().iloc[-1])
        if adx >= 35:   adx_bonus = 20
        elif adx >= 25: adx_bonus = 12
        elif adx >= 20: adx_bonus = 5
    except Exception:
        pass

    accel = 0.0
    if e1m > e3m > 0:
        accel += min(25.0, (e1m - e3m) * 0.7)
    if e3m > e6m > 0:
        accel += min(15.0, (e3m - e6m) * 0.4)

    lk = min(252, len(close)-1)
    h52 = float(close.iloc[-lk:].max())
    h52_bonus = 0.0
    if h52 > 0:
        d52 = (last_price / h52 - 1) * 100
        if d52 >= -3:    h52_bonus = 25
        elif d52 >= -10: h52_bonus = 15
        elif d52 >= -20: h52_bonus = 7

    sma200_bonus = 0.0
    if sma200 and sma200 > 0:
        gap = (last_price / sma200 - 1) * 100
        if gap >= 20:   sma200_bonus = 20
        elif gap >= 10: sma200_bonus = 12
        elif gap >= 0:  sma200_bonus = 5

    vol_bonus = 0.0
    if len(volume) >= 20:
        v5 = float(volume.iloc[-5:].mean())
        v20 = float(volume.iloc[-20:].mean())
        if v20 > 0:
            vr = v5 / v20
            if vr > 2.5:   vol_bonus = 18
            elif vr > 1.8: vol_bonus = 10
            elif vr > 1.3: vol_bonus = 4

    vol_penalty = 0.0
    dr = close.pct_change().dropna()
    if len(dr) >= 20:
        ann_vol = float(dr.std()) * np.sqrt(252)
        if bench_ann_vol and bench_ann_vol > 0:
            vr = ann_vol / bench_ann_vol
            if vr > 2.5:
                vol_penalty = min(0.45, (vr-2.5) * 0.20)

    momentum = e12m*0.30 + e6m*0.30 + e3m*0.25 + e1m*0.15
    bonus    = accel + h52_bonus + sma200_bonus + vol_bonus + adx_bonus

    return {
        "Sembol"      : ticker,
        "rs_slope"    : momentum,
        "vol_penalty" : vol_penalty,
        "_bonus"      : bonus,
        "_excess_1m"  : e1m,
        "_excess_3m"  : e3m,
        "_excess_6m"  : e6m,
        "_excess_12m" : e12m,
        "RS Eğimi"    : round(e6m, 2),
    }


# ─── Temel skor (USA için — BIST'te çağrılmaz) ───────────────────────────────
def _get_hist_fund_score(ticker: str, as_of_date: str,
                         strategy: str = "Alfa") -> Tuple[Optional[float], dict]:
    """
    Look-ahead bias'sız tarihsel temel skor.
    Temel veri yoksa (None, {}) döner.
    """
    if ticker.endswith(".IS"):
        return None, {}
    try:
        fund = get_fundamentals_as_of(ticker, as_of_date)
        if fund is None:
            return None, {}
        return calc_historical_fund_score(fund, strategy)
    except Exception:
        return None, {}


# ─── AI Score hesaplama ───────────────────────────────────────────────────────
def _calc_ai_score_for_ticker(ticker: str, as_of_date: str, prev_date: str) -> tuple:
    """AI score için mevcut ve önceki dönem temel verisini çeker."""
    if ticker.endswith(".IS"):
        return 50.0, {}  # BIST için proxy yok — nötr
    try:
        curr = get_fundamentals_as_of(ticker, as_of_date)
        prev = get_fundamentals_as_of(ticker, prev_date)
        return calc_ai_score(curr, prev)
    except Exception:
        return 50.0, {}


# ─── Metrik hesaplama ─────────────────────────────────────────────────────────
def _calc_metrics(equity: pd.Series, bench: pd.Series, initial: float) -> dict:
    if equity.empty:
        return {}
    eq = equity.sort_index()
    total_return = (eq.iloc[-1] / initial - 1) * 100
    days = (eq.index[-1] - eq.index[0]).days or 1
    years = days / 365.25
    cagr = ((eq.iloc[-1] / initial) ** (1 / years) - 1) * 100 if years > 0 else 0

    dr = eq.pct_change().dropna()
    sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if dr.std() > 0 else 0
    neg = dr[dr < 0]
    sortino = float(dr.mean() / neg.std() * np.sqrt(252)) if len(neg) > 1 and neg.std() > 0 else 0
    roll_max = eq.cummax()
    dd = (eq - roll_max) / roll_max
    max_dd = float(dd.min() * 100)
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0

    bench_aligned = bench.reindex(eq.index, method="ffill").dropna()
    bench_total = (bench_aligned.iloc[-1] / bench_aligned.iloc[0] - 1) * 100 if len(bench_aligned) > 1 else 0
    excess = total_return - bench_total

    return {
        "Toplam Getiri (%)": round(total_return, 2),
        "CAGR (%)": round(cagr, 2),
        "Sharpe": round(sharpe, 3),
        "Sortino": round(sortino, 3),
        "Max Drawdown (%)": round(max_dd, 2),
        "Calmar": round(calmar, 3),
        "Benchmark Getirisi (%)": round(bench_total, 2),
        "Benchmark Üstü Getiri (%)": round(excess, 2),
    }


# ─── AI BACKTEST ──────────────────────────────────────────────────────────────
def run_ai_temel_backtest(
    tickers: list,
    market: str,
    start_dt: datetime,
    end_dt: datetime,
    top_n: int,
    freq: str,
    fund_weight: float,
    initial_capital: float,
    use_regime: bool = True,
    use_ai: bool = True,
    use_risk_control: bool = True,
    exit_sensitivity: str = "Normal",
    progress_ph=None,
) -> dict:
    """
    AI Temel Optimizer backtesti.
    USA: adjusted_final_score = tech*w1 + fund*w2 + ai*w3 + regime*w4
    BIST: fund_weight zorla 0.0
    """
    is_bist = "BIST" in market
    fw = 0.0 if is_bist else fund_weight

    bench_sym = "XU100.IS" if is_bist else "SPY"
    start_str = (start_dt - timedelta(days=400)).strftime("%Y-%m-%d")
    end_str   = end_dt.strftime("%Y-%m-%d")

    # ── Fiyat verisi ─────────────────────────────────────────────────────────
    def _pcb(pct, txt):
        if progress_ph:
            progress_ph.progress(min(pct*0.30, 0.30), text=f"[1/3] {txt}")

    if progress_ph:
        progress_ph.progress(0.02, text="[1/3] Fiyat verisi indiriliyor...")
    all_data = _batch_prices(tickers, start_str, end_str, progress_cb=_pcb)

    bench_df = _get_prices(bench_sym, start_str, end_str)
    bench_close = bench_df["close"] if not bench_df.empty else pd.Series(dtype=float)

    # ── Tarihsel temel veri ön yükleme (USA) ────────────────────────────────
    if fw > 0 and not is_bist:
        if progress_ph:
            progress_ph.progress(0.30, text="[2/3] Tarihsel temel veri indiriliyor (FMP)...")

        def _fundcb(pct, txt):
            if progress_ph:
                progress_ph.progress(0.30 + pct*0.30, text=f"[2/3] {txt}")

        usa_tickers = [t for t in tickers if not t.endswith(".IS")]
        prefetch_fundamentals_batch(usa_tickers, progress_callback=_fundcb)
    else:
        if progress_ph:
            progress_ph.progress(0.60, text="[2/3] BIST — temel veri atlandı (fund_weight=0)")

    # ── Rebalance döngüsü ────────────────────────────────────────────────────
    reb_dates   = _rebalance_dates(start_dt, end_dt, freq)
    total_p     = len(reb_dates) - 1
    cash        = float(initial_capital)
    holdings    = {}
    equity_curve = {}
    trade_log   = []
    period_detail = []

    bench_ann_vol = None
    if len(bench_close) >= 60:
        b_ret = bench_close.pct_change().dropna()
        if len(b_ret) >= 20:
            bench_ann_vol = float(b_ret.std()) * np.sqrt(252)

    def _pval(dt):
        total = cash
        for sym, h in holdings.items():
            sl = all_data.get(sym, pd.DataFrame())
            sl = sl[sl.index <= dt] if not sl.empty else sl
            _cl = sl["close"].dropna() if not sl.empty else pd.Series(dtype=float)
            p  = float(_cl.iloc[-1]) if not _cl.empty else h.get("buy_price", 0)
            total += h["shares"] * p
        return total

    def _sell(sym, dt, reason):
        nonlocal cash
        h = holdings.get(sym)
        if not h:
            return
        sl = all_data.get(sym, pd.DataFrame())
        sl = sl[sl.index <= dt] if not sl.empty else sl
        _cl = sl["close"].dropna() if not sl.empty else pd.Series(dtype=float)
        if _cl.empty:
            del holdings[sym]
            return
        raw_p = float(_cl.iloc[-1])
        adj_p = raw_p * SLIPPAGE_SELL
        gross = h["shares"] * adj_p
        net   = gross * (1 - COMMISSION_RATE)
        pnl_pct = (raw_p / h["buy_price"] - 1) * 100 if h.get("buy_price") else 0
        cash += net
        trade_log.append({
            "Tarih": dt.strftime("%Y-%m-%d"), "İşlem": "SAT", "Sembol": sym,
            "Fiyat": round(raw_p,2), "Alış Fiyatı": round(h["buy_price"],2),
            "Adet": round(h["shares"],4),
            "K/Z (%)": round(pnl_pct,2),
            "Bakiye": round(_pval(dt),2), "Açıklama": reason,
        })
        del holdings[sym]

    _bt_start = time.time()
    for pidx in range(total_p):
        reb   = reb_dates[pidx]
        n_reb = reb_dates[pidx + 1]

        elapsed = time.time() - _bt_start
        pct = 0.60 + (pidx+1)/total_p * 0.38
        eta = ""
        if pidx > 0 and elapsed > 0:
            rem = elapsed/pidx * (total_p - pidx)
            eta = f" — Kalan: ~{int(rem)}s" if rem < 60 else f" — Kalan: ~{int(rem/60)}dk"
        if progress_ph:
            progress_ph.progress(min(pct, 0.98),
                text=f"[3/3] Periyot {pidx+1}/{total_p}: {reb.strftime('%Y-%m-%d')}{eta}")

        b_slice = bench_close[bench_close.index <= reb]
        b_ann   = None
        if len(b_slice) >= 60:
            br = b_slice.pct_change().dropna()
            b_ann = float(br.std()) * np.sqrt(252) if len(br) >= 20 else None

        # ── Market Regime ────────────────────────────────────────────────────
        if use_regime:
            try:
                regime_result = calc_market_regime(reb, market)
                regime_score  = regime_result.get("regime_score", 75.0)
                market_exposure = regime_result.get("market_exposure", 1.0)
            except Exception:
                regime_score  = 75.0
                market_exposure = 1.0
        else:
            regime_score  = 75.0
            market_exposure = 1.0

        # ── Hisseleri skorla ─────────────────────────────────────────────────
        def _score_one(ticker):
            df = all_data.get(ticker)
            if df is None or df.empty:
                return None
            sl = df[df.index <= reb]
            if len(sl) < 130:
                return None
            return _calc_tech_score(ticker, sl, b_slice, bench_ann_vol=b_ann)

        with ThreadPoolExecutor(max_workers=8) as ex:
            raw_results = list(ex.map(_score_one, tickers))

        valid = [r for r in raw_results if r is not None]
        if not valid:
            equity_curve[reb] = _pval(reb)
            continue

        # RS normalize
        all_rs = [r["rs_slope"] for r in valid]
        max_rs = float(np.percentile(all_rs, 95)) if len(all_rs) >= 10 else max(all_rs)
        max_rs = max(max_rs, 1e-9)
        for r in valid:
            rs_norm    = (r["rs_slope"] / max_rs * 100)
            tech_score = max(0.0, min(200.0,
                (rs_norm + r["_bonus"]) * (1 - r.get("vol_penalty", 0))
            ))
            r["tech_score"] = round(tech_score, 2)

        # Temel skor + AI skor + Final skor hesapla
        reb_date_str  = reb.strftime("%Y-%m-%d")
        prev_date_str = (reb - pd.Timedelta(days=90)).strftime("%Y-%m-%d")

        for r in valid:
            sym = r["Sembol"]

            # Temel skor (USA, look-ahead bias'sız)
            fund_sc = None
            if fw > 0 and not sym.endswith(".IS"):
                fund_sc_val, _ = _get_hist_fund_score(sym, reb_date_str)
                if fund_sc_val is not None:
                    r["fund_score"] = round(fund_sc_val, 2)
                    fund_sc = fund_sc_val
                else:
                    r["fund_score"] = "-"
            else:
                r["fund_score"] = "-"

            # AI skor
            if use_ai:
                ai_sc, _ = _calc_ai_score_for_ticker(sym, reb_date_str, prev_date_str)
            else:
                ai_sc = 50.0

            # Final skor formülü
            tech_score = r["tech_score"]
            if is_bist:
                if use_ai:
                    base_score = tech_score * 0.70 + ai_sc * 0.15 + regime_score * 0.15
                else:
                    base_score = tech_score * 0.85 + regime_score * 0.15
            else:
                if fund_sc is not None and use_ai:
                    base_score = tech_score*0.45 + fund_sc*0.25 + ai_sc*0.15 + regime_score*0.15
                elif fund_sc is not None and not use_ai:
                    base_score = tech_score*0.55 + fund_sc*0.30 + regime_score*0.15
                elif fund_sc is None and use_ai:
                    base_score = tech_score*0.60 + ai_sc*0.25 + regime_score*0.15
                else:
                    base_score = tech_score*0.75 + regime_score*0.25

            adjusted_final_score = base_score * market_exposure
            r["adjusted_final_score"] = round(adjusted_final_score, 2)
            r["regime_score"]         = round(regime_score, 1)
            r["market_exposure"]      = market_exposure
            r["ai_score"]             = round(ai_sc, 1)
            # Geriye dönük uyumluluk için final_score da set et
            r["final_score"]          = r["adjusted_final_score"]

        # Sıralama: adjusted_final_score'a göre
        valid.sort(key=lambda x: x["adjusted_final_score"], reverse=True)
        selected = valid[:top_n]
        new_syms = [s["Sembol"] for s in selected]

        # ── Çıkış sinyalleri (risk control) ─────────────────────────────────
        if use_risk_control:
            for sym in list(holdings):
                df_sym = all_data.get(sym, pd.DataFrame())
                sl_sym = df_sym[df_sym.index <= reb] if not df_sym.empty else df_sym
                # Excess return hesapla
                excess_3m = 0.0
                excess_6m = 0.0
                if not sl_sym.empty and len(sl_sym) >= 63:
                    try:
                        c = sl_sym["close"]
                        stock_3m = float(c.iloc[-1] / c.iloc[-63] - 1) * 100
                        bench_3m_sl = b_slice.iloc[-63:] if len(b_slice) >= 63 else b_slice
                        bench_3m = float(bench_3m_sl.iloc[-1] / bench_3m_sl.iloc[0] - 1) * 100 if len(bench_3m_sl) > 1 else 0.0
                        excess_3m = stock_3m - bench_3m
                    except Exception:
                        pass
                if not sl_sym.empty and len(sl_sym) >= 126:
                    try:
                        c = sl_sym["close"]
                        stock_6m = float(c.iloc[-1] / c.iloc[-126] - 1) * 100
                        bench_6m_sl = b_slice.iloc[-126:] if len(b_slice) >= 126 else b_slice
                        bench_6m = float(bench_6m_sl.iloc[-1] / bench_6m_sl.iloc[0] - 1) * 100 if len(bench_6m_sl) > 1 else 0.0
                        excess_6m = stock_6m - bench_6m
                    except Exception:
                        pass
                try:
                    exit_sig = get_exit_signals(sym, sl_sym, bench_ann_vol or 0.15, excess_3m, excess_6m)
                    if exit_sig.get("signal") == "EXIT":
                        _sell(sym, reb, f"Çıkış: {exit_sig.get('reason', 'Risk sinyali')}")
                except Exception:
                    pass

        # Sat (portföyden çıkarılanlar)
        for sym in list(holdings):
            if sym not in new_syms:
                _sell(sym, reb, "Portföyden çıkarıldı")

        # ── Ağırlıklar ───────────────────────────────────────────────────────
        total_val = _pval(reb)

        if use_risk_control:
            # Volatilite bazlı pozisyon boyutlandırma
            stock_vols = {}
            for s in selected:
                sym = s["Sembol"]
                df_s = all_data.get(sym, pd.DataFrame())
                sl = df_s[df_s.index <= reb] if not df_s.empty else df_s
                if not sl.empty and len(sl) >= 60:
                    rets = sl["close"].pct_change().dropna()
                    stock_vols[sym] = float(rets.std()) * np.sqrt(252)
                else:
                    stock_vols[sym] = bench_ann_vol or 0.15

            sector_map = {s["Sembol"]: "Unknown" for s in selected}
            try:
                weights = calc_position_sizes(
                    [{"ticker": s["Sembol"], "adjusted_final_score": s["adjusted_final_score"]} for s in selected],
                    bench_ann_vol or 0.15,
                    stock_vols,
                    sector_map,
                )
                allocs = {sym: weights.get(sym, 1.0/len(new_syms)) * total_val for sym in new_syms}
            except Exception:
                # Fallback: rank weights
                n = len(new_syms)
                if n <= 5:
                    rw = [RANK_WEIGHTS.get(i+1, 1/n) for i in range(n)]
                else:
                    step = 1 / (n*(n+1)/2)
                    rw = [(n-i)*step for i in range(n)]
                ws = sum(rw)
                allocs = {sym: (w/ws)*total_val for sym, w in zip(new_syms, rw)}
        else:
            n = len(new_syms)
            if n <= 5:
                rw = [RANK_WEIGHTS.get(i+1, 1/n) for i in range(n)]
            else:
                step = 1 / (n*(n+1)/2)
                rw = [(n-i)*step for i in range(n)]
            ws = sum(rw)
            allocs = {sym: (w/ws)*total_val for sym, w in zip(new_syms, rw)}

        # ── Alım ─────────────────────────────────────────────────────────────
        for sym in new_syms:
            sl = all_data.get(sym, pd.DataFrame())
            sl = sl[sl.index <= reb] if not sl.empty else sl
            _cl = sl["close"].dropna() if not sl.empty else pd.Series(dtype=float)
            if _cl.empty:
                continue
            raw_p = float(_cl.iloc[-1])
            if raw_p <= 0 or pd.isna(raw_p):
                continue
            adj_p  = raw_p * SLIPPAGE_BUY
            alloc  = min(allocs.get(sym, 0), cash)
            if alloc <= 1:
                continue
            net    = alloc * (1 - COMMISSION_RATE)
            shares = net / adj_p
            if sym in holdings:
                old = holdings[sym]
                new_total = old["shares"] + shares
                new_bp = (old["shares"]*old["buy_price"] + shares*raw_p) / new_total
                holdings[sym] = {"shares": new_total, "buy_price": new_bp, "buy_date": reb_date_str}
            else:
                holdings[sym] = {"shares": shares, "buy_price": raw_p, "buy_date": reb_date_str}
            cash -= alloc
            score_info = next((s for s in selected if s["Sembol"]==sym), {})
            trade_log.append({
                "Tarih": reb_date_str, "İşlem": "AL", "Sembol": sym,
                "Fiyat": round(raw_p,2), "Alış Fiyatı": round(raw_p,2),
                "Adet": round(shares,4), "K/Z (%)": 0,
                "Bakiye": round(_pval(reb),2),
                "Teknik Skor"        : score_info.get("tech_score","-"),
                "Temel Skor"         : score_info.get("fund_score","-"),
                "AI Skoru"           : score_info.get("ai_score","-"),
                "Regime Skoru"       : round(regime_score, 1),
                "Market Exposure"    : market_exposure,
                "Adjusted Final Skor": score_info.get("adjusted_final_score","-"),
                "Açıklama"           : "Portföye eklendi",
            })

        equity_curve[reb] = _pval(reb)
        period_detail.append({
            "Dönem Başı"      : reb.strftime("%Y-%m-%d"),
            "Dönem Sonu"      : n_reb.strftime("%Y-%m-%d"),
            "Seçilen Hisseler": ", ".join(new_syms),
            "Temel Ağırlık"   : f"%{int(fw*100)}",
            "Regime Skoru"    : round(regime_score, 1),
            "Market Exposure" : f"%{int(market_exposure*100)}",
            "Nakit Oranı"     : f"%{int((cash/_pval(reb))*100)}" if _pval(reb) > 0 else "-%",
        })

    # Final satış
    if reb_dates:
        fd = reb_dates[-1]
        for sym in list(holdings):
            _sell(sym, fd, "Backtest sonu")
        equity_curve[fd] = cash

    eq_series  = pd.Series(equity_curve).sort_index()
    bench_algn = bench_close.reindex(eq_series.index, method="ffill")
    metrics    = _calc_metrics(eq_series, bench_algn, initial_capital)

    return {
        "equity"       : eq_series,
        "bench"        : bench_algn,
        "metrics"      : metrics,
        "trades"       : trade_log,
        "period_detail": period_detail,
    }


# ─── AI TARAMA ────────────────────────────────────────────────────────────────
def run_ai_temel_screening(
    tickers: list,
    market: str,
    fund_weight: float,
    use_regime: bool = True,
    use_ai: bool = True,
    as_of_date: Optional[datetime] = None,
    progress_ph=None,
) -> pd.DataFrame:
    is_bist = "BIST" in market
    fw = 0.0 if is_bist else fund_weight
    bench_sym = "XU100.IS" if is_bist else "SPY"

    as_of   = as_of_date if as_of_date else datetime.now()
    end_s   = as_of.strftime("%Y-%m-%d")
    start_s = (as_of - timedelta(days=600)).strftime("%Y-%m-%d")
    bench_start_s = (as_of - timedelta(days=760)).strftime("%Y-%m-%d")

    if progress_ph:
        progress_ph.progress(0.05, "Fiyat verisi indiriliyor...")
    all_data = _batch_prices(tickers, start_s, end_s)

    bench_long_df = _get_prices(bench_sym, bench_start_s, end_s)
    bench_long    = bench_long_df[bench_long_df.index <= as_of]["close"] if not bench_long_df.empty else pd.Series(dtype=float)

    bench_df = _get_prices(bench_sym, start_s, end_s)
    bench_df_sliced = bench_df[bench_df.index <= as_of] if not bench_df.empty else bench_df
    b_close  = bench_df_sliced["close"] if not bench_df_sliced.empty else pd.Series(dtype=float)

    b_ann = None
    if len(bench_long) >= 60:
        b_ann = float(bench_long.pct_change().dropna().std()) * np.sqrt(252)
    elif len(b_close) >= 60:
        b_ann = float(b_close.pct_change().dropna().std()) * np.sqrt(252)

    # Market Regime (tarama tarihi için)
    if use_regime:
        try:
            regime_result   = calc_market_regime(as_of, market)
            regime_score    = regime_result.get("regime_score", 75.0)
            market_exposure = regime_result.get("market_exposure", 1.0)
        except Exception:
            regime_score    = 75.0
            market_exposure = 1.0
    else:
        regime_score    = 75.0
        market_exposure = 1.0

    rows = []
    total = len(tickers)

    def _score_one_scan(ticker):
        try:
            df = all_data.get(ticker)
            if df is None or df.empty:
                return None
            df_sliced = df[df.index <= as_of]
            if len(df_sliced) < 130:
                return None
            return _calc_tech_score(ticker, df_sliced, b_close, bench_ann_vol=b_ann)
        except Exception:
            return None

    if progress_ph:
        progress_ph.progress(0.12, f"Teknik skorlar hesaplanıyor ({total} hisse)...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        raw_results = list(ex.map(_score_one_scan, tickers))
    valid_results = [r for r in raw_results if r is not None]

    if not valid_results:
        n_with_data   = sum(1 for t in tickers if all_data.get(t) is not None and not all_data[t].empty)
        n_enough_bars = sum(1 for t in tickers
                            if all_data.get(t) is not None
                            and len(all_data[t][all_data[t].index <= as_of]) >= 130)
        if progress_ph:
            progress_ph.progress(1.0, "Tamamlandı.")
        return pd.DataFrame({"_diag": [
            f"Veri olan hisse: {n_with_data}/{total} | "
            f"130+ bar olan: {n_enough_bars}/{total} | "
            f"Teknik skor hesaplanan: 0"
        ]})

    # RS normalize
    all_rs = [r["rs_slope"] for r in valid_results]
    max_rs = float(np.percentile(all_rs, 95)) if len(all_rs) >= 10 else max(all_rs)
    max_rs = max(max_rs, 1e-9)
    for r in valid_results:
        rs_norm    = (r["rs_slope"] / max_rs * 100)
        tech_score = max(0.0, min(200.0,
            (rs_norm + r["_bonus"]) * (1 - r.get("vol_penalty", 0))
        ))
        r["tech_score"] = round(tech_score, 2)

    valid_results.sort(key=lambda x: x["tech_score"], reverse=True)
    FUND_FETCH_LIMIT = 100

    if progress_ph:
        progress_ph.progress(0.75, f"Temel + AI veriler işleniyor (ilk {FUND_FETCH_LIMIT} aday)...")

    as_of_str   = end_s
    prev_90_str = (as_of - timedelta(days=90)).strftime("%Y-%m-%d")

    for idx, r in enumerate(valid_results):
        sym = r["Sembol"]
        fund_score  = "-"
        fund_sc     = None
        final_score = r["tech_score"]
        fund_period = "-"
        eps_g = rev_g = roe = nm = pe = pb = "-"
        ai_sc = 50.0

        if fw > 0 and not sym.endswith(".IS") and idx < FUND_FETCH_LIMIT:
            try:
                fund = get_fundamentals_as_of(sym, as_of_str)
                if fund:
                    fs, _ = calc_historical_fund_score(fund, "Alfa")
                    fund_score  = round(fs, 1)
                    fund_sc     = fs
                    fund_period = fund.get("period_date", "-")
                    eps_g = f"{fund['eps_growth']:.1f}%" if fund.get("eps_growth") is not None else "-"
                    rev_g = f"{fund['rev_growth']:.1f}%" if fund.get("rev_growth") is not None else "-"
                    roe   = f"{fund['roe']:.1f}%"        if fund.get("roe")         is not None else "-"
                    nm    = f"{fund['net_margin']:.1f}%" if fund.get("net_margin")  is not None else "-"
                    pe    = f"{fund['pe_ratio']:.1f}"    if fund.get("pe_ratio")    is not None else "-"
                    pb    = f"{fund['pb_ratio']:.1f}"    if fund.get("pb_ratio")    is not None else "-"
            except Exception:
                pass

        # AI skor
        if use_ai and idx < FUND_FETCH_LIMIT:
            try:
                ai_sc, _ = _calc_ai_score_for_ticker(sym, as_of_str, prev_90_str)
            except Exception:
                ai_sc = 50.0

        # Adjusted final skor
        tech_score = r["tech_score"]
        if is_bist:
            if use_ai:
                base_score = tech_score * 0.70 + ai_sc * 0.15 + regime_score * 0.15
            else:
                base_score = tech_score * 0.85 + regime_score * 0.15
        else:
            if fund_sc is not None and use_ai:
                base_score = tech_score*0.45 + fund_sc*0.25 + ai_sc*0.15 + regime_score*0.15
            elif fund_sc is not None and not use_ai:
                base_score = tech_score*0.55 + fund_sc*0.30 + regime_score*0.15
            elif fund_sc is None and use_ai:
                base_score = tech_score*0.60 + ai_sc*0.25 + regime_score*0.15
            else:
                base_score = tech_score*0.75 + regime_score*0.25

        adjusted_final_score = round(base_score * market_exposure, 2)

        rows.append({
            "Sembol"             : sym,
            "RS Eğimi"           : r["RS Eğimi"],
            "1A Excess"          : round(r["_excess_1m"], 2),
            "3A Excess"          : round(r["_excess_3m"], 2),
            "6A Excess"          : round(r["_excess_6m"], 2),
            "Teknik Skor"        : r["tech_score"],
            "Temel Skor"         : fund_score,
            "AI Skoru"           : round(ai_sc, 1),
            "Regime Skoru"       : round(regime_score, 1),
            "Market Exposure"    : f"%{int(market_exposure*100)}",
            "Adjusted Final Skor": adjusted_final_score,
            "EPS Büy."           : eps_g,
            "Gelir Büy."         : rev_g,
            "ROE"                : roe,
            "Net Marj"           : nm,
            "F/K"                : pe,
            "F/DD"               : pb,
            "Temel Dönem"        : fund_period,
        })

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("Adjusted Final Skor", ascending=False).reset_index(drop=True)
    if progress_ph:
        progress_ph.progress(1.0, "Tarama tamamlandı.")
    return df_out


# ─── GRAFİK ───────────────────────────────────────────────────────────────────
def _plot_equity(eq: pd.Series, bench: pd.Series, title: str):
    if not _HAS_PLOTLY:
        st.line_chart(pd.DataFrame({"Portföy": eq, "Benchmark": bench}))
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name="Portföy",
                             line=dict(color="#00D4AA", width=2)))
    if not bench.empty:
        b_scaled = bench / bench.iloc[0] * eq.iloc[0]
        fig.add_trace(go.Scatter(x=b_scaled.index, y=b_scaled.values, name="Benchmark",
                                 line=dict(color="#888", width=1.5, dash="dash")))
    fig.update_layout(title=title, template="plotly_dark",
                      height=420, margin=dict(l=30,r=30,t=50,b=30),
                      legend=dict(x=0.01, y=0.99))
    st.plotly_chart(fig, use_container_width=True)


# ─── UI ───────────────────────────────────────────────────────────────────────
def main():
    st.title("🤖 AI TEMEL OPTİMİZER")
    st.caption("Temel Optimizer + Market Regime + AI Score + Portfolio Risk Control")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🤖 AI Katmanları")
        use_regime = st.sidebar.checkbox("Market Regime Filter", value=True)
        use_ai     = st.sidebar.checkbox("AI Narrative Score", value=True)
        use_risk   = st.sidebar.checkbox("Portfolio Risk Control", value=True)
        exit_sens  = st.sidebar.selectbox("Çıkış Hassasiyeti", ["Sert", "Normal", "Yumuşak"], index=1)

        st.markdown("---")
        st.markdown("### ⚙️ Parametreler")

        market = st.selectbox("Piyasa", [
            "USA (S&P 500)", "USA (S&P 900)", "BIST (Borsa İstanbul)"
        ])
        is_bist = "BIST" in market

        if is_bist:
            st.info("BIST modunda temel veri ağırlığı = 0 (değiştirilemez)")
            fund_weight_pct = 0
        else:
            fund_weight_pct = st.slider(
                "Temel Veri Ağırlığı (%)", 0, 60, 40,
                help="0 = sadece teknik/momentum | 60 = temel ağırlıklı\n"
                     "Backtest ve tarama her ikisini de kullanır."
            )
        fw = fund_weight_pct / 100

        top_n = st.selectbox("Portföy Hisse Sayısı", [3, 5, 10, 15, 20], index=1)
        freq  = st.selectbox("Rebalance Sıklığı", ["Aylık", "15 Günlük", "Çeyreklik"])
        initial = st.number_input("Başlangıç Sermayesi ($)", 10000, 10_000_000, 100_000, step=10_000)

        st.markdown("---")
        st.caption("BIST: fund_weight = 0.0 (sabit)\nUSA: look-ahead bias yok\nFillingDate ≤ rebalance tarihi")

    # ── Sekmeler ──────────────────────────────────────────────────────────────
    tab_screen, tab_bt, tab_hist = st.tabs(["🔍 Tarama", "📊 Backtest", "📋 Geçmiş"])

    # ── TARAMA ────────────────────────────────────────────────────────────────
    with tab_screen:
        st.subheader("Tarama")

        # Aktif AI katmanları bilgisi
        ai_info_parts = []
        if use_regime: ai_info_parts.append("Market Regime")
        if use_ai:     ai_info_parts.append("AI Score")
        if use_risk:   ai_info_parts.append("Risk Control")
        ai_info = " + ".join(ai_info_parts) if ai_info_parts else "Yok"

        if not is_bist:
            st.info(f"Teknik **%{100-fund_weight_pct}** + Temel **%{fund_weight_pct}** + AI Katmanları: **{ai_info}** → Adjusted Final Skor")
        else:
            st.info(f"BIST taraması: teknik/momentum + AI Katmanları: **{ai_info}** (fund_weight=0)")

        sc1, sc2 = st.columns([1, 2])
        with sc1:
            scan_mode = st.radio("Tarama Tarihi", ["Bugün (Canlı)", "Geçmiş Tarih"],
                                 horizontal=True, key="scan_mode")
        with sc2:
            if scan_mode == "Geçmiş Tarih":
                scan_date = st.date_input(
                    "Tarama Tarihi Seçin",
                    value=(datetime.now() - timedelta(days=30)).date(),
                    min_value=datetime(2015, 1, 1).date(),
                    max_value=datetime.now().date(),
                    key="scan_date_picker",
                )
                scan_as_of = datetime.combine(scan_date, datetime.max.time())
                st.caption(f"Fiyat + temel veri {scan_date} itibarıyla kesiliyor — look-ahead bias yok")
            else:
                scan_as_of = None
                st.caption("Bugünün verileriyle canlı tarama yapılır")

        if st.button("🔍 Tarama Başlat", key="btn_screen"):
            tickers = _get_universe(market)
            ph = st.progress(0)
            if scan_mode == "Geçmiş Tarih":
                lbl = scan_date.strftime("%Y-%m-%d")
                scan_date_str = lbl
            else:
                lbl = "bugün"
                scan_date_str = datetime.now().strftime("%Y-%m-%d")
            with st.spinner(f"Taranıyor ({lbl})..."):
                df_res = run_ai_temel_screening(
                    tickers, market, fw,
                    use_regime=use_regime,
                    use_ai=use_ai,
                    as_of_date=scan_as_of,
                    progress_ph=ph,
                )
            ph.empty()
            if df_res.empty:
                st.warning("Kriterleri karşılayan hisse bulunamadı.")
            elif "_diag" in df_res.columns:
                msg = df_res["_diag"].iloc[0]
                st.error(f"Hisse bulunamadı. Tanı: {msg}")
                st.info("Öneri: Önce Backtest sekmesinden aynı tarih aralığında bir backtest çalıştırın — bu verinin cache'lenmesini sağlar. Sonra taramayı tekrar deneyin.")
            else:
                st.success(f"{len(df_res)} hisse bulundu — tarama tarihi: **{lbl}**")
                for col in ["Teknik Skor","Adjusted Final Skor"]:
                    if col in df_res.columns:
                        df_res[col] = pd.to_numeric(df_res[col], errors="coerce")

                df_res.insert(0, "Sıra", range(1, len(df_res)+1))
                df_res.insert(1, f"Top {top_n}?", df_res["Sıra"].apply(lambda x: "✅" if x <= top_n else ""))

                _scan_save(scan_date_str, market, fw, top_n, df_res)
                st.caption("Tarama geçmişe kaydedildi.")

                st.dataframe(df_res, use_container_width=True, height=500)

                buf = BytesIO()
                df_res.to_excel(buf, index=False)
                st.download_button("📥 Excel İndir", buf.getvalue(),
                                   file_name=f"ai_temel_tarama_{lbl}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # ── Tarama Geçmişi ────────────────────────────────────────────────────
        st.divider()
        st.subheader("Tarama Geçmişi")
        scan_rows = _scan_list()
        if not scan_rows:
            st.caption("Henüz kaydedilmiş tarama yok.")
        else:
            for row in scan_rows:
                sid, created_at, scan_date_s, s_market, s_fw, s_topn, s_found = row
                fw_pct = int(round(s_fw * 100))
                label = (f"#{sid}  {created_at}  |  {s_market}  "
                         f"Tarih: {scan_date_s}  |  Top {s_topn}  "
                         f"Temel %{fw_pct}  |  {s_found} hisse bulundu")
                with st.expander(label):
                    df_hist = _scan_get(sid)
                    if df_hist.empty:
                        st.warning("Veri bulunamadı.")
                    else:
                        st.dataframe(df_hist, use_container_width=True, height=400)
                        buf2 = BytesIO()
                        df_hist.to_excel(buf2, index=False)
                        c1, c2 = st.columns([1, 4])
                        with c1:
                            st.download_button(
                                "📥 Excel",
                                buf2.getvalue(),
                                file_name=f"tarama_{sid}_{scan_date_s}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_scan_{sid}",
                            )
                        with c2:
                            if st.button("🗑️ Sil", key=f"del_scan_{sid}"):
                                _scan_delete(sid)
                                st.rerun()

    # ── BACKTEST ──────────────────────────────────────────────────────────────
    with tab_bt:
        st.subheader("Backtest")

        # AI katman bilgisi
        ai_layers = []
        if use_regime: ai_layers.append("Market Regime")
        if use_ai:     ai_layers.append("AI Score")
        if use_risk:   ai_layers.append(f"Risk Control ({exit_sens})")
        ai_layer_str = " + ".join(ai_layers) if ai_layers else "Devre dışı"

        if not is_bist:
            st.markdown(f"""
            <div style='background:#1a2740;padding:12px;border-radius:8px;font-size:13px;color:#94a3b8'>
            🤖 AI Katmanları: <b>{ai_layer_str}</b><br>
            ℹ️ Her rebalance tarihinde <code>get_fundamentals_as_of(ticker, reb_date)</code> çağrılır.<br>
            Yalnızca o tarihte SEC'e dosyalanmış raporlar kullanılır — <b>look-ahead bias yoktur</b>.<br>
            Temel ağırlığı: <b>%{fund_weight_pct}</b> | Teknik ağırlığı: <b>%{100-fund_weight_pct}</b>
            </div>""", unsafe_allow_html=True)
        else:
            st.info(f"BIST backtestinde temel veri kullanılmaz (fund_weight=0.0 — sabit). AI Katmanları: {ai_layer_str}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            start_date = st.date_input("Başlangıç Tarihi",
                value=datetime(2022, 1, 1), min_value=datetime(2015, 1, 1))
        with col2:
            end_date = st.date_input("Bitiş Tarihi",
                value=datetime.now(), min_value=datetime(2015, 6, 1))
        with col3:
            top_n = st.selectbox("Portföy Hisse Adedi", [3, 5, 10, 15, 20, 30],
                                 index=1, key="bt_top_n")
        with col4:
            freq = st.selectbox("Rebalance Sıklığı",
                                ["Aylık", "15 Günlük", "Çeyreklik"],
                                key="bt_freq")

        if st.button("🚀 Backtest Çalıştır", type="primary"):
            if start_date >= end_date:
                st.error("Başlangıç tarihi bitiş tarihinden önce olmalı.")
            else:
                tickers = _get_universe(market)
                st.info(f"{len(tickers)} hisselik evren | {freq} rebalance | Top {top_n} | AI: {ai_layer_str}")
                ph = st.progress(0)
                t0 = time.time()

                with st.spinner("Backtest çalışıyor..."):
                    res = run_ai_temel_backtest(
                        tickers=tickers,
                        market=market,
                        start_dt=datetime.combine(start_date, datetime.min.time()),
                        end_dt=datetime.combine(end_date, datetime.min.time()),
                        top_n=top_n,
                        freq=freq,
                        fund_weight=fw,
                        initial_capital=float(initial),
                        use_regime=use_regime,
                        use_ai=use_ai,
                        use_risk_control=use_risk,
                        exit_sensitivity=exit_sens,
                        progress_ph=ph,
                    )
                ph.empty()
                elapsed = time.time() - t0
                st.success(f"Backtest tamamlandı — {elapsed:.1f}s")

                m = res.get("metrics", {})
                if not m:
                    st.warning("Sonuç hesaplanamadı.")
                else:
                    # Temel metrik kartlar
                    c1,c2,c3,c4,c5,c6 = st.columns(6)
                    c1.metric("Toplam Getiri", f"{m.get('Toplam Getiri (%)',0):.1f}%")
                    c2.metric("CAGR", f"{m.get('CAGR (%)',0):.1f}%")
                    c3.metric("Sharpe", f"{m.get('Sharpe',0):.2f}")
                    c4.metric("Max DD", f"{m.get('Max Drawdown (%)',0):.1f}%")
                    c5.metric("Calmar", f"{m.get('Calmar',0):.2f}")
                    c6.metric("Bench Üstü", f"{m.get('Benchmark Üstü Getiri (%)',0):.1f}%")

                    # AI metrik kartları
                    period_detail = res.get("period_detail", [])
                    if period_detail:
                        regime_scores = [p.get("Regime Skoru", 75.0) for p in period_detail if isinstance(p.get("Regime Skoru"), (int, float))]
                        trades_list   = res.get("trades", [])
                        ai_scores_t   = [t.get("AI Skoru") for t in trades_list if isinstance(t.get("AI Skoru"), (int, float))]
                        me_vals       = [t.get("Market Exposure") for t in trades_list if isinstance(t.get("Market Exposure"), (int, float))]

                        st.markdown("#### 🤖 AI Katman Metrikleri")
                        ac1, ac2, ac3 = st.columns(3)
                        ac1.metric("Ort. Regime Skoru",
                                   f"{np.mean(regime_scores):.1f}" if regime_scores else "—")
                        ac2.metric("Ort. Market Exposure",
                                   f"%{int(np.mean(me_vals)*100)}" if me_vals else "—")
                        ac3.metric("Ort. AI Skoru",
                                   f"{np.mean(ai_scores_t):.1f}" if ai_scores_t else "—")

                    # Grafik
                    _plot_equity(res["equity"], res["bench"],
                                 f"AI TEMEL OPTİMİZER — {market} | Temel: %{fund_weight_pct} | AI: {ai_layer_str}")

                    # Dönem detayı
                    if res.get("period_detail"):
                        st.markdown("#### Dönem Detayı")
                        st.dataframe(_clean_df_for_display(pd.DataFrame(res["period_detail"])),
                                     use_container_width=True)

                    if res.get("trades"):
                        with st.expander("📋 İşlem Geçmişi"):
                            df_t = _clean_df_for_display(pd.DataFrame(res["trades"]))
                            st.dataframe(df_t, use_container_width=True, height=400)
                            buf = BytesIO()
                            df_t.to_excel(buf, index=False)
                            st.download_button("📥 Excel", buf.getvalue(),
                                file_name=f"ai_temel_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                    # Kaydet
                    _db_save({
                        "market": market, "strategy": "AI-Alfa",
                        "start_date": str(start_date), "end_date": str(end_date),
                        "top_n": top_n, "rebalance": freq,
                        "fund_weight": fw,
                        "cagr"  : m.get("CAGR (%)",0),
                        "sharpe": m.get("Sharpe",0),
                        "max_dd": m.get("Max Drawdown (%)",0),
                        "total_return": m.get("Toplam Getiri (%)",0),
                        "params": {
                            "initial": initial, "top_n": top_n, "freq": freq,
                            "use_regime": use_regime, "use_ai": use_ai,
                            "use_risk": use_risk, "exit_sens": exit_sens,
                        },
                        "trades": res.get("trades",[]),
                        "period_detail": res.get("period_detail",[]),
                    })
                    st.caption("✅ Backtest geçmişe kaydedildi.")

    # ── GEÇMİŞ ────────────────────────────────────────────────────────────────
    with tab_hist:
        st.subheader("Kayıtlı Backtestler")

        db_rows = _db_list()
        if not db_rows:
            st.info("Henüz kayıtlı backtest yok.")
        else:
            df_h = pd.DataFrame(db_rows, columns=[
                "ID","Tarih","Piyasa","Strateji","Başlangıç","Bitiş",
                "Hisse","Rebalance","Temel Ağırlık","CAGR%","Sharpe","MaxDD%","Getiri%"
            ])
            df_h["Temel Ağırlık"] = df_h["Temel Ağırlık"].apply(lambda x: f"%{int(x*100)}")
            st.dataframe(df_h.drop(columns=["ID"]), use_container_width=True)
            st.markdown("---")
            st.markdown("#### Detay — Bir backtest seçin")

            for row in db_rows:
                (rid, created_at, mkt, strat, sd, ed,
                 top_n_r, reb_r, fw_r,
                 cagr_r, sharpe_r, maxdd_r, ret_r) = row

                getiri_str  = f"{ret_r:+.1f}%" if ret_r is not None else "—"
                cagr_str    = f"{cagr_r:.1f}%"  if cagr_r is not None else "—"
                sharpe_str  = f"{sharpe_r:.2f}"  if sharpe_r is not None else "—"
                maxdd_str   = f"{maxdd_r:.1f}%"  if maxdd_r is not None else "—"
                fw_pct      = int((fw_r or 0) * 100)
                label       = (f"#{rid}  {created_at[:16]}  |  {mkt}  "
                               f"{sd} → {ed}  |  Top {top_n_r}  {reb_r}  "
                               f"Temel %{fw_pct}  |  "
                               f"Getiri: {getiri_str}  CAGR: {cagr_str}  "
                               f"Sharpe: {sharpe_str}  MaxDD: {maxdd_str}")

                with st.expander(label):
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Toplam Getiri", getiri_str)
                    mc2.metric("CAGR",          cagr_str)
                    mc3.metric("Sharpe",         sharpe_str)
                    mc4.metric("Max Drawdown",   maxdd_str)

                    detail = _db_get_detail(rid)
                    trades  = detail["trades"]
                    periods = detail["period_detail"]

                    # AI sütunları varsa göster
                    if periods:
                        df_periods = pd.DataFrame(periods)
                        ai_cols = [c for c in ["Regime Skoru","Market Exposure","Nakit Oranı"] if c in df_periods.columns]
                        if ai_cols:
                            st.markdown("**Dönem Detayı (AI Katmanları)**")
                            st.dataframe(_clean_df_for_display(df_periods), use_container_width=True)

                    df_pr = _build_period_returns(trades, periods)
                    if not df_pr.empty:
                        st.markdown("**Dönem Bazlı Hisse Kazançları**")
                        st.dataframe(_clean_df_for_display(df_pr), use_container_width=True, height=min(400, 40 + len(df_pr)*36))

                        numeric_kz = df_pr[df_pr["K/Z (%)"].apply(lambda v: isinstance(v,(int,float)))]
                        if not numeric_kz.empty:
                            ozet = (numeric_kz.groupby("Hisse")["K/Z (%)"]
                                    .agg(["mean","count","sum"])
                                    .rename(columns={"mean":"Ort K/Z%","count":"İşlem","sum":"Toplam K/Z%"})
                                    .sort_values("Toplam K/Z%", ascending=False)
                                    .reset_index())
                            ozet["Ort K/Z%"]   = ozet["Ort K/Z%"].apply(lambda v: f"{v:+.2f}%")
                            ozet["Toplam K/Z%"] = ozet["Toplam K/Z%"].apply(lambda v: f"{v:+.2f}%")
                            st.markdown("**Hisse Bazlı Özet**")
                            st.dataframe(ozet, use_container_width=True)
                    elif periods and not pd.DataFrame(periods).empty:
                        st.markdown("**Dönem Detayı**")
                        st.dataframe(pd.DataFrame(periods), use_container_width=True)

                    if trades:
                        st.markdown("**İşlem Geçmişi (AL / SAT)**")
                        df_t = _clean_df_for_display(pd.DataFrame(trades))
                        # AI sütunlarını öne al
                        ai_trade_cols = ["AI Skoru","Regime Skoru","Market Exposure","Adjusted Final Skor"]
                        existing_ai = [c for c in ai_trade_cols if c in df_t.columns]
                        if existing_ai:
                            other_cols = [c for c in df_t.columns if c not in existing_ai]
                            df_t = df_t[other_cols[:6] + existing_ai + other_cols[6:]]
                        st.dataframe(df_t, use_container_width=True, height=300)

                        buf = BytesIO()
                        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                            df_t.to_excel(writer, sheet_name="İşlemler", index=False)
                            if not df_pr.empty:
                                df_pr.to_excel(writer, sheet_name="Dönem Kazançları", index=False)
                        st.download_button(
                            "📥 Excel İndir",
                            buf.getvalue(),
                            file_name=f"ai_temel_bt_{rid}_{sd}_{ed}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{rid}",
                        )
                    else:
                        st.caption("Bu kayıt için işlem verisi bulunamadı.")

                    if st.button("🗑️ Bu kaydı sil", key=f"del_{rid}"):
                        _db_delete(rid)
                        st.success(f"#{rid} silindi.")
                        st.rerun()


if __name__ == "__main__":
    main()
