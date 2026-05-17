import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import ta
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
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests
import os
import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO


class _pta:
    """pandas_ta uyumlu adapter — ta kütüphanesi üzerinde çalışır."""

    @staticmethod
    def sma(series, length=20):
        return series.rolling(window=length).mean()

    @staticmethod
    def ema(series, length=20):
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def rsi(series, length=14):
        return ta.momentum.RSIIndicator(close=series, window=length).rsi()

    @staticmethod
    def macd(series, fast=12, slow=26, signal=9):
        ind = ta.trend.MACD(close=series, window_fast=fast, window_slow=slow, window_sign=signal)
        df = pd.DataFrame({
            f"MACD_{fast}_{slow}_{signal}": ind.macd(),
            f"MACDh_{fast}_{slow}_{signal}": ind.macd_diff(),
            f"MACDs_{fast}_{slow}_{signal}": ind.macd_signal(),
        })
        return df

    @staticmethod
    def bbands(series, length=20, std=2.0):
        ind = ta.volatility.BollingerBands(close=series, window=length, window_dev=std)
        df = pd.DataFrame({
            f"BBL_{length}_{std}": ind.bollinger_lband(),
            f"BBM_{length}_{std}": ind.bollinger_mavg(),
            f"BBU_{length}_{std}": ind.bollinger_hband(),
            f"BBB_{length}_{std}": ind.bollinger_wband(),
            f"BBP_{length}_{std}": ind.bollinger_pband(),
        })
        return df

    @staticmethod
    def atr(high, low, close, length=14):
        return ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=length).average_true_range()

    @staticmethod
    def stoch(high, low, close, k=14, d=3, smooth_k=3):
        ind = ta.momentum.StochasticOscillator(high=high, low=low, close=close, window=k, smooth_window=d)
        df = pd.DataFrame({
            f"STOCHk_{k}_{d}_{smooth_k}": ind.stoch(),
            f"STOCHd_{k}_{d}_{smooth_k}": ind.stoch_signal(),
        })
        return df

    @staticmethod
    def obv(close, volume):
        return ta.volume.OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()

    @staticmethod
    def adx(high, low, close, length=14):
        ind = ta.trend.ADXIndicator(high=high, low=low, close=close, window=length)
        df = pd.DataFrame({
            f"ADX_{length}": ind.adx(),
            f"DMP_{length}": ind.adx_pos(),
            f"DMN_{length}": ind.adx_neg(),
        })
        return df

    @staticmethod
    def mfi(high, low, close, volume, length=14):
        return ta.volume.MFIIndicator(high=high, low=low, close=close, volume=volume, window=length).money_flow_index()


pta = _pta()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.db")

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            market TEXT,
            scan_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portfolio_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            shares REAL,
            buy_price REAL,
            buy_date TEXT,
            strategy TEXT,
            score REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_id, symbol, buy_date)
        );
        CREATE TABLE IF NOT EXISTS saved_backtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            market TEXT,
            strategy TEXT,
            start_date TEXT,
            initial_capital REAL,
            rebalance_period TEXT,
            top_n INTEGER,
            total_return REAL,
            annual_return REAL,
            sharpe REAL,
            max_drawdown REAL,
            final_equity REAL,
            bench_total_return REAL,
            benchmark_name TEXT,
            n_periods INTEGER,
            result_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS saved_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            market TEXT,
            strategy TEXT,
            top5_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

db_init()


def db_save_scan(scan_date, market, strategy, top5: list):
    """Tarama sonucunu (en iyi 5 hisse) kaydet. Aynı tarih+strateji varsa güncelle."""
    import json
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO saved_scans (scan_date, market, strategy, top5_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (str(scan_date), market, strategy, json.dumps(top5, ensure_ascii=False))
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def db_get_saved_scans():
    import json
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM saved_scans ORDER BY scan_date DESC, created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            try:
                r["top5"] = json.loads(r.get("top5_json", "[]"))
            except Exception:
                r["top5"] = []
        return rows
    finally:
        conn.close()


def db_delete_scan(scan_id):
    conn = get_db_conn()
    try:
        conn.execute("DELETE FROM saved_scans WHERE id = ?", (scan_id,))
        conn.commit()
    finally:
        conn.close()

def db_create_portfolio(name, description, market, scan_date=None):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        # Eski veritabanlarında scan_date sütunu yoksa ekle
        try:
            cur.execute("ALTER TABLE portfolios ADD COLUMN scan_date TEXT")
            conn.commit()
        except Exception:
            pass
        cur.execute(
            "INSERT INTO portfolios (name, description, market, scan_date) VALUES (?, ?, ?, ?)",
            (name, description, market, str(scan_date) if scan_date else None)
        )
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()

def _parse_date_fields(row_dict, date_fields=("created_at", "updated_at"), date_only_fields=("buy_date",)):
    from datetime import date as _d, datetime as _dt
    for f in date_fields:
        v = row_dict.get(f)
        if v and isinstance(v, str):
            try:
                row_dict[f] = _dt.fromisoformat(v)
            except Exception:
                pass
    for f in date_only_fields:
        v = row_dict.get(f)
        if v and isinstance(v, str):
            try:
                row_dict[f] = _d.fromisoformat(v[:10])
            except Exception:
                pass
    return row_dict

def db_get_portfolios():
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM portfolios ORDER BY created_at DESC")
        return [_parse_date_fields(dict(r)) for r in cur.fetchall()]
    finally:
        conn.close()

def db_delete_portfolio(pid):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM portfolios WHERE id = ?", (pid,))
        conn.commit()
    finally:
        conn.close()

def db_add_stock_to_portfolio(portfolio_id, symbol, shares, buy_price, buy_date, strategy="", score=0, notes=""):
    if hasattr(buy_date, 'strftime'):
        buy_date = buy_date.strftime("%Y-%m-%d")
    elif buy_date is not None:
        buy_date = str(buy_date)[:10]
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO portfolio_stocks (portfolio_id, symbol, shares, buy_price, buy_date, strategy, score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(portfolio_id, symbol, buy_date)
            DO UPDATE SET shares = portfolio_stocks.shares + excluded.shares,
                          notes = excluded.notes
        """, (portfolio_id, symbol, shares, buy_price, buy_date, strategy, score, notes))
        sid = cur.lastrowid
        conn.commit()
        return sid
    finally:
        conn.close()

def db_get_portfolio_stocks(portfolio_id):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM portfolio_stocks WHERE portfolio_id = ? ORDER BY buy_date DESC", (portfolio_id,))
        return [_parse_date_fields(dict(r)) for r in cur.fetchall()]
    finally:
        conn.close()

def db_remove_stock_from_portfolio(stock_id):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM portfolio_stocks WHERE id = ?", (stock_id,))
        conn.commit()
    finally:
        conn.close()

def db_update_portfolio(pid, name, description):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE portfolios SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, description, pid))
        conn.commit()
    finally:
        conn.close()

def _serialize_bt_result(bt_result):
    data = {}
    for k, v in bt_result.items():
        if isinstance(v, pd.Series):
            data[k] = {"_type": "series", "index": [str(d) for d in v.index], "values": [float(x) for x in v.values]}
        elif isinstance(v, pd.DataFrame):
            data[k] = {"_type": "dataframe", "json": v.to_json(date_format="iso")}
        elif isinstance(v, (np.integer,)):
            data[k] = int(v)
        elif isinstance(v, (np.floating,)):
            data[k] = float(v)
        elif isinstance(v, (int, float, str, bool, type(None), list, dict)):
            data[k] = v
        else:
            data[k] = str(v)
    return json.dumps(data, ensure_ascii=False, default=str)

def _deserialize_bt_result(json_str):
    data = json.loads(json_str)
    result = {}
    for k, v in data.items():
        if isinstance(v, dict) and v.get("_type") == "series":
            idx = pd.to_datetime(v["index"])
            result[k] = pd.Series(v["values"], index=idx)
        elif isinstance(v, dict) and v.get("_type") == "dataframe":
            result[k] = pd.read_json(v["json"])
        else:
            result[k] = v
    return result

def db_save_backtest(name, market, strategy, start_date, initial_capital, rebalance_period, top_n, bt_result):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO saved_backtests (name, market, strategy, start_date, initial_capital, rebalance_period, top_n,
                total_return, annual_return, sharpe, max_drawdown, final_equity, bench_total_return, benchmark_name, n_periods, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, market, strategy, str(start_date), initial_capital, rebalance_period, top_n,
              float(bt_result.get("total_return", 0) or 0), float(bt_result.get("annual_return", 0) or 0), float(bt_result.get("sharpe", 0) or 0),
              float(bt_result.get("max_drawdown", 0) or 0), float(bt_result.get("final_equity", 0) or 0), float(bt_result.get("bench_total_return", 0) or 0),
              bt_result.get("benchmark_name"), int(bt_result.get("n_periods", 0) or 0), _serialize_bt_result(bt_result)))
        bid = cur.lastrowid
        conn.commit()
        return bid
    finally:
        conn.close()

def db_get_saved_backtests():
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, market, strategy, start_date, initial_capital, rebalance_period, top_n, total_return, annual_return, sharpe, max_drawdown, final_equity, benchmark_name, n_periods, created_at FROM saved_backtests ORDER BY created_at DESC")
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("created_at") and isinstance(d["created_at"], str):
                try:
                    d["created_at"] = datetime.strptime(d["created_at"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            result.append(d)
        return result
    finally:
        conn.close()

def db_get_backtest_result(bid):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT result_json FROM saved_backtests WHERE id = ?", (bid,))
        row = cur.fetchone()
        if row:
            return _deserialize_bt_result(row[0])
        return None
    finally:
        conn.close()

def db_delete_backtest(bid):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM saved_backtests WHERE id = ?", (bid,))
        conn.commit()
    finally:
        conn.close()

st.set_page_config(page_title="Portföy Optimizer", layout="wide")

# BIST 100 endeksi hisseleri (Kaynak: Borsa İstanbul, Şubat 2026)
BIST100_STOCKS = [
    "AEFES", "AFYON", "AGESA", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKFYE",
    "AKSA", "AKSEN", "ALARK", "ALFAS", "ALKIM", "ALTNY", "ANSGR", "ARCLK",
    "ARDYZ", "ASELS", "ASUZU", "ATAGY", "AYDEM", "AYGAZ", "BAGFS", "BASGZ",
    "BERA", "BIMAS", "BIOEN", "BRISA", "BRYAT", "BTCIM", "BUCIM", "CCOLA",
    "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA",
    "ENKAI", "EREGL", "EUPWR", "FROTO", "GARAN", "GENIL", "GESAN", "GLYHO",
    "GUBRF", "GWIND", "HALKB", "HEKTS", "ISCTR", "ISGYO", "ISMEN",
    "KAYSE", "KCHOL", "KLSER", "KMPUR", "KONTR", "KONYA",
    "KRDMD", "KZBGY", "LMKDC", "MAGEN", "MGROS", "MIATK", "OBAMS",
    "ODAS", "OTKAR", "OYAKC", "PAPIL", "PETKM", "PGSUS", "SAHOL",
    "SASA", "SISE", "SKBNK", "SMRTG", "SNGYO", "SOKM", "TABGD", "TATGD",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TKNSA", "TMSN", "TOASO", "TRGYO",
    "TTKOM", "TTRAK", "TUKAS", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE",
    "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN",
]

# BIST TÜM endeksi hisseleri - BIST 100 dışı (Kaynak: Borsa İstanbul / KAP, Şubat 2026)
@st.cache_data(ttl=86400)
def fetch_all_bist_stocks():
    """Bigpara'dan güncel BIST hisse listesini çeker (günlük cache)."""
    try:
        import requests as _req
        _r = _req.get(
            "https://bigpara.hurriyet.com.tr/api/v1/hisse/list",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        _data = _r.json().get("data", [])
        _tickers = sorted(set(
            x["kod"].strip() for x in _data
            if x.get("kod","").strip().isalpha() and 4 <= len(x.get("kod","").strip()) <= 6
        ))
        if len(_tickers) > 200:
            return _tickers
    except Exception:
        pass
    return None  # fallback: statik liste kullanılacak

_dynamic_bist = fetch_all_bist_stocks()

BIST_TUM_STOCKS = BIST100_STOCKS + [
    "ACSEL", "ADEL", "ADESE", "ADGYO", "AGHOL", "AGROT", "AHSGY",
    "AKBNK", "AKFGY", "AKGRT", "AKMGY", "AKSGY", "AKSUE", "AKYHO", "ALBRK",
    "ALCAR", "ALCTL", "ALKA", "ANELE", "ANGEN", "ANHYT", "ARENA",
    "ARSAN", "ARTMS", "ARZUM", "ATATP", "ATEKS", "ATLAS", "ATSYH",
    "AVHOL", "AVOD", "AVPGY", "AVTUR", "AYCES", "AYEN", "BAKAB", "BALAT",
    "BANVT", "BARMA", "BASCM", "BAYRK", "BEYAZ", "BFREN", "BIGCH", "BINHO",
    "BJKAS", "BLCYT", "BMSCH", "BMSTL", "BNTAS", "BOSSA", "BRKO",
    "BRKSN", "BRKVY", "BRLSM", "BRMEN", "BSOKE", "BURCE", "BURVA", "CASA",
    "CANTE", "CELHA", "CEMAS", "CEMTS", "CEOEM", "CMBTN", "CMENT", "CONSE",
    "COSMO", "CUSAN", "CVKMD", "DAPGM", "DARDL", "DENGE", "DERHL",
    "DERIM", "DESA", "DESPC", "DGATE", "DGGYO", "DGNMO", "DIRIT", "DITAS",
    "DMRGD", "DMSAS", "DNISI", "DOCO", "DOKTA", "DURDO", "DYOBY",
    "DZGYO", "EDATA", "EDIP", "EGEPO", "EGPRO", "EGSER", "EKIZ", "EKSUN",
    "ELITE", "EMKEL", "EMNIS", "ENERY", "ENSRI", "EPLAS", "ERBOS", "ERCB",
    "ERSU", "ESCAR", "ESCOM", "ESEN", "ETILR", "ETYAT", "EUHOL", "EUYO",
    "EYGYO", "FADE", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO",
    "FZLGY", "GARAN", "GEDIK", "GEDZA", "GEREL", "GLBMD", "GLCVY", "GLYHO",
    "GMTAS", "GOKNR", "GOLTS", "GOODY", "GOZDE", "GRSEL", "GSDDE", "GSDHO",
    "GSRAY", "GUBRF", "GUNDG", "HATEK", "HDFGS", "HEDEF", "HKTM", "HLGYO",
    "HOROZ", "HRKET", "HTTBT", "HUBVC", "HUNER", "HURGZ", "ICBCT",
    "IDGYO", "IEYHO", "IHEVA", "IHGZT", "IHLAS", "IHLGM", "IHYAY", "IMASM",
    "INDES", "INFO", "INGRM", "INTEM", "INVEO", "ISATR", "ISDMR",
    "ISFIN", "ISGSY", "ISKPL", "ISSEN", "IZFAS", "IZINV", "IZMDC", "JANTS",
    "KAPLM", "KATMR", "KAYSE", "KBORU", "KCAER", "KENT", "KERVN",
    "KFEIN", "KGYO", "KIMMR", "KLGYO", "KLMSN", "KLNMA", "KLRHO", "KLSYN",
    "KNFRT", "KONKA", "KOPOL", "KORDS", "KRPLS", "KRSTL", "KRTEK", "KRVGD",
    "KTLEV", "KTSKR", "KUTPO", "KUYAS", "KZBGY", "LIDER", "LIDFA", "LILAK",
    "LINK", "LKMNH", "LOGO", "LUKSK", "MAALT", "MACKO", "MAGEN", "MAKIM",
    "MAKTK", "MANAS", "MEGAP", "MEPET", "MERCN", "MERKO", "METRO",
    "MGROS", "MHRGY", "MIATK", "MMCAS", "MNDRS", "MNDTR", "MOBTL",
    "MOGAN", "MPARK", "MRGYO", "MRSHL", "MSGYO", "MTRKS", "MTRYO", "MZHLD",
    "NATEN", "NETAS", "NIBAS", "NUGYO", "NUHCM", "OBAMS", "OBASE", "ODAS",
    "OFSYM", "ONCSM", "ORCAY", "ORGE", "ORMA", "OSMEN", "OSTIM", "OTKAR",
    "OTTO", "OYAKC", "OYLUM", "OZKGY", "OZRDN", "OZSUB", "PAGYO", "PAMEL",
    "PAPIL", "PARSN", "PASEU", "PCILT", "PEKGY", "PENGD", "PENTA",
    "PNLSN", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME", "PSDTC", "PSGYO",
    "QUAGR", "RALYH", "RAYSG", "REEDR", "RGYAS", "RODRG", "RTALB", "RUBNS",
    "RYGYO", "RYSAS", "SAFKR", "SAMAT", "SANEL", "SANFM", "SANKO", "SARKY",
    "SASA", "SAYAS", "SEGYO", "SEKFK", "SEKUR", "SELEC", "SELVA",
    "SILVR", "SISE", "SKTAS", "SMART", "SMRTG", "SNGYO", "SNKRN", "SNPAM",
    "SODSN", "SOKM", "SONME", "SRVGY", "SUMAS", "SUNTK", "SUWEN", "TABGD",
    "TATEN", "TATGD", "TBORG", "TCELL", "TDGYO", "TEKTU", "TERA", "TEZOL",
    "TGSAS", "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL", "TMSN", "TNZTP",
    "TOASO", "TRILC", "TRGYO", "TSGYO", "TSPOR", "TTKOM", "TTRAK", "TUCLK",
    "TUKAS", "TUPRS", "TUREX", "TURSG", "UFUK", "ULAS", "ULKER", "ULUFA",
    "ULUSE", "ULUUN", "UMPAS", "UNLU", "USAK", "VAKBN", "VAKKO",
    "VANGD", "VBTYZ", "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO",
    "VRGYO", "YAPRK", "YATAS", "YEOTK", "YGGYO", "YGYO", "YKBNK", "YKSLN",
    "YONGA", "YUNSA", "YYLGD", "ZEDUR", "ZOREN", "ZRGYO",
]

BIST_TUM_STOCKS = sorted(list(set(BIST_TUM_STOCKS)))

# Dinamik liste varsa statik listeyi genişlet
if _dynamic_bist:
    BIST_TUM_STOCKS = sorted(set(BIST_TUM_STOCKS) | set(_dynamic_bist))

BIST100_DISI_STOCKS = sorted(list(set(BIST_TUM_STOCKS) - set(BIST100_STOCKS)))

BIST_STOCKS = BIST100_STOCKS

# ── ABD Hisse Evrenler ────────────────────────────────────────────────────────

MEGA_CAP_30 = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","BRK-B",
    "JPM","V","UNH","XOM","MA","COST","JNJ","HD","PG","WMT",
    "NFLX","BAC","ABBV","CRM","AMD","ORCL","LLY","MRK","CVX",
    "KO","PEP","ADBE",
]

NASDAQ_100 = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
    "NFLX","ASML","AMD","CSCO","ADBE","QCOM","INTC","INTU","TXN","AMAT",
    "BKNG","ISRG","MELI","REGN","VRTX","MU","LRCX","KLAC","PANW","CDNS",
    "SNPS","MRVL","ADP","ORLY","MAR","ABNB","CTAS","FTNT","MNST","KDP",
    "CHTR","PCAR","ROST","PAYX","DXCM","GEHC","FANG","AEP","ODFL","TEAM",
    "FAST","CEG","IDXX","MRNA","CRWD","CTSH","ON","LULU","BIIB","SIRI",
    "NXPI","ILMN","WBA","SPLK","WDAY","ZS","ANSS","MCHP","DLTR","CSGP",
    "APP","TTD","GILD","VRSK","ROP","TTWO","GFS","DDOG","CPRT","ALGN",
    "HON","ADSK","EBAY","XEL","EXC","CCEP","FWONK","JBHT","BMRN","LPLA",
    "NBIX","RIVN","SGEN","SWKS","TMUS","VRSN","ZBRA","CDW","SMCI","ARM",
]

# S&P 500 Wikipedia'dan alınamazsa kullanılacak yedek liste (~50 büyük hisse)
_SP500_FALLBACK = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","BRK-B","JPM","LLY",
    "UNH","V","XOM","MA","COST","HD","PG","JNJ","WMT","NFLX","ABBV","BAC",
    "CRM","AMD","ORCL","MRK","CVX","TMO","ADBE","KO","PEP","ACN","LIN","MCD",
    "CSCO","ABT","DHR","TXN","NKE","WFC","PM","IBM","INTU","NOW","CAT","AMGN",
    "SPGI","GE","ISRG","RTX","BKNG","HON","SYK","T","LOW","VRTX","MS","ETN",
    "GS","ELV","C","BSX","BLK","AXP","REGN","PLD","ADI","CB","DE","LRCX",
    "PANW","MMC","SO","GILD","PGR","MO","CI","KLAC","DUK","APH","EOG","ITW",
    "AON","SLB","CME","MCO","ZTS","CL","CSX","NSC","EMR","FDX","USB","WM",
    "MDLZ","MPC","PSX","TGT","PH","HCA","TJX","ICE","ECL","WELL","ORLY","GD",
]

# S&P 400 Wikipedia'dan alınamazsa kullanılacak yedek liste (~50 hisse)
_SP400_FALLBACK = [
    "GNRC","TREX","POOL","RBC","WSM","LFUS","BECN","NDSN","BLD","BLDR",
    "IBP","UFP","CSL","NVT","REXR","EXR","CUBE","STAG","VICI","GLPI",
    "CCL","RCL","ABNB","LYFT","UBER","CMG","TXRH","QSR","ROST","BURL",
    "ANF","URBN","PVH","RL","CBRE","JLL","NEE","AES","CEG","VST","NRG",
    "FSLR","ENPH","SEDG","AZO","GPC","LKQ","BWA","APTV","LEA","DAN",
]

def _last_trading_day(ref_date=None):
    """Verilen tarihin (veya bugünün) en son işlem gününü döndür.
    Cumartesi → Cuma, Pazar → Cuma, Hafta içi → aynı gün."""
    from datetime import date as _date, timedelta as _td
    d = ref_date if ref_date else _date.today()
    if hasattr(d, 'date'):
        d = d.date()
    wd = d.weekday()
    if wd == 5:    # Cumartesi
        return d - _td(days=1)
    elif wd == 6:  # Pazar
        return d - _td(days=2)
    return d


@st.cache_data(ttl=86400)
def fetch_sp500_tickers() -> list:
    """Wikipedia'dan güncel S&P 500 listesini çeker. Hata olursa _SP500_FALLBACK kullanılır."""
    import urllib.request, re as _re
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        found = _re.findall(r'<td[^>]*>\s*<a[^>]*>([A-Z]{1,5})</a>\s*</td>', html)
        result = sorted(list(set(t for t in found if t and len(t) <= 5)))
        if len(result) >= 400:
            return result
    except Exception:
        pass
    return _SP500_FALLBACK


_US_903_TICKERS = [
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
    "BF.B","BG","BHF","BIIB","BILL","BIO","BJ","BK","BKH","BKNG",
    "BKR","BLD","BLDR","BLK","BLKB","BMRN","BMY","BR","BRBR","BRK.B",
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
    "MIDD","MKC","MKSI","MLI","MLM","MMM","MMS","MNST","MO","MOG.A",
    "MORN","MOS","MP","MPC","MPWR","MRK","MRNA","MRSH","MS","MSA",
    "MSCI","MSFT","MSI","MSM","MTB","MTD","MTDR","MTG","MTN","MTSI",
    "MTZ","MU","MUR","MUSA","MZTI","NBIX","NCLH","NDAQ","NDSN","NEE",
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
    "WYNN","XEL","XOM","XPO","XRAY","XYL","XYZ","YETI","YUM","ZBH",
    "ZBRA","ZION","ZTS",
]

def fetch_sp900_tickers() -> list:
    """S&P 500 + S&P MidCap 400 — 903 sabit hisse listesi (Super Investor ile aynı)."""
    return _US_903_TICKERS


def get_us_stock_pool(pool_name: str) -> tuple:
    """4 hazır ABD hisse evreninden birini döndürür."""
    if pool_name == "Mega Cap 30":
        return MEGA_CAP_30, {}
    elif pool_name == "Nasdaq 100":
        return NASDAQ_100, {}
    elif pool_name == "S&P 500":
        return fetch_sp500_tickers(), {}
    elif pool_name in ("S&P 500 + MidCap 400", "S&P 500 + MidCap 400 (903)"):
        return fetch_sp900_tickers(), {}
    elif pool_name == "Tüm US Hisseler":
        return fetch_all_us_tickers(), {}
    return MEGA_CAP_30, {}

BIST_INDICES = {
    "BIST 100": "XU100.IS",
    "BIST 30": "XU030.IS",
    "BIST TÜM (XUTUM)": "XUTUM.IS",
    "BIST 100 DIŞI (XTUMY)": "XTUMY.IS",
    "BIST Banka": "XBANK.IS",
}

US_INDICES = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "Dow Jones": "^DJI",
}


@st.cache_data(ttl=86400)
def fetch_all_us_tickers() -> list:
    """S&P 500 + MidCap 400 + SmallCap 600 Wikipedia listelerinden ~1500 hisse çeker."""
    import urllib.request, re as _re
    tickers = set()
    urls = [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            found = _re.findall(r'<td><a[^>]*>([A-Z]{1,5}(?:\.[A-Z])?)</a>', html)
            if not found:
                found = _re.findall(r'"ticker">([A-Z]{1,5}(?:\.[A-Z])?)<', html)
            tickers.update(found)
        except Exception:
            pass
    result = sorted(t.replace(".", "-") for t in tickers if t.isalpha() or (len(t) <= 5))
    if len(result) < 100:
        # Fallback: S&P 900
        from functools import lru_cache
        return fetch_sp900_tickers()
    return result

@st.cache_data(ttl=300)
def fetch_data(tickers, start, end):
    data = {}
    errors = []
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[ticker] = df
            else:
                errors.append(ticker)
        except Exception:
            errors.append(ticker)
    return data, errors


def add_indicators(df, indicators):
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    if "SMA 20" in indicators:
        df["SMA_20"] = pta.sma(close, length=20)
    if "SMA 50" in indicators:
        df["SMA_50"] = pta.sma(close, length=50)
    if "EMA 20" in indicators:
        df["EMA_20"] = pta.ema(close, length=20)
    if "RSI" in indicators:
        df["RSI"] = pta.rsi(close, length=14)
    if "MACD" in indicators:
        macd_df = pta.macd(close)
        if macd_df is not None:
            df["MACD"] = macd_df.iloc[:, 0]
            df["MACD_Hist"] = macd_df.iloc[:, 1]
            df["MACD_Signal"] = macd_df.iloc[:, 2]
    if "Bollinger Bands" in indicators:
        bb_df = pta.bbands(close)
        if bb_df is not None:
            df["BB_Lower"] = bb_df.iloc[:, 0]
            df["BB_Middle"] = bb_df.iloc[:, 1]
            df["BB_Upper"] = bb_df.iloc[:, 2]
    if "ATR" in indicators:
        df["ATR"] = pta.atr(high, low, close)
    if "Stochastic" in indicators:
        stoch_df = pta.stoch(high, low, close)
        if stoch_df is not None:
            df["Stoch_K"] = stoch_df.iloc[:, 0]
            df["Stoch_D"] = stoch_df.iloc[:, 1]

    return df




def plot_stock_chart(df, ticker, indicators):
    has_macd = "MACD" in indicators
    has_rsi = "RSI" in indicators
    has_stoch = "Stochastic" in indicators
    n_subplots = 1 + int(has_macd) + int(has_rsi) + int(has_stoch)
    row_heights = [0.5] + [0.17] * (n_subplots - 1) if n_subplots > 1 else [1]

    subplot_titles = [ticker]
    if has_rsi:
        subplot_titles.append("RSI")
    if has_macd:
        subplot_titles.append("MACD")
    if has_stoch:
        subplot_titles.append("Stochastic")

    fig = make_subplots(
        rows=n_subplots, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=row_heights,
        subplot_titles=subplot_titles
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Fiyat"
    ), row=1, col=1)

    colors = {"SMA_20": "#FF6B6B", "SMA_50": "#4ECDC4", "EMA_20": "#FFE66D"}
    for col, color in colors.items():
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], name=col, line=dict(color=color, width=1)
            ), row=1, col=1)

    if "BB_Upper" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], name="BB Upper",
                                 line=dict(color="rgba(173,216,230,0.7)", width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], name="BB Lower",
                                 line=dict(color="rgba(173,216,230,0.7)", width=1),
                                 fill="tonexty", fillcolor="rgba(173,216,230,0.1)"), row=1, col=1)

    current_row = 2
    if has_rsi and "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                                 line=dict(color="#AB63FA", width=1.5)), row=current_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
        current_row += 1

    if has_macd and "MACD" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD",
                                 line=dict(color="#636EFA", width=1.5)), row=current_row, col=1)
        if "MACD_Signal" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="Signal",
                                     line=dict(color="#EF553B", width=1.5)), row=current_row, col=1)
        if "MACD_Hist" in df.columns:
            colors_hist = ["green" if v >= 0 else "red" for v in df["MACD_Hist"].fillna(0)]
            fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="Histogram",
                                 marker_color=colors_hist), row=current_row, col=1)
        current_row += 1

    if has_stoch and "Stoch_K" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_K"], name="%K",
                                 line=dict(color="#00CC96", width=1.5)), row=current_row, col=1)
        if "Stoch_D" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_D"], name="%D",
                                     line=dict(color="#FFA15A", width=1.5)), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)

    fig.update_layout(
        height=200 + n_subplots * 250,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50),
    )
    return fig




