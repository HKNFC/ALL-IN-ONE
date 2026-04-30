#!/bin/bash
set -e

if [ ! -d ".venv" ]; then
    echo "Hata: .venv bulunamadı. Önce 'bash setup.sh' komutunu çalıştırın."
    exit 1
fi

# Port 5000 başka bir process tarafından kullanılıyorsa temizle
if lsof -ti :5000 &>/dev/null; then
    echo "Port 5000 temizleniyor..."
    lsof -ti :5000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

source .venv/bin/activate
echo "Streamlit başlatılıyor → http://localhost:5000"
streamlit run app.py
