#!/bin/bash
cd "$(dirname "$0")"
echo "============================================================"
echo "BIST veritabanı kuruluyor (638 hisse, ~5 yıl veri)..."
echo "Tahmini süre: 15-25 dakika (rate limiting'e göre)"
echo "============================================================"
python3 db_updater.py
echo "============================================================"
echo "Kurulum tamamlandı."
echo "Doğrulama için:"
echo "  python3 -c \"from stock_db import get_db; db=get_db(); print('Hisse sayısı:', db.ticker_count())\""
echo "============================================================"
