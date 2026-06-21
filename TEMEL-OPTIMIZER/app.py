"""
TEMEL OPTİMİZER
===============
Portfolio Optimizer altyapısından türetilmiştir.

FARK:
  USA backtestinde ve taramasında Temel Veri Ağırlığı (fund_weight)
  kullanıcı parametresidir (varsayılan %40).
  Her rebalance tarihinde get_fundamentals_as_of(ticker, reb_date)
  çağrılır → look-ahead bias yoktur.

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
    page_title="TEMEL OPTİMİZER | Fundamental + Momentum",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sabitler ─────────────────────────────────────────────────────────────────
DB_PATH        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temel_optimizer.db")
COMMISSION_RATE = 0.001
SLIPPAGE_BUY   = 1.001
SLIPPAGE_SELL  = 0.999
RANK_WEIGHTS   = {1: 0.40, 2: 0.25, 3: 0.18, 4: 0.10, 5: 0.07}

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE    = "https://financialmodelingprep.com/stable"

# ─── pandas-ta adapter (Portfolio Optimizer'dan kopyalandı) ──────────────────
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
    # Migration: eski DB'lere period_json sütunu ekle
    try:
        conn.execute("ALTER TABLE temel_backtests ADD COLUMN period_json TEXT")
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
    # Dönem bilgisiyle eşleştir
    rows = []
    for p in period_detail:
        d_basi = p.get("Dönem Başı","")
        d_sonu = p.get("Dönem Sonu","")
        hisseler = [h.strip() for h in p.get("Seçilen Hisseler","").split(",") if h.strip()]
        for sym in hisseler:
            # Bu dönemde yapılan SAT işlemi bul (dönem sonu tarihine yakın)
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
# Portfolio Optimizer ile aynı liste; Wikipedia erişimi gerekmez, her zaman 913 hisse
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
    # USA için her zaman 913 hisselik statik liste kullan (Wikipedia bağımlılığı yok)
    return list(_US_913_TICKERS)

# ─── Sütun adlarını normalize et (yfinance sürüm farklarına karşı) ───────────
def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex veya büyük-küçük harf farklarını normalize eder."""
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        # ('Close','AAPL') → 'close'
        df.columns = [str(c[0]).lower().strip() for c in df.columns]
    else:
        df.columns = [str(c).lower().strip() for c in df.columns]
    # yfinance bazen 'adj close' döndürür — 'close' olarak yeniden adlandır
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
            # data_cache büyük harfli sütunlar döndürür → _normalize_cols uygula
            for k, v in raw_dc.items():
                if v is not None and not v.empty:
                    result[k] = _normalize_cols(v.copy())
            if result:
                return result
        except Exception:
            pass
    # Fallback yfinance bulk
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

