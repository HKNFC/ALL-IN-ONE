import os

plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sepa.scanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-l</string>
        <string>-c</string>
        <string>cd "/Users/hakanficicilar/Documents/A\u0130/MARK M\u0130NERV\u0130N\u0130" &amp;&amp; /usr/bin/python3 app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/sepa.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/sepa.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/hakanficicilar</string>
        <key>USER</key>
        <string>hakanficicilar</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>"""

path = os.path.expanduser("~/Library/LaunchAgents/com.sepa.scanner.plist")
with open(path, "w", encoding="utf-8") as f:
    f.write(plist)
print("OK:", path)
