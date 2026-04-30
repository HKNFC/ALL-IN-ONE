"""
migrate_to_sqlite.py — Tek seferlik migration scripti
Mevcut backtests/*.json ve portfolios/*.csv dosyalarını SQLite'a taşır.
Kullanım: python3 migrate_to_sqlite.py
"""
import os, sys, json, glob
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage

BASE = os.path.dirname(os.path.abspath(__file__))

storage.init_db()

# ── Backtests ────────────────────────────────────────────────────────────────
backtests_dir = os.path.join(BASE, 'backtests')
bt_count = 0
if os.path.isdir(backtests_dir):
    for fpath in sorted(glob.glob(os.path.join(backtests_dir, '*.json'))):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                rec = json.load(f)
            existing = storage.get_backtest(rec['id'])
            if existing:
                print(f"  ↩  Zaten var, atlandı: {rec['name'][:60]}")
                continue
            storage.save_backtest(rec['id'], rec['name'], rec['params'], rec['report'])
            bt_count += 1
            print(f"  ✅ Backtest taşındı: {rec['name'][:60]}")
        except Exception as e:
            print(f"  ❌ Hata ({os.path.basename(fpath)}): {e}")
print(f"\n📦 Toplam {bt_count} backtest SQLite'a taşındı.\n")

# ── Portfolios ───────────────────────────────────────────────────────────────
portfolios_dir = os.path.join(BASE, 'portfolios')
pf_count = 0
if os.path.isdir(portfolios_dir):
    for fpath in sorted(glob.glob(os.path.join(portfolios_dir, '*.csv'))):
        name = os.path.basename(fpath)[:-4]
        try:
            df = pd.read_csv(fpath)
            if df.empty:
                print(f"  ↩  Boş portföy, atlandı: {name}")
                continue
            col_map = {c.lower(): c for c in df.columns}
            for _, row in df.iterrows():
                ticker    = str(row.get(col_map.get('ticker', 'Ticker'), '')).strip().upper()
                market    = str(row.get(col_map.get('market', 'Market'), 'US')).strip()
                maliyet   = float(row.get(col_map.get('maliyet', 'Maliyet'), 0))
                adet      = float(row.get(col_map.get('adet', 'Adet'), 1) or 1)
                alis_t    = str(row.get(col_map.get('alış_tarihi', 'Alış_Tarihi'), '') or '')
                stop      = float(row.get(col_map.get('stop_seviyesi', 'Stop_Seviyesi'), maliyet * 0.93) or maliyet * 0.93)
                if not ticker:
                    continue
                storage.add_position(name, ticker, market, maliyet, adet, alis_t, stop)
                pf_count += 1
            print(f"  ✅ Portföy taşındı: {name} ({len(df)} pozisyon)")
        except Exception as e:
            print(f"  ❌ Hata ({name}): {e}")

print(f"\n💼 Toplam {pf_count} portföy pozisyonu SQLite'a taşındı.")
print("\n✅ Migration tamamlandı. sepa.db hazır.")
print("   Not: backtests/ ve portfolios/ klasörleri hâlâ duruyor, isterseniz silebilirsiniz.")