def analyze_obv_signal(close, volume):
    obv = pta.obv(close, volume)
    if obv is None or len(obv) < 22:
        return None, None, "Yetersiz Veri"

    obv_clean = obv.dropna()
    if len(obv_clean) < 22:
        return None, None, "Yetersiz Veri"

    last_10_close = close.iloc[-10:]
    price_std = float(last_10_close.std())
    price_mean = float(last_10_close.mean())
    price_cv = (price_std / price_mean * 100) if price_mean != 0 else 999

    obv_10_ago = float(obv_clean.iloc[-10])
    obv_now = float(obv_clean.iloc[-1])
    if obv_10_ago != 0:
        obv_change_pct = ((obv_now - obv_10_ago) / abs(obv_10_ago)) * 100
    else:
        obv_change_pct = 0

    is_price_flat = price_cv < 2.0
    is_obv_rising = obv_change_pct > 10

    if is_price_flat and is_obv_rising:
        signal = "GÜÇLÜ ALFA SİNYALİ"
    elif is_obv_rising:
        signal = "OBV Yükseliyor"
    elif is_price_flat:
        signal = "Fiyat Yatay"
    else:
        signal = "-"

    return round(obv_change_pct, 2), round(price_cv, 2), signal


@st.cache_data(ttl=300)
def get_fundamental_data(ticker):
    try:
        info = yf.Ticker(ticker).info
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        return pe, pb
    except Exception:
        return None, None


def _td_symbol(sym):
    """Yahoo Finance sembolünü Twelve Data formatına çevirir."""
    if sym.endswith(".IS"):
        return sym[:-3] + ":BIST"
    return sym


def _get_price_twelvedata(sym):
    """Tek sembol için Twelve Data API'den güncel fiyat çeker."""
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not api_key:
        return None
    td_sym = _td_symbol(sym)
    try:
        url = f"https://api.twelvedata.com/price?symbol={td_sym}&apikey={api_key}"
        r = requests.get(url, timeout=8)
        data = r.json()
        price = data.get("price")
        if price:
            return float(price)
    except Exception:
        pass
    return None


@st.cache_data(ttl=180, show_spinner=False)
def get_current_prices(symbols_tuple):
    """Verilen sembol listesi için güncel kapanış fiyatlarını döndürür. {sembol: fiyat}
    Önce Twelve Data API dener, başarısız olursa yfinance'e fallback yapar."""
    result = {}
    syms = list(symbols_tuple)
    if not syms:
        return result

    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")

    # Twelve Data toplu istek (batch)
    if api_key and syms:
        try:
            td_syms = [_td_symbol(s) for s in syms]
            batch_sym = ",".join(td_syms)
            url = f"https://api.twelvedata.com/price?symbol={batch_sym}&apikey={api_key}"
            r = requests.get(url, timeout=15)
            data = r.json()
            if len(syms) == 1:
                price = data.get("price")
                if price:
                    result[syms[0]] = float(price)
            else:
                for orig_sym, td_sym in zip(syms, td_syms):
                    entry = data.get(td_sym, {})
                    if isinstance(entry, dict):
                        price = entry.get("price")
                        if price:
                            result[orig_sym] = float(price)
        except Exception:
            pass

    # Twelve Data'dan gelemeyen sembolleri yfinance ile tamamla
    missing = [s for s in syms if s not in result]
    if missing:
        try:
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                if len(missing) == 1:
                    hist = yf.Ticker(missing[0]).history(period="10d", auto_adjust=False)
                    if hist is not None and not hist.empty:
                        cl = hist["Close"].dropna()
                        if not cl.empty:
                            result[missing[0]] = float(cl.iloc[-1])
                else:
                    dl = yf.download(missing, period="10d", auto_adjust=True,
                                     progress=False, threads=False)
                    if dl is not None and not dl.empty:
                        if isinstance(dl.columns, pd.MultiIndex):
                            close_df = dl["Close"]
                        else:
                            close_df = dl[["Close"]] if "Close" in dl.columns else dl
                        for col in close_df.columns:
                            s = close_df[col].dropna()
                            if not s.empty:
                                result[str(col)] = float(s.iloc[-1])
        except Exception:
            pass
        # Hâlâ eksik kalanları tek tek dene
        for sym in missing:
            if sym not in result:
                try:
                    hist = yf.Ticker(sym).history(period="15d", auto_adjust=False)
                    if hist is not None and not hist.empty:
                        cl = hist["Close"].dropna()
                        if not cl.empty:
                            result[sym] = float(cl.iloc[-1])
                except Exception:
                    pass

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_comprehensive_fundamentals(ticker):
    """Kapsamlı temel analiz verilerini çeker ve normalize eder.
    
    Döndürülen dict:
        pe, pb, roe, earnings_growth, revenue_growth,
        net_margin, debt_equity, current_ratio, free_cashflow,
        eps_growth_q, peg, sector
    Tüm alanlar None olabilir — None = veri yok.
    """
    try:
        info = yf.Ticker(ticker).info
        
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        
        roe = info.get("returnOnEquity")
        if roe is not None:
            roe = roe * 100
        
        earnings_growth = info.get("earningsGrowth")
        if earnings_growth is not None:
            earnings_growth = earnings_growth * 100
        
        revenue_growth = info.get("revenueGrowth")
        if revenue_growth is not None:
            revenue_growth = revenue_growth * 100
        
        net_margin = info.get("profitMargins")
        if net_margin is not None:
            net_margin = net_margin * 100
        
        debt_equity = info.get("debtToEquity")
        if debt_equity is not None:
            debt_equity = debt_equity / 100
        
        current_ratio = info.get("currentRatio")
        
        eps_growth_q = info.get("earningsQuarterlyGrowth")
        if eps_growth_q is not None:
            eps_growth_q = eps_growth_q * 100
        
        peg = info.get("pegRatio")
        sector = info.get("sector") or "-"
        
        fcf = info.get("freeCashflow")
        fcf_positive = True if (fcf is not None and fcf > 0) else (False if (fcf is not None and fcf <= 0) else None)
        
        return {
            "pe": pe,
            "pb": pb,
            "roe": roe,
            "earnings_growth": earnings_growth,
            "revenue_growth": revenue_growth,
            "net_margin": net_margin,
            "debt_equity": debt_equity,
            "current_ratio": current_ratio,
            "eps_growth_q": eps_growth_q,
            "fcf_positive": fcf_positive,
            "peg": peg,
            "sector": sector,
        }
    except Exception:
        return None


def calc_fundamental_score(fund, strategy="Alfa Portföyü"):
    """Temel veri sözlüğünden 0-100 arası bir temel analiz skoru hesaplar.
    
    Strateji bazlı ağırlıklar:
      Alfa  → büyüme odaklı  (EPS büyümesi, ciro büyümesi, ROE yüksek)
      Beta  → momentum+kalite (EPS büyümesi, net marj, borç/özkaynaklar)
      Delta → değer odaklı   (düşük F/K, F/DD, borç ve nakit akışı)
    """
    if fund is None:
        return 0.0, {}

    # Tüm sayısal alanları güvenli float'a çevir (string gelirse hata vermesin)
    def _safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    fund = {k: (_safe_float(v) if k not in ("fcf_positive",) else v) for k, v in fund.items()}

    score = 0.0
    max_score = 0.0
    detail = {}

    def _add(label, value, weight, description=""):
        nonlocal score, max_score
        max_score += weight
        if value is not None and value > 0:
            score += value * weight
        detail[label] = {"value": value, "contribution": round((value or 0) * weight, 1), "description": description}

    def _add_raw(label, pts, weight, description=""):
        nonlocal score, max_score
        max_score += weight
        score += pts * weight
        detail[label] = {"value": pts, "contribution": round(pts * weight, 1), "description": description}

    # ── TEMEL METRİKLER (tüm stratejiler) ───────────────────────────────────
    # ROE (Özsermaye Kârlılığı)
    roe = fund.get("roe")
    roe_score = 0.0
    if roe is not None:
        if roe >= 30:    roe_score = 1.0
        elif roe >= 20:  roe_score = 0.8
        elif roe >= 15:  roe_score = 0.6
        elif roe >= 10:  roe_score = 0.4
        elif roe >= 5:   roe_score = 0.2
        else:            roe_score = 0.0

    # Kâr Büyümesi (YoY)
    eg = fund.get("earnings_growth")
    eg_score = 0.0
    if eg is not None:
        if eg >= 50:     eg_score = 1.0
        elif eg >= 30:   eg_score = 0.85
        elif eg >= 20:   eg_score = 0.7
        elif eg >= 10:   eg_score = 0.5
        elif eg >= 0:    eg_score = 0.3
        else:            eg_score = 0.0

    # Çeyreksel EPS büyümesi (hızlanma sinyali)
    eps_q = fund.get("eps_growth_q")
    eps_q_score = 0.0
    if eps_q is not None:
        if eps_q >= 30:   eps_q_score = 1.0
        elif eps_q >= 15: eps_q_score = 0.7
        elif eps_q >= 0:  eps_q_score = 0.4
        else:             eps_q_score = 0.0

    # Ciro Büyümesi
    rg = fund.get("revenue_growth")
    rg_score = 0.0
    if rg is not None:
        if rg >= 30:     rg_score = 1.0
        elif rg >= 20:   rg_score = 0.8
        elif rg >= 10:   rg_score = 0.6
        elif rg >= 5:    rg_score = 0.4
        elif rg >= 0:    rg_score = 0.2
        else:            rg_score = 0.0

    # Net Kâr Marjı
    nm = fund.get("net_margin")
    nm_score = 0.0
    if nm is not None:
        if nm >= 25:     nm_score = 1.0
        elif nm >= 15:   nm_score = 0.8
        elif nm >= 10:   nm_score = 0.6
        elif nm >= 5:    nm_score = 0.4
        elif nm >= 0:    nm_score = 0.2
        else:            nm_score = 0.0

    # F/K Oranı (P/E)
    pe = fund.get("pe")
    pe_score = 0.0
    if pe is not None and pe > 0:
        if pe <= 10:     pe_score = 1.0
        elif pe <= 15:   pe_score = 0.85
        elif pe <= 20:   pe_score = 0.65
        elif pe <= 30:   pe_score = 0.45
        elif pe <= 40:   pe_score = 0.25
        else:            pe_score = 0.0

    # F/DD Oranı (P/B)
    pb = fund.get("pb")
    pb_score = 0.0
    if pb is not None and pb > 0:
        if pb <= 1.0:    pb_score = 1.0
        elif pb <= 2.0:  pb_score = 0.8
        elif pb <= 3.0:  pb_score = 0.6
        elif pb <= 5.0:  pb_score = 0.3
        else:            pb_score = 0.0

    # Borç / Özsermaye
    de = fund.get("debt_equity")
    de_score = 0.0
    if de is not None:
        if de <= 0.2:    de_score = 1.0
        elif de <= 0.5:  de_score = 0.8
        elif de <= 1.0:  de_score = 0.6
        elif de <= 2.0:  de_score = 0.3
        else:            de_score = 0.0

    # Cari Oran (Likidite)
    cr = fund.get("current_ratio")
    cr_score = 0.0
    if cr is not None:
        if cr >= 3.0:    cr_score = 1.0
        elif cr >= 2.0:  cr_score = 0.8
        elif cr >= 1.5:  cr_score = 0.6
        elif cr >= 1.0:  cr_score = 0.3
        else:            cr_score = 0.0

    # Serbest Nakit Akışı
    fcf_pos = fund.get("fcf_positive")
    fcf_score = 1.0 if fcf_pos is True else (0.0 if fcf_pos is False else 0.5)

    # ── STRATEJİ BAZLI AĞIRLIKLAR ────────────────────────────────────────────
    if strategy == "Alfa Portföyü":
        # Büyüme odaklı: EPS büyümesi + ROE + ciro büyümesi en önemli
        weights = {
            "ROE":           (roe_score,   25),
            "EPS Büyümesi":  (eg_score,    25),
            "Çeyreksel EPS": (eps_q_score, 15),
            "Ciro Büyümesi": (rg_score,    15),
            "Net Marj":      (nm_score,    10),
            "Borç/Özkaynk":  (de_score,     5),
            "Serbest NCF":   (fcf_score,    5),
        }

    elif strategy == "Beta Portföyü":
        # Momentum + kalite: EPS büyümesi + net marj + borç güvenliği
        weights = {
            "EPS Büyümesi":  (eg_score,    30),
            "Çeyreksel EPS": (eps_q_score, 20),
            "Ciro Büyümesi": (rg_score,    15),
            "Net Marj":      (nm_score,    15),
            "ROE":           (roe_score,   10),
            "Borç/Özkaynk":  (de_score,    10),
        }

    else:  # Delta Portföyü — değer odaklı
        weights = {
            "F/K Oranı":     (pe_score,    25),
            "F/DD Oranı":    (pb_score,    25),
            "ROE":           (roe_score,   15),
            "Net Marj":      (nm_score,    15),
            "Borç/Özkaynk":  (de_score,    10),
            "Cari Oran":     (cr_score,     5),
            "Serbest NCF":   (fcf_score,    5),
        }

    raw_total = 0.0
    total_weight = 0.0
    for label, (val_score, weight) in weights.items():
        contribution = val_score * weight
        raw_total += contribution
        total_weight += weight
        detail[label] = {
            "skor": round(val_score * 100, 1),
            "katkı": round(contribution, 1),
            "ağırlık": weight,
        }

    final_score = (raw_total / total_weight * 100) if total_weight > 0 else 0.0
    return round(final_score, 1), detail


@st.cache_data(ttl=300)
def get_alfa_fundamental_data(ticker):
    try:
        info = yf.Ticker(ticker).info
        pe = info.get("trailingPE") or info.get("forwardPE")
        roe = info.get("returnOnEquity")
        if roe is not None:
            roe = roe * 100
        earnings_growth = info.get("earningsGrowth")
        if earnings_growth is not None:
            earnings_growth = earnings_growth * 100
        peg = info.get("pegRatio")
        sector = info.get("sector") or "-"
        return {
            "pe": pe,
            "roe": roe,
            "earnings_growth": earnings_growth,
            "peg": peg,
            "sector": sector,
        }
    except Exception:
        return None


def calc_rs_slope(close_series, bench_close_series, period=20):
    if close_series is None or bench_close_series is None:
        return None
    if len(close_series) < period or len(bench_close_series) < period:
        return None

    common_idx = close_series.index.intersection(bench_close_series.index)
    if len(common_idx) < period:
        return None

    stock_c = close_series.loc[common_idx].iloc[-period:]
    bench_c = bench_close_series.loc[common_idx].iloc[-period:]

    bench_vals = bench_c.values.astype(float)
    if (bench_vals == 0).any():
        return None

    rs_line = stock_c.values.astype(float) / bench_vals

    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    rs_mean = rs_line.mean()
    slope = np.sum((x - x_mean) * (rs_line - rs_mean)) / np.sum((x - x_mean) ** 2)

    return slope


def _normalize_weights(weights, keys):
    raw = {k: weights.get(k, 0) for k in keys}
    total = sum(raw.values())
    if total == 0:
        n = len(keys)
        return {k: 1.0 / n for k in keys}
    return {k: v / total for k, v in raw.items()}


def calc_alfa_score(rs_slope_norm, eg_rank_pct, roe_rank_pct, weights, vol_penalty=0, fund_score=0.0, fund_weight=0.40):
    """Alfa skoru: teknik (RS eğimi) + temel (EPS büyümesi, ROE) birleşik skor.
    
    fund_weight: temel analizin toplam skordaki ağırlığı (0.0-1.0). Varsayılan %40.
    Geriye kalan (1 - fund_weight) teknik bileşene verilir.
    """
    tech_weight = max(0.0, 1.0 - fund_weight)

    nw = _normalize_weights(weights, ["rs_slope", "kar_buyumesi_rank", "roe_rank"])

    rs_score = max(0, min(100, rs_slope_norm))
    eg_score = max(0, min(100, eg_rank_pct))
    roe_score = max(0, min(100, roe_rank_pct))

    tech_total = rs_score * nw["rs_slope"] + eg_score * nw["kar_buyumesi_rank"] + roe_score * nw["roe_rank"]
    tech_total = max(0, min(100, tech_total))

    combined = tech_total * tech_weight + fund_score * fund_weight
    combined = combined * (1 - vol_penalty)
    return round(max(0, min(100, combined)), 1)


def calc_beta_score(mfi_val, adx_val, relative_return, weights, fund_score=0.0, fund_weight=0.30):
    """Beta skoru: teknik momentum (ADX, MFI) + temel kalite birleşik skor.
    
    fund_weight: temel analizin ağırlığı. Varsayılan %30 (momentum ağırlıklı).
    """
    tech_weight = max(0.0, 1.0 - fund_weight)

    nw = _normalize_weights(weights, ["momentum_mfi", "adx_gucu", "relative_strength"])

    mfi_dist = abs(mfi_val - 80)
    mfi_score = max(0, min(100, 100 - mfi_dist * 3))
    adx_score = max(0, min(100, (adx_val - 20) / 80 * 100))
    rs_score = max(0, min(100, 50 + relative_return * 5))

    tech_total = mfi_score * nw["momentum_mfi"] + adx_score * nw["adx_gucu"] + rs_score * nw["relative_strength"]
    tech_total = max(0, min(100, tech_total))

    combined = tech_total * tech_weight + fund_score * fund_weight
    return round(max(0, min(100, combined)), 1)


def calc_delta_score(rs_3m_excess, sma50_proximity_pct, mfi_val, mfi_rising, weights, fund_score=0.0, fund_weight=0.40):
    """Delta skoru: teknik destek (SMA50, MFI) + temel değer birleşik skor.
    
    fund_weight: temel analizin ağırlığı. Varsayılan %40 (değer odaklı).
    """
    tech_weight = max(0.0, 1.0 - fund_weight)

    nw = _normalize_weights(weights, ["relative_strength", "destek_yakinligi", "para_girisi"])

    rs_score = max(0, min(100, rs_3m_excess * 5))
    proximity_score = max(0, min(100, (8 - sma50_proximity_pct) / 8 * 100)) if sma50_proximity_pct <= 8 else 0
    mfi_score = 0
    if mfi_val > 40 and mfi_rising:
        mfi_score = max(0, min(100, (mfi_val - 40) * 2.5))

    tech_total = rs_score * nw["relative_strength"] + proximity_score * nw["destek_yakinligi"] + mfi_score * nw["para_girisi"]
    tech_total = max(0, min(100, tech_total))

    combined = tech_total * tech_weight + fund_score * fund_weight
    return round(max(0, min(100, combined)), 1)


