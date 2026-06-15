#!/bin/bash
set -e

echo "=== Super Investor - Kurulum ==="

# Python venv oluştur
python3 -m venv .venv
source .venv/bin/activate

# Python bağımlılıklarını yükle
pip install --upgrade pip
pip install -r requirements.txt

# .env dosyasını oluştur (varsa dokunma)
if [ ! -f ".env" ]; then
    cp env.example .env
    echo ".env dosyası oluşturuldu. Lütfen TWELVE_DATA_API_KEY değerini girin."
else
    echo ".env dosyası zaten mevcut, atlandı."
fi

echo ""
echo "=== Kurulum tamamlandı! ==="
echo "Streamlit uygulamasını başlatmak için:"
echo "  bash run_app.sh"
echo ""
echo "Tüm servisleri başlatmak için:"
echo "  bash run_all.sh"
