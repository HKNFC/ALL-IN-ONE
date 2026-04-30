"""
stock_db.py — Kalıcı SQLite fiyat veritabanı
Backtest her çalıştığında aynı veriyi okur → deterministik sonuç
"""
import sqlite3
import os
import threading
from datetime import date, timedelta
from typing import List, Optional
import pandas as pd

DB_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "MARK MİNERVİNİ", "data", "stock_prices.db"))

_local = threading.local()   # thread-safe bağlantı havuzu


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    """Tabloları oluştur (ilk çalıştırmada)."""
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker  TEXT NOT NULL,
            date    TEXT NOT NULL,
            open    REAL,
            high    REAL,
            low     REAL,
            close   REAL NOT NULL,
            volume  INTEGER,
            PRIMARY KEY (ticker, date)
        );
        CREATE INDEX IF NOT EXISTS idx_ticker_date ON prices(ticker, date);

        CREATE TABLE IF NOT EXISTS meta (
            ticker      TEXT PRIMARY KEY,
            last_update TEXT,
            row_count   INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'pending'
        );
    """)
    c.commit()


class StockDB:
    """Thread-safe SQLite fiyat veritabanı erişim sınıfı."""

    def __init__(self):
        init_db()

    # ── Okuma ──────────────────────────────────────────────────────────────

    def get_prices(self, ticker: str, start=None, end=None) -> pd.DataFrame:
        """Ticker için OHLCV DataFrame döndür. Boş → veri yok."""
        sql = "SELECT date,open,high,low,close,volume FROM prices WHERE ticker=?"
        params = [ticker]
        if start:
            sql += " AND date>=?"
            params.append(str(start)[:10])
        if end:
            sql += " AND date<=?"
            params.append(str(end)[:10])
        sql += " ORDER BY date"
        try:
            df = pd.read_sql_query(sql, _conn(), params=params, parse_dates=["date"])
            if df.empty:
                return pd.DataFrame()
            df = df.set_index("date")
            df.index = pd.DatetimeIndex(df.index)
            df.columns = ["Open", "High", "Low", "Close", "Volume"]
            return df
        except Exception:
            return pd.DataFrame()

    def has_data(self, ticker: str, min_rows: int = 50) -> bool:
        row = _conn().execute(
            "SELECT row_count, status FROM meta WHERE ticker=?", (ticker,)
        ).fetchone()
        if row is None:
            return False
        row_count, status = row
        return status == "ok" and (row_count or 0) >= min_rows

    def get_all_tickers(self) -> List[str]:
        rows = _conn().execute(
            "SELECT ticker FROM meta WHERE status='ok' ORDER BY ticker"
        ).fetchall()
        return [r[0] for r in rows]

    def get_stale_tickers(self, all_tickers: List[str], days: int = 7) -> List[str]:
        """DB'de olmayan veya `days` günden eski güncellenen hisseleri döndür."""
        cutoff = str(date.today() - timedelta(days=days))
        stale = []
        for t in all_tickers:
            row = _conn().execute(
                "SELECT last_update, status FROM meta WHERE ticker=?", (t,)
            ).fetchone()
            if row is None or row[1] != "ok" or (row[0] or "") < cutoff:
                stale.append(t)
        return stale

    def ticker_count(self) -> int:
        r = _conn().execute("SELECT COUNT(*) FROM meta WHERE status='ok'").fetchone()
        return r[0] if r else 0

    # ── Yazma ──────────────────────────────────────────────────────────────

    def upsert_prices(self, ticker: str, df: pd.DataFrame):
        """DataFrame'i DB'ye yaz; mevcut satırları günceller."""
        if df is None or df.empty:
            return
        # Sütunları düzleştir (MultiIndex gelebilir)
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Yalnızca ihtiyaç duyulan sütunları al, kalanları at
        needed = [col for col in ["Open","High","Low","Close","Volume"] if col in df.columns]
        df = df[needed]
        # Her sütunu tek boyutlu hale getir (Series of scalars, not Series of Series)
        for col in df.columns:
            if hasattr(df[col].iloc[0], '__len__') and not isinstance(df[col].iloc[0], str):
                df[col] = df[col].apply(lambda x: float(x.iloc[0]) if hasattr(x,'iloc') else float(x))
        c = _conn()
        rows = []
        for dt, row in df.iterrows():
            def _scalar(v):
                if hasattr(v, 'iloc'): v = v.iloc[0]
                elif hasattr(v, 'item'): v = v.item()
                return _safe(v)
            try:
                vol_raw = row.get("Volume", 0) if hasattr(row, 'get') else row["Volume"]
                if hasattr(vol_raw, 'iloc'): vol_raw = vol_raw.iloc[0]
                elif hasattr(vol_raw, 'item'): vol_raw = vol_raw.item()
                vol = int(float(vol_raw or 0))
            except Exception:
                vol = 0
            rows.append((
                ticker,
                str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
                _scalar(row.get("Open") if hasattr(row,'get') else row["Open"]) if "Open" in row.index else None,
                _scalar(row.get("High") if hasattr(row,'get') else row["High"]) if "High" in row.index else None,
                _scalar(row.get("Low") if hasattr(row,'get') else row["Low"]) if "Low" in row.index else None,
                _scalar(row.get("Close") if hasattr(row,'get') else row["Close"]) if "Close" in row.index else None,
                vol,
            ))
        c.executemany(
            "INSERT OR REPLACE INTO prices(ticker,date,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
        c.execute(
            "INSERT OR REPLACE INTO meta(ticker,last_update,row_count,status) VALUES(?,?,?,'ok')",
            (ticker, str(date.today()), len(rows)),
        )
        c.commit()

    def mark_bad(self, ticker: str, reason: str = "error"):
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO meta(ticker,last_update,row_count,status) VALUES(?,?,0,?)",
            (ticker, str(date.today()), reason),
        )
        c.commit()

    def close(self):
        if hasattr(_local, "conn") and _local.conn:
            _local.conn.close()
            _local.conn = None


def _safe(val):
    try:
        f = float(val)
        import math
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None


# Singleton
_db_instance: Optional[StockDB] = None
_db_lock = threading.Lock()


def get_db() -> StockDB:
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = StockDB()
    return _db_instance
