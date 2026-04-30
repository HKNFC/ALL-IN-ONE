#!/bin/bash
cd "$(dirname "$0")"
echo "ALL-IN-ONE INVESTING PLATFORM baslatiliyor..."

# Virtual environment var mi?
if [ -d "venv" ]; then
    source venv/bin/activate
fi

python app.py
