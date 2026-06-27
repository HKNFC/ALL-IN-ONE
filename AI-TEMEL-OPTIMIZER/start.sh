#!/bin/bash
cd "$(dirname "$0")"
echo "======================================"
echo "🤖 AI TEMEL OPTİMİZER — Port 8507"
echo "======================================"
streamlit run app.py \
  --server.port 8507 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --theme.base dark \
  --theme.primaryColor "#8b5cf6"
