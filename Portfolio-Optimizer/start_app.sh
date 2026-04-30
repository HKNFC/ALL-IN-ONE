#!/bin/bash
export HOME="/Users/hakanficicilar"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer"
exec /usr/bin/python3 -m streamlit run app.py \
    --server.port 5556 \
    --server.headless true \
    --server.runOnSave false \
    2>&1
