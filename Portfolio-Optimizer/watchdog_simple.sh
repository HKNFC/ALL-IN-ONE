#!/bin/bash
# Watchdog: 5556 portunu izler, çökmüşse yeniden başlatır
LOG="/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/logs/watchdog.log"

while true; do
    if ! lsof -ti:5556 > /dev/null 2>&1; then
        echo "$(date): 5556 kapalı, yeniden başlatılıyor..." >> "$LOG"
        cd /Users/hakanficicilar/borsa_app
        nohup /usr/bin/python3 -m streamlit run app.py --server.port 5556 --server.headless true >> "$LOG" 2>&1 &
        sleep 15
    fi
    sleep 30
done
