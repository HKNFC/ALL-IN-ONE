#!/bin/bash
# Borsa Portföy Seçici — LaunchAgent kurulum scripti

PLIST_PATH="$HOME/Library/LaunchAgents/com.borsa.portfoy.plist"
APP_DIR="/Users/hakanficicilar/borsa_app"
LOG_DIR="/Users/hakanficicilar/Documents/Aİ/Portfolio-Optimizer/logs"
WRAPPER="$HOME/start_borsa_app.sh"

mkdir -p "$LOG_DIR"

# Wrapper script oluştur (HOME altında, özel karakter yok)
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/bin/bash
export HOME="/Users/hakanficicilar"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd /Users/hakanficicilar/borsa_app
exec /usr/bin/python3 -m streamlit run app.py \
    --server.port 5556 \
    --server.headless true \
    --server.runOnSave false
WRAPPER_EOF
chmod +x "$WRAPPER"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.borsa.portfoy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$WRAPPER</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/hakanficicilar</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>/Users/hakanficicilar/borsa_app</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/app_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/app_stderr.log</string>
    <key>ThrottleInterval</key>
    <integer>15</integer>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null
lsof -ti:5556 | xargs kill -9 2>/dev/null
sleep 2

launchctl load "$PLIST_PATH"
sleep 10

if lsof -ti:5556 > /dev/null 2>&1; then
    echo "✅ Servis kuruldu! localhost:5556 çalışıyor."
    echo "   Mac her açıldığında otomatik başlar, çökerse otomatik yeniden başlar."
else
    echo "⚠️  Hata:"
    tail -8 "$LOG_DIR/app_stderr.log"
fi
