"""
BIST Fundamental Snapshot Sistemi
==================================

Look-ahead bias sorunu:
  FMP, BIST hisseleri için TARIHSEL bilanço verisi sağlamıyor.
  Yani geçmişe dönük backtest'te "bugünkü" temel veriler kullanılıyor —
  bu da gerçek hayatta o tarihte bilinemeyen bilgileri kullanmak demek.

Bu modülün çözümü:
  - Her gün çalıştırıldığında güncel BIST temel verilerini SQLite'a kaydeder.
  - Gelecekteki bir backtest "01.06.2026 tarihinde hangi temel veriler mevcuttu?"
    diye sorduğunda, snapshot'tan gerçek tarihli veriyi döner.
  - Türkiye raporlama takvimi (Q4→Mart, Q1→Mayıs, Q2→Ağustos, Q3→Kasım)
    da ek bir "bildirilmemiş veri güvencesi" sağlar.

Kullanım:
  # Günlük snapshot kaydet (LaunchAgent/cron ile çağrılabilir):
  python3 bist_snapshot.py --save

  # Belirli tarihe ait en son snapshot'ı al:
  from bist_snapshot import get_snapshot_at_date
  df = get_snapshot_at_date("2026-03-15")
"""

import argparse
import logging
import os
import sqlite3
import json
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bist_snapshots.db")

# ---------------------------------------------------------------------------
# Raporlama Takvimi Güvencesi
# ---------------------------------------------------------------------------
# BIST'te her çeyrek bilançosu bu takvimde yayınlanır:
#   Q4 (yıl sonu) → Mart ayı sonu
#   Q1             → Mayıs ortası
#   Q2 (yarıyıl)   → Ağustos sonu
#   Q3             → Kasım ortası
#
# Bu fonksiyon bir tarih için "o tarihte açıklanmış en son çeyrek" 
# dönemini döner.

def get_last_reported_quarter(as_of: date) -> tuple:
    """
    Verilen tarih itibarıyla açıklanmış en son çeyreği döner.
    Returns: (year, quarter) örn. (2024, 3)
    """
    yr = as_of.year
    mo = as_of.month

    # Q4 önceki yılın → Mart sonu açıklanır
    if mo < 4:   # Ocak, Şubat, Mart: önceki yılın Q3 açık
        return (yr - 1, 3)
    elif mo < 6:  # Nisan, Mayıs: önceki yılın Q4 açık
        return (yr - 1, 4)
    elif mo < 9:  # Haziran, Temmuz, Ağustos: Q1 açık
        return (yr, 1)
    elif mo < 12:  # Eylül, Ekim, Kasım: Q2 açık
        return (yr, 2)
    else:          # Aralık: Q3 açık
        return (yr, 3)


