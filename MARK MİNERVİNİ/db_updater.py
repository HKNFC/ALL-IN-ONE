"""
db_updater.py — BIST + USA hisselerini SQLite DB'ye toplu indir / güncelle

Kullanım:
    python3 db_updater.py            # tüm BIST hisselerini indir
    python3 db_updater.py --update   # sadece eskimiş hisseleri güncelle
    python3 db_updater.py --usa      # USA hisselerini de dahil et
"""
import sys, os, time, argparse
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stock_db import get_db

# ── Hisse listeleri ───────────────────────────────────────────────────────
try:
    from universal_scanner import UniversalStockScanner as _Scanner
    BIST_TICKERS = list(_Scanner._STANDARD_BIST)
    USA_TICKERS  = list(_Scanner._STANDARD_US)
except Exception:
    BIST_TICKERS = []
    USA_TICKERS = []

# Benchmark endeksleri (RS hesabı için kritik)
BENCHMARK_TICKERS = ["XU100.IS", "^GSPC", "SPY", "^IXIC"]

FETCH_START = str(date.today() - timedelta(days=5*365))
FETCH_END   = str(date.today())

MAX_WORKERS  = 5      # paralel thread sayısı — rate limiting dostu
SLEEP_BETWEEN = 0.3   # thread'ler arası bekleme (sn)


def download_one(ticker: str) -> tuple:
    """Tek hisse indir. (ticker, df, hata_mesajı) döndür."""
    try:
        df = yf.download(
            ticker,
            start=FETCH_START,
            end=FETCH_END,
            auto_adjust=True,
            progress=False,
            timeout=15,
        )
        if df.empty:
            return ticker, None, "no_data"
        # Sütunları düzelt (MultiIndex gelirse)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        if len(df) < 10:
            return ticker, None, "too_few_rows"
        return ticker, df, None
    except Exception as e:
        return ticker, None, str(e)[:80]


def run_update(tickers: list, label: str = ""):
    db = get_db()
    total   = len(tickers)
    ok      = 0
    failed  = 0
    no_data = 0

    print(f"\n{'='*60}")
    print(f"📥 {label} — {total} hisse indiriliyor")
    print(f"   Başlangıç: {FETCH_START}  Bitiş: {FETCH_END}")
    print(f"{'='*60}")

    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for t in tickers:
            futures[pool.submit(download_one, t)] = t
            time.sleep(SLEEP_BETWEEN / MAX_WORKERS)

        for fut in as_completed(futures):
            ticker, df, err = fut.result()
            done += 1

            if df is not None:
                db.upsert_prices(ticker, df)
                ok += 1
                status = f"✓ {len(df)} gün"
            elif err == "no_data":
                db.mark_bad(ticker, "no_data")
                no_data += 1
                status = "— veri yok"
            else:
                db.mark_bad(ticker, "error")
                failed += 1
                status = f"✗ {err}"

            # Her 50 hissede özet
            pct = done * 100 // total
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r[{bar}] {pct}%  {done}/{total}  {ticker}: {status}   ", end="", flush=True)

    print(f"\n\n{'='*60}")
    print(f"✅ Tamamlandı: {ok} başarılı  |  {no_data} veri yok  |  {failed} hata")
    print(f"   Toplam DB hisse sayısı: {db.ticker_count()}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="BIST/USA fiyat veritabanı güncelleyici")
    parser.add_argument("--update", action="store_true", help="Sadece eskimiş hisseleri güncelle (7 günden eski)")
    parser.add_argument("--usa",    action="store_true", help="USA hisselerini de dahil et")
    parser.add_argument("--days",   type=int, default=7,  help="Güncelleme eşiği (gün, varsayılan 7)")
    args = parser.parse_args()

    db = get_db()

    # BIST
    if args.update:
        bist_to_update = db.get_stale_tickers(BIST_TICKERS, days=args.days)
        print(f"🔄 Güncelleme modu: {len(bist_to_update)}/{len(BIST_TICKERS)} BIST hissesi eskimiş")
    else:
        bist_to_update = BIST_TICKERS

    if bist_to_update:
        run_update(bist_to_update, "BIST")

    # USA (isteğe bağlı)
    if args.usa and USA_TICKERS:
        if args.update:
            usa_to_update = db.get_stale_tickers(USA_TICKERS, days=args.days)
            print(f"🔄 {len(usa_to_update)}/{len(USA_TICKERS)} USA hissesi eskimiş")
        else:
            usa_to_update = USA_TICKERS

        if usa_to_update:
            run_update(usa_to_update, "USA")

    # Benchmark endekslerini her zaman güncelle (RS hesabı için kritik)
    print("\n📊 Benchmark endeksleri güncelleniyor...")
    run_update(BENCHMARK_TICKERS, "Benchmarks")

    print("🏁 Güncelleme tamamlandı.")


if __name__ == "__main__":
    main()
