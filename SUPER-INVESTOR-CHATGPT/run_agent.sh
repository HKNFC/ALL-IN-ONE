#!/bin/bash
# LaunchAgent wrapper — Launch Agent bu scripti çalıştırır.
# Çalışma dizinini ve venv'i doğru şekilde kurar.

APP_DIR="/Users/hakanficicilar/Documents/Aİ/SUPER-INVESTOR-CHATGPT"
STREAMLIT="$APP_DIR/.venv/bin/streamlit"

cd "$APP_DIR"

# Port 5000 başka bir process tarafından kullanılıyorsa temizle
if lsof -ti :5000 &>/dev/null; then
    lsof -ti :5000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

exec "$STREAMLIT" run app.py \
    --server.address localhost \
    --server.port 5000 \
    --server.headless true \
    --browser.gatherUsageStats false
