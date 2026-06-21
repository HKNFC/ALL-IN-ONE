"""
TEMEL M. MİNERVİNİ — Flask App
================================
Mark Minervini altyapısı üzerine USA temel verisi eklenmiş bağımsız modül.
Port: 5556
BIST: desteklenmiyor — yalnızca USA.
"""

import math
import json
import os
import sys
import uuid
import threading
import logging
from datetime import datetime, timedelta, date

import pandas as pd
import numpy as np
import yfinance as yf
from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

# Bu modülün dizinini path'e ekle (symlink'ler burada)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

import storage
from temel_scanner import TemelUSAScanner
from temel_backtest_engine import TemelBacktest

logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

# ── Flask kurulumu ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# ── Tarama durumu (async scan) ────────────────────────────────────────────────
_scan_lock     = threading.Lock()
_scan_progress = {'pct': 0, 'msg': 'Bekleniyor', 'result': None, 'error': None}

def _set_progress(pct, msg, result=None, error=None):
    with _scan_lock:
        _scan_progress.update({'pct': pct, 'msg': msg, 'result': result, 'error': error})

# ── Backtest görev havuzu ─────────────────────────────────────────────────────
_backtest_tasks = {}
_backtest_lock  = threading.Lock()

# ── JSON yardımcıları ─────────────────────────────────────────────────────────

