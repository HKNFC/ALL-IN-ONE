#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

echo "=== Ekonomik Haber Akisi Baslatiliyor ==="

# Backend
cd "$BACKEND_DIR"

if [ ! -f ".env" ]; then
  echo ""
  echo "UYARI: backend/.env dosyasi bulunamadi!"
  echo "Lutfen asagidaki komutu calistirin ve API anahtarinizi ekleyin:"
  echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > $BACKEND_DIR/.env"
  echo ""
fi

if [ ! -d "venv" ]; then
  echo "Python sanal ortam olusturuluyor..."
  python3 -m venv venv
fi

source venv/bin/activate
echo "Bagimliliklar yukleniyor..."
pip install -r requirements.txt -q

echo "Backend baslatiliyor (port 8000)..."
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# Frontend
cd "$FRONTEND_DIR"
echo "Frontend baslatiliyor (port 5173)..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Platform baslatildi!"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo ""
echo "Durdurmak icin Ctrl+C'ye basin."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Platform durduruldu.'" EXIT INT TERM
wait
