#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_mac.sh  —  macOS .app üretir
# Kullanım: bash build_mac.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_NAME="SEPA Stock Scanner"
DIST_DIR="dist"

echo "════════════════════════════════════════════"
echo " SEPA Stock Scanner — macOS Build"
echo "════════════════════════════════════════════"

# Bağımlılıkları kur
echo "📦 Bağımlılıklar kuruluyor..."
pip install pywebview pyinstaller --quiet

# Eski build temizle
rm -rf build "$DIST_DIR/$APP_NAME.app" "$DIST_DIR/$APP_NAME"

# Build
echo "🔨 Build başlatılıyor..."
pyinstaller sepa_scanner.spec --noconfirm

echo ""
echo "✅ Build tamamlandı!"
echo "📁 Çıktı: $DIST_DIR/$APP_NAME.app"
echo ""
echo "Uygulamayı açmak için:"
echo "  open \"$DIST_DIR/$APP_NAME.app\""
