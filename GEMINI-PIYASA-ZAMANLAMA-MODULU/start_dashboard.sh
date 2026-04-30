#!/bin/bash
# Replit ortamına özgü sabit yol yerine scriptin bulunduğu dizini kullan
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while true; do
    streamlit run "$SCRIPT_DIR/app.py" --server.port 8501 --server.address localhost
    echo "Streamlit exited with code $?. Restarting in 2 seconds..."
    sleep 2
done