# ─── Teknik skor (Portfolio Optimizer Alfa ile aynı) ─────────────────────────
def _calc_tech_score(ticker: str, df: pd.DataFrame,
                     bench_close: pd.Series,
                     bench_ann_vol: float = None) -> Optional[Dict]:
    """
    Portfolio Optimizer'daki _screen_alfa_backtest ile aynı formül.
    Döndürür: {"rs_slope": float, "vol_penalty": float, bonuslar...}
    """
    try:
        close  = df["close"].astype(float)
        volume = df.get("volume", pd.Series(dtype=float)).astype(float)
    except Exception:
        return None

    if len(close) < 130:
        return None

    last_price = float(close.iloc[-1])

    # SMA filtreler
    sma50  = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if last_price < sma50:
        return None
    if sma200 and last_price < sma200 * 0.97:
        return None

    # Excess return hesapla
    def _excess(n):
        if len(close) <= n or len(bench_close) <= n:
            return 0.0
        stock_r = float(close.iloc[-1] / close.iloc[-n] - 1) * 100
        bench_r = float(bench_close.iloc[-1] / bench_close.iloc[-n] - 1) * 100
        return stock_r - bench_r

    e1m, e3m, e6m, e12m = _excess(21), _excess(63), _excess(126), _excess(252)

    # 6A mutlak getiri kontrolü
    if len(close) > 126:
        ret6m_abs = float(close.iloc[-1] / close.iloc[-126] - 1) * 100
        if ret6m_abs <= 0:
            return None

    # Çift momentum filtresi
    if e3m < -5 and e6m < -10:
        return None

    # Ortalama hacim
    if len(volume) >= 20:
        avg_vol20 = float(volume.iloc[-20:].mean())
        min_vol = 10000 if ticker.endswith(".IS") else 200000
        if avg_vol20 < min_vol:
            return None

    # ADX bonusu
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

    # İvme bonusu
    accel = 0.0
    if e1m > e3m > 0:
        accel += min(25.0, (e1m - e3m) * 0.7)
    if e3m > e6m > 0:
        accel += min(15.0, (e3m - e6m) * 0.4)

    # 52H yakınlık
    lk = min(252, len(close)-1)
    h52 = float(close.iloc[-lk:].max())
    h52_bonus = 0.0
    if h52 > 0:
        d52 = (last_price / h52 - 1) * 100
        if d52 >= -3:    h52_bonus = 25
        elif d52 >= -10: h52_bonus = 15
        elif d52 >= -20: h52_bonus = 7

    # SMA200 mesafe bonusu
    sma200_bonus = 0.0
    if sma200 and sma200 > 0:
        gap = (last_price / sma200 - 1) * 100
        if gap >= 20:   sma200_bonus = 20
        elif gap >= 10: sma200_bonus = 12
        elif gap >= 0:  sma200_bonus = 5

    # Hacim patlaması
    vol_bonus = 0.0
    if len(volume) >= 20:
        v5 = float(volume.iloc[-5:].mean())
        v20 = float(volume.iloc[-20:].mean())
        if v20 > 0:
            vr = v5 / v20
            if vr > 2.5:   vol_bonus = 18
            elif vr > 1.8: vol_bonus = 10
            elif vr > 1.3: vol_bonus = 4

    # Volatilite cezası
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
    Temel veri yoksa (None, {}) döner — 50.0 default KULLANILMAZ.
    Böylece backtest ve taramada fund skor yoksa final_score = tech_score (tutarlı).
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