def run_screening(stock_list, market, screen_type, score_weights=None, screen_date=None):
    is_bist = market == "BIST (Borsa İstanbul)"
    tickers = [s + ".IS" for s in stock_list] if is_bist else list(stock_list)
    display_map = {(s + ".IS" if is_bist else s): s for s in stock_list}

    if score_weights is None:
        score_weights = {}

    if screen_date is None:
        end = datetime.now()
    else:
        end = datetime.combine(screen_date, datetime.max.time())

    # yfinance end parametresi exclusive — screen_date'i dahil etmek için +1 gün
    download_end = end + timedelta(days=1)

    # Benchmark indir — backtest ile aynı 400 günlük lookback
    benchmark_ticker = None
    bench_1m_return = 0.0
    bench_close = None
    bench_start = end - timedelta(days=400)
    bench_candidates = ["XU100.IS", "^XU100", "GARAN.IS"] if is_bist else ["SPY", "^GSPC"]
    for _cand in bench_candidates:
        try:
            _bd = batch_download(tuple([_cand]), str(bench_start.date()), str(download_end.date()))
            _df = _bd.get(_cand)
            if _df is not None and not _df.empty and len(_df) > 30:
                if isinstance(_df.columns, pd.MultiIndex):
                    _df.columns = _df.columns.get_level_values(0)
                # Backtest gibi: sadece screen_date'e kadar olan veriyi kullan
                _df = _df[_df.index <= end]
                bench_close = _df["Close"].squeeze()
                if isinstance(bench_close, pd.DataFrame):
                    bench_close = bench_close.iloc[:, 0]
                if len(bench_close) >= 22:
                    bench_1m_return = (float(bench_close.iloc[-1]) / float(bench_close.iloc[-22]) - 1) * 100
                benchmark_ticker = _cand
                break
        except Exception:
            continue

    # Backtest ile aynı 400 günlük lookback
    start = end - timedelta(days=400)

    results = []
    progress_bar = st.progress(0, text="Veriler toplu indiriliyor...")

    # ── Tüm hisseleri tek seferde toplu indir ────────────────────────────────
    all_data = batch_download(tuple(tickers), str(start.date()), str(download_end.date()))

    # Backtest gibi: her hisse verisini screen_date'e kadar kes
    for tk in list(all_data.keys()):
        all_data[tk] = all_data[tk][all_data[tk].index <= end]

    progress_bar.progress(0.2, text="Tarama yapılıyor...")

    if screen_type == "Alfa Portföyü":
        bench_ann_vol = None
        if bench_close is not None and len(bench_close) >= 60:
            bench_daily_ret = bench_close.pct_change().dropna()
            if len(bench_daily_ret) >= 20:
                bench_ann_vol = float(bench_daily_ret.std()) * np.sqrt(252)

        alfa_candidates = []
        for idx, ticker in enumerate(tickers):
            progress_bar.progress(0.2 + 0.6 * (idx + 1) / max(len(tickers), 1), text=f"Analiz: {display_map.get(ticker, ticker)}")
            try:
                df = all_data.get(ticker)
                if df is None or df.empty or len(df) < 60:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                close  = df["Close"]
                volume = df["Volume"]
                high   = df["High"] if "High" in df.columns else close
                low    = df["Low"]  if "Low"  in df.columns else close
                last_price = float(close.iloc[-1])
                name = display_map.get(ticker, ticker)

                # ── Zorunlu 1: SMA50 üzeri ───────────────────────────────────
                sma50_val = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
                if sma50_val is None or sma50_val <= 0 or last_price < sma50_val:
                    continue

                # ── Zorunlu 2: SMA200 üzeri ──────────────────────────────────
                sma200_val = None
                sma200_bonus = 0.0
                if len(close) >= 200:
                    sma200_val = float(close.rolling(200).mean().iloc[-1])
                    if sma200_val > 0 and last_price < sma200_val * 0.97:
                        continue
                    if sma200_val and sma200_val > 0:
                        gap = (last_price / sma200_val - 1) * 100
                        if gap >= 20:   sma200_bonus = 20.0
                        elif gap >= 10: sma200_bonus = 12.0
                        elif gap >= 0:  sma200_bonus = 5.0

                # ── Zorunlu 3: 6 aylık mutlak getiri pozitif ─────────────────
                if len(close) >= 126:
                    abs_6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100
                    if abs_6m < 0:
                        continue

                # ── Zorunlu 4: Minimum likidite ──────────────────────────────
                if len(volume) >= 20:
                    avg_vol_20d = float(volume.iloc[-20:].mean())
                    min_vol = 10_000 if is_bist else 500_000
                    if avg_vol_20d < min_vol:
                        continue

                # ── Göreceli getiriler ────────────────────────────────────────
                excess_1m = excess_3m = excess_6m = excess_12m = 0.0
                if bench_close is not None:
                    if len(close) >= 22 and len(bench_close) >= 22:
                        excess_1m = ((close.iloc[-1]/close.iloc[-22]) - (bench_close.iloc[-1]/bench_close.iloc[-22])) * 100
                    if len(close) >= 63 and len(bench_close) >= 63:
                        excess_3m = ((close.iloc[-1]/close.iloc[-63]) - (bench_close.iloc[-1]/bench_close.iloc[-63])) * 100
                    if len(close) >= 126 and len(bench_close) >= 126:
                        excess_6m = ((close.iloc[-1]/close.iloc[-126]) - (bench_close.iloc[-1]/bench_close.iloc[-126])) * 100
                    if len(close) >= 240 and len(bench_close) >= 240:
                        excess_12m = ((close.iloc[-1]/close.iloc[-240]) - (bench_close.iloc[-1]/bench_close.iloc[-240])) * 100

                if excess_3m < -5 and excess_6m < -10:
                    continue

                # ── Momentum skoru (backtest ile aynı ağırlıklar) ────────────
                momentum_score = (excess_12m * 0.30 + excess_6m * 0.30 +
                                  excess_3m  * 0.25 + excess_1m * 0.15)

                # ── ADX — Trend gücü bonusu ───────────────────────────────────
                adx_bonus = 0.0
                if len(close) >= 28:
                    try:
                        hi = high.values; lo = low.values; cl = close.values
                        tr = np.maximum(hi[1:]-lo[1:], np.maximum(
                             np.abs(hi[1:]-cl[:-1]), np.abs(lo[1:]-cl[:-1])))
                        atr14 = pd.Series(tr).ewm(span=14, adjust=False).mean()
                        dm_pos = np.where((hi[1:]-hi[:-1]) > (lo[:-1]-lo[1:]),
                                          np.maximum(hi[1:]-hi[:-1], 0), 0)
                        dm_neg = np.where((lo[:-1]-lo[1:]) > (hi[1:]-hi[:-1]),
                                          np.maximum(lo[:-1]-lo[1:], 0), 0)
                        di_pos = pd.Series(dm_pos).ewm(span=14,adjust=False).mean()/(atr14+1e-9)*100
                        di_neg = pd.Series(dm_neg).ewm(span=14,adjust=False).mean()/(atr14+1e-9)*100
                        dx = np.abs(di_pos-di_neg)/(di_pos+di_neg+1e-9)*100
                        adx = float(pd.Series(dx).ewm(span=14,adjust=False).mean().iloc[-1])
                        if adx >= 35:   adx_bonus = 20.0
                        elif adx >= 25: adx_bonus = 12.0
                        elif adx >= 20: adx_bonus = 5.0
                    except Exception:
                        pass

                # ── İvme bonusu (backtest ile aynı) ──────────────────────────
                acceleration = 0.0
                if excess_1m > excess_3m > 0:
                    acceleration += min(25.0, (excess_1m - excess_3m) * 0.7)
                if excess_3m > excess_6m > 0:
                    acceleration += min(15.0, (excess_3m - excess_6m) * 0.4)

                # ── 52-hafta yüksek yakınlığı (backtest ile aynı) ────────────
                high52w_bonus = 0.0
                lookback_52w = min(252, len(close) - 1)
                high_52w = float(close.iloc[-lookback_52w:].max())
                if high_52w > 0:
                    dist_pct = (last_price / high_52w - 1) * 100
                    if dist_pct >= -3:    high52w_bonus = 25.0
                    elif dist_pct >= -10: high52w_bonus = 15.0
                    elif dist_pct >= -20: high52w_bonus = 7.0

                # ── Hacim ivmesi (backtest ile aynı) ─────────────────────────
                vol_surge_bonus = 0.0
                if len(volume) >= 20:
                    v5  = float(volume.iloc[-5:].mean())
                    v20 = float(volume.iloc[-20:].mean())
                    if v20 > 0:
                        vr = v5 / v20
                        if vr > 2.5:   vol_surge_bonus = 18.0
                        elif vr > 1.8: vol_surge_bonus = 10.0
                        elif vr > 1.3: vol_surge_bonus = 4.0

                # ── Volatilite cezası (backtest ile aynı) ────────────────────
                vol_penalty = 0.0
                vol_excessive = False
                stock_daily_ret = close.pct_change().dropna()
                stock_ann_vol = float(stock_daily_ret.std()) * np.sqrt(252) if len(stock_daily_ret) >= 20 else None
                if stock_ann_vol is not None and bench_ann_vol is not None and bench_ann_vol > 0:
                    vr2 = stock_ann_vol / bench_ann_vol
                    if vr2 > 2.5:
                        vol_excessive = True
                        vol_penalty = min(0.45, (vr2 - 2.5) * 0.20)

                fund = get_alfa_fundamental_data(ticker)
                pe  = fund.get("pe")  if fund else None
                roe = fund.get("roe") if fund else None
                eg  = fund.get("earnings_growth") if fund else None

                alfa_candidates.append({
                    "ticker": ticker,
                    "name": name,
                    "df": df,
                    "close": close,
                    "volume": volume,
                    "last_price": last_price,
                    "momentum_score": momentum_score,
                    "excess_1m": excess_1m,
                    "excess_3m": excess_3m,
                    "excess_6m": excess_6m,
                    "excess_12m": excess_12m,
                    "acceleration": acceleration,
                    "high52w_bonus": high52w_bonus,
                    "sma200_bonus": sma200_bonus,
                    "vol_surge_bonus": vol_surge_bonus,
                    "adx_bonus": adx_bonus,
                    "sma200_val": sma200_val,
                    "roe": roe,
                    "eg": eg,
                    "pe": pe,
                    "stock_ann_vol": stock_ann_vol,
                    "vol_penalty": vol_penalty,
                    "vol_excessive": vol_excessive,
                    "_comprehensive_fund": get_comprehensive_fundamentals(ticker),
                })
            except Exception:
                continue

        progress_bar.progress(0.0, text="Sıralama ve puanlama yapılıyor...")

        # ── Normalize: momentum_score (backtest ile aynı yöntem) ─────────────
        all_mom = [c["momentum_score"] for c in alfa_candidates]
        max_mom = max(all_mom) if all_mom else 1

        fund_weight_alfa = score_weights.get("temel_agirlik", 0.40)

        for cidx, cand in enumerate(alfa_candidates):
            progress_bar.progress((cidx + 1) / max(len(alfa_candidates), 1), text=f"Puanlama: {cand['name']}")

            mom_norm = (cand["momentum_score"] / max_mom * 100) if max_mom != 0 else 50
            bonus = (cand["acceleration"] + cand["high52w_bonus"] + cand["sma200_bonus"] +
                     cand["vol_surge_bonus"] + cand.get("adx_bonus", 0.0))
            score = round(max(0, min(200, (mom_norm + bonus) * (1 - cand["vol_penalty"]))), 1)

            # Temel veri: sadece bilgi kolonları için (skoru etkilemez)
            fund_data = cand.get("_comprehensive_fund")
            fund_score, _ = calc_fundamental_score(fund_data, "Alfa Portföyü")

            vol_str = f"{cand['stock_ann_vol']*100:.1f}%" if cand["stock_ann_vol"] else "-"
            fund_nm = fund_data.get("net_margin") if fund_data else None
            fund_rg = fund_data.get("revenue_growth") if fund_data else None
            fund_de = fund_data.get("debt_equity") if fund_data else None
            fund_pb = fund_data.get("pb") if fund_data else None

            def _fmt(v, d=2):
                try:
                    return round(float(v), d) if v is not None else "-"
                except (TypeError, ValueError):
                    return "-"

            results.append({
                "Sembol": cand["name"],
                "Yatırım Uzmanı Skoru": score,
                "Temel Skor": round(fund_score, 1),
                "Son Fiyat": round(cand["last_price"], 2),
                "Excess 1A (%)": round(cand["excess_1m"], 2),
                "Excess 3A (%)": round(cand["excess_3m"], 2),
                "Excess 6A (%)": round(cand["excess_6m"], 2),
                "Momentum Skoru": round(mom_norm, 1),
                "İvme Bonusu": round(cand["acceleration"], 1),
                "52H Yüksek Yakınlık": round(cand["high52w_bonus"], 1),
                "Hacim İvmesi": round(cand["vol_surge_bonus"], 1),
                "ROE (%)": _fmt(cand["roe"]),
                "Kar Büyümesi (%)": _fmt(cand["eg"]),
                "Ciro Büyümesi (%)": _fmt(fund_rg),
                "Net Marj (%)": _fmt(fund_nm),
                "F/K": _fmt(cand["pe"]),
                "F/DD": _fmt(fund_pb),
                "Borç/Özkaynk": _fmt(fund_de),
                "Volatilite": vol_str,
                "SMA200": round(cand["sma200_val"], 2) if cand["sma200_val"] else "-",
                "Sinyal": "Momentum İvmesi",
            })

        progress_bar.empty()
        results.sort(key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)
        return results

    fund_weight_beta = 0.0   # Backtest uyumu: temel veri skoru etkilemez
    fund_weight_delta = 0.0  # Backtest uyumu: temel veri skoru etkilemez

    for idx, ticker in enumerate(tickers):
        progress_bar.progress(0.2 + 0.7 * (idx + 1) / max(len(tickers), 1), text=f"Analiz: {display_map.get(ticker, ticker)}")
        try:
            df = all_data.get(ticker)
            if df is None or df.empty or len(df) < 50:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]
            last_price = float(close.iloc[-1])
            name = display_map.get(ticker, ticker)

            if screen_type == "Beta Portföyü":
                adx_df = pta.adx(high, low, close)
                if adx_df is None:
                    continue
                adx_val = float(adx_df.iloc[-1, 0])
                if adx_val <= 20:
                    continue

                ema50 = pta.ema(close, length=50)
                if ema50 is None:
                    continue
                if last_price <= float(ema50.iloc[-1]):
                    continue

                mfi = pta.mfi(high, low, close, volume)
                if mfi is None:
                    continue
                mfi_val = float(mfi.iloc[-1])
                if mfi_val <= 50:
                    continue

                stock_1m_return = 0.0
                if len(close) >= 22:
                    stock_1m_return = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100
                relative_return = stock_1m_return - bench_1m_return

                # Beta temel analiz — EPS büyümesi zorunlu değil ama skor katkısı
                fund_data = get_comprehensive_fundamentals(ticker)
                fund_score, _ = calc_fundamental_score(fund_data, "Beta Portföyü")

                # Negatif EPS büyümesi → skor cezası
                if fund_data:
                    eg_val = fund_data.get("earnings_growth")
                    if eg_val is not None and eg_val < -30:
                        continue  # Kâr ciddi düşüşte ise hisseyi ele

                score = calc_beta_score(
                    mfi_val, adx_val, relative_return, score_weights,
                    fund_score=fund_score, fund_weight=fund_weight_beta,
                )

                fund_roe = fund_data.get("roe") if fund_data else None
                fund_eg = fund_data.get("earnings_growth") if fund_data else None
                fund_rg = fund_data.get("revenue_growth") if fund_data else None
                fund_nm = fund_data.get("net_margin") if fund_data else None
                fund_de = fund_data.get("debt_equity") if fund_data else None

                results.append({
                    "Sembol": name,
                    "Yatırım Uzmanı Skoru": score,
                    "Temel Skor": fund_score,
                    "Son Fiyat": round(last_price, 2),
                    "ADX": round(adx_val, 2),
                    "EMA(50)": round(float(ema50.iloc[-1]), 2),
                    "MFI": round(mfi_val, 2),
                    "Göreceli Getiri (%)": round(relative_return, 2),
                    "ROE (%)": round(fund_roe, 2) if fund_roe else "-",
                    "Kar Büyümesi (%)": round(fund_eg, 2) if fund_eg else "-",
                    "Ciro Büyümesi (%)": round(fund_rg, 2) if fund_rg else "-",
                    "Net Marj (%)": round(fund_nm, 2) if fund_nm else "-",
                    "Borç/Özkaynk": round(fund_de, 2) if fund_de else "-",
                    "Sinyal": "Momentum",
                })

            elif screen_type == "Delta Portföyü":
                if len(close) < 60:
                    continue

                # ── SMA200 toparlanma filtresi ──────────────────────────────
                sma200_series = close.rolling(200).mean() if len(close) >= 200 else close.rolling(100).mean()
                if pd.isna(sma200_series.iloc[-1]):
                    continue
                sma200_val = float(sma200_series.iloc[-1])
                dist_to_sma200 = (last_price / sma200_val - 1) * 100

                crossed_above = False
                if len(close) >= 210:
                    c10ago = float(close.iloc[-10])
                    sma200_10ago = float(sma200_series.iloc[-10])
                    if c10ago < sma200_10ago and last_price >= sma200_val:
                        crossed_above = True

                if not crossed_above and abs(dist_to_sma200) > 12:
                    continue

                # ── 52-hafta yüksekten düzeltme ────────────────────────────
                lookback_52w = min(252, len(close) - 1)
                high_52w = float(close.iloc[-lookback_52w:].max())
                dist_from_high = (last_price / high_52w - 1) * 100
                if not (-70 <= dist_from_high <= -10):
                    continue

                # ── RSI toparlanma ─────────────────────────────────────────
                rsi_series = pta.rsi(close, length=14)
                if rsi_series is None or len(rsi_series) < 5:
                    continue
                rsi_now = float(rsi_series.iloc[-1])
                if not (35 <= rsi_now <= 68):
                    continue
                rsi_rising = rsi_now > float(rsi_series.iloc[-5])

                # ── Göreceli momentum ──────────────────────────────────────
                bench_close_now = float(bench_df["Close"].iloc[-1]) if bench_df is not None and not bench_df.empty else None
                excess_1m = 0.0
                excess_3m = 0.0
                if bench_df is not None and len(bench_df) >= 22 and len(close) >= 22:
                    s1 = (last_price / float(close.iloc[-22]) - 1) * 100
                    b1 = (float(bench_df["Close"].iloc[-1]) / float(bench_df["Close"].iloc[-22]) - 1) * 100
                    excess_1m = s1 - b1
                if bench_df is not None and len(bench_df) >= 63 and len(close) >= 63:
                    s3 = (last_price / float(close.iloc[-63]) - 1) * 100
                    b3 = (float(bench_df["Close"].iloc[-1]) / float(bench_df["Close"].iloc[-63]) - 1) * 100
                    excess_3m = s3 - b3

                if excess_1m < -10:
                    continue

                # ── Hacim ──────────────────────────────────────────────────
                vol_ratio = 1.0
                if len(volume) >= 20:
                    v5 = float(volume.iloc[-5:].mean())
                    v20 = float(volume.iloc[-20:].mean())
                    if v20 > 0:
                        vol_ratio = v5 / v20

                # ── Temel analiz ───────────────────────────────────────────
                fund_data = get_comprehensive_fundamentals(ticker)
                fund_score, _ = calc_fundamental_score(fund_data, "Delta Portföyü")
                fund_pe = fund_data.get("pe") if fund_data else None
                fund_pb = fund_data.get("pb") if fund_data else None
                fund_roe = fund_data.get("roe") if fund_data else None
                fund_nm = fund_data.get("net_margin") if fund_data else None
                fund_de = fund_data.get("debt_equity") if fund_data else None

                # ── Skor ───────────────────────────────────────────────────
                base_score = excess_1m * 0.5 + excess_3m * 0.3
                crossing_bonus = 30.0 if crossed_above else (15.0 if dist_to_sma200 >= 0 else 5.0)
                rsi_bonus = 10.0 if (rsi_rising and rsi_now > 45) else 3.0
                vol_bonus = min(15.0, (vol_ratio - 1.0) * 15) if vol_ratio > 1.2 else 0.0
                depth_bonus = min(20.0, abs(dist_from_high) * 0.3)
                tech_score = base_score + crossing_bonus + rsi_bonus + vol_bonus + depth_bonus

                fund_wt = fund_weight_delta
                total_score = tech_score * (1 - fund_wt) + fund_score * fund_wt

                results.append({
                    "Sembol": name,
                    "Yatırım Uzmanı Skoru": round(max(0, total_score), 1),
                    "Temel Skor": fund_score,
                    "Son Fiyat": round(last_price, 2),
                    "SMA200 Uzaklık (%)": round(dist_to_sma200, 2),
                    "52H Yüksekten (%)": round(dist_from_high, 2),
                    "RSI(14)": round(rsi_now, 1),
                    "Excess 1A (%)": round(excess_1m, 2),
                    "Excess 3A (%)": round(excess_3m, 2),
                    "SMA200 Geçişi": "✓ Yeni Geçiş" if crossed_above else "-",
                    "Hacim/20G Ort": round(vol_ratio, 2),
                    "F/K": round(fund_pe, 2) if fund_pe else "-",
                    "F/DD": round(fund_pb, 2) if fund_pb else "-",
                    "ROE (%)": round(fund_roe, 2) if fund_roe else "-",
                    "Net Marj (%)": round(fund_nm, 2) if fund_nm else "-",
                    "Borç/Özkaynk": round(fund_de, 2) if fund_de else "-",
                    "Sinyal": "SMA200 Toparlanma",
                })

        except Exception:
            continue

    progress_bar.empty()

    results.sort(key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def batch_download(tickers, start_str, end_str):
    """
    Veri okuma — SADECE SQLite cache'ten oku, yeni indirme yapma.
    Tüm indirmeler pre-download adımında tamamlanmış olmalı.
    Cache eksikse yfinance ile TEK SEFERLIK küçük fallback (sadece eksik hisseler).
    """
    ticker_list = list(tickers)
    if not ticker_list:
        return {}

    # ── 1. SQLite cache'ten oku (indirme YOK) ────────────────────────────────
    if _USE_DATA_CACHE:
        try:
            from data_cache import _load_from_cache, init_price_cache as _dc_init3
            _dc_init3()
            result = {}
            missing = []
            import pandas as _pd_stale
            _end_ts = _pd_stale.Timestamp(end_str)
            _stale_cutoff = _end_ts - _pd_stale.Timedelta(days=5)
            for tk in ticker_list:
                df = _load_from_cache(tk, start_str, end_str)
                if df is not None and not df.empty:
                    _last = _pd_stale.Timestamp(df.index[-1])
                    if _last.tz is not None:
                        _last = _last.tz_localize(None)
                    if _last < _stale_cutoff:
                        missing.append(tk)
                    else:
                        result[tk] = df

            # Eksik hisseler için Twelve Data (BIST) / yfinance (ABD) indirme
            if missing:
                from data_cache import _batch_download_yfinance_bulk as _yf_bulk, _save_to_cache as _save_c
                bulk = _yf_bulk(missing, start_str, end_str)
                for tk, df in bulk.items():
                    result[tk] = df
                    try:
                        _save_c(tk, df)
                    except Exception:
                        pass
            return result
        except Exception:
            pass

    # ── 2. Fallback: yfinance (cache kapalıysa) ───────────────────────────────
    return _batch_download_yfinance(tickers, start_str, end_str)


def _batch_download_yfinance(tickers, start_str, end_str):
    """yfinance toplu indirme (fallback)."""
    data = {}
    ticker_list = list(tickers)
    if not ticker_list:
        return data
    try:
        raw = yf.download(ticker_list, start=start_str, end=end_str,
                          auto_adjust=True, progress=False, group_by="ticker",
                          threads=True)
        if raw is None or raw.empty:
            return data
        for tk in ticker_list:
            try:
                if len(ticker_list) == 1:
                    df = raw.copy()
                    if isinstance(df.columns, pd.MultiIndex):
                        names = df.columns.names
                        price_level = names.index("Price") if "Price" in names else 0
                        df.columns = df.columns.get_level_values(price_level)
                else:
                    df = raw[tk].copy()
                    if isinstance(df.columns, pd.MultiIndex):
                        names = df.columns.names
                        price_level = names.index("Price") if "Price" in names else -1
                        df.columns = df.columns.get_level_values(price_level)
                if isinstance(df.get("Close"), pd.DataFrame):
                    df["Close"] = df["Close"].iloc[:, 0]
                df = df.dropna(how="all")
                if not df.empty and "Close" in df.columns:
                    data[tk] = df
            except Exception:
                pass
    except Exception:
        pass
    return data


def _screen_ticker_on_date(ticker, name, df_slice, screen_type, score_weights, bench_1m_return, bench_close_slice=None):
    if df_slice is None or len(df_slice) < 50:
        return None

    close = df_slice["Close"]
    high = df_slice["High"]
    low = df_slice["Low"]
    volume = df_slice["Volume"]
    last_price = float(close.iloc[-1])

    if screen_type == "Alfa Portföyü":
        return None

    elif screen_type == "Beta Portföyü":
        if len(close) < 60:
            return None

        # ── Zorunlu 1: SMA200 üzeri ──────────────────────────────────────────
        sma200_b = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        if sma200_b and sma200_b > 0 and last_price < sma200_b * 0.97:
            return None

        # ── Zorunlu 2: EMA50 üzeri ───────────────────────────────────────────
        ema50 = pta.ema(close, length=50)
        if ema50 is None or last_price <= float(ema50.iloc[-1]):
            return None

        # ── Zorunlu 3: Minimum likidite ──────────────────────────────────────
        if len(volume) >= 20:
            avg_vol_20d = float(volume.iloc[-20:].mean())
            min_vol = 10_000 if ticker.endswith(".IS") else 500_000
            if avg_vol_20d < min_vol:
                return None

        # ── ADX: Trend gücü (zorunlu >= 20) ─────────────────────────────────
        adx_val = 0.0
        try:
            adx_df = pta.adx(high, low, close)
            if adx_df is None or adx_df.empty:
                return None
            adx_val = float(adx_df.iloc[-1, 0])
            if adx_val <= 18:
                return None
        except Exception:
            return None

        # ── MFI: Para akışı (50+ gerekli) ────────────────────────────────────
        mfi_val = 50.0
        try:
            mfi = pta.mfi(high, low, close, volume)
            if mfi is None:
                return None
            mfi_val = float(mfi.iloc[-1])
            if mfi_val <= 45:
                return None
        except Exception:
            return None

        # ── Göreceli momentum (çok periyotlu) ────────────────────────────────
        excess_1m = excess_3m = excess_6m = 0.0
        if bench_close_slice is not None:
            if len(close) >= 22 and len(bench_close_slice) >= 22:
                excess_1m = ((close.iloc[-1]/close.iloc[-22]) - (bench_close_slice.iloc[-1]/bench_close_slice.iloc[-22])) * 100
            if len(close) >= 63 and len(bench_close_slice) >= 63:
                excess_3m = ((close.iloc[-1]/close.iloc[-63]) - (bench_close_slice.iloc[-1]/bench_close_slice.iloc[-63])) * 100
            if len(close) >= 126 and len(bench_close_slice) >= 126:
                excess_6m = ((close.iloc[-1]/close.iloc[-126]) - (bench_close_slice.iloc[-1]/bench_close_slice.iloc[-126])) * 100

        # Mutlak pozitif trend gerekli
        if len(close) >= 63:
            abs_3m = (float(close.iloc[-1]) / float(close.iloc[-63]) - 1) * 100
            if abs_3m < 0:
                return None

        # ── Skor hesabı ──────────────────────────────────────────────────────
        # MFI normlalize (50-100 → 0-50)
        mfi_norm = max(0, mfi_val - 50) * 1.0
        # ADX normalize (18-50 → 0-32)
        adx_norm = max(0, adx_val - 18) * 1.0
        # Momentum skoru
        mom_score = excess_1m * 0.3 + excess_3m * 0.4 + excess_6m * 0.3

        score = (mfi_norm   * score_weights.get("momentum_mfi", 40) / 100 +
                 adx_norm   * score_weights.get("adx_gucu", 40) / 100 +
                 mom_score  * score_weights.get("relative_strength", 20) / 100)

        return {"Sembol": name, "Yatırım Uzmanı Skoru": round(score, 2)}

    elif screen_type == "Delta Portföyü":
        """Delta — Derin Değer + Toparlanma (Deep Value Recovery) Stratejisi.

        Fikir: Queen Stock Delta picks (EKGYO, ENKA, KTLEV, GUBRF) büyük
        düzeltme yaşamış ancak fundamental olarak sağlam, sektör rotasyonu
        başlamış hisselerdi.

        Filtreler:
          1. SMA200 toparlanması: Fiyat SMA200 altındayken tekrar üstüne çıkıyor
             VEYA SMA200'e çok yakın (±5%) + RSI 40'ı yukarı kesiyor
          2. Önemli düzeltme: 52-hafta yüksekten %20-60 aşağıda
             (çok düşük = batıyor, çok yüksek = düzeltme olmamış)
          3. Kısa vadeli toparlanma sinyali: son 20 günde piyasayı geçiyor
          4. Hacim artışı: toparlanmada kurumsal ilgi
        """
        if len(close) < 60:
            return None

        last_price = float(close.iloc[-1])

        # ── Zorunlu 1: SMA200 yakınında veya üzerinde ──────────────────────
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        sma50_v = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        # SMA200 yoksa SMA100 kullan
        if sma200 is None and len(close) >= 100:
            sma200 = float(close.rolling(100).mean().iloc[-1])

        if sma200 is None:
            return None

        dist_to_sma200 = (last_price / sma200 - 1) * 100

        # Fiyat SMA200'ü son 10 gün içinde yukarı kesti mi?
        crossed_above_sma200 = False
        if len(close) >= 210:
            close_10d_ago = float(close.iloc[-10])
            sma200_10d_ago = float(close.iloc[-210:-10].mean()) if len(close) >= 210 else sma200
            if close_10d_ago < sma200_10d_ago and last_price >= sma200:
                crossed_above_sma200 = True

        # Kriter: SMA200'ün %10 içinde VEYA yeni geçiş
        if not crossed_above_sma200 and abs(dist_to_sma200) > 12:
            return None

        # ── Zorunlu 2: 52-hafta yüksekten önemli düzeltme (sağlıklı geri çekilme)
        lookback_52w = min(252, len(close) - 1)
        high_52w = float(close.iloc[-lookback_52w:].max())
        low_52w  = float(close.iloc[-lookback_52w:].min())
        dist_from_high = (last_price / high_52w - 1) * 100

        # %15-%70 arasında düzeltme yaşamış olmalı
        if not (-70 <= dist_from_high <= -10):
            return None

        # ── RSI toparlanma sinyali ───────────────────────────────────────────
        rsi_series = pta.rsi(close, length=14)
        if rsi_series is None or len(rsi_series) < 5:
            return None
        rsi_now = float(rsi_series.iloc[-1])
        rsi_5d_ago = float(rsi_series.iloc[-5])

        # RSI 35-65 aralığında ve yükseliyor mu?
        if not (35 <= rsi_now <= 68):
            return None
        rsi_rising = rsi_now > rsi_5d_ago

        # ── Kısa vadeli excess return (toparlanma onayı) ─────────────────────
        excess_1m = 0.0
        excess_3m = 0.0
        if bench_close_slice is not None and len(bench_close_slice) >= 22 and len(close) >= 22:
            s1 = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100
            b1 = (float(bench_close_slice.iloc[-1]) / float(bench_close_slice.iloc[-22]) - 1) * 100
            excess_1m = s1 - b1
        if bench_close_slice is not None and len(bench_close_slice) >= 63 and len(close) >= 63:
            s3 = (float(close.iloc[-1]) / float(close.iloc[-63]) - 1) * 100
            b3 = (float(bench_close_slice.iloc[-1]) / float(bench_close_slice.iloc[-63]) - 1) * 100
            excess_3m = s3 - b3

        # Son 1 ayda piyasayı tamamen geride bırakmıyorsa geç
        if excess_1m < -10:
            return None

        # ── Hacim onayı ───────────────────────────────────────────────────────
        vol_ratio = 1.0
        if len(volume) >= 20:
            vol_5d = float(volume.iloc[-5:].mean())
            vol_20d = float(volume.iloc[-20:].mean())
            if vol_20d > 0:
                vol_ratio = vol_5d / vol_20d

        # ── Skor hesabı ──────────────────────────────────────────────────────
        # Temel skor: göreceli momentum
        base_score = excess_1m * 0.5 + excess_3m * 0.3

        # Bonus: SMA200 geçişi en güçlü sinyal
        crossing_bonus = 30.0 if crossed_above_sma200 else (
            15.0 if dist_to_sma200 >= 0 else 5.0
        )

        # RSI toparlanma bonusu
        rsi_bonus = 10.0 if (rsi_rising and rsi_now > 45) else 3.0

        # Hacim bonusu
        vol_bonus = min(15.0, (vol_ratio - 1.0) * 15) if vol_ratio > 1.2 else 0.0

        # Düzeltme derinliği bonusu: daha derin düzeltmeden toparlanma daha değerli
        depth_bonus = min(20.0, abs(dist_from_high) * 0.3)

        total_score = base_score + crossing_bonus + rsi_bonus + vol_bonus + depth_bonus

        return {
            "Sembol": name,
            "Yatırım Uzmanı Skoru": round(max(0, total_score), 1),
            "SMA200 Uzaklık%": round(dist_to_sma200, 2),
            "52H Yüksekten%": round(dist_from_high, 2),
            "RSI": round(rsi_now, 1),
            "Excess 1A%": round(excess_1m, 2),
            "SMA200 Geçişi": crossed_above_sma200,
        }


def _screen_alfa_backtest(ticker, name, df_slice, bench_close_slice, bench_ann_vol=None):
    """Alfa — Gelişmiş Göreceli Momentum Stratejisi (v2).

    Akademik temel: Jegadeesh & Titman 1993 + IBD RS Rating yaklaşımı.

    Skor = Ağırlıklı Göreceli Momentum:
      - 12 aylık excess return  → ağırlık %30  (uzun dönem trend)
      - 6  aylık excess return  → ağırlık %30  (orta dönem momentum)
      - 3  aylık excess return  → ağırlık %25  (kısa dönem ivme)
      - 1  aylık excess return  → ağırlık %15  (son hareket)
      + Bonuslar: ivme, 52w high, SMA200, hacim, ADX trend gücü

    Zorunlu filtreler:
      - Fiyat > SMA50 (trend üzerinde)
      - Fiyat > SMA200 (ana trend üzerinde — en kritik filtre)
      - 6 aylık mutlak getiri > 0 (hisse gerçekten yükseliyor)
      - Minimum hacim (likidite)
    """
    if df_slice is None or len(df_slice) < 60:
        return None
    if bench_close_slice is None or len(bench_close_slice) < 22:
        return None

    close  = df_slice["Close"]
    volume = df_slice["Volume"]
    high   = df_slice["High"] if "High" in df_slice.columns else close
    low    = df_slice["Low"]  if "Low"  in df_slice.columns else close
    last_price = float(close.iloc[-1])

    # ── Zorunlu filtre 1: SMA50 üzeri ────────────────────────────────────────
    sma50 = float(close.rolling(50).mean().iloc[-1])
    if sma50 <= 0 or last_price < sma50:
        return None

    # ── Zorunlu filtre 2: SMA200 üzeri (ana trend) ───────────────────────────
    sma200 = None
    if len(close) >= 200:
        sma200 = float(close.rolling(200).mean().iloc[-1])
        if sma200 > 0 and last_price < sma200 * 0.97:
            return None   # ana trend altında → geç

    # ── Zorunlu filtre 3: Mutlak 6 aylık getiri pozitif ─────────────────────
    if len(close) >= 126:
        abs_6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100
        if abs_6m < 0:
            return None   # hisse düşüyor → momentum yok

    # ── Zorunlu filtre 4: Minimum likidite ───────────────────────────────────
    if len(volume) >= 20:
        avg_vol_20d = float(volume.iloc[-20:].mean())
        min_vol = 10_000 if ticker.endswith(".IS") else 500_000
        if avg_vol_20d < min_vol:
            return None

    # ── Göreceli getiriler ───────────────────────────────────────────────────
    excess_1m = excess_3m = excess_6m = excess_12m = 0.0

    if len(close) >= 22 and len(bench_close_slice) >= 22:
        excess_1m = ((close.iloc[-1] / close.iloc[-22]) - (bench_close_slice.iloc[-1] / bench_close_slice.iloc[-22])) * 100

    if len(close) >= 63 and len(bench_close_slice) >= 63:
        excess_3m = ((close.iloc[-1] / close.iloc[-63]) - (bench_close_slice.iloc[-1] / bench_close_slice.iloc[-63])) * 100

    if len(close) >= 126 and len(bench_close_slice) >= 126:
        excess_6m = ((close.iloc[-1] / close.iloc[-126]) - (bench_close_slice.iloc[-1] / bench_close_slice.iloc[-126])) * 100

    if len(close) >= 240 and len(bench_close_slice) >= 240:
        excess_12m = ((close.iloc[-1] / close.iloc[-240]) - (bench_close_slice.iloc[-1] / bench_close_slice.iloc[-240])) * 100

    # Benchmarkı belirgin şekilde geçemiyor → geç
    if excess_3m < -5 and excess_6m < -10:
        return None

    # ── ADX — Trend gücü ─────────────────────────────────────────────────────
    adx_bonus = 0.0
    if len(close) >= 28:
        try:
            hi = high.values; lo = low.values; cl = close.values
            tr  = np.maximum(hi[1:] - lo[1:],
                  np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
            atr14 = pd.Series(tr).ewm(span=14, adjust=False).mean()
            dm_pos = np.where((hi[1:] - hi[:-1]) > (lo[:-1] - lo[1:]),
                               np.maximum(hi[1:] - hi[:-1], 0), 0)
            dm_neg = np.where((lo[:-1] - lo[1:]) > (hi[1:] - hi[:-1]),
                               np.maximum(lo[:-1] - lo[1:], 0), 0)
            di_pos = pd.Series(dm_pos).ewm(span=14, adjust=False).mean() / (atr14 + 1e-9) * 100
            di_neg = pd.Series(dm_neg).ewm(span=14, adjust=False).mean() / (atr14 + 1e-9) * 100
            dx     = np.abs(di_pos - di_neg) / (di_pos + di_neg + 1e-9) * 100
            adx    = float(pd.Series(dx).ewm(span=14, adjust=False).mean().iloc[-1])
            if adx >= 35:   adx_bonus = 20.0
            elif adx >= 25: adx_bonus = 12.0
            elif adx >= 20: adx_bonus = 5.0
        except Exception:
            pass

    # ── İvme katsayısı ────────────────────────────────────────────────────────
    acceleration = 0.0
    if excess_1m > excess_3m > 0:
        acceleration += min(25.0, (excess_1m - excess_3m) * 0.7)
    if excess_3m > excess_6m > 0:
        acceleration += min(15.0, (excess_3m - excess_6m) * 0.4)

    # ── 52-hafta yüksek yakınlığı ─────────────────────────────────────────────
    high52w_bonus = 0.0
    lookback_52w = min(252, len(close) - 1)
    high_52w = float(close.iloc[-lookback_52w:].max())
    if high_52w > 0:
        dist_pct = (last_price / high_52w - 1) * 100
        if dist_pct >= -3:    high52w_bonus = 25.0
        elif dist_pct >= -10: high52w_bonus = 15.0
        elif dist_pct >= -20: high52w_bonus = 7.0

    # ── SMA200 konumu ─────────────────────────────────────────────────────────
    sma200_bonus = 0.0
    if sma200 and sma200 > 0:
        gap = (last_price / sma200 - 1) * 100
        if gap >= 20:    sma200_bonus = 20.0
        elif gap >= 10:  sma200_bonus = 12.0
        elif gap >= 0:   sma200_bonus = 5.0

    # ── Hacim ivmesi (kurumsal birikim sinyali) ───────────────────────────────
    vol_surge_bonus = 0.0
    if len(volume) >= 20:
        vol_5d_avg  = float(volume.iloc[-5:].mean())
        vol_20d_avg = float(volume.iloc[-20:].mean())
        if vol_20d_avg > 0:
            vol_ratio = vol_5d_avg / vol_20d_avg
            if vol_ratio > 2.5:   vol_surge_bonus = 18.0
            elif vol_ratio > 1.8: vol_surge_bonus = 10.0
            elif vol_ratio > 1.3: vol_surge_bonus = 4.0

    # ── Volatilite cezası ─────────────────────────────────────────────────────
    vol_penalty = 0.0
    daily_ret = close.pct_change().dropna()
    if len(daily_ret) >= 20:
        ann_vol = float(daily_ret.std()) * np.sqrt(252)
        if bench_ann_vol and bench_ann_vol > 0:
            vr = ann_vol / bench_ann_vol
            if vr > 2.5: vol_penalty = min(0.45, (vr - 2.5) * 0.20)

    # ── Ana momentum skoru (12 aylık en ağır) ────────────────────────────────
    momentum_score = (excess_12m * 0.30 + excess_6m * 0.30 +
                      excess_3m  * 0.25 + excess_1m * 0.15)
    bonus = acceleration + high52w_bonus + sma200_bonus + vol_surge_bonus + adx_bonus

    return {
        "Sembol": name,
        "rs_slope": momentum_score,
        "vol_penalty": vol_penalty,
        "_sma200_bonus": sma200_bonus,
        "_obv_bonus": vol_surge_bonus,
        "_momentum_bonus": acceleration,
        "_rs_rating_bonus": adx_bonus,
        "_high52w_bonus": high52w_bonus,
        "RS Eğimi": round(excess_6m, 2),
        "_excess_1m": excess_1m,
        "_excess_3m": excess_3m,
        "_bonus": bonus,
    }


def _screen_ticker_on_date_technical_only(ticker, name, df_slice, screen_type, score_weights, bench_1m_return, bench_close_slice=None):
    if screen_type == "Beta Portföyü":
        return _screen_ticker_on_date(ticker, name, df_slice, screen_type, score_weights, bench_1m_return)

    elif screen_type == "Delta Portföyü":
        return _screen_ticker_on_date(ticker, name, df_slice, screen_type, score_weights, bench_1m_return, bench_close_slice=bench_close_slice)

    return None


def generate_rebalance_dates(start_date, end_date, period, trading_days):
    dates = []
    if period == "Haftalık":
        delta = timedelta(days=7)
    elif period == "15 Günlük":
        delta = timedelta(days=15)
    else:
        delta = timedelta(days=30)

    current = start_date
    while current <= end_date:
        valid_days = trading_days[trading_days >= pd.Timestamp(current)]
        if len(valid_days) > 0:
            dates.append(valid_days[0])
        current += delta

    final_day = trading_days[-1] if len(trading_days) > 0 else pd.Timestamp(end_date)
    if len(dates) == 0 or dates[-1] < final_day:
        dates.append(final_day)

    return sorted(list(set(dates)))


def detect_market_regime(bench_df, as_of_date=None):
    """Detect market regime from benchmark data.
    Returns: dict with regime name, description, allocations"""
    if bench_df is None or len(bench_df) < 200:
        return {"regime": "unknown", "name": "Belirsiz", "desc": "Yeterli veri yok", 
                "allocations": {"Alfa": 25, "Beta": 25, "Delta": 25, "Nakit": 25},
                "color": "gray"}
    
    if as_of_date is not None:
        bench_df = bench_df[bench_df.index <= pd.Timestamp(as_of_date)]
        if len(bench_df) < 200:
            return {"regime": "unknown", "name": "Belirsiz", "desc": "Yeterli veri yok",
                    "allocations": {"Alfa": 25, "Beta": 25, "Delta": 25, "Nakit": 25},
                    "color": "gray"}
    
    close = bench_df["Close"]
    high = bench_df["High"]
    low = bench_df["Low"]
    
    sma200 = close.rolling(200).mean()
    sma50 = close.rolling(50).mean()
    
    adx_df = pta.adx(high, low, close)
    adx_val = float(adx_df.iloc[-1, 0]) if adx_df is not None and len(adx_df) > 0 else 15
    
    latest_close = float(close.iloc[-1])
    latest_sma200 = float(sma200.dropna().iloc[-1]) if len(sma200.dropna()) > 0 else latest_close
    latest_sma50 = float(sma50.dropna().iloc[-1]) if len(sma50.dropna()) > 0 else latest_close
    
    if len(close) >= 25:
        rs_ratio = close / sma200
        rs_ratio = rs_ratio.dropna()
        if len(rs_ratio) >= 5:
            recent_5 = rs_ratio.iloc[-5:].values.astype(float)
            x5 = np.arange(5, dtype=float)
            rs_slope_val = np.polyfit(x5, recent_5, 1)[0]
        else:
            rs_slope_val = 0
    else:
        rs_slope_val = 0
    
    if latest_close > latest_sma200:
        if adx_val > 25:
            if rs_slope_val > 0:
                return {"regime": "bull_rally", "name": "Güçlü Yükseliş (Bull Rally)",
                        "desc": f"Benchmark SMA200 üzerinde, ADX={adx_val:.0f} (güçlü trend), momentum yükseliyor",
                        "allocations": {"Beta": 50, "Alfa": 30, "Delta": 20, "Nakit": 0},
                        "asset_alloc": {"BIST": 45, "USA": 35, "Metaller": 5, "Nakit": 15},
                        "color": "#00CC96"}
            else:
                return {"regime": "late_bull", "name": "Olgun Yükseliş (Late Bull)",
                        "desc": f"Benchmark SMA200 üzerinde, ADX={adx_val:.0f} (güçlü trend), ancak momentum azalıyor",
                        "allocations": {"Alfa": 50, "Delta": 30, "Beta": 20, "Nakit": 0},
                        "asset_alloc": {"BIST": 35, "USA": 30, "Metaller": 15, "Nakit": 20},
                        "color": "#FFA15A"}
        else:
            return {"regime": "sideways", "name": "Yatay Piyasa (Sideways)",
                    "desc": f"Benchmark SMA200 üzerinde ama ADX={adx_val:.0f} (trend zayıf), yön belirsiz",
                    "allocations": {"Delta": 50, "Alfa": 30, "Beta": 0, "Nakit": 20},
                    "asset_alloc": {"BIST": 25, "USA": 20, "Metaller": 20, "Nakit": 35},
                    "color": "#FECB52"}
    else:
        if latest_close > latest_sma50:
            return {"regime": "correction", "name": "Düzeltme (Correction)",
                    "desc": f"Benchmark SMA200 altında ama SMA50 üzerinde, düzeltme aşamasında",
                    "allocations": {"Delta": 40, "Alfa": 0, "Beta": 0, "Nakit": 60},
                    "asset_alloc": {"BIST": 10, "USA": 10, "Metaller": 25, "Nakit": 55},
                    "color": "#EF553B"}
        else:
            return {"regime": "bear", "name": "Ayı Piyasası (Bear Market)",
                    "desc": f"Benchmark hem SMA200 hem SMA50 altında, risk yüksek",
                    "allocations": {"Delta": 20, "Alfa": 0, "Beta": 0, "Nakit": 80},
                    "asset_alloc": {"BIST": 0, "USA": 0, "Metaller": 30, "Nakit": 70},
                    "color": "#AB63FA"}


def run_manual_portfolio_backtest(monthly_portfolios, market, initial_capital=100000, progress_placeholder=None):
    """Manuel portföy backtesti — kullanıcının girdiği aylık hisse listesini kullanır.

    monthly_portfolios: dict {  '2025-01': ['AVPGY','ISGSY',...], '2025-02': [...], ... }
    market: "BIST (Borsa İstanbul)" or "USA"
    """
    COMMISSION_RATE = 0.002
    SLIPPAGE_BUY = 1.001
    SLIPPAGE_SELL = 0.999

    is_bist = market == "BIST (Borsa İstanbul)"
    benchmark_ticker = "XU100.IS" if is_bist else "SPY"

    all_symbols = set()
    for stocks in monthly_portfolios.values():
        for s in stocks:
            all_symbols.add(s)

    sorted_months = sorted(monthly_portfolios.keys())
    if not sorted_months:
        return None

    first_month = sorted_months[0]
    year0, mon0 = int(first_month.split('-')[0]), int(first_month.split('-')[1])
    data_start = (datetime(year0, mon0, 1) - timedelta(days=30)).strftime('%Y-%m-%d')
    data_end = datetime.now().strftime('%Y-%m-%d')

    if progress_placeholder:
        progress_placeholder.info(f"{len(all_symbols)} hisse verisi indiriliyor...")

    tickers = [(s + '.IS' if is_bist else s) for s in all_symbols]
    bench_data = batch_download(tuple([benchmark_ticker]), data_start, data_end)
    all_data = batch_download(tuple(tickers), data_start, data_end)

    bench_df = bench_data.get(benchmark_ticker)
    if bench_df is None or bench_df.empty:
        return None
    bench_close = bench_df["Close"].squeeze()

    def _get_price_on_or_before(sym, date):
        tk = sym + '.IS' if is_bist else sym
        if tk not in all_data:
            return None
        df_f = all_data[tk]
        valid = df_f[df_f.index <= date]
        if valid.empty:
            return None
        return float(valid["Close"].iloc[-1])

    equity_curve = {}
    trade_log = []
    holdings = {}
    cash = float(initial_capital)
    win_trades, loss_trades = [], []

    def _sell(sym, sell_date, reason):
        nonlocal cash
        info = holdings.get(sym)
        if not info:
            return
        raw_price = _get_price_on_or_before(sym, sell_date)
        if raw_price:
            sell_price = raw_price * SLIPPAGE_SELL
            gross = info["shares"] * sell_price
            commission = gross * COMMISSION_RATE
            proceeds = gross - commission
            pnl = proceeds - info["shares"] * info["buy_price"]
            pnl_pct = (sell_price / info["buy_price"] - 1) * 100 if info["buy_price"] else 0
            if pnl_pct > 0:
                win_trades.append(pnl_pct)
            else:
                loss_trades.append(pnl_pct)
            cash += proceeds
            trade_log.append({
                "Tarih": sell_date.strftime("%Y-%m-%d"),
                "İşlem": "SAT", "Sembol": sym,
                "Fiyat": round(raw_price, 2), "Alış Fiyatı": round(info["buy_price"], 2),
                "Adet": round(info["shares"], 4), "K/Z": round(pnl, 2), "K/Z (%)": round(pnl_pct, 2),
                "Bakiye": round(cash, 2), "Skor": "-", "RS Eğimi": "-", "Açıklama": reason,
            })
        del holdings[sym]

    def _portfolio_value(date):
        val = cash
        for sym, info in holdings.items():
            p = _get_price_on_or_before(sym, date)
            if p:
                val += info["shares"] * p
        return val

    all_rebalance_dates = []
    for month_str in sorted_months:
        year, mon = int(month_str.split('-')[0]), int(month_str.split('-')[1])
        td = bench_close.index
        month_days = td[(td >= pd.Timestamp(f'{year}-{mon:02d}-01')) &
                        (td < pd.Timestamp(f'{year}-{mon+1:02d}-01' if mon < 12 else f'{year+1}-01-01'))]
        if len(month_days) > 0:
            all_rebalance_dates.append((month_str, month_days[0], month_days[-1]))

    for i, (month_str, buy_date, sell_date) in enumerate(all_rebalance_dates):
        if progress_placeholder:
            progress_placeholder.info(f"Periyot {i+1}/{len(all_rebalance_dates)}: {month_str} ({buy_date.strftime('%Y-%m-%d')})")

        new_symbols = [s for s in monthly_portfolios.get(month_str, []) if s in all_symbols]

        current_syms = list(holdings.keys())
        for sym in [h for h in current_syms if h not in new_symbols]:
            _sell(sym, buy_date, "Portföyden çıkarıldı")

        total_val = _portfolio_value(buy_date)
        n_total = len(new_symbols)
        target_alloc = total_val / n_total if n_total > 0 else 0

        for sym in new_symbols:
            if sym in holdings:
                continue
            buy_price = _get_price_on_or_before(sym, buy_date)
            if not buy_price or buy_price <= 0:
                continue
            slip_price = buy_price * SLIPPAGE_BUY
            alloc = min(target_alloc, cash)
            if alloc <= 0:
                continue
            commission = alloc * COMMISSION_RATE
            net_alloc = alloc - commission
            shares = net_alloc / slip_price
            effective_price = alloc / shares
            holdings[sym] = {"shares": shares, "buy_price": effective_price, "buy_date": buy_date.strftime("%Y-%m-%d")}
            cash -= alloc
            trade_log.append({
                "Tarih": buy_date.strftime("%Y-%m-%d"),
                "İşlem": "AL", "Sembol": sym,
                "Fiyat": round(buy_price, 2), "Alış Fiyatı": round(buy_price, 2),
                "Adet": round(shares, 4), "K/Z": 0, "K/Z (%)": 0,
                "Bakiye": round(_portfolio_value(buy_date), 2), "Skor": "-", "RS Eğimi": "-",
                "Açıklama": "Manuel portföye eklendi",
            })

        equity_curve[buy_date] = _portfolio_value(buy_date)

        if i == len(all_rebalance_dates) - 1:
            for sym in list(holdings.keys()):
                _sell(sym, sell_date, "Backtest sonu")
            equity_curve[sell_date] = cash

    if not equity_curve:
        return None

    equity_series = pd.Series(equity_curve).sort_index()
    final_equity = cash
    total_return = (final_equity / initial_capital - 1) * 100
    n_days = (equity_series.index[-1] - equity_series.index[0]).days
    annual_return = ((final_equity / initial_capital) ** (365 / n_days) - 1) * 100 if n_days > 0 else 0

    ret_series = equity_series.pct_change().dropna()
    sharpe = (ret_series.mean() / ret_series.std() * np.sqrt(252)) if ret_series.std() > 0 else 0
    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min()) * 100

    bench_at_dates = []
    for d in equity_series.index:
        valid = bench_close[bench_close.index <= d]
        bench_at_dates.append(float(valid.iloc[-1]) if len(valid) > 0 else np.nan)
    bench_series = pd.Series(bench_at_dates, index=equity_series.index).dropna()
    bench_normalized = bench_series / bench_series.iloc[0] * initial_capital if len(bench_series) > 1 else None

    win_rate = len(win_trades) / (len(win_trades) + len(loss_trades)) * 100 if (win_trades or loss_trades) else 0

    return {
        "equity_curve": equity_series,
        "benchmark_curve": bench_normalized,
        "trade_log": pd.DataFrame(trade_log) if trade_log else pd.DataFrame(),
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "sharpe": round(float(sharpe), 2),
        "max_drawdown": round(max_drawdown, 2),
        "win_rate": round(win_rate, 2),
        "final_equity": round(final_equity, 2),
        "initial_capital": initial_capital,
        "n_trades": len(trade_log),
    }


def run_rebalancing_backtest(stock_list, market, screen_type, score_weights,
                              bt_start_date, initial_capital, rebalance_period, top_n,
                              progress_placeholder=None,
                              weighting_mode="Sıralama Ağırlıklı",
                              hold_continuation=True,
                              bt_end_date=None):
    """Periyodik yeniden dengelemeli backtest.

    Parametreler
    ------------
    weighting_mode : "Eşit Ağırlık" | "Sıralama Ağırlıklı"
        Sıralama Ağırlıklı: top hisseye daha fazla sermaye tahsis eder.
    hold_continuation : bool
        True ise önceki dönemde de seçilmiş VE hâlâ skoru yüksek olan
        hisseler satılıp tekrar alınmaz — gereksiz komisyon kesilmez.
    """
    COMMISSION_RATE = 0.001   # %0.1 (BIST gerçekçi aracı kurum komisyonu)
    SLIPPAGE_BUY  = 1.0005   # %0.05 alış kayması
    SLIPPAGE_SELL = 0.9995   # %0.05 satış kayması


    # Sıralama ağırlık tablosu (toplam = 1.0)
    RANK_WEIGHTS = {
        1: 0.40, 2: 0.25, 3: 0.18, 4: 0.10, 5: 0.07,
    }

    is_bist = market == "BIST (Borsa İstanbul)"
    tickers = [s + ".IS" for s in stock_list] if is_bist else list(stock_list)
    display_map = {(s + ".IS" if is_bist else s): s for s in stock_list}

    benchmark_name = "BIST 100" if is_bist else "S&P 500"

    lookback_start = bt_start_date - timedelta(days=400)
    if bt_end_date is not None:
        end_date = datetime.combine(bt_end_date, datetime.max.time()) if hasattr(bt_end_date, 'year') else datetime.now()
    else:
        end_date = datetime.now()

    if progress_placeholder:
        progress_placeholder.progress(0.05, text="Veriler toplu olarak indiriliyor...")
    bench_df = None
    benchmark_ticker = None
    bench_candidates = (["XU100.IS", "^XU100", "GARAN.IS"] if is_bist else ["SPY", "^GSPC", "QQQ"])
    for _cand in bench_candidates:
        _bd = batch_download(tuple([_cand]), str(lookback_start.date()), str(end_date.date()))
        _df = _bd.get(_cand)
        if _df is not None and not _df.empty and len(_df) > 30:
            bench_df = _df
            benchmark_ticker = _cand
            break
    if bench_df is None:
        return None

    all_data = batch_download(tuple(tickers), str(lookback_start.date()), str(end_date.date()))

    bench_close = bench_df["Close"]
    if isinstance(bench_close, pd.DataFrame):
        bench_close = bench_close.iloc[:, 0]
    bench_close = bench_close.squeeze()

    trading_days = bench_close.index.sort_values()
    valid_start = trading_days[trading_days >= pd.Timestamp(bt_start_date)]
    if len(valid_start) == 0:
        return None

    rebalance_dates = generate_rebalance_dates(
        bt_start_date, end_date, rebalance_period, trading_days
    )

    if len(rebalance_dates) < 2:
        return None

    equity_curve = {}
    trade_log = []
    win_trades = []
    loss_trades = []
    holdings = {}
    cash = initial_capital

    def _safe_ts(d):
        ts = pd.Timestamp(d)
        return ts.tz_localize(None) if ts.tzinfo else ts

    def _get_price(sym, date):
        tk = sym + ".IS" if is_bist else sym
        if tk not in all_data:
            return None
        df_f = all_data[tk]
        if hasattr(df_f.index, "tz") and df_f.index.tz is not None:
            df_f = df_f.copy()
            df_f.index = df_f.index.tz_localize(None)
        valid = df_f[df_f.index <= _safe_ts(date)]
        if valid.empty:
            return None
        return float(valid["Close"].iloc[-1])

    def _portfolio_value(at_date):
        val = cash
        for sym, info in holdings.items():
            p = _get_price(sym, at_date)
            if p:
                val += info["shares"] * p
        return val

    def _sell_holding(sym, sell_date, reason_text):
        nonlocal cash
        info = holdings.get(sym)
        if not info:
            return
        raw_sell_price = _get_price(sym, sell_date)
        buy_price = info["buy_price"]
        shares = info["shares"]
        if raw_sell_price and buy_price and buy_price > 0:
            sell_price = raw_sell_price * SLIPPAGE_SELL
            gross_proceeds = shares * sell_price
            commission = gross_proceeds * COMMISSION_RATE
            proceeds = gross_proceeds - commission
            cost = shares * buy_price
            pnl = proceeds - cost
            pnl_pct = (sell_price / buy_price - 1) * 100
            if pnl_pct > 0:
                win_trades.append(pnl_pct)
            else:
                loss_trades.append(pnl_pct)
        else:
            # Fiyat verisi bulunamadı → maliyet bazını nakit olarak geri al (kayıp oluşmasın)
            sell_price = buy_price or 0
            proceeds = shares * sell_price if sell_price else 0
            pnl = 0
            pnl_pct = 0
        cash += proceeds
        del holdings[sym]
        total_val = _portfolio_value(sell_date)
        trade_log.append({
            "Tarih": sell_date.strftime("%Y-%m-%d") if hasattr(sell_date, 'strftime') else str(sell_date),
            "İşlem": "SAT",
            "Sembol": sym,
            "Fiyat": round(raw_sell_price, 2) if raw_sell_price else "-",
            "Alış Fiyatı": round(buy_price, 2) if buy_price else "-",
            "Adet": round(shares, 4),
            "K/Z": round(pnl, 2),
            "K/Z (%)": round(pnl_pct, 2),
            "Bakiye": round(total_val, 2),
            "Skor": "",
            "RS Eğimi": "-",
            "Açıklama": reason_text,
        })

    is_alfa = screen_type == "Alfa Portföyü"

    total_periods = len(rebalance_dates) - 1
    _bt_start_time = time.time()

    for period_idx in range(total_periods):
        reb_date = rebalance_dates[period_idx]
        next_reb_date = rebalance_dates[period_idx + 1]

        elapsed = time.time() - _bt_start_time
        pct = (period_idx + 1) / total_periods
        eta_str = ""
        if period_idx > 0 and elapsed > 0:
            eta_sec = elapsed / period_idx * (total_periods - period_idx)
            if eta_sec < 60:
                eta_str = f" — Kalan: ~{int(eta_sec)}s"
            else:
                eta_str = f" — Kalan: ~{int(eta_sec/60)}dk {int(eta_sec%60)}s"

        if progress_placeholder:
            progress_placeholder.progress(
                pct,
                text=(
                    f"Periyot {period_idx + 1}/{total_periods}: "
                    f"{reb_date.strftime('%Y-%m-%d')} → {next_reb_date.strftime('%Y-%m-%d')}"
                    f"{eta_str}"
                ),
            )

        bench_slice = bench_close[bench_close.index <= reb_date]
        bench_1m_return = 0.0
        if len(bench_slice) >= 22:
            bench_1m_return = (float(bench_slice.iloc[-1]) / float(bench_slice.iloc[-22]) - 1) * 100



        bench_ann_vol_bt = None
        if len(bench_slice) >= 60:
            b_ret = bench_slice.pct_change().dropna()
            if len(b_ret) >= 20:
                bench_ann_vol_bt = float(b_ret.std()) * np.sqrt(252)

        scored_stocks = []

        def _score_ticker(ticker):
            if ticker not in all_data:
                return None
            df_full = all_data[ticker]
            df_slice = df_full[df_full.index <= reb_date]
            if df_slice is None or len(df_slice) < 50:
                return None
            name = display_map.get(ticker, ticker)
            try:
                if is_alfa:
                    return _screen_alfa_backtest(ticker, name, df_slice, bench_slice, bench_ann_vol=bench_ann_vol_bt)
                else:
                    return _screen_ticker_on_date(ticker, name, df_slice, screen_type, score_weights, bench_1m_return, bench_close_slice=bench_slice)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            for result in executor.map(_score_ticker, tickers):
                if result is not None:
                    scored_stocks.append(result)

        if is_alfa and scored_stocks:
            all_rs = [s["rs_slope"] for s in scored_stocks]
            max_rs = max(all_rs) if all_rs else 1
            for s in scored_stocks:
                rs_norm = (s["rs_slope"] / max_rs * 100) if max_rs != 0 else 50
                bonus = (
                    s.get("_sma200_bonus", 0)
                    + s.get("_obv_bonus", 0)
                    + s.get("_momentum_bonus", 0)
                    + s.get("_rs_rating_bonus", 0)
                    + s.get("_high52w_bonus", 0)
                )
                score = (rs_norm + bonus) * (1 - s.get("vol_penalty", 0))
                s["Yatırım Uzmanı Skoru"] = round(max(0, min(200, score)), 1)

        scored_stocks.sort(key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)

        # Hold continuation: mevcut tutulan hisseler top_n + 2 içindeyse satma
        if hold_continuation:
            extended_pool = {s["Sembol"] for s in scored_stocks[:top_n + 2]}
            for sym in list(holdings.keys()):
                if sym not in extended_pool:
                    _sell_holding(sym, reb_date, "Portföyden çıkarıldı")
        
        selected = scored_stocks[:top_n]

        if not selected:
            for sym in list(holdings.keys()):
                _sell_holding(sym, reb_date, "Yeni seçim yok, pozisyon kapatıldı")
            equity_curve[reb_date] = cash
            continue

        new_symbols = [s["Sembol"] for s in selected]
        new_scores = {s["Sembol"]: s["Yatırım Uzmanı Skoru"] for s in selected}
        new_rs_slopes = {s["Sembol"]: s.get("RS Eğimi", "") for s in selected}

        # Hold continuation modunda tutulmayan eski hisseleri sat
        if not hold_continuation:
            current_syms = list(holdings.keys())
            for s in [h for h in current_syms if h not in new_symbols]:
                _sell_holding(s, reb_date, "Portföyden çıkarıldı")

        # ── Hedef ağırlıkları hesapla ────────────────────────────────────────
        total_val = _portfolio_value(reb_date)
        if weighting_mode == "Sıralama Ağırlıklı":
            n = len(new_symbols)
            if n <= 5:
                raw_weights = [RANK_WEIGHTS.get(i + 1, 1 / n) for i in range(n)]
            else:
                # 5'ten fazla hisse için lineer azalan ağırlık
                step = 1.0 / (n * (n + 1) / 2)
                raw_weights = [(n - i) * step for i in range(n)]
            weight_sum = sum(raw_weights)
            target_allocs = {sym: (w / weight_sum) * total_val
                             for sym, w in zip(new_symbols, raw_weights)}
        else:
            per_stock = total_val / len(new_symbols)
            target_allocs = {sym: per_stock for sym in new_symbols}

        kept = [sym for sym in holdings if sym in new_symbols]
        bought = [sym for sym in new_symbols if sym not in holdings]

        for sym in kept:
            raw_price = _get_price(sym, reb_date)
            if not raw_price:
                continue
            cur_value = holdings[sym]["shares"] * raw_price
            target = target_allocs[sym]
            diff = target - cur_value
            if abs(diff) < max(1.0, target * 0.02):   # %2'den küçük farkı işlem yapma
                continue
            if diff > 0:
                actual_diff = min(diff, cash) if cash > 0 else 0
                if actual_diff <= 0:
                    continue
                adj_buy_price = raw_price * SLIPPAGE_BUY
                commission = actual_diff * COMMISSION_RATE
                net_diff = actual_diff - commission
                if net_diff <= 0:
                    continue
                add_shares = net_diff / adj_buy_price
                eff_add_price = actual_diff / add_shares
                old_shares = holdings[sym]["shares"]
                old_bp = holdings[sym]["buy_price"]
                new_total_shares = old_shares + add_shares
                holdings[sym]["buy_price"] = (old_shares * old_bp + add_shares * eff_add_price) / new_total_shares
                holdings[sym]["shares"] = new_total_shares
                cash -= actual_diff
                trade_log.append({
                    "Tarih": reb_date.strftime("%Y-%m-%d"),
                    "İşlem": "REBALANCE AL",
                    "Sembol": sym,
                    "Fiyat": round(raw_price, 2),
                    "Alış Fiyatı": round(holdings[sym]["buy_price"], 2),
                    "Adet": round(add_shares, 4),
                    "K/Z": 0,
                    "K/Z (%)": 0,
                    "Bakiye": round(_portfolio_value(reb_date), 2),
                    "Skor": str(new_scores.get(sym, "")),
                    "RS Eğimi": new_rs_slopes.get(sym, "-"),
                    "Açıklama": f"Rebalance: +{round(actual_diff,0):.0f}₺ eklendi (hedef %{target/(_portfolio_value(reb_date) or 1)*100:.1f})",
                })
            else:
                adj_sell_price = raw_price * SLIPPAGE_SELL
                sell_shares = min(abs(diff) / raw_price, holdings[sym]["shares"])
                gross_proceeds = sell_shares * adj_sell_price
                commission = gross_proceeds * COMMISSION_RATE
                net_proceeds = gross_proceeds - commission
                holdings[sym]["shares"] -= sell_shares
                cash += net_proceeds
                pnl_pct = (raw_price / holdings[sym]["buy_price"] - 1) * 100 if holdings[sym].get("buy_price") else 0
                trade_log.append({
                    "Tarih": reb_date.strftime("%Y-%m-%d"),
                    "İşlem": "REBALANCE SAT",
                    "Sembol": sym,
                    "Fiyat": round(raw_price, 2),
                    "Alış Fiyatı": round(holdings[sym].get("buy_price", 0), 2),
                    "Adet": round(sell_shares, 4),
                    "K/Z": round(net_proceeds - sell_shares * holdings[sym].get("buy_price", raw_price), 2),
                    "K/Z (%)": round(pnl_pct, 2),
                    "Bakiye": round(_portfolio_value(reb_date), 2),
                    "Skor": str(new_scores.get(sym, "")),
                    "RS Eğimi": new_rs_slopes.get(sym, "-"),
                    "Açıklama": f"Rebalance: -{round(abs(diff),0):.0f}₺ azaltıldı (hedef %{target/(_portfolio_value(reb_date) or 1)*100:.1f})",
                })

        for b in bought:
            raw_buy_price = _get_price(b, reb_date)
            if not raw_buy_price or raw_buy_price <= 0:
                continue
            slip_buy_price = raw_buy_price * SLIPPAGE_BUY
            alloc = min(target_allocs[b], cash)
            if alloc <= 0:
                continue
            commission = alloc * COMMISSION_RATE
            net_alloc = alloc - commission
            if net_alloc <= 0:
                continue
            shares = net_alloc / slip_buy_price
            effective_buy_price = alloc / shares
            holdings[b] = {"shares": shares, "buy_price": effective_buy_price, "buy_date": reb_date.strftime("%Y-%m-%d")}
            cash -= alloc
            rs_val = new_rs_slopes.get(b, "")
            trade_log.append({
                "Tarih": reb_date.strftime("%Y-%m-%d"),
                "İşlem": "AL",
                "Sembol": b,
                "Fiyat": round(raw_buy_price, 2),
                "Alış Fiyatı": round(raw_buy_price, 2),
                "Adet": round(shares, 4),
                "K/Z": 0,
                "K/Z (%)": 0,
                "Bakiye": round(_portfolio_value(reb_date), 2),
                "Skor": str(new_scores.get(b, "")),
                "RS Eğimi": rs_val if rs_val != "" else "-",
                "Açıklama": "Portföye eklendi",
            })

        equity_curve[reb_date] = _portfolio_value(reb_date)

    if rebalance_dates:
        final_date = rebalance_dates[-1]
        for sym in list(holdings.keys()):
            _sell_holding(sym, final_date, "Backtest sonu, pozisyon kapatıldı")
        equity_curve[final_date] = cash

    equity_series = pd.Series(equity_curve).sort_index()

    final_equity = float(equity_series.iloc[-1]) if len(equity_series) > 0 else cash

    bench_at_dates = []
    for d in equity_series.index:
        valid = bench_close[bench_close.index <= d]
        if len(valid) > 0:
            bench_at_dates.append(float(valid.iloc[-1]))
        else:
            bench_at_dates.append(np.nan)
    bench_series_at_dates = pd.Series(bench_at_dates, index=equity_series.index).dropna()

    if len(bench_series_at_dates) > 1:
        bench_normalized = bench_series_at_dates / bench_series_at_dates.iloc[0] * initial_capital
    else:
        bench_normalized = None

    total_return = (final_equity / initial_capital - 1) * 100
    n_days = (equity_series.index[-1] - equity_series.index[0]).days
    annual_return = ((1 + total_return / 100) ** (365 / max(n_days, 1)) - 1) * 100

    period_returns_series = equity_series.pct_change().dropna()
    std_ret = period_returns_series.std()
    if rebalance_period == "Haftalık":
        periods_per_year = 52
    elif rebalance_period == "15 Günlük":
        periods_per_year = 24
    else:
        periods_per_year = 12
    sharpe = (period_returns_series.mean() / std_ret * np.sqrt(periods_per_year)) if std_ret > 0 else 0

    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100

    downside_returns = period_returns_series[period_returns_series < 0]
    downside_std = downside_returns.std()
    sortino = (period_returns_series.mean() / downside_std * np.sqrt(periods_per_year)) if downside_std > 0 else 0

    calmar = (annual_return / abs(max_drawdown)) if max_drawdown != 0 else 0

    n_wins = len(win_trades)
    n_losses = len(loss_trades)
    n_total_closed = n_wins + n_losses
    win_rate = (n_wins / n_total_closed * 100) if n_total_closed > 0 else 0
    avg_win = float(np.mean(win_trades)) if win_trades else 0
    avg_loss = float(np.mean(loss_trades)) if loss_trades else 0
    profit_factor = (sum(win_trades) / abs(sum(loss_trades))) if loss_trades and sum(loss_trades) != 0 else None

    traded_symbols = list({t["Sembol"] for t in trade_log if t["İşlem"] == "AL"})
    close_prices_dict = {}
    for sym in traded_symbols:
        tk = sym + ".IS" if is_bist else sym
        if tk in all_data:
            df_sym = all_data[tk]
            valid = df_sym[(df_sym.index >= equity_series.index[0]) & (df_sym.index <= equity_series.index[-1])]
            if not valid.empty:
                close_prices_dict[sym] = valid["Close"]

    bench_total_return = None
    if bench_normalized is not None and len(bench_normalized) > 1:
        bench_total_return = (float(bench_normalized.iloc[-1]) / initial_capital - 1) * 100

    # ── Periyot bazlı getiri tablosu ─────────────────────────────────────────
    period_breakdown = []
    eq_vals = equity_series.to_dict()
    eq_dates = sorted(eq_vals.keys())
    for i in range(1, len(eq_dates)):
        d0, d1 = eq_dates[i - 1], eq_dates[i]
        v0, v1 = eq_vals[d0], eq_vals[d1]
        pct = (v1 / v0 - 1) * 100 if v0 else 0
        # O dönemde tutulan hisseler
        held = [t["Sembol"] for t in trade_log
                if t["Tarih"] <= d1.strftime("%Y-%m-%d")
                and t["İşlem"] in ("AL", "REBALANCE AL")
                and t["Tarih"] >= d0.strftime("%Y-%m-%d")]
        flag = " ⚠️" if abs(pct) > 60 else ""
        period_breakdown.append({
            "Dönem Başı": d0.strftime("%Y-%m-%d"),
            "Dönem Sonu": d1.strftime("%Y-%m-%d"),
            "Başlangıç Değer": round(v0, 0),
            "Bitiş Değer": round(v1, 0),
            "Getiri (%)": round(pct, 1),
            "Uyarı": flag.strip(),
        })

    return {
        "equity_series": equity_series,
        "bench_normalized": bench_normalized,
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_drawdown,
        "bench_total_return": bench_total_return,
        "benchmark_name": benchmark_name,
        "trade_log": trade_log,
        "n_periods": len(rebalance_dates) - 1,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "close_prices_dict": close_prices_dict,
        "period_breakdown": period_breakdown,
    }


def run_regime_backtest(stock_list, market, bt_start_date, initial_capital, rebalance_period, top_n, progress_placeholder=None):
    COMMISSION_RATE = 0.002
    SLIPPAGE_BUY = 1.001
    SLIPPAGE_SELL = 0.999
    
    is_bist = market == "BIST (Borsa İstanbul)"
    tickers = [s + ".IS" for s in stock_list] if is_bist else list(stock_list)
    display_map = {(s + ".IS" if is_bist else s): s for s in stock_list}
    
    benchmark_name = "BIST 100" if is_bist else "S&P 500"
    
    lookback_start = bt_start_date - timedelta(days=400)
    end_date = datetime.now()
    
    if progress_placeholder:
        progress_placeholder.progress(0.05, text="Veriler toplu olarak indiriliyor...")
    
    bench_df = None
    benchmark_ticker = None
    bench_candidates = (["XU100.IS", "^XU100", "GARAN.IS"] if is_bist else ["SPY", "^GSPC", "QQQ"])
    for _cand in bench_candidates:
        _bd = batch_download(tuple([_cand]), str(lookback_start.date()), str(end_date.date()))
        _df = _bd.get(_cand)
        if _df is not None and not _df.empty and len(_df) > 30:
            bench_df = _df
            benchmark_ticker = _cand
            break
    if bench_df is None:
        return None

    all_data = batch_download(tuple(tickers), str(lookback_start.date()), str(end_date.date()))
    
    bench_close = bench_df["Close"]
    if isinstance(bench_close, pd.DataFrame):
        bench_close = bench_close.iloc[:, 0]
    bench_close = bench_close.squeeze()
    trading_days = bench_close.index.sort_values()
    valid_start = trading_days[trading_days >= pd.Timestamp(bt_start_date)]
    if len(valid_start) == 0:
        return None
    
    rebalance_dates = generate_rebalance_dates(bt_start_date, end_date, rebalance_period, trading_days)
    if len(rebalance_dates) < 2:
        return None
    
    STRATEGY_WEIGHTS = {
        "Alfa Portföyü": {"rs_slope": 40, "kar_buyumesi_rank": 30, "roe_rank": 30},
        "Beta Portföyü": {"momentum_mfi": 40, "adx_gucu": 40, "relative_strength": 20},
        "Delta Portföyü": {"relative_strength": 50, "destek_yakinligi": 30, "para_girisi": 20},
    }
    
    equity_curve = {}
    trade_log = []
    regime_log = []
    holdings = {}
    cash = initial_capital
    
    def _safe_ts(d):
        ts = pd.Timestamp(d)
        return ts.tz_localize(None) if ts.tzinfo else ts

    def _get_price(sym, date):
        tk = sym + ".IS" if is_bist else sym
        if tk not in all_data:
            return None
        df_f = all_data[tk]
        if hasattr(df_f.index, "tz") and df_f.index.tz is not None:
            df_f = df_f.copy()
            df_f.index = df_f.index.tz_localize(None)
        valid = df_f[df_f.index <= _safe_ts(date)]
        if valid.empty:
            return None
        return float(valid["Close"].iloc[-1])
    
    def _portfolio_value(at_date):
        val = cash
        for sym, info in holdings.items():
            p = _get_price(sym, at_date)
            if p:
                val += info["shares"] * p
        return val
    
    def _sell_holding(sym, sell_date, reason_text):
        nonlocal cash
        info = holdings.get(sym)
        if not info:
            return
        raw_sell_price = _get_price(sym, sell_date)
        buy_price = info["buy_price"]
        shares = info["shares"]
        if raw_sell_price and buy_price and buy_price > 0:
            sell_price = raw_sell_price * SLIPPAGE_SELL
            gross_proceeds = shares * sell_price
            commission = gross_proceeds * COMMISSION_RATE
            proceeds = gross_proceeds - commission
            cost = shares * buy_price
            pnl = proceeds - cost
            pnl_pct = (sell_price / buy_price - 1) * 100
        else:
            # Fiyat verisi bulunamadı → maliyet bazını nakit olarak geri al
            sell_price = buy_price or 0
            proceeds = shares * sell_price if sell_price else 0
            pnl = 0
            pnl_pct = 0
        cash += proceeds
        del holdings[sym]
        trade_log.append({
            "Tarih": sell_date.strftime("%Y-%m-%d") if hasattr(sell_date, 'strftime') else str(sell_date),
            "İşlem": "SAT",
            "Sembol": sym,
            "Fiyat": round(raw_sell_price, 2) if raw_sell_price else "-",
            "Alış Fiyatı": round(buy_price, 2) if buy_price else "-",
            "Adet": round(shares, 4),
            "K/Z": round(pnl, 2),
            "K/Z (%)": round(pnl_pct, 2),
            "Strateji": info.get("strategy", ""),
            "Rejim": info.get("regime", ""),
            "Açıklama": reason_text,
        })
    
    _regime_bt_start = time.time()
    _regime_total = len(rebalance_dates) - 1

    for period_idx in range(_regime_total):
        reb_date = rebalance_dates[period_idx]
        next_reb_date = rebalance_dates[period_idx + 1]

        elapsed = time.time() - _regime_bt_start
        pct = (period_idx + 1) / _regime_total
        eta_str = ""
        if period_idx > 0 and elapsed > 0:
            eta_sec = elapsed / period_idx * (_regime_total - period_idx)
            if eta_sec < 60:
                eta_str = f" — Kalan: ~{int(eta_sec)}s"
            else:
                eta_str = f" — Kalan: ~{int(eta_sec/60)}dk {int(eta_sec%60)}s"

        if progress_placeholder:
            progress_placeholder.progress(
                pct,
                text=(
                    f"Periyot {period_idx + 1}/{_regime_total}: "
                    f"{reb_date.strftime('%Y-%m-%d')} → {next_reb_date.strftime('%Y-%m-%d')}"
                    f"{eta_str}"
                ),
            )

        regime_info = detect_market_regime(bench_df, as_of_date=reb_date)
        allocations = regime_info["allocations"]
        regime_log.append({
            "Tarih": reb_date.strftime("%Y-%m-%d"),
            "Rejim": regime_info["name"],
            "Alfa (%)": allocations.get("Alfa", 0),
            "Beta (%)": allocations.get("Beta", 0),
            "Delta (%)": allocations.get("Delta", 0),
            "Nakit (%)": allocations.get("Nakit", 0),
        })
        
        for sym in list(holdings.keys()):
            _sell_holding(sym, reb_date, f"Rejim değişimi: {regime_info['name']}")
        
        total_val = cash
        
        all_strategy_picks = {}
        for strat_name in ["Alfa Portföyü", "Beta Portföyü", "Delta Portföyü"]:
            alloc_key = strat_name.split()[0]
            alloc_pct = allocations.get(alloc_key, 0)
            if alloc_pct <= 0:
                continue
            
            bench_slice = bench_close[bench_close.index <= reb_date]
            bench_1m_return = 0.0
            if len(bench_slice) >= 22:
                bench_1m_return = (float(bench_slice.iloc[-1]) / float(bench_slice.iloc[-22]) - 1) * 100
            
            bench_ann_vol_bt = None
            if len(bench_slice) >= 60:
                b_ret = bench_slice.pct_change().dropna()
                if len(b_ret) >= 20:
                    bench_ann_vol_bt = float(b_ret.std()) * np.sqrt(252)
            
            scored_stocks = []
            for ticker in tickers:
                if ticker not in all_data:
                    continue
                df_full = all_data[ticker]
                df_slice = df_full[df_full.index <= reb_date]
                if df_slice is None or len(df_slice) < 50:
                    continue
                name = display_map.get(ticker, ticker)
                try:
                    if strat_name == "Alfa Portföyü":
                        result = _screen_alfa_backtest(ticker, name, df_slice, bench_slice, bench_ann_vol=bench_ann_vol_bt)
                    else:
                        result = _screen_ticker_on_date(ticker, name, df_slice, strat_name, STRATEGY_WEIGHTS[strat_name], bench_1m_return, bench_close_slice=bench_slice)
                    if result is not None:
                        scored_stocks.append(result)
                except Exception:
                    continue
            
            if strat_name == "Alfa Portföyü" and scored_stocks:
                all_rs = [s["rs_slope"] for s in scored_stocks]
                max_rs = max(all_rs) if all_rs else 1
                for s in scored_stocks:
                    rs_norm = (s["rs_slope"] / max_rs * 100) if max_rs != 0 else 50
                    bonus = (
                        s.get("_sma200_bonus", 0)
                        + s.get("_obv_bonus", 0)
                        + s.get("_momentum_bonus", 0)
                        + s.get("_rs_rating_bonus", 0)
                        + s.get("_high52w_bonus", 0)
                    )
                    score = (rs_norm + bonus) * (1 - s.get("vol_penalty", 0))
                    s["Yatırım Uzmanı Skoru"] = round(max(0, min(200, score)), 1)
            
            scored_stocks.sort(key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)
            selected = scored_stocks[:top_n]
            
            if selected:
                all_strategy_picks[strat_name] = {
                    "stocks": selected,
                    "alloc_pct": alloc_pct,
                }
        
        for strat_name, pick_info in all_strategy_picks.items():
            strat_alloc = total_val * pick_info["alloc_pct"] / 100
            stocks = pick_info["stocks"]
            n_stocks = len(stocks)
            per_stock_alloc = strat_alloc / n_stocks if n_stocks > 0 else 0
            
            for s in stocks:
                sym = s["Sembol"]
                raw_buy_price = _get_price(sym, reb_date)
                if not raw_buy_price or raw_buy_price <= 0:
                    continue
                slip_buy_price = raw_buy_price * SLIPPAGE_BUY
                alloc = min(per_stock_alloc, cash)
                if alloc <= 0:
                    continue
                commission = alloc * COMMISSION_RATE
                net_alloc = alloc - commission
                if net_alloc <= 0:
                    continue
                shares = net_alloc / slip_buy_price
                effective_buy_price = alloc / shares
                holdings[sym] = {
                    "shares": shares,
                    "buy_price": effective_buy_price,
                    "buy_date": reb_date.strftime("%Y-%m-%d"),
                    "strategy": strat_name,
                    "regime": regime_info["name"],
                }
                cash -= alloc
                trade_log.append({
                    "Tarih": reb_date.strftime("%Y-%m-%d"),
                    "İşlem": "AL",
                    "Sembol": sym,
                    "Fiyat": round(raw_buy_price, 2),
                    "Alış Fiyatı": round(raw_buy_price, 2),
                    "Adet": round(shares, 4),
                    "K/Z": 0,
                    "K/Z (%)": 0,
                    "Strateji": strat_name,
                    "Rejim": regime_info["name"],
                    "Açıklama": f"{strat_name} - Portföye eklendi",
                })
        
        equity_curve[reb_date] = _portfolio_value(reb_date)
    
    if rebalance_dates:
        final_date = rebalance_dates[-1]
        for sym in list(holdings.keys()):
            _sell_holding(sym, final_date, "Backtest sonu, pozisyon kapatıldı")
        equity_curve[final_date] = cash
    
    equity_series = pd.Series(equity_curve).sort_index()
    
    bench_at_dates = []
    for d in equity_series.index:
        valid = bench_close[bench_close.index <= d]
        if len(valid) > 0:
            bench_at_dates.append(float(valid.iloc[-1]))
        else:
            bench_at_dates.append(np.nan)
    bench_series_at_dates = pd.Series(bench_at_dates, index=equity_series.index).dropna()
    
    if len(bench_series_at_dates) > 1:
        bench_normalized = bench_series_at_dates / bench_series_at_dates.iloc[0] * initial_capital
    else:
        bench_normalized = None
    
    final_equity = cash
    total_return = (final_equity / initial_capital - 1) * 100
    n_days = (equity_series.index[-1] - equity_series.index[0]).days
    annual_return = ((1 + total_return / 100) ** (365 / max(n_days, 1)) - 1) * 100
    
    period_returns_series = equity_series.pct_change().dropna()
    std_ret = period_returns_series.std()
    if rebalance_period == "Haftalık":
        periods_per_year = 52
    elif rebalance_period == "15 Günlük":
        periods_per_year = 24
    else:
        periods_per_year = 12
    sharpe = (period_returns_series.mean() / std_ret * np.sqrt(periods_per_year)) if std_ret > 0 else 0
    
    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100
    
    bench_total_return = None
    if bench_normalized is not None and len(bench_normalized) > 1:
        bench_total_return = (float(bench_normalized.iloc[-1]) / initial_capital - 1) * 100
    
    return {
        "equity_series": equity_series,
        "bench_normalized": bench_normalized,
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "bench_total_return": bench_total_return,
        "benchmark_name": benchmark_name,
        "trade_log": trade_log,
        "regime_log": regime_log,
        "n_periods": len(rebalance_dates) - 1,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
    }


def run_monte_carlo(equity_series, initial_capital, n_simulations=500, n_periods=None):
    period_returns = equity_series.pct_change().dropna().values
    if len(period_returns) < 2:
        return None
    if n_periods is None:
        n_periods = len(period_returns)
    rng = np.random.default_rng(42)
    simulations = np.zeros((n_simulations, n_periods + 1))
    simulations[:, 0] = initial_capital
    for i in range(n_simulations):
        sampled = rng.choice(period_returns, size=n_periods, replace=True)
        for t in range(n_periods):
            simulations[i, t + 1] = simulations[i, t] * (1 + sampled[t])
    return simulations


def calc_correlation_matrix(close_prices_dict):
    if not close_prices_dict or len(close_prices_dict) < 2:
        return None
    price_df = pd.DataFrame(close_prices_dict)
    price_df = price_df.dropna(how="all")
    returns_df = price_df.pct_change().dropna()
    if len(returns_df) < 5:
        return None
    return returns_df.corr()


def send_telegram_message(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)


st.title("Portföy Optimizer")

with st.sidebar:
    st.header("Ayarlar")

    market = st.selectbox("Piyasa", ["BIST (Borsa İstanbul)", "ABD (US Market)"])

    st.subheader("Hisse Tarama (Screening)")

    if market == "BIST (Borsa İstanbul)":
        screen_pool_name = st.selectbox("Tarama Havuzu", [
            "BIST 100",
            "BIST TÜM (XUTUM)",
            "BIST 100 DIŞI (XTUMY)",
        ])
        if screen_pool_name == "BIST TÜM (XUTUM)":
            screen_stock_pool = BIST_TUM_STOCKS
        elif screen_pool_name == "BIST 100 DIŞI (XTUMY)":
            screen_stock_pool = BIST100_DISI_STOCKS
        else:
            screen_stock_pool = BIST100_STOCKS
        st.caption(f"Havuz: {len(screen_stock_pool)} hisse")
    else:
        screen_pool_name = st.selectbox("Tarama Havuzu", [
            "S&P 500 + MidCap 400 (903)",
            "S&P 500 (Top 30)",
            "NYSE",
            "NASDAQ",
            "Tüm US Hisseler",
        ], key="us_screen_pool")
        screen_stock_pool, us_name_map = get_us_stock_pool(screen_pool_name)
        st.session_state["us_name_map"] = us_name_map
        st.caption(f"Havuz: {len(screen_stock_pool)} hisse")

    screen_type = st.selectbox("Tarama Algoritması", [
        "Alfa Portföyü",
        "Beta Portföyü",
        "Delta Portföyü",
    ])

    screen_descriptions = {
        "Alfa Portföyü": "Dinamik Liderlik: RS Slope ↑ (5G yükseliş), Fiyat > SMA200×1.05, OBV yükseliş, ROE/Kar üst %20 sıralama, Vol filtre, F/K < 50",
        "Beta Portföyü": "ADX > 25, Fiyat > EMA(50), MFI > 70 (Momentum)",
        "Delta Portföyü": "Trend İçi Geri Çekilme (Pullback) — Güçlü hisselerde destek dönüşü",
    }
    st.caption(screen_descriptions[screen_type])

    with st.expander("Ağırlık Ayarları (Puanlama)"):
        if screen_type == "Alfa Portföyü":
            sw_rs = st.slider("RS Eğimi (İvme) Ağırlığı (%)", 0, 100, 40, key="sw_alfa_rs")
            sw_kar = st.slider("Kar Büyümesi Sıralaması Ağırlığı (%)", 0, 100, 30, key="sw_alfa_kar")
            sw_roe = st.slider("ROE Sıralaması Ağırlığı (%)", 0, 100, 30, key="sw_alfa_roe")
            total_w = sw_rs + sw_kar + sw_roe
            if total_w != 100:
                st.warning(f"Toplam ağırlık %{total_w} — ideal olarak %100 olmalı.")
            score_weights = {"rs_slope": sw_rs, "kar_buyumesi_rank": sw_kar, "roe_rank": sw_roe}
        elif screen_type == "Beta Portföyü":
            sw_mfi = st.slider("Momentum/MFI Ağırlığı (%)", 0, 100, 40, key="sw_beta_mfi")
            sw_adx = st.slider("ADX Gücü Ağırlığı (%)", 0, 100, 40, key="sw_beta_adx")
            sw_rs = st.slider("Göreceli Güç Ağırlığı (%)", 0, 100, 20, key="sw_beta_rs")
            total_w = sw_mfi + sw_adx + sw_rs
            if total_w != 100:
                st.warning(f"Toplam ağırlık %{total_w} — ideal olarak %100 olmalı.")
            score_weights = {"momentum_mfi": sw_mfi, "adx_gucu": sw_adx, "relative_strength": sw_rs}
        elif screen_type == "Delta Portföyü":
            sw_rs = st.slider("Göreceli Güç (3A) Ağırlığı (%)", 0, 100, 50, key="sw_delta_rs")
            sw_destek = st.slider("Destek Yakınlığı (SMA50) Ağırlığı (%)", 0, 100, 30, key="sw_delta_destek")
            sw_mfi = st.slider("Para Girişi (MFI) Ağırlığı (%)", 0, 100, 20, key="sw_delta_mfi")
            total_w = sw_rs + sw_destek + sw_mfi
            if total_w != 100:
                st.warning(f"Toplam ağırlık %{total_w} — ideal olarak %100 olmalı.")
            score_weights = {"relative_strength": sw_rs, "destek_yakinligi": sw_destek, "para_girisi": sw_mfi}

    screen_date = st.date_input(
        "Tarama Tarihi",
        value=datetime.now().date(),
        key="screen_date",
    )
    screen_btn = st.button("Taramayı Başlat", type="secondary", use_container_width=True)

    st.divider()
    st.subheader("Yeniden Dengelemeli Backtest")

    bt_screen_type_sel = st.selectbox("Backtest Portföy Tipi", [
        "Alfa Portföyü",
        "Beta Portföyü",
        "Delta Portföyü",
    ], key="bt_screen_type_sel")

    if market == "BIST (Borsa İstanbul)":
        bt_pool_name = st.selectbox("Backtest Havuzu", [
            "BIST 100",
            "BIST TÜM (XUTUM)",
            "BIST 100 DIŞI (XTUMY)",
        ], key="bt_pool")
        if bt_pool_name == "BIST TÜM (XUTUM)":
            bt_stock_pool = BIST_TUM_STOCKS
        elif bt_pool_name == "BIST 100 DIŞI (XTUMY)":
            bt_stock_pool = BIST100_DISI_STOCKS
        else:
            bt_stock_pool = BIST100_STOCKS
        st.caption(f"Backtest Havuzu: {len(bt_stock_pool)} hisse")
    else:
        bt_pool_name = st.selectbox("Backtest Havuzu", [
            "S&P 500 + MidCap 400 (903)",
            "S&P 500 (Top 30)",
            "NYSE",
            "NASDAQ",
            "Tüm US Hisseler",
        ], key="us_bt_pool")
        bt_stock_pool, _ = get_us_stock_pool(bt_pool_name)
        st.caption(f"Backtest Havuzu: {len(bt_stock_pool)} hisse")

    bt_start_date = st.date_input(
        "Backtest Başlangıç",
        value=datetime.now() - timedelta(days=365),
        key="bt_start",
    )
    bt_capital = st.number_input("Başlangıç Sermayesi (₺/$)", value=100000, step=10000, min_value=1000, key="bt_cap")
    bt_period = st.selectbox("Yeniden Dengeleme Periyodu", ["Haftalık", "15 Günlük", "Aylık"], index=2, key="bt_period")
    bt_top_n = st.selectbox("Portföy Büyüklüğü (Top N)", [3, 5, 10, 15, 20], index=1, key="bt_topn")
    bt_top_n_weight = st.selectbox("Pozisyon Ağırlıklandırma", ["Eşit Ağırlık", "Sıralama Ağırlıklı"], key="bt_weight_type")
    bt_weighting = "rank" if bt_top_n_weight == "Sıralama Ağırlıklı" else "equal"
    bt_hold_continuation = st.checkbox("Güçlü Pozisyonları Tut (Hold Continuation)", value=False, key="bt_hold_cont")
    bt_excluded_raw = st.text_input("Hariç Tutulacak Hisseler", key="bt_excluded", placeholder="Örn: THYAO,GARAN")
    bt_excluded = set(x.strip().upper() for x in bt_excluded_raw.split(",") if x.strip()) if bt_excluded_raw else set()
    bt_end_date = None  # Bitiş tarihi: None = bugün
    bt_save_name = st.text_input("Backtest İsmi (kaydetmek için)", key="bt_save_name", placeholder="Örn: BIST Alfa 1Y Test")
    bt_btn = st.button("Backtest Başlat", type="primary", use_container_width=True, key="bt_run")
    bt_compare_btn = st.button("Tüm Stratejileri Karşılaştır", type="secondary", use_container_width=True, key="bt_compare")

tab_piyasa, tab_tarama, tab_backtest, tab_portfolyo = st.tabs(["Piyasa Analizi", "Hisse Tarama", "Backtest", "Portföyler"])


@st.cache_data(ttl=300)
def fetch_stock_detail(ticker):
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("shortName") or info.get("longName") or ticker,
            "pe": info.get("trailingPE") or info.get("forwardPE"),
            "pb": info.get("priceToBook"),
            "market_cap": info.get("marketCap"),
            "dividend_yield": info.get("dividendYield"),
            "sector": info.get("sector") or "-",
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
        }
    except Exception:
        return None


