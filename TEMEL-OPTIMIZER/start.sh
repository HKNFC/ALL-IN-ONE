#!/bin/bash
# TEMEL OPTİMİZER Başlatma Script'i
# Port: 8506

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/logs/temel_optimizer.log"
mkdir -p "$DIR/logs"

echo "[$(date)] TEMEL OPTİMİZER başlatılıyor... (port 8506)" | tee -a "$LOG"

cd "$DIR"

# Gerekli bağımlılıkları kontrol et
python3 -c "import streamlit, requests, pandas, numpy, ta, plotly" 2>/dev/null || {
    echo "Eksik bağımlılıklar kuruluyor..."
    pip3 install streamlit requests pandas numpy ta plotly python-dotenv openpyxl -q
}

# Başlat
exec streamlit run app.py \
    --server.port 8506 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    >> "$LOG" 2>&1
