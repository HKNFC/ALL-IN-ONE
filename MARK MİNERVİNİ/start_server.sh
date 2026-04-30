#!/bin/zsh
# SEPA Stock Scanner — Kalıcı Sunucu Başlatıcı

APP_DIR="/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sunucu başlatılıyor..." >> /tmp/sepa_server.log 2>&1
    /usr/bin/python3 "$APP_DIR/app.py" >> /tmp/sepa_server.log 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sunucu durdu, 3 saniye sonra yeniden başlıyor..." >> /tmp/sepa_server.log 2>&1
    sleep 3
done