def plot_stock_price_obv(ticker, display_name, market_name):
    is_bist = market_name == "BIST (Borsa İstanbul)"
    full_ticker = ticker + ".IS" if is_bist else ticker
    end = datetime.now()
    start = end - timedelta(days=180)

    try:
        df = yf.download(full_ticker, start=start, end=end, auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    except Exception:
        return None

    close  = df["Close"].squeeze()   # MultiIndex sonrası 2D olabilir → 1D'ye çevir
    volume = df["Volume"].squeeze()
    obv = pta.obv(close, volume)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=[f"{display_name} Fiyat", "Hacim", "OBV"],
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Fiyat",
    ), row=1, col=1)

    ema20 = pta.ema(close, length=20)
    if ema20 is not None:
        fig.add_trace(go.Scatter(
            x=df.index, y=ema20, name="EMA(20)",
            line=dict(color="#FFE66D", width=1),
        ), row=1, col=1)

    vol_colors = ["#00CC96" if c >= o else "#EF553B"
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=volume, name="Hacim",
        marker_color=vol_colors, opacity=0.7,
    ), row=2, col=1)

    if obv is not None:
        obv_avg = obv.rolling(22).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=obv, name="OBV",
            line=dict(color="#AB63FA", width=1.5),
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=obv_avg, name="OBV Ort(22)",
            line=dict(color="#FFA15A", width=1, dash="dash"),
        ), row=3, col=1)

    fig.update_layout(
        height=650,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=30),
    )
    return fig


