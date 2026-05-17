#!/bin/bash
# SEPA Stock Scanner - Kalıcı servis kurulum scripti
# Türkçe karakter içeren yolu bypass eder

SEPA_DIR="/Users/hakanficicilar/Documents/A\u0130/MARK M\u0130NERV\u0130N\u0130"
WRAPPER="$HOME/sepa_run.sh"
PLIST="$HOME/Library/LaunchAgents/com.sepa.scanner.plist"
LOG="/tmp/sepa.log"

# 1. Wrapper script oluştur (ASCII yolda)
cat > "$WRAPPER" << 'EOF'
#!/bin/bash
cd "/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"
/usr/bin/python3 app.py >> /tmp/sepa.log 2>&1
EOF
chmod +x "$WRAPPER"

# 2. Mevcut servisi durdur
launchctl unload "$PLIST" 2>/dev/null
sleep 1

# 3. plist yaz
cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sepa.scanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$(echo $WRAPPER)</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST

# 4. Servisi başlat
launchctl load "$PLIST"
sleep 3

# 5. Kontrol
if lsof -ti:5555 > /dev/null 2>&1; then
    echo "✅ SEPA Scanner çalışıyor: http://localhost:5555"
    echo "   Log: tail -f $LOG"
    echo "   Durdur: launchctl unload $PLIST"
else
    echo "⚠️  Servis başlatıldı ama port henüz dinlenmiyor"
    echo "   10 saniye bekleyip tekrar deneyin"
    echo "   Log: cat $LOG"
fi
