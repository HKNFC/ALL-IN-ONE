#!/bin/bash
# ============================================================
# STABLE ALL-IN-ONE — Başlatma Scripti
# Portlar: 5700 (portal), 8601 (Gemini), 5655 (Minervini),
#          8605 (Optimizer), 8603 (Super Investor)
# ============================================================

STABLE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "  STABLE ALL-IN-ONE başlatılıyor..."
echo "  Klasör: $STABLE_DIR"
echo "========================================"

# Önceki stabil süreçleri durdur
pkill -f "5655\|5700\|8601\|8603\|8605" 2>/dev/null
sleep 1

# Piyasa Zamanlaması — port 8601
echo "▶ Piyasa Zamanlaması (8601)..."
cd "$STABLE_DIR/GEMINI-PIYASA-ZAMANLAMA-MODULU"
nohup python3 -m streamlit run app.py --server.port 8601 --server.headless true > /tmp/stable_gemini.log 2>&1 &

# Mark Minervini — port 5655
echo "▶ Mark Minervini (5655)..."
cd "$STABLE_DIR/MARK MİNERVİNİ"
PORT=5655 nohup python3 app.py > /tmp/stable_minervini.log 2>&1 &

# Portföy Optimizer — port 8605
echo "▶ Portföy Optimizer (8605)..."
cd "$STABLE_DIR/Portfolio-Optimizer"
nohup python3 -m streamlit run app.py --server.port 8605 --server.headless true > /tmp/stable_optimizer.log 2>&1 &

# Super Investor — port 8603
echo "▶ Super Investor (8603)..."
cd "$STABLE_DIR/SUPER-INVESTOR-CHATGPT"
nohup python3 -m streamlit run app.py --server.port 8603 --server.headless true > /tmp/stable_super.log 2>&1 &





sleep 4

# QuantumScan (EMERGENT) — paylaşımlı, zaten çalışıyorsa atla
echo "▶ QuantumScan — port durumu kontrol (5175/8090)..."
if ! lsof -i :5175 -sTCP:LISTEN -t > /dev/null 2>&1; then
  echo "  QuantumScan backend (8090) başlatılıyor..."
  cd "$STABLE_DIR/../../../EMERGENT/backend" 2>/dev/null || cd "/Users/hakanficicilar/Documents/Aİ/EMERGENT/backend"
  nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 8090 > /tmp/qs_backend.log 2>&1 &
  sleep 2
  echo "  QuantumScan frontend (5175) başlatılıyor..."
  cd "$STABLE_DIR/../../../EMERGENT/frontend" 2>/dev/null || cd "/Users/hakanficicilar/Documents/Aİ/EMERGENT/frontend"
  nohup npx serve -s build -l 5175 > /tmp/qs_frontend.log 2>&1 &
else
  echo "  QuantumScan zaten çalışıyor (5175)"
fi

# Portal — port 5700
echo "▶ Portal (5700)..."
cd "$STABLE_DIR/ALL-IN-ONE-PLATFORM"
nohup python3 app.py > /tmp/stable_portal.log 2>&1 &

sleep 3
echo ""
echo "========================================"
echo "  STABLE ALL-IN-ONE HAZIR"
echo "  http://localhost:5700"
echo "========================================"
