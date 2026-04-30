#!/bin/bash
# Bu scripti bir kez çalıştır: bash ~/Documents/Aİ/Portfolio-Optimizer/setup_autostart.sh

LOG_DIR="/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/logs"
mkdir -p "$LOG_DIR"

# Mevcut crontab'ı al (varsa)
crontab -l 2>/dev/null | grep -v "borsa_app\|Portfolio-Optimizer" > /tmp/_cron_tmp.txt

# @reboot satırı ekle
echo "@reboot sleep 30 && cd /Users/hakanficicilar/borsa_app && /usr/bin/python3 -m streamlit run app.py --server.port 5556 --server.headless true >> /Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/logs/cron_app.log 2>&1" >> /tmp/_cron_tmp.txt

# Crontab'ı güncelle
crontab /tmp/_cron_tmp.txt
rm /tmp/_cron_tmp.txt

echo "✅ @reboot cron job kuruldu."
echo ""

# Şimdi de hemen başlat
echo "Uygulama başlatılıyor..."
lsof -ti:5556 | xargs kill -9 2>/dev/null
sleep 1
cd /Users/hakanficicilar/borsa_app
nohup /usr/bin/python3 -m streamlit run app.py --server.port 5556 --server.headless true >> "$LOG_DIR/cron_app.log" 2>&1 &
sleep 8

if lsof -ti:5556 > /dev/null 2>&1; then
    echo "✅ localhost:5556 çalışıyor!"
    echo "   Mac her açıldığında otomatik başlayacak."
else
    echo "⚠️ Başlatılamadı. Log:"
    tail -10 "$LOG_DIR/cron_app.log"
fi

echo ""
echo "Sonraki kullanım:"
echo "  Dur   : lsof -ti:5556 | xargs kill -9"
echo "  Başlat: cd /Users/hakanficicilar/borsa_app && nohup /usr/bin/python3 -m streamlit run app.py --server.port 5556 --server.headless true &"
echo "  Log   : tail -f $LOG_DIR/cron_app.log"
