"""
storage.py — SQLite kalıcı depolama katmanı
Backtests, portfolios ve signals için tek merkezi CRUD modülü.
DB_PATH env variable'dan okunur; yoksa ./sepa.db kullanılır.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sepa.db'))


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Tablolar yoksa oluştur. Uygulama başlarken bir kez çağrılır."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS backtests (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                params_json TEXT NOT NULL,
                report_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portfolio_positions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio     TEXT NOT NULL,
                ticker        TEXT NOT NULL,
                market        TEXT NOT NULL DEFAULT 'US',
                maliyet       REAL NOT NULL,
                adet          REAL NOT NULL DEFAULT 0,
                alis_tarihi   TEXT,
                stop_seviyesi REAL,
                backstop      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS signals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                data_json  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS top_picks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                market    TEXT NOT NULL,
                ticker    TEXT NOT NULL,
                status    TEXT,
                rs        REAL,
                price     REAL,
                rank      INTEGER,
                saved_at  TEXT NOT NULL,
                engine    TEXT DEFAULT 'classic',
                UNIQUE(scan_date, market, ticker, engine)
            );
        """)


# ── Backtests ────────────────────────────────────────────────────────────────

def save_backtest(bt_id, name, params, report):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO backtests (id, name, created_at, params_json, report_json) VALUES (?,?,?,?,?)",
            (bt_id, name, datetime.now().strftime('%Y-%m-%d %H:%M'),
             json.dumps(params, ensure_ascii=False),
             json.dumps(report, ensure_ascii=False))
        )


def list_backtests():
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, created_at, params_json, report_json FROM backtests ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        params = json.loads(r['params_json'])
        report = json.loads(r['report_json'])
        result.append({
            'id':         r['id'],
            'name':       r['name'],
            'created_at': r['created_at'],
            'params':     params,
            'summary':    report.get('summary', {}),
        })
    return result


def get_backtest(bt_id):
    with _conn() as c:
        row = c.execute(
            "SELECT id, name, created_at, params_json, report_json FROM backtests WHERE id=?",
            (bt_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'id':         row['id'],
        'name':       row['name'],
        'created_at': row['created_at'],
        'params':     json.loads(row['params_json']),
        'report':     json.loads(row['report_json']),
    }


def delete_backtest(bt_id):
    with _conn() as c:
        c.execute("DELETE FROM backtests WHERE id=?", (bt_id,))


def find_duplicate_backtest(params_key):
    """params_key eşleşen kayıtlı backtest id'sini döndürür, yoksa None."""
    with _conn() as c:
        rows = c.execute("SELECT id, params_json FROM backtests").fetchall()
    for r in rows:
        p = json.loads(r['params_json'])
        k = f"{p.get('market')}_{p.get('method')}_{p.get('frequency')}_{p.get('start_date')}_{p.get('end_date')}_{p.get('initial_capital', 100000)}"
        if k == params_key:
            return r['id']
    return None


# ── Portfolios ───────────────────────────────────────────────────────────────

def list_portfolios():
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT portfolio FROM portfolio_positions ORDER BY portfolio"
        ).fetchall()
    return [r['portfolio'] for r in rows]


def portfolio_exists(name):
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM portfolio_positions WHERE portfolio=? LIMIT 1", (name,)
        ).fetchone()
    return row is not None


def create_portfolio(name):
    """Boş portföy oluşturmak için bir yer tutucu satır eklenmez;
    ilk pozisyon eklendiğinde otomatik oluşur. Bu fonksiyon sadece
    var olup olmadığını kontrol etmek için kullanılır."""
    pass


def get_portfolio(name):
    """Portföydeki tüm pozisyonları liste olarak döndürür."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM portfolio_positions WHERE portfolio=? ORDER BY id",
            (name,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_position(name, ticker, market, maliyet, adet, alis_tarihi, stop_seviyesi):
    with _conn() as c:
        c.execute(
            """INSERT INTO portfolio_positions
               (portfolio, ticker, market, maliyet, adet, alis_tarihi, stop_seviyesi, backstop)
               VALUES (?,?,?,?,?,?,?,0)""",
            (name, ticker.upper(), market, maliyet, adet, alis_tarihi, stop_seviyesi)
        )


def delete_position(name, ticker):
    with _conn() as c:
        c.execute(
            "DELETE FROM portfolio_positions WHERE portfolio=? AND ticker=?",
            (name, ticker.upper())
        )


def delete_portfolio(name):
    with _conn() as c:
        c.execute("DELETE FROM portfolio_positions WHERE portfolio=?", (name,))


def rename_portfolio(old_name, new_name):
    with _conn() as c:
        c.execute(
            "UPDATE portfolio_positions SET portfolio=? WHERE portfolio=?",
            (new_name, old_name)
        )


# ── Signals ──────────────────────────────────────────────────────────────────

def save_signal(data):
    with _conn() as c:
        c.execute(
            "INSERT INTO signals (created_at, data_json) VALUES (?,?)",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), json.dumps(data, ensure_ascii=False))
        )


def list_signals(limit=200):
    with _conn() as c:
        rows = c.execute(
            "SELECT created_at, data_json FROM signals ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [json.loads(r['data_json']) for r in rows]


# ── Top Picks ─────────────────────────────────────────────────────────────────

def save_top_picks(scan_date, market, picks, engine='classic'):
    """En iyi 5 hisseyi kaydet. Aynı scan_date+market+ticker+engine varsa güncelle."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    with _conn() as c:
        for p in picks:
            c.execute("""
                INSERT INTO top_picks (scan_date, market, ticker, status, rs, price, rank, saved_at, engine)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scan_date, market, ticker, engine)
                DO UPDATE SET status=excluded.status, rs=excluded.rs,
                              price=excluded.price, rank=excluded.rank, saved_at=excluded.saved_at
            """, (scan_date, market, p.get('ticker',''), p.get('status'),
                  p.get('rs'), p.get('price'), p.get('rank'), now, engine))


def list_top_picks():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM top_picks ORDER BY saved_at DESC, rank ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_top_pick(pick_id):
    with _conn() as c:
        c.execute("DELETE FROM top_picks WHERE id=?", (pick_id,))


def delete_top_picks_session(scan_date, market, engine='classic'):
    """Belirli bir tarama oturumuna ait tüm hisseleri sil."""
    with _conn() as c:
        c.execute("DELETE FROM top_picks WHERE scan_date=? AND market=? AND engine=?", (scan_date, market, engine))