def render_stock_cards(symbols, market_name):
    is_bist = market_name == "BIST (Borsa İstanbul)"

    for i in range(0, len(symbols), 3):
        cols = st.columns(min(3, len(symbols) - i))
        for j, col in enumerate(cols):
            if i + j >= len(symbols):
                break
            sym = symbols[i + j]
            full_ticker = sym + ".IS" if is_bist else sym
            detail = fetch_stock_detail(full_ticker)

            with col:
                if detail:
                    st.markdown(f"### {sym}")
                    st.caption(detail["name"])
                    m1, m2 = st.columns(2)
                    try:
                        pe_val = f"{float(detail['pe']):.2f}" if detail['pe'] else "-"
                    except (ValueError, TypeError):
                        pe_val = str(detail['pe']) if detail['pe'] else "-"
                    try:
                        pb_val = f"{float(detail['pb']):.2f}" if detail['pb'] else "-"
                    except (ValueError, TypeError):
                        pb_val = str(detail['pb']) if detail['pb'] else "-"
                    m1.metric("F/K", pe_val)
                    m2.metric("PD/DD", pb_val)

                    m3, m4 = st.columns(2)
                    if detail["market_cap"]:
                        if detail["market_cap"] >= 1e12:
                            cap_str = f"{detail['market_cap']/1e12:.1f}T"
                        elif detail["market_cap"] >= 1e9:
                            cap_str = f"{detail['market_cap']/1e9:.1f}B"
                        elif detail["market_cap"] >= 1e6:
                            cap_str = f"{detail['market_cap']/1e6:.0f}M"
                        else:
                            cap_str = f"{detail['market_cap']:,.0f}"
                    else:
                        cap_str = "-"
                    m3.metric("Piyasa Değeri", cap_str)
                    beta_val = f"{detail['beta']:.2f}" if detail['beta'] else "-"
                    m4.metric("Beta", beta_val)

                    m5, m6 = st.columns(2)
                    h52 = f"{detail['52w_high']:.2f}" if detail['52w_high'] else "-"
                    l52 = f"{detail['52w_low']:.2f}" if detail['52w_low'] else "-"
                    m5.metric("52H Yüksek", h52)
                    m6.metric("52H Düşük", l52)

                    st.caption(f"Sektör: {detail['sector']}")
                else:
                    st.markdown(f"### {sym}")
                    st.warning("Veri alınamadı")