# ---------------------------------------------------------------------------
# SQLite Veritabanı
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bist_snapshots (
            snapshot_date TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            data_json     TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            PRIMARY KEY (snapshot_date, ticker)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshot_date
        ON bist_snapshots(snapshot_date)
    """)
    conn.commit()


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    _init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Snapshot Kaydet
# ---------------------------------------------------------------------------

def save_snapshot(df: pd.DataFrame, snapshot_date: Optional[str] = None):
    """
    DataFrame'i snapshot olarak SQLite'a kaydeder.
    snapshot_date: 'YYYY-MM-DD' formatı. Boşsa bugün kullanılır.
    """
    if df.empty:
        logger.warning("Boş DataFrame, snapshot kaydedilmedi")
        return 0

    sdate = snapshot_date or date.today().isoformat()
    now_str = datetime.now().isoformat()

    conn = _get_conn()
    saved = 0
    try:
        for _, row in df.iterrows():
            ticker = row.get("ticker")
            if not ticker:
                continue
            row_dict = {k: (None if pd.isna(v) else v)
                        for k, v in row.items()
                        if k not in ("price_data",)}
            conn.execute("""
                INSERT OR REPLACE INTO bist_snapshots
                (snapshot_date, ticker, data_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (sdate, str(ticker), json.dumps(row_dict), now_str))
            saved += 1
        conn.commit()
        logger.info("BIST snapshot kaydedildi: %s — %d hisse", sdate, saved)
    finally:
        conn.close()
    return saved


# ---------------------------------------------------------------------------
# Snapshot Oku
# ---------------------------------------------------------------------------

def get_snapshot_at_date(as_of: str) -> pd.DataFrame:
    """
    Verilen tarihe ait en son BIST snapshot'ını döner.

    as_of: 'YYYY-MM-DD' formatı
    Returns: DataFrame (boş DataFrame eğer snapshot yok)
    """
    try:
        conn = _get_conn()
        # O tarihten önceki (veya o tarihteki) en son snapshot tarihini bul
        cursor = conn.execute("""
            SELECT MAX(snapshot_date) FROM bist_snapshots
            WHERE snapshot_date <= ?
        """, (as_of,))
        row = cursor.fetchone()
        if not row or not row[0]:
            logger.debug("BIST snapshot yok (<= %s)", as_of)
            conn.close()
            return pd.DataFrame()

        best_date = row[0]
        cursor2 = conn.execute("""
            SELECT ticker, data_json FROM bist_snapshots
            WHERE snapshot_date = ?
        """, (best_date,))
        rows = cursor2.fetchall()
        conn.close()

        if not rows:
            return pd.DataFrame()

        records = []
        for ticker, data_json in rows:
            try:
                d = json.loads(data_json)
                d["ticker"] = ticker
                records.append(d)
            except Exception:
                pass

        df = pd.DataFrame(records)
        logger.debug("BIST snapshot yüklendi: %s (%d hisse) ← %s isteği için",
                     best_date, len(df), as_of)
        return df

    except Exception as e:
        logger.warning("BIST snapshot okunamadı: %s", e)
        return pd.DataFrame()


def list_snapshots() -> list:
    """Mevcut snapshot tarihlerini listeler."""
    try:
        conn = _get_conn()
        cursor = conn.execute("""
            SELECT snapshot_date, COUNT(*) as cnt
            FROM bist_snapshots
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            LIMIT 30
        """)
        rows = cursor.fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception:
        return []


def snapshot_count() -> int:
    """Toplam unique snapshot tarihi sayısı."""
    return len(list_snapshots())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_save():
    """Güncel BIST verilerini çekip snapshot kaydeder."""
    from data_fetcher import fetch_market_data
    print("BIST verileri çekiliyor...")
    df, _ = fetch_market_data("BIST", skip_momentum=False, skip_fundamentals=False)
    if df.empty:
        print("HATA: BIST verileri alınamadı")
        return
    saved = save_snapshot(df)
    print(f"Snapshot kaydedildi: {date.today().isoformat()} — {saved} hisse")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="BIST Fundamental Snapshot Aracı")
    parser.add_argument("--save", action="store_true", help="Günlük snapshot kaydet")
    parser.add_argument("--list", action="store_true", help="Mevcut snapshotları listele")
    parser.add_argument("--get", type=str, metavar="YYYY-MM-DD",
                        help="Belirli tarihe ait snapshot göster")
    args = parser.parse_args()

    if args.save:
        _cli_save()
    elif args.list:
        snaps = list_snapshots()
        if snaps:
            print(f"{'Tarih':<12} {'Hisse Sayısı':>12}")
            print("-" * 26)
            for d, cnt in snaps:
                print(f"{d:<12} {cnt:>12}")
        else:
            print("Henüz snapshot yok. --save ile başlatın.")
    elif args.get:
        df = get_snapshot_at_date(args.get)
        if df.empty:
            print(f"'{args.get}' için snapshot bulunamadı")
        else:
            print(f"{len(df)} hisse bulundu")
            print(df[["ticker", "rs_score", "revenue_growth", "pe"]].to_string())
    else:
        parser.print_help()
