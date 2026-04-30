#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Borsa Portföy Seçici — macOS Build ==="

# Eski build temizle
rm -rf build dist

# İkon oluştur
python3 create_icon.py 2>/dev/null || true

# PyInstaller build
python3 -m PyInstaller BorsaPortfoySecici.spec --noconfirm --clean

# Quarantine bit'ini kaldır
xattr -cr dist/BorsaPortfoySecici.app 2>/dev/null || true

echo ""
echo "✓ Build tamamlandı: dist/BorsaPortfoySecici.app"
echo ""
echo "Kurulum için:"
echo "  cp -r dist/BorsaPortfoySecici.app /Applications/"