def score_color(val):
    if val >= 75:
        return "background-color: #00CC96; color: black; font-weight: bold"
    elif val >= 50:
        return "background-color: #FFA15A; color: black; font-weight: bold"
    elif val >= 25:
        return "background-color: #FECB52; color: black; font-weight: bold"
    else:
        return "background-color: #EF553B; color: white; font-weight: bold"


def display_screening_results(screening_results, s_type, s_market, s_screen_date=None):
    from datetime import date as _date_cls
    if s_screen_date is not None and not hasattr(s_screen_date, 'strftime'):
        try:
            s_screen_date = _date_cls.fromisoformat(str(s_screen_date)[:10])
        except Exception:
            s_screen_date = None
    st.subheader(f"{s_type} Sonuçları")

    if screening_results:
        st.success(f"{len(screening_results)} hisse kriterlere uydu.")
        result_df = pd.DataFrame(screening_results)

        csv = result_df.to_csv(index=False).encode("utf-8")

        if "RS Eğimi" in result_df.columns and s_type == "Alfa Portföyü":
            def rs_arrow(val):
                try:
                    v = float(val)
                    if v > 0.01:
                        return f"{v:.4f} ↑↑↑"
                    elif v > 0.005:
                        return f"{v:.4f} ↑↑"
                    elif v > 0:
                        return f"{v:.4f} ↑"
                    else:
                        return f"{v:.4f} ↓"
                except (ValueError, TypeError):
                    return str(val)
            result_df["RS Eğimi"] = result_df["RS Eğimi"].apply(rs_arrow)

        # '-' string değerlerini sayısal sütunlarda NaN'a çevir (Arrow uyumu)
        for _col in ["ROE (%)", "RS Eğimi", "EPS Büyümesi (%)", "Ciro Büyümesi (%)"]:
            if _col in result_df.columns:
                result_df[_col] = pd.to_numeric(result_df[_col], errors="coerce")

        if "Yatırım Uzmanı Skoru" in result_df.columns:
            styled_df = result_df.style.applymap(
                score_color, subset=["Yatırım Uzmanı Skoru"]
            ).format({"Yatırım Uzmanı Skoru": "{:.1f}"})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Skor Dağılımı")
            fig_score = go.Figure()
            colors = []
            for s in result_df["Yatırım Uzmanı Skoru"]:
                if s >= 75:
                    colors.append("#00CC96")
                elif s >= 50:
                    colors.append("#FFA15A")
                elif s >= 25:
                    colors.append("#FECB52")
                else:
                    colors.append("#EF553B")

            fig_score.add_trace(go.Bar(
                x=result_df["Sembol"],
                y=result_df["Yatırım Uzmanı Skoru"],
                marker_color=colors,
                text=result_df["Yatırım Uzmanı Skoru"].apply(lambda x: f"{x:.1f}"),
                textposition="outside",
            ))
            fig_score.update_layout(
                title=f"{s_type} — Yatırım Uzmanı Skorları",
                xaxis_title="Hisse",
                yaxis_title="Skor (0-100)",
                yaxis=dict(range=[0, 110]),
                template="plotly_dark",
                height=400,
            )
            st.plotly_chart(fig_score, use_container_width=True)
        else:
            st.dataframe(result_df, use_container_width=True, hide_index=True)
        st.download_button(
            label="Sonuçları CSV Olarak İndir",
            data=csv,
            file_name=f"{s_type.lower().replace(' ', '_')}_tarama.csv",
            mime="text/csv",
            use_container_width=True,
        )

        tg_tok = st.session_state.get("tg_token", "")
        tg_cid = st.session_state.get("tg_chat_id", "")
        if tg_tok and tg_cid:
            if st.button("Tarama Sonuçlarını Telegram'a Gönder", key="tg_send_screening", use_container_width=True):
                top5_send = sorted(screening_results if screening_results else [], key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)[:7]
                lines = [f"<b>{s_type} Tarama — {s_screen_date or 'Bugün'}</b>"]
                for r in top5_send:
                    lines.append(f"• <b>{r['Sembol']}</b> — Skor: {r.get('Yatırım Uzmanı Skoru','')}")
                lines.append(f"\nToplam: {len(screening_results or [])} hisse bulundu.")
                ok, _ = send_telegram_message(tg_tok, tg_cid, "\n".join(lines))
                if ok:
                    st.success("Telegram'a gönderildi!")
                else:
                    st.error("Gönderilemedi. Token/Chat ID kontrol edin.")

        st.divider()
        st.subheader("Hızlı Portföy Oluştur")

        def _fetch_price_for_date(ticker_sym, target_date):
            try:
                if target_date and target_date < datetime.now().date():
                    start_dt = target_date - timedelta(days=5)
                    end_dt = target_date + timedelta(days=1)
                    price_data = yf.Ticker(ticker_sym).history(start=start_dt, end=end_dt, auto_adjust=False)
                else:
                    price_data = yf.Ticker(ticker_sym).history(period="5d", auto_adjust=False)
                if price_data is not None and not price_data.empty:
                    return float(price_data["Close"].iloc[-1])
            except Exception:
                pass
            return 0

        use_date = s_screen_date if s_screen_date else datetime.now().date()
        is_past = s_screen_date is not None and s_screen_date < datetime.now().date()
        if is_past:
            st.info(f"Tarama tarihi: **{s_screen_date.strftime('%d.%m.%Y')}** — Hisseler bu tarihteki fiyatlarla eklenecek.")

        sorted_results = sorted(screening_results, key=lambda x: x.get("Yatırım Uzmanı Skoru", 0), reverse=True)
        top5 = sorted_results[:7]
        top5_symbols = [r["Sembol"] for r in top5]

        strategy_short = {"Alfa Portföyü": "ALFA", "Beta Portföyü": "BETA", "Delta Portföyü": "DELTA"}.get(s_type, "STR")
        market_short = screen_pool_name.replace(" (XUTUM)", "").replace(" (XTUMY)", "").replace(" ", "_").upper() if s_market == "BIST (Borsa İstanbul)" else screen_pool_name.replace(" ", "_").upper()
        period_short = {"Haftalık": "HF", "15 Günlük": "15G", "Aylık": "AY"}.get(bt_period, "AY")
        auto_pf_name = f"{market_short}-{strategy_short}-{period_short}-{use_date.strftime('%d.%m.%Y')}"

        qp_name = st.text_input("Portföy Adı", value=auto_pf_name, key="quick_pf_name")

        st.markdown(f"**En yüksek puanlı 7 hisse:** {', '.join(top5_symbols)}")

        currency_label = "TL" if s_market == "BIST (Borsa İstanbul)" else "$"
        amounts = {}
        cols_amt = st.columns(len(top5))
        for idx, r in enumerate(top5):
            sym = r["Sembol"]
            score_val = r.get("Yatırım Uzmanı Skoru", 0)
            with cols_amt[idx]:
                st.markdown(f"**{sym}**")
                st.caption(f"Skor: {score_val:.1f}")
                amounts[sym] = st.number_input(
                    f"Tutar ({currency_label})", value=10000, min_value=100, step=1000, key=f"qp_amt_{sym}"
                )

        if st.button("Portföy Oluştur ve Hisseleri Ekle", type="primary", use_container_width=True, key="quick_create_pf_btn"):
            if qp_name.strip():
                pf_market_val = "BIST" if s_market == "BIST (Borsa İstanbul)" else "US"
                new_pf_id = db_create_portfolio(qp_name.strip(), f"{s_type} tarama sonuçlarından oluşturuldu", pf_market_val, scan_date=s_screen_date)
                added_count = 0
                for r in top5:
                    sym = r["Sembol"]
                    ticker_sym = sym + ".IS" if s_market == "BIST (Borsa İstanbul)" else sym
                    invest_amount = amounts.get(sym, 10000)
                    current_price = _fetch_price_for_date(ticker_sym, use_date)
                    if current_price > 0:
                        calc_shares = round(invest_amount / current_price, 4)
                    else:
                        calc_shares = 0
                    score = r.get("Yatırım Uzmanı Skoru", 0)
                    if calc_shares > 0:
                        db_add_stock_to_portfolio(
                            portfolio_id=new_pf_id,
                            symbol=sym,
                            shares=calc_shares,
                            buy_price=current_price,
                            buy_date=use_date,
                            strategy=s_type,
                            score=score,
                            notes=f"Tutar: {invest_amount} {currency_label} | Fiyat ({use_date.strftime('%d.%m.%Y')}): {current_price:.2f} | Skor: {score:.1f}"
                        )
                        added_count += 1
                st.success(f"'{qp_name}' portföyü oluşturuldu! {added_count} hisse eklendi.")
                st.rerun()
            else:
                st.warning("Portföy adı boş olamaz.")

        with st.expander("Mevcut Portföye Ekle"):
            portfolios = db_get_portfolios()
            if portfolios:
                portfolio_options = {f"{p['name']} ({p['market']})": p['id'] for p in portfolios}
                selected_portfolio_name = st.selectbox(
                    "Hedef Portföy", list(portfolio_options.keys()), key="screen_portfolio_select"
                )
                selected_portfolio_id = portfolio_options[selected_portfolio_name]
                stock_symbols = [r["Sembol"] for r in screening_results]
                selected_stocks = st.multiselect(
                    "Eklenecek Hisseler", stock_symbols, default=stock_symbols[:7], key="screen_stocks_to_add"
                )
                add_amount = st.number_input(f"Her hisse için yatırım tutarı ({currency_label})", value=10000, min_value=100, step=1000, key="screen_add_amount")
                if st.button("Seçili Hisseleri Portföye Ekle", type="primary", use_container_width=True, key="add_to_portfolio_btn"):
                    added_count = 0
                    for r in screening_results:
                        if r["Sembol"] in selected_stocks:
                            sym = r["Sembol"]
                            ticker_sym = sym + ".IS" if s_market == "BIST (Borsa İstanbul)" else sym
                            current_price = _fetch_price_for_date(ticker_sym, use_date)
                            if current_price > 0:
                                calc_shares = round(add_amount / current_price, 4)
                            else:
                                calc_shares = 0
                            score = r.get("Yatırım Uzmanı Skoru", 0)
                            if calc_shares > 0:
                                db_add_stock_to_portfolio(
                                    portfolio_id=selected_portfolio_id,
                                    symbol=sym,
                                    shares=calc_shares,
                                    buy_price=current_price,
                                    buy_date=use_date,
                                    strategy=s_type,
                                    score=score,
                                    notes=f"Tutar: {add_amount} {currency_label} | Fiyat ({use_date.strftime('%d.%m.%Y')}): {current_price:.2f} | Skor: {score:.1f}"
                                )
                                added_count += 1
                    st.success(f"{added_count} hisse portföye eklendi!")
                    st.rerun()
            else:
                st.info("Henüz portföy oluşturulmadı.")

        st.divider()
        st.subheader("Temel Veriler")
        found_symbols = [r["Sembol"] for r in screening_results]
        render_stock_cards(found_symbols, s_market)

        st.divider()
        st.subheader("Fiyat & OBV Grafikleri")
        for sym in found_symbols:
            fig_detail = plot_stock_price_obv(sym, sym, s_market)
            if fig_detail:
                st.plotly_chart(fig_detail, use_container_width=True)
            else:
                st.warning(f"{sym} için grafik oluşturulamadı.")
    else:
        st.warning("Bu kriterlere uyan hisse bulunamadı. Piyasa koşulları kriterleri karşılamıyor olabilir.")

    st.divider()
    st.subheader("Tarama Kriterleri")
    if s_type == "Alfa Portföyü":
        st.markdown("""
**Alfa-Beta Hibrit Tetikleyici:**
- **RS Slope** > 0 ve son **5 günde yükseliyor** (ivme artışı)
- Fiyat > **SMA(200) × 1.05** (negatif trenddeki kağıtlardan korunma)

**Hacim Onayı:**
- **OBV** son 5 günde yükselen trendde (doğrusal regresyon)

**Uyarlanabilir (Adaptive) Kalite Filtresi:**
- Tüm adaylarda **ROE** ve **Kar Büyümesi** büyükten küçüğe sıralanır
- Sadece ROE veya Kar Büyümesi **üst %20'lik dilimde** olan hisseler aday havuzuna alınır
- Sabit eşik yerine göreceli sıralama kullanılır

**Zayıf Halka Eleme (Volatilite Filtresi):**
- Hisse yıllık volatilitesi, endeks volatilitesinin **1.5 katından** fazlaysa puan düşürülür
- Aşırı riskli kağıtlar otomatik olarak cezalandırılır

**F/K Eşik Filtresi:**
- **F/K > 50** olan hisseler elenir (puanlamaya dahil değil)

**Puanlama:** RS Slope (%40) + Kar Büyümesi Sıralaması (%30) + ROE Sıralaması (%30)

**Holding Süresi:** Seçilen periyot sonunda (15 gün / 1 ay / vs.) tam satış
""")
    elif s_type == "Beta Portföyü":
        st.markdown("""
- **ADX** > 25: Güçlü trend mevcut
- **Fiyat** > EMA(50): Yükseliş trendinde
- **MFI (Money Flow Index)** > 70: Güçlü para akışı
""")
    elif s_type == "Delta Portföyü":
        st.markdown("""
**Trend İçi Geri Çekilme (Pullback) Modeli:**

**Zorunlu Filtreler:**
- Fiyat **SMA(50)** üzerinde (ana trend sağlam)
- Fiyat SMA(50)'ye max **+%3** uzaklıkta (desteğe yakın, risk/ödül yüksek)
- **RSI(14)** değeri **35–50** arasında (soğuma/dinlenme bölgesi)

**Dönüş Tetikleyicisi:**
- Bugünkü kapanış > dünkü en yüksek fiyat (mum onayı)
- Bugünkü hacim > dünkü hacim (hacim onayı)

**Puanlama:** Göreceli Güç - 3 Aylık (%50) + Destek Yakınlığı (%30) + MFI Para Girişi (%20)

**Holding Süresi:** Seçilen periyot sonunda (15 gün / 1 ay / vs.) tam satış
""")


with tab_tarama:
    if screen_btn:
        screening_results = run_screening(tuple(screen_stock_pool), market, screen_type, score_weights, screen_date=screen_date)

        st.session_state["screening_results"] = screening_results
        st.session_state["screening_type"] = screen_type
        st.session_state["screening_market"] = market
        st.session_state["screening_date"] = screen_date

        # ── Taramayı otomatik kaydet (en iyi 7) ──────────────────────────────
        if screening_results:
            top5_to_save = sorted(screening_results,
                                  key=lambda x: x.get("Yatırım Uzmanı Skoru", 0),
                                  reverse=True)[:7]
            top5_minimal = [{"Sembol": r.get("Sembol", ""),
                              "Skor": round(float(r.get("Yatırım Uzmanı Skoru", 0)), 2),
                              "Fiyat": r.get("Son Fiyat", r.get("Fiyat", "-"))}
                             for r in top5_to_save]
            db_save_scan(screen_date, market, screen_type, top5_minimal)

        display_screening_results(screening_results, screen_type, market, s_screen_date=screen_date)
    else:
        saved_results = st.session_state.get("screening_results")
        saved_type = st.session_state.get("screening_type")
        saved_market = st.session_state.get("screening_market")
        saved_date = st.session_state.get("screening_date")

        if saved_results is not None:
            display_screening_results(saved_results, saved_type, saved_market, s_screen_date=saved_date)
        else:
            st.info("Sol panelden bir tarama algoritması seçin ve 'Taramayı Başlat' butonuna tıklayın.")

    # ── Kaydedilmiş Taramalar ─────────────────────────────────────────────────
    st.divider()
    st.subheader("Kaydedilmiş Taramalar")

    saved_scans = db_get_saved_scans()
    if not saved_scans:
        st.caption("Henüz kaydedilmiş tarama yok. Tarama yaptıkça burada listelenir.")
    else:
        for scan in saved_scans:
            col_date, col_strat, col_stocks, col_del = st.columns([1.2, 1.2, 4.5, 0.6])
            with col_date:
                st.markdown(f"**{scan['scan_date']}**")
            with col_strat:
                st.caption(f"{scan.get('strategy','')}")
            with col_stocks:
                symbols = [s.get("Sembol", "") for s in scan.get("top5", [])]
                scores  = [str(s.get("Skor", "")) for s in scan.get("top5", [])]
                pairs   = [f"**{sym}** ({sc})" for sym, sc in zip(symbols, scores)]
                st.markdown("  ·  ".join(pairs) if pairs else "—")
            with col_del:
                if st.button("🗑️", key=f"del_scan_{scan['id']}", help="Bu taramayı sil"):
                    db_delete_scan(scan["id"])
                    st.rerun()