# ─── BACKTEST ─────────────────────────────────────────────────────────────────
def run_temel_backtest(
    tickers: list,
    market: str,
    start_dt: datetime,
    end_dt: datetime,
    top_n: int,
    freq: str,
    fund_weight: float,
    initial_capital: float,
    progress_ph=None,
) -> dict:
    """
    Temel Optimizer backtesti.
    USA: final_score = tech_score*(1-fw) + hist_fund_score*fw
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
    reb_dates  = _rebalance_dates(start_dt, end_dt, freq)
    total_p    = len(reb_dates) - 1
    cash       = float(initial_capital)
    holdings   = {}
    equity_curve = {}
    trade_log  = []
    period_detail= []

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
            p  = float(sl["close"].iloc[-1]) if not sl.empty else h.get("buy_price", 0)
            total += h["shares"] * p
        return total

    def _sell(sym, dt, reason):
        nonlocal cash
        h = holdings.get(sym)
        if not h:
            return
        sl = all_data.get(sym, pd.DataFrame())
        sl = sl[sl.index <= dt] if not sl.empty else sl
        if sl.empty:
            del holdings[sym]
            return
        raw_p = float(sl["close"].iloc[-1])
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

        # ── Hisseleri skorla ────────────────────────────────────────────────
        candidates = []

        def _score_one(ticker):
            df = all_data.get(ticker)
            if df is None or df.empty:
                return None
            sl = df[df.index <= reb]
            if len(sl) < 130:
                return None
            res = _calc_tech_score(ticker, sl, b_slice, bench_ann_vol=b_ann)
            if res is None:
                return None

            # Normalize teknik skor 0-100
            return res

        with ThreadPoolExecutor(max_workers=8) as ex:
            raw_results = list(ex.map(_score_one, tickers))

        valid = [r for r in raw_results if r is not None]
        if not valid:
            equity_curve[reb] = _pval(reb)
            continue

        # RS normalize
        all_rs = [r["rs_slope"] for r in valid]
        # 95. persentil — outlier (data artifact) tüm sıralamayı bozmasın
        max_rs = float(np.percentile(all_rs, 95)) if len(all_rs) >= 10 else max(all_rs)
        max_rs = max(max_rs, 1e-9)
        for r in valid:
            rs_norm    = (r["rs_slope"] / max_rs * 100)          # kırpma yok — 95p üstü avantajlı
            tech_score = max(0.0, min(200.0,
                (rs_norm + r["_bonus"]) * (1 - r.get("vol_penalty", 0))
            ))
            r["tech_score"] = round(tech_score, 2)

        # Temel skor (USA, look-ahead bias'sız)
        reb_date_str = reb.strftime("%Y-%m-%d")
        for r in valid:
            sym = r["Sembol"]
            if fw > 0 and not sym.endswith(".IS"):
                fund_sc, _ = _get_hist_fund_score(sym, reb_date_str)
                if fund_sc is not None:
                    r["fund_score"] = round(fund_sc, 2)
                    r["final_score"] = round(
                        r["tech_score"] * (1 - fw) + fund_sc * fw, 2
                    )
                else:
                    # Temel veri yok → tarama ile tutarlı: sadece teknik skor
                    r["fund_score"] = "-"
                    r["final_score"] = r["tech_score"]
            else:
                r["fund_score"] = "-"
                r["final_score"] = r["tech_score"]

        valid.sort(key=lambda x: x["final_score"], reverse=True)
        selected = valid[:top_n]
        new_syms = [s["Sembol"] for s in selected]
        new_scores = {s["Sembol"]: s["final_score"] for s in selected}

        # Sat
        for sym in list(holdings):
            if sym not in new_syms:
                _sell(sym, reb, "Portföyden çıkarıldı")

        # Ağırlıklar
        total_val = _pval(reb)
        n = len(new_syms)
        if n <= 5:
            rw = [RANK_WEIGHTS.get(i+1, 1/n) for i in range(n)]
        else:
            step = 1 / (n*(n+1)/2)
            rw = [(n-i)*step for i in range(n)]
        ws = sum(rw)
        allocs = {sym: (w/ws)*total_val for sym, w in zip(new_syms, rw)}

        # Alım
        for sym in new_syms:
            sl = all_data.get(sym, pd.DataFrame())
            sl = sl[sl.index <= reb] if not sl.empty else sl
            if sl.empty:
                continue
            raw_p = float(sl["close"].iloc[-1])
            if raw_p <= 0:
                continue
            adj_p  = raw_p * SLIPPAGE_BUY
            alloc  = min(allocs[sym], cash)
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
                "Teknik Skor": score_info.get("tech_score","-"),
                "Temel Skor" : score_info.get("fund_score","-"),
                "Final Skor" : score_info.get("final_score","-"),
                "Açıklama"   : "Portföye eklendi",
            })

        equity_curve[reb] = _pval(reb)
        period_detail.append({
            "Dönem Başı": reb.strftime("%Y-%m-%d"),
            "Dönem Sonu": n_reb.strftime("%Y-%m-%d"),
            "Seçilen Hisseler": ", ".join(new_syms),
            "Temel Ağırlık": f"%{int(fw*100)}",
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
        "equity": eq_series,
        "bench" : bench_algn,
        "metrics": metrics,
        "trades": trade_log,
        "period_detail": period_detail,
    }


# ─── TARAMA ───────────────────────────────────────────────────────────────────
def run_temel_screening(
    tickers: list,
    market: str,
    fund_weight: float,
    as_of_date: Optional[datetime] = None,   # None → bugün
    progress_ph=None,
) -> pd.DataFrame:
    is_bist = "BIST" in market
    fw = 0.0 if is_bist else fund_weight
    bench_sym = "XU100.IS" if is_bist else "SPY"

    as_of   = as_of_date if as_of_date else datetime.now()
    end_s   = as_of.strftime("%Y-%m-%d")
    # Hisse verisi: 600 gün — backtest ile aynı _excess(252) penceresi için
    # (400 gün ile başlatıldığında _excess(252)'nin referans noktası ~40 iş günü kayıyor)
    start_s = (as_of - timedelta(days=600)).strftime("%Y-%m-%d")
    # Benchmark verisi: 760 gün — backtest'in uzun tarihli b_ann hesabını taklit etmek için
    bench_start_s = (as_of - timedelta(days=760)).strftime("%Y-%m-%d")

    if progress_ph:
        progress_ph.progress(0.05, "Fiyat verisi indiriliyor...")
    all_data = _batch_prices(tickers, start_s, end_s)

    # Benchmark: 760 günlük veri → b_ann için; 400 günlük slice → _excess için
    bench_long_df = _get_prices(bench_sym, bench_start_s, end_s)
    bench_long    = bench_long_df[bench_long_df.index <= as_of]["close"] if not bench_long_df.empty else pd.Series(dtype=float)

    bench_df = _get_prices(bench_sym, start_s, end_s)
    bench_df_sliced = bench_df[bench_df.index <= as_of] if not bench_df.empty else bench_df
    b_close  = bench_df_sliced["close"] if not bench_df_sliced.empty else pd.Series(dtype=float)

    # b_ann: backtest ile tutarlı olması için 760 günlük pencereden hesapla
    b_ann = None
    if len(bench_long) >= 60:
        b_ann = float(bench_long.pct_change().dropna().std()) * np.sqrt(252)
    elif len(b_close) >= 60:
        b_ann = float(b_close.pct_change().dropna().std()) * np.sqrt(252)

    rows = []
    total = len(tickers)
    valid_results = []

    # 1. AŞAMA: ham teknik skorları topla — backtest ile aynı ThreadPoolExecutor
    def _score_one_scan(ticker):
        df = all_data.get(ticker)
        if df is None or df.empty:
            return None
        df_sliced = df[df.index <= as_of]
        if len(df_sliced) < 130:
            return None
        return _calc_tech_score(ticker, df_sliced, b_close, bench_ann_vol=b_ann)

    # 1. AŞAMA: ham teknik skorları topla — backtest ile aynı ThreadPoolExecutor
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
        # Diagnostic mesajı için özel bir exception değil, özel bir dict döndür
        return pd.DataFrame({"_diag": [
            f"Veri olan hisse: {n_with_data}/{total} | "
            f"130+ bar olan: {n_enough_bars}/{total} | "
            f"Teknik skor hesaplanan: 0"
        ]})
    # 2. AŞAMA: RS normalize — outlier'a karşı 95. persentil kullan
    all_rs = [r["rs_slope"] for r in valid_results]
    # max() yerine 95. persentil: data artifact olan tek hisse tüm sıralamayı bozmasın
    max_rs = float(np.percentile(all_rs, 95)) if len(all_rs) >= 10 else max(all_rs)
    max_rs = max(max_rs, 1e-9)
    for r in valid_results:
        rs_norm    = (r["rs_slope"] / max_rs * 100)              # kırpma yok — backtest ile aynı
        tech_score = max(0.0, min(200.0,
            (rs_norm + r["_bonus"]) * (1 - r.get("vol_penalty", 0))
        ))
        r["tech_score"] = round(tech_score, 2)

    # Teknik skora göre sırala — fundamentals sadece ilk 100 aday için çekilecek
    valid_results.sort(key=lambda x: x["tech_score"], reverse=True)
    FUND_FETCH_LIMIT = 100   # API rate limit aşımını önlemek için

    # 3. AŞAMA: temel skor — sadece teknik skor ilk FUND_FETCH_LIMIT adaya bak
    if progress_ph:
        progress_ph.progress(0.75, f"Temel veriler işleniyor (ilk {FUND_FETCH_LIMIT} aday)...")

    for idx, r in enumerate(valid_results):
        sym = r["Sembol"]
        fund_score  = "-"
        final_score = r["tech_score"]
        fund_period = "-"
        eps_g = rev_g = roe = nm = pe = pb = "-"

        if fw > 0 and not sym.endswith(".IS") and idx < FUND_FETCH_LIMIT:
            try:
                fund = get_fundamentals_as_of(sym, end_s)
                if fund:
                    fs, _ = calc_historical_fund_score(fund, "Alfa")
                    fund_score  = round(fs, 1)
                    final_score = round(r["tech_score"]*(1-fw) + fs*fw, 2)
                    fund_period = fund.get("period_date", "-")
                    eps_g = f"{fund['eps_growth']:.1f}%" if fund.get("eps_growth") is not None else "-"
                    rev_g = f"{fund['rev_growth']:.1f}%" if fund.get("rev_growth") is not None else "-"
                    roe   = f"{fund['roe']:.1f}%"        if fund.get("roe")         is not None else "-"
                    nm    = f"{fund['net_margin']:.1f}%" if fund.get("net_margin")  is not None else "-"
                    pe    = f"{fund['pe_ratio']:.1f}"    if fund.get("pe_ratio")    is not None else "-"
                    pb    = f"{fund['pb_ratio']:.1f}"    if fund.get("pb_ratio")    is not None else "-"
            except Exception:
                pass

        rows.append({
            "Sembol"       : sym,
            "RS Eğimi"     : r["RS Eğimi"],
            "1A Excess"    : round(r["_excess_1m"], 2),
            "3A Excess"    : round(r["_excess_3m"], 2),
            "6A Excess"    : round(r["_excess_6m"], 2),
            "Teknik Skor"  : r["tech_score"],
            "Temel Skor"   : fund_score,
            "Final Skor"   : final_score,
            "EPS Büy."     : eps_g,
            "Gelir Büy."   : rev_g,
            "ROE"          : roe,
            "Net Marj"     : nm,
            "F/K"          : pe,
            "F/DD"         : pb,
            "Temel Dönem"  : fund_period,
        })

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("Final Skor", ascending=False).reset_index(drop=True)
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
    # Başlık
    st.markdown("""
    <div style='background:linear-gradient(135deg,#0f2744,#1a3a6b);
    padding:20px 28px;border-radius:12px;margin-bottom:18px'>
    <h2 style='color:#34d399;margin:0'>📐 TEMEL OPTİMİZER</h2>
    <p style='color:#94a3b8;margin:4px 0 0'>
    Momentum × Temel Analiz — Tarihsel temel veri ile güçlendirilmiş portföy optimizasyonu
    </p></div>""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
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
        if not is_bist:
            st.info(f"Teknik skor **%{100-fund_weight_pct}** + Tarihsel Temel skor **%{fund_weight_pct}** → Final Skor")
        else:
            st.info("BIST taraması: yalnızca teknik/momentum skoru (fund_weight=0)")

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
                df_res = run_temel_screening(
                    tickers, market, fw,
                    as_of_date=scan_as_of,
                    progress_ph=ph,
                )
            ph.empty()
            if df_res.empty:
                st.warning("Kriterleri karşılayan hisse bulunamadı.")
            elif "_diag" in df_res.columns:
                # Diagnostic: neden 0 hisse bulundu
                msg = df_res["_diag"].iloc[0]
                st.error(f"Hisse bulunamadı. Tanı: {msg}")
                st.info("Öneri: Önce Backtest sekmesinden aynı tarih aralığında bir backtest çalıştırın — bu verinin cache'lenmesini sağlar. Sonra taramayı tekrar deneyin.")
            else:
                st.success(f"{len(df_res)} hisse bulundu — tarama tarihi: **{lbl}**")
                for col in ["Teknik Skor","Final Skor"]:
                    if col in df_res.columns:
                        df_res[col] = pd.to_numeric(df_res[col], errors="coerce")

                # Backtest ile karşılaştırma için "Top N seçim" sütunu ekle
                df_res.insert(0, "Sıra", range(1, len(df_res)+1))
                df_res.insert(1, f"Top {top_n}?", df_res["Sıra"].apply(lambda x: "✅" if x <= top_n else ""))

                # Tarama sonucunu DB'ye kaydet
                _scan_save(scan_date_str, market, fw, top_n, df_res)
                st.caption("Tarama geçmişe kaydedildi.")

                st.dataframe(df_res, use_container_width=True, height=500)

                buf = BytesIO()
                df_res.to_excel(buf, index=False)
                st.download_button("📥 Excel İndir", buf.getvalue(),
                                   file_name=f"temel_tarama_{lbl}.xlsx",
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
        if not is_bist:
            st.markdown(f"""
            <div style='background:#1a2740;padding:12px;border-radius:8px;font-size:13px;color:#94a3b8'>
            ℹ️ Her rebalance tarihinde <code>get_fundamentals_as_of(ticker, reb_date)</code> çağrılır.<br>
            Yalnızca o tarihte SEC'e dosyalanmış raporlar kullanılır — <b>look-ahead bias yoktur</b>.<br>
            Temel ağırlığı: <b>%{fund_weight_pct}</b> | Teknik ağırlığı: <b>%{100-fund_weight_pct}</b>
            </div>""", unsafe_allow_html=True)
        else:
            st.info("BIST backtestinde temel veri kullanılmaz (fund_weight=0.0 — sabit).")

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Başlangıç Tarihi",
                value=datetime(2022, 1, 1), min_value=datetime(2015, 1, 1))
        with col2:
            end_date = st.date_input("Bitiş Tarihi",
                value=datetime.now(), min_value=datetime(2015, 6, 1))

        if st.button("🚀 Backtest Çalıştır", type="primary"):
            if start_date >= end_date:
                st.error("Başlangıç tarihi bitiş tarihinden önce olmalı.")
            else:
                tickers = _get_universe(market)
                st.info(f"{len(tickers)} hisselik evren | {freq} rebalance | Top {top_n}")
                ph = st.progress(0)
                t0 = time.time()

                with st.spinner("Backtest çalışıyor..."):
                    res = run_temel_backtest(
                        tickers=tickers,
                        market=market,
                        start_dt=datetime.combine(start_date, datetime.min.time()),
                        end_dt=datetime.combine(end_date, datetime.min.time()),
                        top_n=top_n,
                        freq=freq,
                        fund_weight=fw,
                        initial_capital=float(initial),
                        progress_ph=ph,
                    )
                ph.empty()
                elapsed = time.time() - t0
                st.success(f"Backtest tamamlandı — {elapsed:.1f}s")

                m = res.get("metrics", {})
                if not m:
                    st.warning("Sonuç hesaplanamadı.")
                else:
                    # Metrik kartlar
                    c1,c2,c3,c4,c5,c6 = st.columns(6)
                    c1.metric("Toplam Getiri", f"{m.get('Toplam Getiri (%)',0):.1f}%")
                    c2.metric("CAGR", f"{m.get('CAGR (%)',0):.1f}%")
                    c3.metric("Sharpe", f"{m.get('Sharpe',0):.2f}")
                    c4.metric("Max DD", f"{m.get('Max Drawdown (%)',0):.1f}%")
                    c5.metric("Calmar", f"{m.get('Calmar',0):.2f}")
                    c6.metric("Bench Üstü", f"{m.get('Benchmark Üstü Getiri (%)',0):.1f}%")

                    # Grafik
                    _plot_equity(res["equity"], res["bench"],
                                 f"TEMEL OPTİMİZER — {market} | Temel Ağırlık: %{fund_weight_pct}")

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
                                file_name=f"temel_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                    # Kaydet
                    _db_save({
                        "market": market, "strategy": "Alfa",
                        "start_date": str(start_date), "end_date": str(end_date),
                        "top_n": top_n, "rebalance": freq,
                        "fund_weight": fw,
                        "cagr"  : m.get("CAGR (%)",0),
                        "sharpe": m.get("Sharpe",0),
                        "max_dd": m.get("Max Drawdown (%)",0),
                        "total_return": m.get("Toplam Getiri (%)",0),
                        "params": {"initial": initial, "top_n": top_n, "freq": freq},
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
            # Üst özet tablosu
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

                getiri_str  = f"{ret_r:+.1f}%" if ret_r else "—"
                cagr_str    = f"{cagr_r:.1f}%"  if cagr_r else "—"
                sharpe_str  = f"{sharpe_r:.2f}"  if sharpe_r else "—"
                maxdd_str   = f"{maxdd_r:.1f}%"  if maxdd_r else "—"
                fw_pct      = int((fw_r or 0) * 100)
                label       = (f"#{rid}  {created_at[:16]}  |  {mkt}  "
                               f"{sd} → {ed}  |  Top {top_n_r}  {reb_r}  "
                               f"Temel %{fw_pct}  |  "
                               f"Getiri: {getiri_str}  CAGR: {cagr_str}  "
                               f"Sharpe: {sharpe_str}  MaxDD: {maxdd_str}")

                with st.expander(label):
                    # ── Metrik kartlar ──────────────────────────────────────
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Toplam Getiri", getiri_str)
                    mc2.metric("CAGR",          cagr_str)
                    mc3.metric("Sharpe",         sharpe_str)
                    mc4.metric("Max Drawdown",   maxdd_str)

                    # ── Veri yükle ──────────────────────────────────────────
                    detail = _db_get_detail(rid)
                    trades  = detail["trades"]
                    periods = detail["period_detail"]

                    # ── Dönem bazlı hisse kazançları ────────────────────────
                    df_pr = _build_period_returns(trades, periods)
                    if not df_pr.empty:
                        st.markdown("**Dönem Bazlı Hisse Kazançları**")

                        st.dataframe(_clean_df_for_display(df_pr), use_container_width=True, height=min(400, 40 + len(df_pr)*36))

                        # Hisse bazlı özet (ortalama K/Z)
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
                    elif periods:
                        # period_detail var ama SAT kaydı yok (backtest henüz bitmemiş dönem)
                        st.markdown("**Dönem Detayı**")
                        st.dataframe(pd.DataFrame(periods), use_container_width=True)

                    if trades:
                        st.markdown("**İşlem Geçmişi (AL / SAT)**")
                        df_t = _clean_df_for_display(pd.DataFrame(trades))
                        st.dataframe(df_t, use_container_width=True, height=300)

                        # Excel indir
                        buf = BytesIO()
                        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                            df_t.to_excel(writer, sheet_name="İşlemler", index=False)
                            if not df_pr.empty:
                                df_pr.to_excel(writer, sheet_name="Dönem Kazançları", index=False)
                        st.download_button(
                            "📥 Excel İndir",
                            buf.getvalue(),
                            file_name=f"temel_bt_{rid}_{sd}_{ed}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{rid}",
                        )
                    else:
                        st.caption("Bu kayıt için işlem verisi bulunamadı.")

                    # ── Sil butonu ───────────────────────────────────────────
                    if st.button("🗑️ Bu kaydı sil", key=f"del_{rid}"):
                        _db_delete(rid)
                        st.success(f"#{rid} silindi.")
                        st.rerun()


if __name__ == "__main__":
    main()
