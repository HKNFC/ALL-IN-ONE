#!/bin/bash
# ALL-IN-ONE INVESTING PLATFORM — Tam Başlatma Scripti

BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_DIR="/Users/hakanficicilar/Documents/Aİ"
LOG_DIR="$BASEDIR/logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        ALL-IN-ONE INVESTING PLATFORM                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

PYTHON=$(which python3 || which python)
STREAMLIT="$PYTHON -m streamlit"

# Önceki instance'ları temizle
echo "Önceki instance'lar temizleniyor..."
for port in 5600 5555 8501 8503 8505 8506; do
  lsof -ti:$port | xargs kill -9 2>/dev/null
done
sleep 1

# 1. MARK MİNERVİNİ (Flask - port 5555)
echo -e "${YELLOW}▶ Mark Minervini${NC} başlatılıyor (port 5555)..."
cd "$AI_DIR/MARK MİNERVİNİ"
$PYTHON app.py > "$LOG_DIR/minervini.log" 2>&1 &

# 2. GEMINI ZAMANLAMA (Streamlit - port 8501)
echo -e "${YELLOW}▶ Gemini Piyasa Zamanlaması${NC} başlatılıyor (port 8501)..."
cd "$AI_DIR/GEMINI-PIYASA-ZAMANLAMA-MODULU"
$STREAMLIT run app.py \
  --server.port 8501 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false \
  > "$LOG_DIR/gemini.log" 2>&1 &

# 3. PORTFÖY OPTİMİZER (Streamlit - port 8505)
echo -e "${YELLOW}▶ Portföy Optimizer${NC} başlatılıyor (port 8505)..."
cd "$AI_DIR/Portfolio-Optimizer"
$STREAMLIT run app.py \
  --server.port 8505 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false \
  > "$LOG_DIR/borsa.log" 2>&1 &

# 4. SUPER INVESTOR (Streamlit - port 8503)
echo -e "${YELLOW}▶ Super Investor${NC} başlatılıyor (port 8503)..."
cd "$AI_DIR/SUPER-INVESTOR-CHATGPT"
$STREAMLIT run app.py \
  --server.port 8503 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false \
  > "$LOG_DIR/super.log" 2>&1 &

# 5. ENSEMBLE PORTFÖY (Streamlit - port 8506)
echo -e "${YELLOW}▶ Ensemble Portföy${NC} başlatılıyor (port 8506)..."
cd "$AI_DIR/Ensemble-Portfoy"
$STREAMLIT run app.py \
  --server.port 8506 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false \
  > "$LOG_DIR/ensemble.log" 2>&1 &

# 6. PORTAL (Flask - port 5600)
echo -e "${YELLOW}▶ Portal${NC} başlatılıyor (port 5600)..."
cd "$BASEDIR"
$PYTHON app.py > "$LOG_DIR/portal.log" 2>&1 &

echo ""
echo "Uygulamalar başlatılıyor (10 saniye)..."
sleep 10

# Durum kontrolü
check_port() {
  if lsof -ti:$1 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} $2 → http://localhost:$1"
  else
    echo -e "  ${RED}✗${NC} $2 (port $1) — hata için: cat logs/$3.log"
  fi
}

echo "── DURUM ──────────────────────────────────────────────"
check_port 5555 "Mark Minervini         " "minervini"
check_port 8501 "Gemini Zamanlaması     " "gemini"
check_port 8505 "Portföy Optimizer      " "borsa"
check_port 8503 "Super Investor         " "super"
check_port 8506 "Ensemble Portföy       " "ensemble"
check_port 5600 "PORTAL                 " "portal"
echo "───────────────────────────────────────────────────────"
echo ""
echo -e "${GREEN}Portal açılıyor → http://localhost:5600${NC}"
sleep 1
# open "http://localhost:5600"  # otomatik başlatmada tarayıcı açılmaz

trap 'echo ""; echo "Durduruluyor..."; kill $(lsof -ti:5600,5555,8501,8503,8505,8506) 2>/dev/null; exit 0' INT TERM
wait
