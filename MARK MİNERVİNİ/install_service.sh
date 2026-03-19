#!/bin/zsh
# SEPA Stock Scanner — Kalıcı Servis Kurulum Scripti
# Bir kez çalıştır, sonra uygulama her zaman arka planda hazır olur.

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.sepa.stockscanner.plist"
APP_DIR="/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"

mkdir -p "$PLIST_DIR"

cat > "$PLIST_FILE" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sepa.stockscanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ/start_server.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/sepa_server.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/sepa_server_error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ</string>
</dict>
</plist>
EOF

# Eski servisi durdur (varsa)
launchctl unload "$PLIST_FILE" 2>/dev/null

# Portu temizle
lsof -ti:5555 | xargs kill -9 2>/dev/null
sleep 1

# Yeni servisi yükle ve başlat
launchctl load "$PLIST_FILE"

echo ""
echo "✅ SEPA Stock Scanner servisi kuruldu!"
echo "   http://localhost:5555 adresinde çalışıyor"
echo ""
echo "Servis yönetimi:"
echo "  Durdur : launchctl unload ~/Library/LaunchAgents/com.sepa.stockscanner.plist"
echo "  Başlat : launchctl load ~/Library/LaunchAgents/com.sepa.stockscanner.plist"
echo "  Log    : tail -f /tmp/sepa_server.log"
