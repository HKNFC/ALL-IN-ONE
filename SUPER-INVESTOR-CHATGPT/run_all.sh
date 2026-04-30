#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT_DIR/.venv" ]; then
    echo "Hata: .venv bulunamadı. Önce 'bash setup.sh' komutunu çalıştırın."
    exit 1
fi

if ! command -v pnpm &> /dev/null; then
    echo "Hata: pnpm bulunamadı. 'npm install -g pnpm' ile yükleyin."
    exit 1
fi

echo "=== Node bağımlılıkları yükleniyor... ==="
cd "$ROOT_DIR" && pnpm install

echo ""
echo "=== Tüm servisler başlatılıyor ==="
echo "  Streamlit  → http://localhost:5000"
echo "  API Server → http://localhost:4000"
echo "  React App  → http://localhost:3000"
echo ""
echo "Durdurmak için Ctrl+C kullanın."
echo ""

# Streamlit
(cd "$ROOT_DIR" && source .venv/bin/activate && streamlit run app.py) &
STREAMLIT_PID=$!

# Node API Server
(cd "$ROOT_DIR/artifacts/api-server" && pnpm dev) &
API_PID=$!

# React Frontend
(cd "$ROOT_DIR/artifacts/stock-screener" && PORT=3000 BASE_PATH=/ pnpm dev)

# Temizlik
kill $STREAMLIT_PID $API_PID 2>/dev/null || true
