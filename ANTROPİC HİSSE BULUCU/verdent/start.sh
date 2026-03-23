#!/bin/zsh

BASE="/Users/hakanficicilar/Documents/Aİ/ANTROPİC HİSSE BULUCU/verdent"

echo "🚀 VERDENT başlatılıyor..."

# Backend
osascript -e "tell application \"Terminal\"
  do script \"cd '$BASE/backend' && npm run dev\"
end tell"

# Frontend
osascript -e "tell application \"Terminal\"
  do script \"cd '$BASE/frontend' && npm run dev\"
end tell"

echo "✅ Backend: http://localhost:3001"
echo "✅ Frontend: http://localhost:3000"
echo ""
echo "Tarayıcıda aç: http://localhost:3000"
open "http://localhost:3000"