with tab_backtest:
    st.subheader("Periyodik Yeniden Dengelemeli Backtest")

    progress_ph = None  # aşağıda divider'dan önce tanımlanacak

    # ── Manuel Portföy Backtest ───────────────────────────────────────────────
    with st.expander("Manuel Portföy Backtesti (Aylık Hisse Listesi ile)", expanded=False):
        st.markdown("""
**Nasıl kullanılır?** Her satır bir ay ve o aya ait hisseleri içerir.  
Format: `YYYY-MM: HİSSE1, HİSSE2, HİSSE3, ...`  
Örnek:
```
2025-01: AVPGY, ISGSY, ARASE, ATLAS, GLRYH
2025-02: ATLAS, AVPGY, ARASE, ISGSY, GOLTS
2025-03: BUCIM, ARASE, GLRYH, ISGSY, GOLTS
```
        """)

        col_man1, col_man2 = st.columns([3, 1])
        with col_man1:
            manual_portfolio_text = st.text_area(
                "Aylık Portföy Listesi",
                height=200,
                key="manual_portfolio_text",
                placeholder="2025-01: AVPGY, ISGSY, ARASE, ATLAS, GLRYH\n2025-02: ATLAS, AVPGY, ARASE, ISGSY, GOLTS\n...",
            )
        with col_man2:
            st.markdown("**Örnek Şablonlar**")
            if st.button("Alfa Portföy Örneği", key="fill_alfa_example", use_container_width=True):
                st.session_state["manual_portfolio_text"] = (
                    "2025-01: AVPGY, ISGSY, ARASE, ATLAS, GLRYH\n"
                    "2025-02: ATLAS, AVPGY, ARASE, ISGSY, GOLTS\n"
                    "2025-03: BUCIM, ARASE, GLRYH, ISGSY, GOLTS\n"
                    "2025-04: KZBGY, BULGS, ISGSY, KTLEV\n"
                    "2025-05: KZBGY, ARTMS, BORSK, ISGSY, KTLEV\n"
                    "2025-06: KZBGY, ARTMS, A1CAP, ISGSY, KTLEV\n"
                    "2025-07: KZBGY, ARTMS, BANVT, ISGSY, KTLEV\n"
                    "2025-08: KZBGY, ARTMS, A1CAP, ISGSY, KTLEV\n"
                    "2025-09: INVEO, ARTMS, ATATP, ISGSY, KTLEV\n"
                    "2025-10: INVEO, ARTMS, ORGE, ISGSY, KTLEV\n"
                    "2025-11: INVEO, ORGE, ISGSY, KTLEV\n"
                    "2025-12: INVEO, SANEL, KRSTL, ISGSY, KTLEV\n"
                    "2026-01: INVEO, ATATP, KRSTL, ISGSY, KTLEV\n"
                    "2026-02: INVEO, SANEL, KRSTL, ISGSY, MACKO"
                )
                st.rerun()

        man_capital = st.number_input("Başlangıç Sermayesi", value=100000, step=10000, min_value=1000, key="man_capital")
        man_btn = st.button("Manuel Backtest Başlat", type="primary", key="man_bt_btn", use_container_width=True)

        man_progress_ph = st.empty()

        if man_btn and manual_portfolio_text.strip():
            monthly_portfolios_parsed = {}
            for line in manual_portfolio_text.strip().split('\n'):
                line = line.strip()
                if not line or ':' not in line:
                    continue
                month_part, stocks_part = line.split(':', 1)
                month_key = month_part.strip()
                if len(month_key) == 7 and month_key[4] == '-':
                    stocks = [s.strip().upper() for s in stocks_part.split(',') if s.strip()]
                    if stocks:
                        monthly_portfolios_parsed[month_key] = stocks

            if monthly_portfolios_parsed:
                with st.spinner("Manuel backtest hesaplanıyor..."):
                    man_result = run_manual_portfolio_backtest(
                        monthly_portfolios=monthly_portfolios_parsed,
                        market=market,
                        initial_capital=man_capital,
                        progress_placeholder=man_progress_ph,
                    )
                man_progress_ph.empty()

                if man_result:
                    st.session_state["man_bt_result"] = man_result
                    st.rerun()
                else:
                    st.error("Manuel backtest için yeterli veri bulunamadı.")
            else:
                st.warning("Geçerli format bulunamadı. Örnek: `2025-01: AVPGY, ISGSY, ARASE`")

        man_result = st.session_state.get("man_bt_result")
        if man_result:
            st.divider()
            st.markdown("#### Manuel Portföy Backtest Sonuçları")

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Toplam Getiri", f"{man_result['total_return']:.2f}%")
            mc2.metric("Yıllık Getiri", f"{man_result['annual_return']:.2f}%")
            mc3.metric("Sharpe Oranı", f"{man_result['sharpe']:.2f}")
            mc4.metric("Maks. Düşüş", f"{man_result['max_drawdown']:.2f}%")

            mc5, mc6 = st.columns(2)
            mc5.metric("Başlangıç", f"{man_result['initial_capital']:,.0f} ₺")
            mc6.metric("Son Değer", f"{man_result['final_equity']:,.0f} ₺")

            eq_man = man_result["equity_curve"]
            bench_man = man_result.get("benchmark_curve")

            fig_man = go.Figure()
            fig_man.add_trace(go.Scatter(
                x=eq_man.index, y=eq_man.values,
                mode='lines+markers', name='Manuel Portföy',
                line=dict(color='#10B981', width=2),
                marker=dict(size=6),
            ))
            if bench_man is not None:
                fig_man.add_trace(go.Scatter(
                    x=bench_man.index, y=bench_man.values,
                    mode='lines', name='XU100 / Benchmark',
                    line=dict(color='#F59E0B', width=1.5, dash='dash'),
                ))
            fig_man.update_layout(
                title="Manuel Portföy — Sermaye Eğrisi",
                xaxis_title="Tarih", yaxis_title="Değer (₺)",
                template="plotly_dark", height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_man, use_container_width=True)

            if not man_result["trade_log"].empty:
                with st.expander("İşlem Günlüğü"):
                    st.dataframe(man_result["trade_log"], use_container_width=True, hide_index=True)

    # ── İlerleme çubuğu — backtest ile kayıtlı backtestler arasında ──────────
    progress_ph = st.empty()

    st.divider()

    saved_bts = db_get_saved_backtests()
    if saved_bts:
        st.markdown("### Kayıtlı Backtestler")

        compare_rows = []
        for sb in saved_bts:
            sb_id = sb["id"]
            sb_name = sb["name"]
            sb_strategy = sb["strategy"]
            sb_return = float(sb['total_return']) if sb.get("total_return") is not None else None
            sb_ann = float(sb['annual_return']) if sb.get("annual_return") is not None else None
            sb_sharpe = float(sb['sharpe']) if sb.get("sharpe") is not None else None
            sb_mdd = float(sb['max_drawdown']) if sb.get("max_drawdown") is not None else None
            _sb_cat = sb.get("created_at")
            sb_date = (_sb_cat.strftime("%d.%m.%Y %H:%M") if hasattr(_sb_cat, 'strftime') else str(_sb_cat)[:16].replace('T', ' ').replace('-', '.').replace('.', '.', 2)) if _sb_cat else "-"
            sb_period = sb.get("rebalance_period", "-")
            sb_capital = float(sb['initial_capital']) if sb.get("initial_capital") else None
            sb_final = float(sb['final_equity']) if sb.get("final_equity") is not None else None

            compare_rows.append({
                "Ad": sb_name,
                "Strateji": sb_strategy,
                "Periyot": sb_period,
                "Başlangıç": f"{sb_capital:,.0f}" if sb_capital else "-",
                "Son Değer": f"{sb_final:,.0f}" if sb_final else "-",
                "Toplam Getiri (%)": f"{sb_return:.2f}" if sb_return is not None else "-",
                "Yıllık Getiri (%)": f"{sb_ann:.2f}" if sb_ann is not None else "-",
                "Sharpe": f"{sb_sharpe:.2f}" if sb_sharpe is not None else "-",
                "Maks. Düşüş (%)": f"{sb_mdd:.2f}" if sb_mdd is not None else "-",
                "Kayıt Tarihi": sb_date,
            })

            col_info, col_load, col_del = st.columns([6, 1, 1])
            with col_info:
                ret_str = f"{sb_return:.2f}%" if sb_return is not None else "-"
                st.markdown(f"**{sb_name}** — {sb_strategy} | Getiri: {ret_str} | {sb_period} | {sb_date}")
            with col_load:
                if st.button("Göster", key=f"load_bt_{sb_id}", use_container_width=True):
                    loaded_result = db_get_backtest_result(sb_id)
                    if loaded_result:
                        st.session_state["bt_result"] = loaded_result
                        st.session_state["bt_screen_type"] = sb_strategy
                        st.rerun()
                    else:
                        st.error("Sonuçlar yüklenemedi.")
            with col_del:
                if st.button("Sil", key=f"del_bt_{sb_id}", type="secondary", use_container_width=True):
                    db_delete_backtest(sb_id)
                    st.toast(f"'{sb_name}' silindi.")
                    st.rerun()

        if len(compare_rows) >= 2:
            st.divider()
            st.markdown("#### Tüm Kayıtlı Backtestler — Karşılaştırma Tablosu")
            compare_df = pd.DataFrame(compare_rows)
            st.dataframe(compare_df, use_container_width=True, hide_index=True)

            st.markdown("#### Toplam Getiri Karşılaştırması")
            fig_cmp = go.Figure()
            for row in compare_rows:
                try:
                    val = float(row["Toplam Getiri (%)"])
                    fig_cmp.add_trace(go.Bar(
                        name=row["Ad"],
                        x=[row["Ad"]],
                        y=[val],
                        text=[f"%{val:.2f}"],
                        textposition="outside",
                    ))
                except ValueError:
                    pass
            fig_cmp.update_layout(
                title="Kayıtlı Backtestler — Toplam Getiri (%)",
                yaxis_title="Getiri (%)",
                template="plotly_dark",
                height=400,
                showlegend=False,
                barmode="group",
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

        st.divider()

    if bt_btn:
        bt_start_dt = datetime.combine(bt_start_date, datetime.min.time())
        if bt_screen_type_sel == "Alfa Portföyü":
            bt_score_weights = {"rs_slope": 40, "kar_buyumesi_rank": 30, "roe_rank": 30}
        elif bt_screen_type_sel == "Beta Portföyü":
            bt_score_weights = {"momentum_mfi": 40, "adx_gucu": 40, "relative_strength": 20}
        else:
            bt_score_weights = {"relative_strength": 50, "destek_yakinligi": 30, "para_girisi": 20}
        filtered_pool = [s for s in bt_stock_pool if s.upper() not in bt_excluded]
        if bt_excluded:
            st.caption(f"Hariç tutulan hisseler: {', '.join(sorted(bt_excluded))} → {len(filtered_pool)} hisse ile devam ediliyor.")

        # ── Adım 1: Veri indirme (cache'te yoksa Twelve Data'dan çek) ────────
        if _USE_DATA_CACHE:
            lookback_start_str = (bt_start_dt - timedelta(days=400)).strftime("%Y-%m-%d")
            end_str_now = bt_end_date.strftime("%Y-%m-%d") if bt_end_date else datetime.now().strftime("%Y-%m-%d")
            is_bist_bt = market == "BIST (Borsa İstanbul)"
            bt_tickers_full = [s + ".IS" for s in filtered_pool] if is_bist_bt else list(filtered_pool)

            from data_cache import _get_cached_date_range, init_price_cache as _dc_init2, batch_get_price_data as _dc_batch2
            _dc_init2()
            missing = []
            for tk in bt_tickers_full:
                cmin, cmax = _get_cached_date_range(tk)
                if not (cmin and cmin <= lookback_start_str and cmax and cmax >= end_str_now):
                    missing.append(tk)

            if missing:
                _total_pool = len(bt_tickers_full)
                progress_ph.progress(0.0, text=f"Veri indiriliyor: {len(missing)}/{_total_pool} hisse cache'te yok — Twelve Data'dan çekiliyor...")
                def _pre_dl_progress(i, total, ticker):
                    pct = (i + 1) / max(total, 1)
                    burst_wait = (i > 0 and i % 8 == 0)
                    status = f"İndiriliyor ({i+1}/{total}): {ticker}"
                    if burst_wait:
                        status += " — rate limit bekleniyor (1 dk)..."
                    progress_ph.progress(pct * 0.4, text=status)
                _dc_batch2(missing, lookback_start_str, end_str_now, progress_callback=_pre_dl_progress)
                progress_ph.progress(0.4, text="Veri indirme tamamlandı. Backtest başlıyor...")
            else:
                progress_ph.progress(0.05, text="Veriler cache'te mevcut. Backtest başlıyor...")

        # ── Adım 2: Backtest çalıştır ─────────────────────────────────────────
        bt_result = run_rebalancing_backtest(
            stock_list=filtered_pool,
            market=market,
            screen_type=bt_screen_type_sel,
            score_weights=bt_score_weights,
            bt_start_date=bt_start_dt,
            initial_capital=bt_capital,
            rebalance_period=bt_period,
            top_n=bt_top_n,
            progress_placeholder=progress_ph,
            weighting_mode=bt_weighting,
            hold_continuation=bt_hold_continuation,
            bt_end_date=bt_end_date,
        )
        progress_ph.empty()

        if bt_result:
            st.session_state["bt_result"] = bt_result
            st.session_state["bt_screen_type"] = bt_screen_type_sel
            if bt_save_name.strip():
                db_save_backtest(
                    name=bt_save_name.strip(),
                    market=market,
                    strategy=bt_screen_type_sel,
                    start_date=bt_start_date,
                    initial_capital=bt_capital,
                    rebalance_period=bt_period,
                    top_n=bt_top_n,
                    bt_result=bt_result,
                )
                st.toast(f"'{bt_save_name.strip()}' kaydedildi!")
            st.rerun()
        else:
            st.error("Backtest için yeterli veri bulunamadı. Olası nedenler: (1) Seçilen tarih aralığında yeterli hisse verisi yok, (2) Benchmark (XU100.IS) indirilemedi — lütfen birkaç dakika bekleyip tekrar deneyin, (3) Daha yakın bir başlangıç tarihi veya farklı havuz seçin.")

    bt_result = st.session_state.get("bt_result")
    bt_screen_type = st.session_state.get("bt_screen_type")

    if bt_result:
        st.markdown(f"**Strateji:** {bt_screen_type} — En İyi {bt_top_n} Hisse — {bt_period} Dengeleme")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Getiri", f"{bt_result['total_return']:.2f}%")
        col2.metric("Yıllıklandırılmış Getiri", f"{bt_result['annual_return']:.2f}%")
        col3.metric("Sharpe Oranı", f"{bt_result['sharpe']:.2f}")
        col4.metric("Maks. Düşüş (Drawdown)", f"{bt_result['max_drawdown']:.2f}%")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Sortino Oranı", f"{bt_result.get('sortino', 0):.2f}")
        col6.metric("Calmar Oranı", f"{bt_result.get('calmar', 0):.2f}")
        col7.metric("Kazanma Oranı", f"%{bt_result.get('win_rate', 0):.1f}  ({bt_result.get('n_wins',0)}K/{bt_result.get('n_losses',0)}Z)")
        pf = bt_result.get("profit_factor")
        col8.metric("Profit Factor", f"{pf:.2f}" if pf is not None else "-")

        col9, col10, col11, col12 = st.columns(4)
        col9.metric("Başlangıç Sermayesi", f"{bt_result['initial_capital']:,.0f}")
        col10.metric("Son Sermaye", f"{bt_result['final_equity']:,.0f}")
        if bt_result["bench_total_return"] is not None:
            col11.metric(f"{bt_result['benchmark_name']} Getirisi", f"{bt_result['bench_total_return']:.2f}%")
            alpha = bt_result["total_return"] - bt_result["bench_total_return"]
            col12.metric("Alfa (Fazla Getiri)", f"{alpha:.2f}%")
        col_p = st.columns(1)[0]
        col_p.metric("Toplam Periyot Sayısı", bt_result["n_periods"])

        st.divider()
        st.subheader("Sermaye Eğrisi (Equity Curve)")

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=bt_result["equity_series"].index,
            y=bt_result["equity_series"].values,
            name=f"{bt_screen_type} Strateji",
            line=dict(color="#00CC96", width=2.5),
            mode="lines+markers",
            marker=dict(size=5),
        ))
        if bt_result["bench_normalized"] is not None:
            fig_eq.add_trace(go.Scatter(
                x=bt_result["bench_normalized"].index,
                y=bt_result["bench_normalized"].values,
                name=bt_result["benchmark_name"],
                line=dict(color="#636EFA", width=2, dash="dash"),
            ))
        fig_eq.add_hline(
            y=bt_result["initial_capital"],
            line_dash="dot", line_color="gray",
            annotation_text=f"Başlangıç: {bt_result['initial_capital']:,.0f}",
        )
        fig_eq.update_layout(
            title=f"Sermaye Eğrisi — {bt_screen_type} vs {bt_result['benchmark_name']}",
            xaxis_title="Tarih",
            yaxis_title="Portföy Değeri",
            template="plotly_dark",
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_eq, use_container_width=True)



        st.divider()
        st.subheader("İstatistikler")
        stats_data = {
            "Metrik": [
                "Toplam Getiri (%)",
                "Yıllıklandırılmış Getiri (%)",
                "Sharpe Oranı",
                "Sortino Oranı",
                "Calmar Oranı",
                "Maksimum Düşüş (%)",
                "Kazanma Oranı (%)",
                "Ortalama Kazanç (%)",
                "Ortalama Kayıp (%)",
                "Profit Factor",
                "Başlangıç Sermayesi",
                "Son Sermaye",
                "Periyot Sayısı",
            ],
            "Değer": [
                f"{bt_result['total_return']:.2f}",
                f"{bt_result['annual_return']:.2f}",
                f"{bt_result['sharpe']:.2f}",
                f"{bt_result.get('sortino', 0):.2f}",
                f"{bt_result.get('calmar', 0):.2f}",
                f"{bt_result['max_drawdown']:.2f}",
                f"{bt_result.get('win_rate', 0):.1f}",
                f"{bt_result.get('avg_win', 0):.2f}",
                f"{bt_result.get('avg_loss', 0):.2f}",
                f"{bt_result.get('profit_factor', 0):.2f}" if bt_result.get('profit_factor') else "-",
                f"{bt_result['initial_capital']:,.0f}",
                f"{bt_result['final_equity']:,.0f}",
                str(bt_result["n_periods"]),
            ],
        }
        if bt_result["bench_total_return"] is not None:
            stats_data["Metrik"].append(f"{bt_result['benchmark_name']} Getirisi (%)")
            stats_data["Değer"].append(f"{bt_result['bench_total_return']:.2f}")
            stats_data["Metrik"].append("Alfa (%)")
            stats_data["Değer"].append(f"{bt_result['total_return'] - bt_result['bench_total_return']:.2f}")

        stats_df = pd.DataFrame(stats_data)
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

        # ── Periyot Bazlı Getiri Tablosu ─────────────────────────────────────
        pb = bt_result.get("period_breakdown", [])
        if pb:
            st.divider()
            st.subheader("Periyot Bazlı Getiri Analizi")
            pb_df = pd.DataFrame(pb)
            suspicious = pb_df[pb_df["Getiri (%)"].abs() > 60]
            if not suspicious.empty:
                st.warning(f"⚠️ {len(suspicious)} periyotta %60'ı aşan getiri tespit edildi — bu periyotları kontrol edin.")
            st.dataframe(
                pb_df.style.applymap(
                    lambda v: "background-color:#d4edda" if isinstance(v, (int, float)) and v > 30
                    else ("background-color:#f8d7da" if isinstance(v, (int, float)) and v < -20 else ""),
                    subset=["Getiri (%)"]
                ),
                use_container_width=True, hide_index=True
            )

        st.divider()
        st.subheader("İşlem Defteri (Trade Log)")
        if bt_result["trade_log"]:
            trade_df = pd.DataFrame(bt_result["trade_log"])

            # Hisse bazlı filtre
            all_symbols = sorted(trade_df["Sembol"].unique().tolist())
            filter_col1, filter_col2 = st.columns([2, 3])
            with filter_col1:
                selected_sym = st.selectbox(
                    "Hisse Filtrele",
                    ["Tümü"] + all_symbols,
                    key="trade_log_sym_filter",
                )
            filtered_trade_df = trade_df if selected_sym == "Tümü" else trade_df[trade_df["Sembol"] == selected_sym]
            # Arrow uyumu: '-' string değerlerini sayısal sütunlarda NaN'a çevir
            _ftdf = filtered_trade_df.copy()
            for _c in _ftdf.select_dtypes(include="object").columns:
                try:
                    _converted = pd.to_numeric(_ftdf[_c], errors="coerce")
                    if _converted.notna().sum() > _ftdf[_c].notna().sum() * 0.3:
                        _ftdf[_c] = _converted
                except Exception:
                    pass
            st.dataframe(_ftdf, use_container_width=True, hide_index=True)

            # Excel indirme (filtreye göre)
            excel_buffer = BytesIO()
            filtered_trade_df.to_excel(excel_buffer, index=False, engine="openpyxl")
            excel_bytes = excel_buffer.getvalue()  # BytesIO yerine bytes — Streamlit ile daha güvenli
            sym_suffix = f"_{selected_sym}" if selected_sym != "Tümü" else ""
            excel_filename = f"{bt_screen_type}_{bt_pool_name}_{bt_period}_{bt_start_date.strftime('%d.%m.%Y')}{sym_suffix}.xlsx".replace(" ", "_")
            st.download_button(
                label=f"{'Tüm' if selected_sym == 'Tümü' else selected_sym} İşlem Defterini Excel Olarak İndir",
                data=excel_bytes,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="dl_excel_trade_log",
            )
        else:
            st.info("Bu backtest döneminde işlem gerçekleşmedi.")

        st.divider()
        st.caption(
            "Not: Tarihsel temel veriler (F/K, ROE) yfinance'de kısıtlı olduğundan, "
            "geçmiş dönemlerde bu kriterler güncel verilerle değerlendirilmiştir. "
            "Bu durum backtest sonuçlarında look-ahead bias oluşturabilir. "
            "Ayrıca tarama havuzundaki hisseler bugünkü listedir; geçmişte delisteden çıkan hisseler dahil değildir (survivorship bias)."
        )
    else:
        if not bt_btn and not bt_compare_btn:
            st.info("Sol panelden backtest ayarlarını yapın ve 'Backtest Başlat' butonuna tıklayın.")

    if bt_compare_btn:
        st.divider()
        st.subheader("Strateji Karşılaştırması (Alfa / Beta / Delta)")
        bt_start_dt = datetime.combine(bt_start_date, datetime.min.time())

        strategy_configs = [
            ("Alfa Portföyü", {"rs_slope": 40, "kar_buyumesi_rank": 30, "roe_rank": 30}, "#00CC96"),
            ("Beta Portföyü", {"momentum_mfi": 40, "adx_gucu": 40, "relative_strength": 20}, "#EF553B"),
            ("Delta Portföyü", {"relative_strength": 50, "destek_yakinligi": 30, "para_girisi": 20}, "#AB63FA"),
        ]

        compare_results = {}
        progress_compare = st.empty()
        for s_name, s_weights, _ in strategy_configs:
            progress_compare.info(f"{s_name} hesaplanıyor...")
            try:
                res = run_rebalancing_backtest(
                    stock_list=filtered_pool,
                    market=market,
                    screen_type=s_name,
                    score_weights=s_weights,
                    bt_start_date=bt_start_dt,
                    initial_capital=bt_capital,
                    rebalance_period=bt_period,
                    top_n=bt_top_n,
                    progress_placeholder=progress_compare,
                    bt_end_date=bt_end_date,
                )
                if res:
                    compare_results[s_name] = res
            except Exception:
                continue
        progress_compare.empty()

        if compare_results:
            fig_compare = go.Figure()
            for s_name, s_weights, color in strategy_configs:
                if s_name in compare_results:
                    eq = compare_results[s_name]["equity_series"]
                    fig_compare.add_trace(go.Scatter(
                        x=eq.index, y=eq.values,
                        name=s_name,
                        line=dict(color=color, width=2.5),
                        mode="lines",
                    ))

            first_result = list(compare_results.values())[0]
            if first_result.get("bench_normalized") is not None:
                bn = first_result["bench_normalized"]
                fig_compare.add_trace(go.Scatter(
                    x=bn.index, y=bn.values,
                    name=first_result["benchmark_name"],
                    line=dict(color="#636EFA", width=2, dash="dash"),
                ))

            fig_compare.add_hline(
                y=bt_capital, line_dash="dot", line_color="gray",
                annotation_text=f"Başlangıç: {bt_capital:,.0f}",
            )
            fig_compare.update_layout(
                title="Kümülatif Performans Karşılaştırması",
                xaxis_title="Tarih",
                yaxis_title="Portföy Değeri",
                template="plotly_dark",
                height=550,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_compare, use_container_width=True)

            st.divider()
            st.subheader("Karşılaştırma Tablosu")
            compare_data = []
            for s_name, _, _ in strategy_configs:
                if s_name not in compare_results:
                    continue
                r = compare_results[s_name]
                row = {
                    "Strateji": s_name,
                    "Toplam Getiri (%)": f"{r['total_return']:.2f}",
                    "Yıllık Getiri (%)": f"{r['annual_return']:.2f}",
                    "Sharpe": f"{r['sharpe']:.2f}",
                    "Maks. Düşüş (%)": f"{r['max_drawdown']:.2f}",
                    "Son Sermaye": f"{r['final_equity']:,.0f}",
                }
                if r.get("bench_total_return") is not None:
                    alpha = r["total_return"] - r["bench_total_return"]
                    row["Alfa (%)"] = f"{alpha:.2f}"
                compare_data.append(row)
            if compare_data:
                compare_df = pd.DataFrame(compare_data)
                st.dataframe(compare_df, use_container_width=True, hide_index=True)

            st.session_state["compare_results"] = compare_results
        else:
            st.warning("Hiçbir strateji için yeterli veri bulunamadı.")

    saved_compare = st.session_state.get("compare_results")
    if saved_compare and not bt_compare_btn:
        st.divider()
        st.subheader("Strateji Karşılaştırması (Son Sonuçlar)")
        strategy_colors = {"Alfa Portföyü": "#00CC96", "Beta Portföyü": "#EF553B", "Delta Portföyü": "#AB63FA"}
        fig_saved = go.Figure()
        for s_name, res in saved_compare.items():
            eq = res["equity_series"]
            fig_saved.add_trace(go.Scatter(
                x=eq.index, y=eq.values,
                name=s_name,
                line=dict(color=strategy_colors.get(s_name, "#FFA15A"), width=2.5),
                mode="lines",
            ))
        first_res = list(saved_compare.values())[0]
        if first_res.get("bench_normalized") is not None:
            bn = first_res["bench_normalized"]
            fig_saved.add_trace(go.Scatter(
                x=bn.index, y=bn.values,
                name=first_res["benchmark_name"],
                line=dict(color="#636EFA", width=2, dash="dash"),
            ))
        fig_saved.update_layout(
            title="Kümülatif Performans Karşılaştırması",
            xaxis_title="Tarih", yaxis_title="Portföy Değeri",
            template="plotly_dark", height=550,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_saved, use_container_width=True)

with tab_portfolyo:
    st.subheader("Portföy Yönetimi")
    
    with st.expander("Yeni Portföy Oluştur", expanded=False):
        pf_market = st.selectbox("Piyasa", ["BIST", "US"], key="new_pf_market")
        pf_strategy = st.selectbox("Strateji", ["ALFA", "BETA", "DELTA", "KARMA", "MANUEL"], key="new_pf_strategy")
        pf_period_label = {"Haftalık": "HF", "15 Günlük": "15G", "Aylık": "AY"}.get(bt_period, "AY")
        pool_short = screen_pool_name.replace(" (XUTUM)", "").replace(" (XTUMY)", "").replace(" ", "_").upper()
        auto_name = f"{pool_short}-{pf_strategy}-{pf_period_label}-{datetime.now().strftime('%d.%m.%Y')}"
        pf_name = st.text_input("Portföy Adı", value=auto_name, key="new_pf_name")
        pf_desc = st.text_area("Açıklama (İsteğe bağlı)", key="new_pf_desc", placeholder="Portföy stratejisi hakkında notlar...")
        if st.button("Portföy Oluştur", type="primary", use_container_width=True, key="create_pf_btn"):
            if pf_name.strip():
                db_create_portfolio(pf_name.strip(), pf_desc.strip(), pf_market)
                st.success(f"'{pf_name}' portföyü oluşturuldu!")
                st.rerun()
            else:
                st.warning("Portföy adı boş olamaz.")
    
    st.divider()
    
    all_portfolios = db_get_portfolios()
    
    if not all_portfolios:
        st.info("Henüz portföy oluşturulmadı. Yukarıdaki formu kullanarak ilk portföyünüzü oluşturun, veya 'Hisse Tarama' sekmesinden tarama yapıp sonuçları portföye ekleyin.")
    else:
        for pf in all_portfolios:
            pf_id = pf["id"]
            scan_dt = pf.get("scan_date")
            scan_dt_fmt = str(scan_dt)[:10].replace('-', '.') if scan_dt else None
            header_label = f"📁 {pf['name']} ({pf['market']})"
            if scan_dt_fmt:
                header_label += f"  —  Tarama: {scan_dt_fmt}"
            with st.expander(header_label, expanded=True):
                pf_col1, pf_col2, pf_col3 = st.columns([3, 1, 1])
                with pf_col1:
                    if pf.get("description"):
                        st.caption(pf["description"])
                    if scan_dt_fmt:
                        st.caption(f"📅 Tarama Tarihi: **{scan_dt_fmt}**")
                    else:
                        _cat = pf.get('created_at')
                        if _cat:
                            _cat_fmt = _cat.strftime('%d.%m.%Y') if hasattr(_cat, 'strftime') else str(_cat)[:10].replace('-', '.')
                        else:
                            _cat_fmt = '-'
                        st.caption(f"Oluşturulma: {_cat_fmt}")
                with pf_col2:
                    if st.button("Düzenle", key=f"edit_pf_{pf_id}"):
                        st.session_state[f"editing_pf_{pf_id}"] = True
                with pf_col3:
                    if st.button("Portföyü Sil", key=f"del_pf_{pf_id}", type="secondary"):
                        db_delete_portfolio(pf_id)
                        st.rerun()
                
                if st.session_state.get(f"editing_pf_{pf_id}", False):
                    edit_col1, edit_col2 = st.columns([2, 1])
                    with edit_col1:
                        new_name = st.text_input("Yeni İsim", value=pf["name"], key=f"edit_name_{pf_id}")
                        new_desc = st.text_area("Yeni Açıklama", value=pf.get("description") or "", key=f"edit_desc_{pf_id}")
                    with edit_col2:
                        if st.button("Kaydet", key=f"save_edit_{pf_id}", type="primary", use_container_width=True):
                            if new_name.strip():
                                db_update_portfolio(pf_id, new_name.strip(), new_desc.strip())
                                st.session_state[f"editing_pf_{pf_id}"] = False
                                st.rerun()
                            else:
                                st.warning("İsim boş olamaz.")
                        if st.button("İptal", key=f"cancel_edit_{pf_id}", use_container_width=True):
                            st.session_state[f"editing_pf_{pf_id}"] = False
                            st.rerun()
                
                stocks = db_get_portfolio_stocks(pf_id)
                
                is_bist_pf = pf["market"] == "BIST"
                
                if not stocks:
                    st.info("Bu portföyde henüz hisse yok. 'Hisse Tarama' sekmesinden tarama yapıp sonuçları bu portföye ekleyebilirsiniz.")
                
                if stocks:
                    total_cost = 0
                    total_current_value = 0
                    stock_rows = []

                    all_syms = tuple(s["symbol"] + (".IS" if is_bist_pf else "") for s in stocks)
                    price_map = get_current_prices(all_syms)

                    for s in stocks:
                        sym = s["symbol"]
                        ticker_sym = sym + ".IS" if is_bist_pf else sym
                        shares = float(s["shares"])
                        buy_price = float(s["buy_price"])
                        cost = shares * buy_price
                        total_cost += cost
                        current_price = price_map.get(ticker_sym, buy_price)
                        
                        current_value = shares * current_price
                        total_current_value += current_value
                        pnl = current_value - cost
                        pnl_pct = ((current_price / buy_price) - 1) * 100 if buy_price > 0 else 0
                        
                        stock_rows.append({
                            "id": s["id"],
                            "Sembol": sym,
                            "Adet": int(round(shares)),
                            "Alış Fiyatı": round(buy_price, 2),
                            "Güncel Fiyat": round(current_price, 2),
                            "Maliyet": int(round(cost)),
                            "Güncel Değer": int(round(current_value)),
                            "K/Z": int(round(pnl)),
                            "K/Z (%)": f"%{pnl_pct:.2f}",
                            "Strateji": s.get("strategy", ""),
                            "Skor": float(s.get("score", 0)),
                            "Alış Tarihi": (s["buy_date"].strftime("%d.%m.%Y") if hasattr(s["buy_date"], 'strftime') else str(s["buy_date"])[:10].replace('-', '.')) if s.get("buy_date") else "-",
                        })
                
                    if stock_rows:
                        total_pnl = total_current_value - total_cost
                        total_pnl_pct = ((total_current_value / total_cost) - 1) * 100 if total_cost > 0 else 0
                        
                        met_col1, met_col2, met_col3, met_col4, met_col5 = st.columns(5)
                        with met_col1:
                            st.metric("Toplam Maliyet", f"{int(round(total_cost)):,}")
                        with met_col2:
                            st.metric("Güncel Değer", f"{int(round(total_current_value)):,}")
                        with met_col3:
                            st.metric("K/Z", f"{int(round(total_pnl)):,}")
                        with met_col4:
                            st.metric("K/Z (%)", f"%{total_pnl_pct:.2f}")
                        with met_col5:
                            st.metric("Hisse Sayısı", len(stock_rows))
                        
                        display_df = pd.DataFrame(stock_rows)
                        
                        def pnl_color(val):
                            try:
                                v = float(val)
                                if v > 0:
                                    return "color: #00CC96; font-weight: bold"
                                elif v < 0:
                                    return "color: #EF553B; font-weight: bold"
                                else:
                                    return ""
                            except (ValueError, TypeError):
                                return ""
                        
                        display_cols = ["Sembol", "Adet", "Alış Fiyatı", "Güncel Fiyat", "Maliyet", "Güncel Değer", "K/Z", "K/Z (%)", "Strateji", "Skor", "Alış Tarihi"]
                        styled = display_df[display_cols].style.applymap(
                            pnl_color, subset=["K/Z", "K/Z (%)"]
                        ).format({
                            "Alış Fiyatı": "{:.2f}",
                            "Güncel Fiyat": "{:.2f}",
                            "Skor": "{:.1f}",
                        })
                        st.dataframe(styled, use_container_width=True, hide_index=True)
                        
                        if len(stock_rows) > 1:
                            fig_alloc = go.Figure(data=[go.Pie(
                                labels=[r["Sembol"] for r in stock_rows],
                                values=[r["Güncel Değer"] for r in stock_rows],
                                hole=0.4,
                                textinfo="label+percent",
                            )])
                            fig_alloc.update_layout(
                                title="Portföy Dağılımı",
                                template="plotly_dark",
                                height=350,
                                margin=dict(t=40, b=20, l=20, r=20),
                            )
                            st.plotly_chart(fig_alloc, use_container_width=True)
                            
                            fig_pnl = go.Figure()
                            pnl_colors = ["#00CC96" if r["K/Z"] >= 0 else "#EF553B" for r in stock_rows]
                            pnl_pct_vals = [float(str(r["K/Z (%)"]).replace("%", "")) for r in stock_rows]
                            fig_pnl.add_trace(go.Bar(
                                x=[r["Sembol"] for r in stock_rows],
                                y=pnl_pct_vals,
                                marker_color=pnl_colors,
                                text=[f"%{v:.1f}" for v in pnl_pct_vals],
                                textposition="outside",
                            ))
                            fig_pnl.update_layout(
                                title="Hisse Bazlı Performans (%)",
                                xaxis_title="Hisse", yaxis_title="K/Z (%)",
                                template="plotly_dark", height=350,
                            )
                            st.plotly_chart(fig_pnl, use_container_width=True)
                        
                        st.divider()
                        st.markdown("**Hisse Çıkar**")
                        remove_options = {f"{r['Sembol']} ({r['Alış Tarihi']})": r["id"] for r in stock_rows}
                        selected_remove = st.multiselect(
                            "Çıkarılacak hisseler", list(remove_options.keys()), key=f"remove_stocks_{pf_id}"
                        )
                        if selected_remove and st.button("Seçili Hisseleri Çıkar", key=f"remove_btn_{pf_id}"):
                            for label in selected_remove:
                                db_remove_stock_from_portfolio(remove_options[label])
                            st.success(f"{len(selected_remove)} hisse portföyden çıkarıldı.")
                            st.rerun()
                
                st.divider()
                st.markdown("**Manuel Hisse Ekle**")
                man_col1, man_col2 = st.columns(2)
                with man_col1:
                    man_sym = st.text_input("Sembol", key=f"man_sym_{pf_id}", placeholder="Örn: THYAO")
                with man_col2:
                    man_amount = st.number_input("Yatırım Tutarı", value=10000, min_value=100, step=1000, key=f"man_amount_{pf_id}")
                
                if st.button("Hisse Ekle", key=f"man_add_{pf_id}", use_container_width=True):
                    if man_sym.strip():
                        sym_clean = man_sym.strip().upper()
                        ticker_sym = sym_clean + ".IS" if is_bist_pf else sym_clean
                        man_price = 0.0
                        try:
                            hist = yf.Ticker(ticker_sym).history(period="1d", auto_adjust=False)
                            if hist is not None and not hist.empty:
                                man_price = float(hist["Close"].iloc[-1])
                        except Exception:
                            pass
                        if man_price > 0:
                            calc_shares = round(man_amount / man_price, 4)
                            db_add_stock_to_portfolio(
                                portfolio_id=pf_id,
                                symbol=sym_clean,
                                shares=calc_shares,
                                buy_price=man_price,
                                buy_date=datetime.now().date(),
                            )
                            st.success(f"{sym_clean} portföye eklendi! ({calc_shares} adet @ {man_price:.2f})")
                            st.rerun()
                        else:
                            st.warning("Fiyat bilgisi alınamadı. Lütfen geçerli bir sembol girin.")
                    else:
                        st.warning("Sembol boş olamaz.")

