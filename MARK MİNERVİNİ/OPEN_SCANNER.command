#!/bin/bash

echo "🚀 Minervini Advanced Scanner Başlatılıyor..."

cd "$(dirname "$0")"

# Server çalışıyor mu?
if lsof -ti:8888 > /dev/null 2>&1; then
    echo "✅ Server zaten çalışıyor!"
else
    echo "🔄 Server başlatılıyor..."
    python3 app.py > server.log 2>&1 &
    sleep 3
fi

# Tarayıcıyı aç
echo "🌐 Tarayıcı açılıyor..."
open "http://localhost:8888/scanner"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ Advanced Scanner Hazır!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📍 URL: http://localhost:8888/scanner"
echo ""
echo "Eğer sayfa açılmadıysa, bu URL'yi tarayıcınıza yapıştırın:"
echo "👉 http://localhost:8888/scanner"
echo ""
echo "════════════════════════════════════════════════════════════"
