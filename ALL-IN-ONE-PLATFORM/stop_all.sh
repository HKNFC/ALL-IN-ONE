#!/bin/bash
echo "Tüm platformlar durduruluyor..."
for port in 5600 5555 8501 8502 8503; do
  lsof -ti:$port | xargs kill -9 2>/dev/null && echo "  Port $port durduruldu"
done
echo "Tamamlandı."