with tab_piyasa:
    st.subheader("Piyasa Durumu & Yatırım Sinyali")
    st.markdown("BIST ve ABD piyasalarının güncel teknik durumunu analiz eder. İşlem öncesi bu ekranı kontrol edin.")

    if st.button("Piyasaları Analiz Et", type="primary", use_container_width=True, key="pa_market_btn"):
        with st.spinner("Veriler indiriliyor..."):
            try:
                _tickers = ["XU100.IS", "SPY", "^VIX", "USDTRY=X", "GC=F", "^TNX"]
                _raw = {}
                for _t in _tickers:
                    try:
                        _df = yf.download(_t, period="1y", auto_adjust=True, progress=False)
                        if isinstance(_df.columns, pd.MultiIndex):
                            _df.columns = _df.columns.get_level_values(0)
                        if not _df.empty:
                            _raw[_t] = _df
                    except Exception:
                        pass
                st.session_state["pa_raw"] = _raw
            except Exception as _e:
                st.error(f"Veri indirilemedi: {_e}")

    _raw = st.session_state.get("pa_raw", {})

    if _raw:
        def _last(sym, col="Close"):
            df = _raw.get(sym)
            if df is None or df.empty: return None
            s = df[col].dropna()
            if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
            return float(s.iloc[-1]) if not s.empty else None

        def _chg(sym, days=22):
            df = _raw.get(sym)
            if df is None or df.empty: return None
            s = df["Close"].dropna()
            if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
            if len(s) < days + 1: return None
            return (float(s.iloc[-1]) / float(s.iloc[-days]) - 1) * 100

        def _sma(sym, n):
            df = _raw.get(sym)
            if df is None or df.empty: return None
            s = df["Close"].dropna()
            if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
            if len(s) < n: return None
            return float(s.rolling(n).mean().iloc[-1])

        # ── Metrikler ──────────────────────────────────────────────────────────
        st.divider()
        st.markdown("### Anlık Piyasa Göstergeleri")
        m1, m2, m3, m4, m5, m6 = st.columns(6)

        xu100 = _last("XU100.IS"); xu_chg = _chg("XU100.IS", 22)
        spy   = _last("SPY");      spy_chg = _chg("SPY", 22)
        vix   = _last("^VIX")
        usdtry= _last("USDTRY=X"); usd_chg = _chg("USDTRY=X", 22)
        gold  = _last("GC=F")
        tnx   = _last("^TNX")

        m1.metric("BIST 100", f"{xu100:,.0f}" if xu100 else "—", f"%{xu_chg:.1f}" if xu_chg else None)
        m2.metric("S&P 500 (SPY)", f"${spy:.1f}" if spy else "—", f"%{spy_chg:.1f}" if spy_chg else None)
        vix_lbl = "Düşük Korku" if vix and vix < 20 else ("Orta Korku" if vix and vix < 30 else "Yüksek Korku")
        m3.metric(f"VIX  ({vix_lbl})", f"{vix:.1f}" if vix else "—")
        m4.metric("USD/TRY", f"{usdtry:.4f}" if usdtry else "—", f"%{usd_chg:.1f}" if usd_chg else None)
        m5.metric("Altın ($/oz)", f"${gold:,.0f}" if gold else "—")
        m6.metric("ABD 10Y Faiz", f"%{tnx:.2f}" if tnx else "—")

        # ── BIST Analizi ───────────────────────────────────────────────────────
        st.divider()
        bist_col, usa_col = st.columns(2)

        with bist_col:
            st.markdown("### 🇹🇷 BIST Durumu")
            xu_sma50  = _sma("XU100.IS", 50)
            xu_sma200 = _sma("XU100.IS", 200)
            xu_chg5   = _chg("XU100.IS", 5)
            xu_chg63  = _chg("XU100.IS", 63)

            bist_signals = []
            bist_score   = 0

            if xu100 and xu_sma200 and xu100 > xu_sma200:
                bist_signals.append(("✅", "Endeks SMA200 üzerinde (uzun vadeli yükseliş trendi)"))
                bist_score += 2
            elif xu100 and xu_sma200:
                bist_signals.append(("🔴", "Endeks SMA200 altında (uzun vadeli düşüş trendi)"))
                bist_score -= 2

            if xu100 and xu_sma50 and xu100 > xu_sma50:
                bist_signals.append(("✅", "Endeks SMA50 üzerinde (kısa vadeli trend pozitif)"))
                bist_score += 1
            elif xu100 and xu_sma50:
                bist_signals.append(("⚠️", "Endeks SMA50 altında (kısa vadeli trend zayıf)"))
                bist_score -= 1

            if xu_chg63 and xu_chg63 > 10:
                bist_signals.append(("✅", f"3 aylık momentum güçlü (%{xu_chg63:.1f})"))
                bist_score += 1
            elif xu_chg63 and xu_chg63 < -10:
                bist_signals.append(("🔴", f"3 aylık momentum zayıf (%{xu_chg63:.1f})"))
                bist_score -= 1

            if usd_chg and usd_chg > 5:
                bist_signals.append(("⚠️", f"TL son 1 ayda %{usd_chg:.1f} değer kaybetti (kur riski)"))
                bist_score -= 1
            elif usd_chg and usd_chg < -2:
                bist_signals.append(("✅", f"TL güçleniyor (%{abs(usd_chg):.1f}) — yurt içi hisseler için olumlu"))
                bist_score += 1

            for icon, msg in bist_signals:
                st.markdown(f"{icon} {msg}")

            if bist_score >= 3:
                bist_verdict = ("🟢", "YATIRIM YAP", "Piyasa güçlü yükseliş trendinde. Pozisyon almak uygun.", "success")
            elif bist_score >= 1:
                bist_verdict = ("🟡", "TEMKİNLİ YATIRıM", "Piyasa karışık sinyaller veriyor. Seçici olun.", "warning")
            elif bist_score == 0:
                bist_verdict = ("🟠", "BEKLE / GÖZLE", "Net bir trend yok. Nakitte kalmak düşünülebilir.", "warning")
            else:
                bist_verdict = ("🔴", "NAKİTTE KAL", "Piyasa baskı altında. İşlem yapmaktan kaçının.", "error")

            icon_v, label_v, desc_v, fn_v = bist_verdict
            getattr(st, fn_v)(f"**{icon_v} BIST KARARI: {label_v}** — {desc_v}")

        # ── ABD Analizi ────────────────────────────────────────────────────────
        with usa_col:
            st.markdown("### 🇺🇸 ABD Piyasası Durumu")
            spy_sma50  = _sma("SPY", 50)
            spy_sma200 = _sma("SPY", 200)
            spy_chg63  = _chg("SPY", 63)

            usa_signals = []
            usa_score   = 0

            if spy and spy_sma200 and spy > spy_sma200:
                usa_signals.append(("✅", "S&P 500 SMA200 üzerinde (uzun vadeli yükseliş trendi)"))
                usa_score += 2
            elif spy and spy_sma200:
                usa_signals.append(("🔴", "S&P 500 SMA200 altında (uzun vadeli düşüş trendi)"))
                usa_score -= 2

            if spy and spy_sma50 and spy > spy_sma50:
                usa_signals.append(("✅", "S&P 500 SMA50 üzerinde (kısa vadeli trend pozitif)"))
                usa_score += 1
            elif spy and spy_sma50:
                usa_signals.append(("⚠️", "S&P 500 SMA50 altında (kısa vadeli trend zayıf)"))
                usa_score -= 1

            if vix:
                if vix < 15:
                    usa_signals.append(("✅", f"VIX {vix:.1f} — Piyasa sakin, korku düşük"))
                    usa_score += 1
                elif vix < 25:
                    usa_signals.append(("🟡", f"VIX {vix:.1f} — Orta düzeyde belirsizlik"))
                elif vix < 35:
                    usa_signals.append(("⚠️", f"VIX {vix:.1f} — Korku yüksek, volatilite artmış"))
                    usa_score -= 1
                else:
                    usa_signals.append(("🔴", f"VIX {vix:.1f} — AŞIRI KORKU! Piyasada panik var"))
                    usa_score -= 2

            if tnx:
                if tnx > 5:
                    usa_signals.append(("⚠️", f"10Y faiz %{tnx:.2f} — Yüksek faiz hisse değerlemelerini baskılıyor"))
                    usa_score -= 1
                elif tnx < 3.5:
                    usa_signals.append(("✅", f"10Y faiz %{tnx:.2f} — Düşük faiz hisseler için destekleyici"))
                    usa_score += 1
                else:
                    usa_signals.append(("🟡", f"10Y faiz %{tnx:.2f} — Nötr bölge"))

            if spy_chg63 and spy_chg63 > 8:
                usa_signals.append(("✅", f"3 aylık momentum güçlü (%{spy_chg63:.1f})"))
                usa_score += 1
            elif spy_chg63 and spy_chg63 < -8:
                usa_signals.append(("🔴", f"3 aylık momentum zayıf (%{spy_chg63:.1f})"))
                usa_score -= 1

            for icon, msg in usa_signals:
                st.markdown(f"{icon} {msg}")

            if usa_score >= 3:
                usa_verdict = ("🟢", "YATIRIM YAP", "ABD piyasası güçlü. Pozisyon almak uygun.", "success")
            elif usa_score >= 1:
                usa_verdict = ("🟡", "TEMKİNLİ YATIRIM", "Karışık sinyaller. Seçici ve savunmacı olun.", "warning")
            elif usa_score == 0:
                usa_verdict = ("🟠", "BEKLE / GÖZLE", "Net trend yok. Nakitte kalmayı değerlendirin.", "warning")
            else:
                usa_verdict = ("🔴", "NAKİTTE KAL", "ABD piyasası baskı altında. İşlem yapmaktan kaçının.", "error")

            icon_v, label_v, desc_v, fn_v = usa_verdict
            getattr(st, fn_v)(f"**{icon_v} ABD KARARI: {label_v}** — {desc_v}")

        # ── Grafik ─────────────────────────────────────────────────────────────
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            df_xu = _raw.get("XU100.IS")
            if df_xu is not None and len(df_xu) > 50:
                cl = df_xu["Close"].dropna()
                if isinstance(cl, pd.DataFrame): cl = cl.iloc[:, 0]
                fig_xu = go.Figure()
                fig_xu.add_trace(go.Scatter(x=cl.index, y=cl.values, name="BIST 100", line=dict(color="#00CC96", width=2)))
                fig_xu.add_trace(go.Scatter(x=cl.index, y=cl.rolling(50).mean().values, name="SMA50", line=dict(color="#FFA15A", width=1.5, dash="dot")))
                fig_xu.add_trace(go.Scatter(x=cl.index, y=cl.rolling(200).mean().values, name="SMA200", line=dict(color="#EF553B", width=1.5, dash="dash")))
                fig_xu.update_layout(title="BIST 100 (1 Yıl)", template="plotly_dark", height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_xu, use_container_width=True)
        with g2:
            df_spy = _raw.get("SPY")
            if df_spy is not None and len(df_spy) > 50:
                cl = df_spy["Close"].dropna()
                if isinstance(cl, pd.DataFrame): cl = cl.iloc[:, 0]
                fig_spy = go.Figure()
                fig_spy.add_trace(go.Scatter(x=cl.index, y=cl.values, name="S&P 500", line=dict(color="#636EFA", width=2)))
                fig_spy.add_trace(go.Scatter(x=cl.index, y=cl.rolling(50).mean().values, name="SMA50", line=dict(color="#FFA15A", width=1.5, dash="dot")))
                fig_spy.add_trace(go.Scatter(x=cl.index, y=cl.rolling(200).mean().values, name="SMA200", line=dict(color="#EF553B", width=1.5, dash="dash")))
                fig_spy.update_layout(title="S&P 500 / SPY (1 Yıl)", template="plotly_dark", height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_spy, use_container_width=True)

        # ── VIX Grafiği ────────────────────────────────────────────────────────
        df_vix = _raw.get("^VIX")
        if df_vix is not None and not df_vix.empty:
            cl_vix = df_vix["Close"].dropna()
            if isinstance(cl_vix, pd.DataFrame): cl_vix = cl_vix.iloc[:, 0]
            fig_vix = go.Figure()
            fig_vix.add_trace(go.Scatter(x=cl_vix.index, y=cl_vix.values, name="VIX",
                fill="tozeroy", line=dict(color="#AB63FA", width=2)))
            for lvl, color, lbl in [(20, "#FFA15A", "Orta Korku"), (30, "#EF553B", "Yüksek Korku")]:
                fig_vix.add_hline(y=lvl, line_dash="dash", line_color=color,
                    annotation_text=lbl, annotation_position="top right")
            fig_vix.update_layout(title="VIX Korku Endeksi (1 Yıl)", template="plotly_dark", height=280,
                xaxis_title="Tarih", yaxis_title="VIX")
            st.plotly_chart(fig_vix, use_container_width=True)

    # ── Rejim Analizi ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Piyasa Rejimi Analizi")
    st.markdown("Benchmark endeksinin teknik göstergelerine göre hangi portföy stratejisinin uygulanması gerektiğini analiz eder.")

    is_bist_pa = market == "BIST (Borsa İstanbul)"
    bench_ticker_pa = "XU100.IS" if is_bist_pa else "SPY"
    bench_name_pa = "BIST 100" if is_bist_pa else "S&P 500"

    pa_analyze_btn = st.button("Güncel Rejimi Analiz Et", type="primary", use_container_width=True, key="pa_analyze")

    if pa_analyze_btn:
        with st.spinner(f"{bench_name_pa} verileri indiriliyor..."):
            bench_data_pa, _ = fetch_data([bench_ticker_pa],
                                          str((datetime.now() - timedelta(days=500)).date()),
                                          str(datetime.now().date()))

        if bench_ticker_pa in bench_data_pa:
            bench_df_pa = bench_data_pa[bench_ticker_pa]
            regime = detect_market_regime(bench_df_pa)
            st.session_state["current_regime"] = regime
            st.session_state["bench_df_pa"] = bench_df_pa
        else:
            st.error("Benchmark verisi alınamadı.")

    saved_regime = st.session_state.get("current_regime")
    if saved_regime:
        regime = saved_regime

        col_regime1, col_regime2 = st.columns([1, 1])

        with col_regime1:
            st.markdown(f"""
            ### Mevcut Rejim
            <div style="background-color: {regime['color']}22; border-left: 5px solid {regime['color']}; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h3 style="margin: 0; color: {regime['color']};">{regime['name']}</h3>
                <p style="margin: 5px 0 0 0;">{regime['desc']}</p>
            </div>
            """, unsafe_allow_html=True)

        with col_regime2:
            st.markdown("### Önerilen Strateji Dağılımı")
            alloc = regime["allocations"]
            alloc_data = []
            colors_map = {"Alfa": "#00CC96", "Beta": "#EF553B", "Delta": "#AB63FA", "Nakit": "#636EFA"}
            for name, pct in alloc.items():
                if pct > 0:
                    alloc_data.append({"Strateji": name, "Ağırlık (%)": pct})

            if alloc_data:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=[d["Strateji"] for d in alloc_data],
                    values=[d["Ağırlık (%)"] for d in alloc_data],
                    marker_colors=[colors_map.get(d["Strateji"], "#999") for d in alloc_data],
                    hole=0.4,
                    textinfo="label+percent",
                )])
                fig_pie.update_layout(
                    height=280,
                    margin=dict(t=20, b=20, l=20, r=20),
                    template="plotly_dark",
                    showlegend=False,
                )
                st.plotly_chart(fig_pie, use_container_width=True)

        # ── Varlık Sınıfı Dağılımı ────────────────────────────────────────────
        st.divider()
        st.markdown("### Önerilen Varlık Sınıfı Dağılımı")
        st.caption("Piyasa rejimine göre portföyünüzü BIST, ABD Borsası, Değerli Metaller ve Nakit olarak nasıl dağıtmalısınız?")

        asset_alloc = regime.get("asset_alloc", {"BIST": 25, "USA": 25, "Metaller": 25, "Nakit": 25})

        ac1, ac2, ac3, ac4 = st.columns(4)
        asset_colors = {"BIST": "#00CC96", "USA": "#636EFA", "Metaller": "#FECB52", "Nakit": "#AB63FA"}
        asset_icons  = {"BIST": "🇹🇷", "USA": "🇺🇸", "Metaller": "🥇", "Nakit": "💵"}
        for col, (name, pct) in zip([ac1, ac2, ac3, ac4], asset_alloc.items()):
            col.metric(f"{asset_icons[name]} {name}", f"%{pct}")

        fig_asset = go.Figure(data=[go.Pie(
            labels=list(asset_alloc.keys()),
            values=list(asset_alloc.values()),
            marker_colors=[asset_colors[k] for k in asset_alloc],
            hole=0.45,
            textinfo="label+percent",
            textfont_size=13,
        )])
        fig_asset.update_layout(
            title=dict(text=f"Varlık Dağılımı — {regime['name']}", x=0.5),
            height=360,
            margin=dict(t=50, b=20, l=20, r=20),
            template="plotly_dark",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_asset, use_container_width=True)

        # Açıklama tablosu
        regime_table = {
            "bull_rally":  ("🟢 Güçlü Yükseliş", "BIST %45", "USA %35", "Metaller %5",  "Nakit %15",  "Risk iştahı yüksek. BIST ve ABD'de ağırlıklı pozisyon alın."),
            "late_bull":   ("🟡 Olgun Yükseliş",  "BIST %35", "USA %30", "Metaller %15", "Nakit %20",  "Trend yavaşlıyor. Seçici kalın, kısmen metale geçin."),
            "sideways":    ("🟠 Yatay Piyasa",    "BIST %25", "USA %20", "Metaller %20", "Nakit %35",  "Net yön yok. Nakit ve metal ağırlığını artırın."),
            "correction":  ("🔴 Düzeltme",        "BIST %10", "USA %10", "Metaller %25", "Nakit %55",  "Piyasa baskı altında. Büyük ölçüde nakite ve metale geçin."),
            "bear":        ("🔴 Ayı Piyasası",    "BIST %0",  "USA %0",  "Metaller %30", "Nakit %70",  "Borsa pozisyonu kapatın. Koruma moduna geçin."),
            "unknown":     ("⚪ Belirsiz",         "BIST %25", "USA %25", "Metaller %25", "Nakit %25",  "Veri yetersiz. Eşit dağılım uygulayın."),
        }
        if regime["regime"] in regime_table:
            r = regime_table[regime["regime"]]
            st.info(f"**{r[0]}** — {r[5]}")

        st.divider()
        st.markdown("### Rejim Karar Ağacı")
        st.markdown("""
| Koşul | Rejim | BIST | USA | Metaller | Nakit |
|-------|-------|------|-----|----------|-------|
| SMA200↑, ADX>25, Momentum↑ | **Güçlü Yükseliş** | %45 | %35 | %5 | %15 |
| SMA200↑, ADX>25, Momentum↓ | **Olgun Yükseliş** | %35 | %30 | %15 | %20 |
| SMA200↑, ADX≤25 | **Yatay Piyasa** | %25 | %20 | %20 | %35 |
| SMA50↑ < Benchmark < SMA200 | **Düzeltme** | %10 | %10 | %25 | %55 |
| Benchmark < SMA50 ve SMA200 | **Ayı Piyasası** | %0 | %0 | %30 | %70 |
        """)

        bench_df_pa = st.session_state.get("bench_df_pa")
        if bench_df_pa is not None and len(bench_df_pa) > 200:
            close_pa = bench_df_pa["Close"]
            sma200_pa = close_pa.rolling(200).mean()
            sma50_pa  = close_pa.rolling(50).mean()

            fig_regime = go.Figure()
            fig_regime.add_trace(go.Scatter(x=close_pa.index, y=close_pa.values,
                name=bench_name_pa, line=dict(color="white", width=2), mode="lines"))
            fig_regime.add_trace(go.Scatter(x=sma200_pa.index, y=sma200_pa.values,
                name="SMA 200", line=dict(color="#EF553B", width=1.5, dash="dash"), mode="lines"))
            fig_regime.add_trace(go.Scatter(x=sma50_pa.index, y=sma50_pa.values,
                name="SMA 50", line=dict(color="#FFA15A", width=1.5, dash="dot"), mode="lines"))
            fig_regime.update_layout(
                title=f"{bench_name_pa} - SMA50 / SMA200 Analizi",
                xaxis_title="Tarih", yaxis_title="Fiyat",
                template="plotly_dark", height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_regime, use_container_width=True)

    st.divider()
    st.subheader("Rejim Bazlı Otomatik Backtest")
    st.markdown("""
    Bu backtest, her yeniden dengeleme periyodunda piyasa rejimini otomatik tespit eder
    ve rejime göre portföy stratejileri arasında geçiş yaparak yatırım yapar.
    """)

    pa_col1, pa_col2 = st.columns(2)
    with pa_col1:
        pa_start_date = st.date_input(
            "Başlangıç Tarihi",
            value=datetime.now() - timedelta(days=365),
            key="pa_start",
        )
        pa_capital = st.number_input("Başlangıç Sermayesi", value=100000, step=10000, min_value=1000, key="pa_cap")
    with pa_col2:
        pa_period = st.selectbox("Yeniden Dengeleme Periyodu", ["15 Günlük", "Aylık"], index=1, key="pa_period")
        pa_top_n  = st.selectbox("Strateji Başına Top N Hisse", [3, 5, 7, 10], index=2, key="pa_topn")

    pa_run_btn = st.button("Rejim Bazlı Backtest Başlat", type="primary", use_container_width=True, key="pa_run")

    if pa_run_btn:
        pa_stock_pool = screen_stock_pool
        pa_start_dt   = datetime.combine(pa_start_date, datetime.min.time())
        progress_pa   = st.empty()
        with st.spinner("Rejim bazlı backtest hesaplanıyor..."):
            pa_result = run_regime_backtest(
                stock_list=list(pa_stock_pool),
                market=market,
                bt_start_date=pa_start_dt,
                initial_capital=pa_capital,
                rebalance_period=pa_period,
                top_n=pa_top_n,
                progress_placeholder=progress_pa,
            )
        progress_pa.empty()

        if pa_result:
            st.session_state["pa_result"] = pa_result
        else:
            st.warning("Yeterli veri bulunamadı.")
    
    saved_pa_result = st.session_state.get("pa_result")
    if saved_pa_result:
        pa_r = saved_pa_result
        
        fig_pa_eq = go.Figure()
        eq = pa_r["equity_series"]
        fig_pa_eq.add_trace(go.Scatter(
            x=eq.index, y=eq.values,
            name="Rejim Bazlı Strateji",
            line=dict(color="#00CC96", width=2.5), mode="lines",
        ))
        
        if pa_r.get("bench_normalized") is not None:
            bn = pa_r["bench_normalized"]
            fig_pa_eq.add_trace(go.Scatter(
                x=bn.index, y=bn.values,
                name=pa_r["benchmark_name"],
                line=dict(color="#636EFA", width=2, dash="dash"), mode="lines",
            ))
        
        fig_pa_eq.add_hline(
            y=pa_r["initial_capital"], line_dash="dot", line_color="gray",
            annotation_text=f"Başlangıç: {pa_r['initial_capital']:,.0f}",
        )
        
        if pa_r.get("regime_log"):
            regime_colors = {
                "Güçlü Yükseliş (Bull Rally)": "rgba(0,204,150,0.1)",
                "Olgun Yükseliş (Late Bull)": "rgba(255,161,90,0.1)",
                "Yatay Piyasa (Sideways)": "rgba(254,203,82,0.1)",
                "Düzeltme (Correction)": "rgba(239,85,59,0.1)",
                "Ayı Piyasası (Bear Market)": "rgba(171,99,250,0.1)",
            }
            for i, rlog in enumerate(pa_r["regime_log"]):
                x0 = pd.Timestamp(rlog["Tarih"])
                if i + 1 < len(pa_r["regime_log"]):
                    x1 = pd.Timestamp(pa_r["regime_log"][i + 1]["Tarih"])
                else:
                    x1 = eq.index[-1]
                fig_pa_eq.add_vrect(
                    x0=x0, x1=x1,
                    fillcolor=regime_colors.get(rlog["Rejim"], "rgba(128,128,128,0.05)"),
                    layer="below", line_width=0,
                )
        
        fig_pa_eq.update_layout(
            title="Rejim Bazlı Strateji - Kümülatif Performans",
            xaxis_title="Tarih", yaxis_title="Portföy Değeri",
            template="plotly_dark", height=550,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_pa_eq, use_container_width=True)
        
        st.divider()
        
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("Toplam Getiri", f"%{pa_r['total_return']:.2f}")
            st.metric("Yıllıklandırılmış Getiri", f"%{pa_r['annual_return']:.2f}")
        with col_s2:
            st.metric("Sharpe Oranı", f"{pa_r['sharpe']:.2f}")
            st.metric("Maks. Düşüş", f"%{pa_r['max_drawdown']:.2f}")
        with col_s3:
            st.metric("Başlangıç Sermayesi", f"{pa_r['initial_capital']:,.0f}")
            st.metric("Son Sermaye", f"{pa_r['final_equity']:,.0f}")
            if pa_r.get("bench_total_return") is not None:
                alpha = pa_r["total_return"] - pa_r["bench_total_return"]
                st.metric("Alfa", f"%{alpha:.2f}")
        
        st.divider()
        st.subheader("Rejim Geçmişi")
        if pa_r.get("regime_log"):
            regime_df = pd.DataFrame(pa_r["regime_log"])
            st.dataframe(regime_df, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("İşlem Geçmişi")
        if pa_r.get("trade_log"):
            trade_df = pd.DataFrame(pa_r["trade_log"])
            st.dataframe(trade_df, use_container_width=True, hide_index=True)
            
            csv_pa = trade_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "İşlem Geçmişini İndir (CSV)",
                csv_pa,
                file_name="rejim_backtest_islemler.csv",
                mime="text/csv",
            )
        else:
            st.info("Bu dönemde işlem gerçekleşmedi.")
