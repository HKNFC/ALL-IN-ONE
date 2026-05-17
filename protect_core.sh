#!/bin/bash
# Kullanım: ./protect_core.sh "değişiklik açıklaması"
# Kritik tarama/backtest dosyalarını backup + git commit eder

BASE="/Users/hakanficicilar/Documents/Aİ"
BACKUP="$BASE/_backups/$(date '+%Y%m%d_%H%M%S')"
MSG="${1:-manual checkpoint $(date '+%Y-%m-%d %H:%M')}"

CRITICAL=(
  "MARK MİNERVİNİ/app.py"
  "MARK MİNERVİNİ/backtest_engine.py"
  "MARK MİNERVİNİ/universal_scanner.py"
  "SUPER-INVESTOR-CHATGPT/app.py"
  "SUPER-INVESTOR-CHATGPT/backtest_engine.py"
  "Portfolio-Optimizer/app.py"
  "Ensemble-Portfoy/app.py"
)

echo "📦 Backup alınıyor: $BACKUP"
mkdir -p "$BACKUP"
for f in "${CRITICAL[@]}"; do
  dir=$(dirname "$BACKUP/$f")
  mkdir -p "$dir"
  cp "$BASE/$f" "$BACKUP/$f" 2>/dev/null && echo "  ✓ $f" || echo "  ✗ $f (bulunamadı)"
done

echo ""
echo "💾 Git commit: $MSG"
cd "$BASE"
for f in "${CRITICAL[@]}"; do
  git add "$f" 2>/dev/null
done
git commit -m "checkpoint: $MSG" 2>&1 | head -3

echo ""
echo "✅ Tamamlandı. Geri yüklemek için:"
echo "   cp -r \"$BACKUP/MARK MİNERVİNİ/app.py\" \"$BASE/MARK MİNERVİNİ/app.py\""
