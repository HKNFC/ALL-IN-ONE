#!/bin/bash
# ─────────────────────────────────────────────────────────────
# BIST Rebalancing — macOS Otomatik Zamanlayıcı Kurulum Scripti
# Çalıştır: bash kur_zamanlayici.sh
# ─────────────────────────────────────────────────────────────

PLIST_PATH="$HOME/Library/LaunchAgents/com.yatirim.bist.rebalancing.plist"
SCRIPT_PATH="/Users/hakanficicilar/Documents/Aİ/101 YATIRIM/portfoy_yonetici.py"
LOG_DIR="/Users/hakanficicilar/Documents/Aİ/101 YATIRIM"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yatirim.bist.rebalancing</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_PATH}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>10</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd_stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo ""
echo "Zamanlayici kuruldu."
echo "Her sabah 09:10'da kontrol eder."
echo "Ayın ilk is gununde rebalancing otomatik calisir."
echo ""
echo "Durum kontrol: launchctl list | grep bist"
echo "Iptal etmek : launchctl unload $PLIST_PATH"
