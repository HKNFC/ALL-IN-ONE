"""
ALL-IN-ONE INVESTING PLATFORM — Portal Shell
Her uygulama kendi portunda çalışır, bu portal sol menü + iframe sağlar.
  Gemini Zamanlama  : http://localhost:8501
  Portföy Optimizer : http://localhost:8505
  SUPER INVESTOR    : http://localhost:8503
  MARK MİNERVİNİ   : http://localhost:5555
Portal               : http://localhost:5600
"""

import os
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

APPS = {
    'gemini':    {'name': 'Piyasa Zamanlaması',  'icon': '⏱️',  'url': 'http://localhost:8501', 'port': 8501},
    'minervini': {'name': 'Mark Minervini',       'icon': '📊',  'url': 'http://localhost:5555', 'port': 5555},
    'borsa':     {'name': 'Portföy Optimizer',    'icon': '🔍',  'url': 'http://localhost:8505', 'port': 8505},
    'super':     {'name': 'Super Investor',       'icon': '🏆',  'url': 'http://localhost:8503', 'port': 8503},
    'ensemble':  {'name': 'Ensemble Portföy',     'icon': '🎯',  'url': 'http://localhost:8506', 'port': 8506},
}

@app.route('/')
def index():
    from flask import make_response
    resp = make_response(render_template('index.html', apps=APPS, default_app='gemini'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp

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
    print("=" * 60)
    print("  ALL-IN-ONE INVESTING PLATFORM")
    print("=" * 60)
    print()
    for key, info in APPS.items():
        print(f"  {info['icon']}  {info['name']:20s} → {info['url']}")
    print()
    print("  Portal → http://localhost:5600")
    print()
    print("  Not: Uygulamaları başlatmak için start_all.sh çalıştırın")
    print()
    app.run(debug=False, host='127.0.0.1', port=5600, use_reloader=False)
