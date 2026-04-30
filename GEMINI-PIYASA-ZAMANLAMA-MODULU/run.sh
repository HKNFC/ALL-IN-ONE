#!/bin/bash
# Piyasa Zamanlaması Dashboard - Yerel Başlatma Scripti
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# .env dosyası varsa yükle
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Sanal ortam kontrolü
if [ ! -d ".venv" ]; then
    echo "Sanal ortam bulunamadı. Oluşturuluyor..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Bağımlılıkları yükle
pip install -q -r requirements.txt

echo ""
echo "=================================================="
echo "  Piyasa Zamanlaması Dashboard Başlatılıyor..."
echo "  Adres: http://localhost:8501"
echo "=================================================="
echo ""

streamlit run app.py