def _sanitize(obj):
    """NaN/Inf/Timestamp değerlerini JSON-güvenli hale getir."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime)):
        return str(obj)
    return obj


def _safe_jsonify(data):
    class SafeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, (pd.Timestamp, datetime)):
                return str(obj)
            return super().default(obj)

    sanitized = _sanitize(data)
    resp_str  = json.dumps(sanitized, cls=SafeEncoder, allow_nan=False, ensure_ascii=False)
    return Response(resp_str, mimetype='application/json')


def _last_business_day(dt: pd.Timestamp) -> pd.Timestamp:
    """dt veya önceki iş günü."""
    d = dt
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _sort_scan_results(results: list) -> list:
    """WATCHING en sona, geri kalanlar Final_Score azalan."""
    if not results:
        return results
    def _key(r):
        is_watching = 1 if r.get('Status', 'WATCHING') == 'WATCHING' else 0
        score = -(r.get('Final_Score') or r.get('RS') or 0)
        return (is_watching, score)
    return sorted(results, key=_key)


# ── Sayfa route'ları ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scanner')
def scanner():
    return render_template('scanner.html')

@app.route('/backtest')
def backtest():
    return render_template('backtest.html')

@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html')

@app.route('/about')
def about():
    return render_template('about.html')


# ── Tarama API ────────────────────────────────────────────────────────────────

@app.route('/api/scan/progress', methods=['GET'])
def api_scan_progress():
    with _scan_lock:
        return jsonify(dict(_scan_progress))


@app.route('/api/scan/result', methods=['GET'])
def api_scan_result():
    with _scan_lock:
        result = _scan_progress.get('result')
        error  = _scan_progress.get('error')
    if error:
        return jsonify({'success': False, 'error': error}), 500
    if result is None:
        return jsonify({'success': False, 'error': 'Henüz sonuç yok'}), 404
    return _safe_jsonify(result)


@app.route('/api/scan/full', methods=['POST'])
def api_full_scan():
    """
    USA taraması — temel + teknik skor.
    Parametreler:
        scan_date   : 'YYYY-MM-DD' | null  (null = bugün)
        fund_weight : 0.0 – 0.6           (varsayılan 0.40)
    """
    try:
        data        = request.get_json() or {}
        scan_date   = data.get('scan_date', None)
        fund_weight = float(data.get('fund_weight', 0.40))
        fund_weight = max(0.0, min(0.60, fund_weight))

        # ── Geçmiş tarih: backtest motorunu kullan ───────────────────────────
        if scan_date:
            _set_progress(2, 'Tarama başlatılıyor...')
            today_str = datetime.now().strftime('%Y-%m-%d')
            bt = TemelBacktest(scan_date, today_str, fund_weight=fund_weight)
            scan_dt = pd.Timestamp(scan_date)

            tickers_override = list(bt._us_tickers)
            total = len(tickers_override)
            _set_progress(5, f'Veriler indiriliyor ({total} hisse)...')

            bt._global_prefetch(tickers_override, 'US')
            effective = _last_business_day(scan_dt)
            cutoff    = effective.normalize()
            as_of_str = cutoff.strftime('%Y-%m-%d')
            sp500     = bt._cache.get_slice('^GSPC', cutoff)

            results = []
            for i, ticker in enumerate(sorted(tickers_override)):
                if i % 30 == 0:
                    pct = 10 + int((i + 1) / total * 85)
                    _set_progress(pct, f'Analiz ediliyor... {i+1}/{total}')
                stock_data = bt._cache.get_slice(ticker, cutoff)
                res = bt.scanner.scan_us_stock_temel(
                    ticker      = ticker,
                    sp500_data  = sp500,
                    as_of_date  = as_of_str,
                    fund_weight = fund_weight,
                    stock_data  = stock_data,
                )
                if res:
                    results.append(res)

            results = _sort_scan_results(results)
            _set_progress(100, f'Tamamlandı — {len(results)} hisse bulundu')
            return _safe_jsonify({
                'success':          True,
                'count':            len(results),
                'results':          results,
                'market':           'US',
                'scan_date':        scan_date,
                'effective_cutoff': effective.strftime('%Y-%m-%d'),
                'fund_weight':      fund_weight,
                'timestamp':        datetime.now().isoformat(),
            })

        # ── Bugün: canlı tarama — async thread ──────────────────────────────
        _wd = datetime.now().weekday()
        _live_as_of = None
        _days_back  = 0
        if _wd == 5:    _days_back = 1
        elif _wd == 6:  _days_back = 2
        elif _wd == 0 and datetime.now().hour < 10: _days_back = 3
        elif _wd in (1,2,3,4) and datetime.now().hour < 10: _days_back = 1
        if _days_back > 0:
            _live_as_of = (date.today() - timedelta(days=_days_back)).strftime('%Y-%m-%d')

        def _live_worker():
            try:
                scanner_live = TemelUSAScanner()
                _set_progress(5, 'Benchmark verisi indiriliyor...')
                import contextlib, io
                with contextlib.redirect_stderr(io.StringIO()):
                    sp500 = yf.Ticker('^GSPC').history(period='2y')

                tickers = list(scanner_live.us_tickers)
                total   = len(tickers)
                _set_progress(10, f'Taranıyor ({total} hisse)...')

                results = []
                for i, ticker in enumerate(sorted(tickers)):
                    if i % 20 == 0:
                        pct = 10 + int((i + 1) / total * 85)
                        _set_progress(pct, f'Analiz... {i+1}/{total}')
                    try:
                        res = scanner_live.scan_us_stock_temel(
                            ticker      = ticker,
                            sp500_data  = sp500,
                            as_of_date  = _live_as_of,
                            fund_weight = fund_weight,
                        )
                        if res:
                            results.append(res)
                    except Exception:
                        pass

                results = _sort_scan_results(results)
                _set_progress(100, f'{len(results)} hisse bulundu', result={
                    'success':    True,
                    'count':      len(results),
                    'results':    _sanitize(results),
                    'market':     'US',
                    'fund_weight': fund_weight,
                    'timestamp':  datetime.now().isoformat(),
                })
            except Exception as e:
                _set_progress(100, 'Hata!', error=str(e))

        _set_progress(1, 'Başlatılıyor...')
        threading.Thread(target=_live_worker, daemon=True).start()
        return jsonify({'success': True, 'async': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Backtest API ──────────────────────────────────────────────────────────────

def _run_backtest_task(task_id, start_date, end_date, initial_capital,
                       frequency, portfolio_size, fund_weight):
    """Arka planda TemelBacktest çalıştır."""
    try:
        bt     = TemelBacktest(start_date, end_date, initial_capital, fund_weight=fund_weight)
        report = bt.run_backtest(portfolio_size=portfolio_size, frequency=frequency)
        report = _sanitize(report)

        bt_id = str(uuid.uuid4())[:8]
        freq_labels = {'monthly': 'Aylık', 'biweekly': '15 Günlük', 'weekly': 'Haftalık'}
        fw_pct = int(round(fund_weight * 100))
        name = (f"USA · Temel%{fw_pct} · {freq_labels.get(frequency, frequency)} · "
                f"{portfolio_size} hisse · {start_date} → {end_date}")
        params = {
            'start_date': start_date, 'end_date': end_date,
            'market': 'US', 'frequency': frequency,
            'initial_capital': initial_capital,
            'portfolio_size': portfolio_size,
            'fund_weight': fund_weight,
        }
        storage.save_backtest(bt_id, name, params, report)

        with _backtest_lock:
            _backtest_tasks[task_id] = {
                'status': 'done', 'report': report,
                'saved_id': bt_id, 'saved_name': name,
            }
    except Exception as e:
        with _backtest_lock:
            _backtest_tasks[task_id] = {'status': 'error', 'error': str(e)}


@app.route('/api/backtest', methods=['POST'])
def api_run_backtest():
    """Backtest başlat — hemen task_id döndür."""
    try:
        data            = request.get_json() or {}
        start_date      = data.get('start_date')
        end_date        = data.get('end_date')
        initial_capital = float(data.get('initial_capital', 100_000))
        frequency       = data.get('frequency', 'monthly')
        portfolio_size  = int(data.get('portfolio_size', 7))
        fund_weight     = float(data.get('fund_weight', 0.40))
        fund_weight     = max(0.0, min(0.60, fund_weight))

        if not start_date or not end_date:
            return jsonify({'success': False, 'error': 'start_date ve end_date gerekli'}), 400

        task_id = str(uuid.uuid4())[:12]
        with _backtest_lock:
            _backtest_tasks[task_id] = {'status': 'running'}

        t = threading.Thread(
            target=_run_backtest_task,
            args=(task_id, start_date, end_date, initial_capital,
                  frequency, portfolio_size, fund_weight),
            daemon=True,
        )
        t.start()
        return jsonify({'success': True, 'status': 'running', 'task_id': task_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtest/status/<task_id>', methods=['GET'])
def api_backtest_status(task_id):
    with _backtest_lock:
        task = _backtest_tasks.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Görev bulunamadı'}), 404
    if task['status'] == 'running':
        return jsonify({'success': True, 'status': 'running'})
    if task['status'] == 'error':
        return jsonify({'success': False, 'status': 'error', 'error': task['error']})
    result = dict(task)
    result['success'] = True
    with _backtest_lock:
        _backtest_tasks.pop(task_id, None)
    return _safe_jsonify(result)


@app.route('/api/backtests', methods=['GET'])
def api_list_backtests():
    try:
        items = storage.list_backtests()
        return jsonify({'success': True, 'backtests': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtests/<bt_id>', methods=['GET'])
def api_get_backtest(bt_id):
    try:
        data = storage.get_backtest(bt_id)
        if not data:
            return jsonify({'success': False, 'error': 'Backtest bulunamadı'}), 404
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtests/<bt_id>', methods=['DELETE'])
def api_delete_backtest(bt_id):
    try:
        storage.delete_backtest(bt_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Top Picks API (Mark Minervini ile uyumlu) ─────────────────────────────────

@app.route('/api/top-picks', methods=['POST'])
def api_save_top_picks():
    """Tarama sonrası top picks'i kaydet."""
    try:
        data = request.get_json() or {}
        # storage'da top_picks tablosu yoksa sessizce geç
        try:
            storage.save_top_picks(
                scan_date = data.get('scan_date', datetime.now().strftime('%Y-%m-%d')),
                market    = data.get('market', 'US'),
                picks     = data.get('picks', []),
                engine    = data.get('engine', 'temel'),
            )
        except Exception:
            pass
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/top-picks', methods=['GET'])
def api_get_top_picks():
    try:
        rows = storage.get_top_picks() if hasattr(storage, 'get_top_picks') else []
        return jsonify({'success': True, 'picks': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Market timing (basit — sadece S&P500 trendi) ─────────────────────────────

@app.route('/api/market-timing', methods=['GET'])
def api_market_timing():
    """S&P500 trend bilgisi (USA modül için)."""
    try:
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            spy = yf.Ticker('SPY').history(period='1y')
        if spy.empty or len(spy) < 50:
            return jsonify({'success': False, 'error': 'Veri yetersiz'})

        price   = float(spy['Close'].iloc[-1])
        sma50   = float(spy['Close'].rolling(50).mean().iloc[-1])
        sma200  = float(spy['Close'].rolling(200).mean().iloc[-1]) if len(spy) >= 200 else sma50
        score   = 0
        if price > sma50:  score += 1
        if price > sma200: score += 1
        if sma50 > sma200: score += 1

        if score == 3:   status, action = 'BOĞA',  'SİSTEM AKTİF — Tam pozisyon'
        elif score == 2: status, action = 'KARMA',  'DİKKATLİ — Yarım pozisyon'
        else:            status, action = 'AYI',    'TEMKİNLİ — Pozisyonları koru'

        return jsonify({
            'success': True,
            'market':  'US (S&P500)',
            'price':   round(price, 2),
            'sma50':   round(sma50, 2),
            'sma200':  round(sma200, 2),
            'score':   score,
            'max_score': 3,
            'status':  status,
            'action':  action,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ── Portfolio endpoint'leri (uyumluluk için stub) ─────────────────────────────

@app.route('/api/portfolio', methods=['GET'])
def api_portfolio():
    return jsonify({'success': True, 'portfolio': [], 'note': 'Portföy bu modülde desteklenmiyor'})


# ── Market Status (app.js tarafından çağrılır) ────────────────────────────────

import time as _time
_market_status_cache = {'data': None, 'ts': 0}

@app.route('/api/market-status', methods=['GET'])
def api_market_status():
    """S&P500 piyasa durumu (USA only)."""
    force = request.args.get('force', '0') == '1'
    if not force and _market_status_cache['data'] and (_time.time() - _market_status_cache['ts']) < 900:
        return jsonify(_market_status_cache['data'])

    def _fetch(symbol, period='14mo'):
        import contextlib, io
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                t  = yf.Ticker(symbol)
                df = t.history(period=period, auto_adjust=True)
            if df is not None and len(df) >= 200:
                return df['Close'].squeeze()
        except Exception:
            pass
        return None

    def analyze(symbol, label):
        try:
            close = _fetch(symbol)
            if close is None:
                return {'symbol': symbol, 'label': label, 'error': 'Veri indirilemedi'}
            price   = float(close.iloc[-1])
            sma50   = float(close.rolling(50).mean().iloc[-1])
            sma200  = float(close.rolling(200).mean().iloc[-1])
            sma200_30ago = float(close.rolling(200).mean().iloc[-31]) if len(close) >= 231 else sma200
            high52  = float(close.tail(252).max())
            low52   = float(close.tail(252).min())
            score = 0; criteria = []
            for ok, lbl, det in [
                (price > sma50,   'Fiyat > 50G SMA',         f'{price:.1f} vs {sma50:.1f}'),
                (price > sma200,  'Fiyat > 200G SMA',        f'{price:.1f} vs {sma200:.1f}'),
                (sma50 > sma200,  '50G SMA > 200G SMA',      f'{sma50:.1f} vs {sma200:.1f}'),
                (sma200 > sma200_30ago, '200G SMA yükselen', f'{((sma200-sma200_30ago)/sma200_30ago*100):+.2f}%'),
                (((price-high52)/high52*100) >= -15, '52H zirveden ≤%15', f'{((price-high52)/high52*100):.1f}%'),
            ]:
                score += 1 if ok else 0
                criteria.append({'label': lbl, 'ok': ok, 'detail': det})
            if score == 5:   status, color, action = 'GÜÇLÜ BOĞA', 'green',  'SİSTEM AKTİF — Tam pozisyon al'
            elif score == 4: status, color, action = 'BOĞA',       'green',  'SİSTEM AKTİF — Normal pozisyon al'
            elif score == 3: status, color, action = 'KARMA',       'yellow', 'DİKKATLİ — Yarım pozisyon'
            elif score == 2: status, color, action = 'ZAYIF',       'yellow', 'TEMKİNLİ — Pozisyonları koru'
            else:            status, color, action = 'AYI',         'red',    'NAKİTTE KAL — Yeni alım yapma'
            returns = close.pct_change().dropna()
            vol20   = float(returns.tail(20).std() * (252 ** 0.5) * 100)
            trend_ok = score >= 4; vol_high = vol20 > 25
            if trend_ok and not vol_high:
                combined = {'icon': '🟢', 'text': 'Tam gaz yatırım yap', 'sub': 'Trend güçlü, volatilite normal.', 'color': '#15803d', 'bg': '#dcfce7'}
            elif trend_ok and vol_high:
                combined = {'icon': '🟡', 'text': 'Yatırım yap — pozisyon %50 azalt', 'sub': 'Trend güçlü ama volatilite yüksek.', 'color': '#92400e', 'bg': '#fef9c3'}
            else:
                combined = {'icon': '🔴', 'text': 'Nakitte kal', 'sub': 'Trend bozuk.', 'color': '#b91c1c', 'bg': '#fee2e2'}
            return {'symbol': symbol, 'label': label, 'price': price, 'sma50': sma50, 'sma200': sma200,
                    'high52': high52, 'low52': low52, 'score': score, 'max_score': 5,
                    'status': status, 'color': color, 'action': action, 'criteria': criteria,
                    'vol20': round(vol20, 1), 'combined_decision': combined}
        except Exception as e:
            return {'symbol': symbol, 'label': label, 'error': str(e)}

    us = analyze('^GSPC', 'ABD (S&P 500)')
    payload = {'success': True, 'bist': us, 'us': us}  # bist alanı app.js uyumu için
    payload = _sanitize(payload)
    _market_status_cache['data'] = payload
    _market_status_cache['ts']   = _time.time()
    return jsonify(payload)


# ── Uygulama başlatma ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    storage.init_db()
    os.makedirs('templates', exist_ok=True)

    print("=" * 70)
    print("🔬 TEMEL M. MİNERVİNİ — USA Temel + Teknik")
    print("=" * 70)
    port = int(os.environ.get('PORT', 5556))
    host = '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1'
    print(f"\n✅ Server başlatılıyor...")
    print(f"📡 URL: http://localhost:{port}")
    print(f"🔍 Scanner: http://localhost:{port}/scanner")
    print(f"📊 Backtest: http://localhost:{port}/backtest")
    print(f"⚖️  Temel + Teknik skorlama aktif")
    print(f"🔗 Mark Minervini (5555) etkilenmedi")
    print(f"\n⚠️  Durdurmak için Ctrl+C\n")

    app.run(debug=False, host=host, port=port, use_reloader=False)
