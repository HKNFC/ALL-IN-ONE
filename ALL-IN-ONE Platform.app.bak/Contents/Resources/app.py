"""
ALL-IN-ONE INVESTING PLATFORM — STABLE Portal
Portlar: 5700 (portal), 8601 (Gemini), 5655 (Minervini),
         8605 (Optimizer), 8603 (Super Investor)
"""

import os, subprocess
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

STABLE_DIR = "/Users/hakanficicilar/Documents/Aİ/STABLE-ALL-IN-ONE"

APPS = {
    'gemini':    {'name': 'Piyasa Zamanlaması',  'icon': '⏱️',  'url': 'http://localhost:8601', 'port': 8601},
    'minervini': {'name': 'Mark Minervini',       'icon': '📊',  'url': 'http://localhost:5655', 'port': 5655},
    'borsa':     {'name': 'Portföy Optimizer',    'icon': '🔍',  'url': 'http://localhost:8605', 'port': 8605},
    'super':     {'name': 'Super Investor',       'icon': '🏆',  'url': 'http://localhost:8603', 'port': 8603},
}

@app.route('/')
def index():
    return render_template('index.html', apps=APPS, default_app='gemini')

@app.route('/api/apps')
def api_apps():
    import socket
    statuses = {}
    for key, info in APPS.items():
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(('127.0.0.1', info['port']))
            s.close()
            statuses[key] = 'online'
        except Exception:
            statuses[key] = 'offline'
    result = {}
    for key, info in APPS.items():
        result[key] = {**info, 'status': statuses[key]}
    return jsonify(result)

if __name__ == '__main__':
    # Stabil ortamı otomatik başlat
    import socket
    def is_port_open(p):
        try:
            s = socket.socket(); s.settimeout(0.5)
            s.connect(('127.0.0.1', p)); s.close(); return True
        except: return False

    if not is_port_open(5655):
        print("Stabil ortam başlatılıyor...")
        subprocess.Popen(['bash', STABLE_DIR + '/start_stable.sh'])
        import time; time.sleep(6)

    print("=" * 60)
    print("  ALL-IN-ONE INVESTING PLATFORM (STABLE)")
    print("=" * 60)
    for key, info in APPS.items():
        print(f"  {info['icon']}  {info['name']:20s} → {info['url']}")
    print()
    print("  Portal → http://localhost:5700")
    import webbrowser, time
    time.sleep(1)
    webbrowser.open('http://localhost:5700')
    app.run(debug=False, host='127.0.0.1', port=5700, use_reloader=False)
