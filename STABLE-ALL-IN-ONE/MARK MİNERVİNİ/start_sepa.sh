#!/bin/bash
# SEPA Stock Scanner — Mac otomatik başlatma scripti
# Login Items'a SEPA Starter.app eklenerek çalıştırılır

APP_DIR="/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"
LOG="/tmp/sepa_server.log"
PID_FILE="/tmp/sepa_server.pid"

# Zaten çalışıyorsa durdur
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    kill "$OLD_PID" 2>/dev/null
    sleep 1
fi

# Port temizle
lsof -ti:5555 | xargs kill -9 2>/dev/null
sleep 1

cd "$APP_DIR"

# Migration: ilk çalıştırmada mevcut verileri SQLite'a taşı
if [ ! -f "$APP_DIR/sepa.db" ] && [ -d "$APP_DIR/backtests" ]; then
    python3 "$APP_DIR/migrate_to_sqlite.py" >> "$LOG" 2>&1
fi

# Sunucuyu başlat
python3 "$APP_DIR/app.py" >> "$LOG" 2>&1 &
echo $! > "$PID_FILE"

echo "SEPA Stock Scanner başlatıldı. PID: $(cat $PID_FILE)" >> "$LOG"
