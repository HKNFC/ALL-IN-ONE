"""
Mark Minervini Trading Platform - Web Application
Flask backend with REST API
"""

from flask import Flask, render_template, jsonify, request, send_file, make_response
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import sys
import storage

# Uygulama başlarken DB tablolarını oluştur (gunicorn dahil her ortamda çalışır)
storage.init_db()

try:
    from price_validator import validate_scan_results
    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False


def resource_path(relative):
    """PyInstaller paketlenmiş uygulamada doğru dosya yolunu döndürür."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


# Import our scanners
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sepa_scanner import SEPAScanner
from universal_scanner import UniversalStockScanner
from backtest_engine import MinerviniBacktest

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = 'minervini-trading-platform-2026'
app.config['JSON_SORT_KEYS'] = False

# Tarama ilerleme takibi (thread-safe)
import threading
_scan_progress = {'pct': 0, 'msg': '', 'active': False}
_scan_lock = threading.Lock()

def _set_progress(pct, msg=''):
    with _scan_lock:
        _scan_progress['pct'] = pct
        _scan_progress['msg'] = msg
        _scan_progress['active'] = (pct < 100)

# ============================================================================
# ROUTES - Pages
# ============================================================================

@app.route('/')
def index():
    """Ana sayfa"""
    return render_template('index.html')

@app.route('/scanner')
def scanner_page():
    """Tarayıcı sayfası"""
    resp = make_response(render_template('scanner.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/backtest')
def backtest_page():
    """Backtest sayfası"""
    from flask import make_response
    resp = make_response(render_template('backtest.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp

@app.route('/portfolio')
def portfolio_page():
    """Portföy sayfası"""
    return render_template('portfolio.html')

@app.route('/signals')
def signals_page():
    """Sinyaller sayfası"""
    return render_template('signals.html')

@app.route('/about')
def about_page():
    """Hakkında sayfası"""
    return render_template('about.html')

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/scan/progress', methods=['GET'])
def api_scan_progress():
    with _scan_lock:
        return jsonify(dict(_scan_progress))

@app.route('/api/scan/quick', methods=['POST'])
def api_quick_scan():
    """Hızlı tarama - Küçük liste"""
    try:
        data = request.get_json()
        market = data.get('market', 'US')
        
        if market == 'US':
            tickers = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META', 'TSLA', 'AMZN']
        else:  # BIST - .IS uzantısı ekle
            tickers = ['AKBNK.IS', 'GARAN.IS', 'ISCTR.IS', 'THYAO.IS', 'TUPRS.IS', 'EREGL.IS', 
                      'ASELS.IS', 'SAHOL.IS', 'KCHOL.IS', 'SISE.IS', 'BIMAS.IS', 'HALKB.IS']
        
        scanner = UniversalStockScanner()
        
        # Pazar verisi
        sp500 = yf.Ticker("^GSPC").history(period="1y")
        xu100 = yf.Ticker("XU100.IS").history(period="1y")
        
        results = []
        
        for ticker in tickers:
            if market == 'US':
                result = scanner.scan_us_stock(ticker, sp500)
            else:
                result = scanner.scan_bist_stock(ticker, xu100)
            
            if result:
                results.append(result)
        
        return jsonify({
            'success': True,
            'count': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def _last_business_day(date: pd.Timestamp) -> pd.Timestamp:
    """Verilen tarih bugün veya sonrasıysa bir önceki iş gününü döndür."""
    today = pd.Timestamp.today().normalize()
    d = date.normalize()
    if d >= today:
        d = today - pd.Timedelta(days=1)
        while d.weekday() >= 5:   # Cumartesi=5, Pazar=6
            d -= pd.Timedelta(days=1)
    return d


def _scan_with_progress(bt, scan_dt, market, tickers_override):
    """BacktestEngine taramasını ilerleme takibi ile çalıştırır."""
    cutoff_raw = pd.Timestamp(scan_dt).normalize()
    cutoff     = _last_business_day(cutoff_raw)   # bugün seçildiyse → son iş günü
    total      = len(tickers_override)

    # Veri indir (%5 → %40)
    _set_progress(5, f'Veriler indiriliyor ({total} hisse)...')
    if not bt._prefetched:
        bt._global_prefetch(tickers_override, market)
    _set_progress(40, 'Veriler hazır, analiz başlıyor...')

    sp500  = bt._cache.get_slice('^GSPC',    cutoff)
    xu100  = bt._cache.get_slice('XU100.IS', cutoff)

    results = []
    for i, ticker in enumerate(tickers_override):
        pct = 40 + int((i + 1) / total * 58)   # %40 → %98
        if i % 10 == 0:
            _set_progress(pct, f'Analiz ediliyor... {i+1}/{total} ({pct}%)')

        stock_data = bt._cache.get_slice(ticker, cutoff)
        if len(stock_data) < 200:
            continue
        try:
            is_bist = ticker.endswith('.IS')
            result  = (
                bt.scanner.scan_bist_stock(ticker, xu100, stock_data)
                if is_bist
                else bt.scanner.scan_us_stock(ticker, sp500, stock_data)
            )
            if result:
                results.append(result)
        except Exception:
            pass

    return results


@app.route('/api/scan/full', methods=['POST'])
def api_full_scan():
    """Tam tarama — geçmiş tarih için backtest motoru, bugün için canlı tarama"""
    try:
        data = request.get_json()
        market    = data.get('market', 'BOTH')
        scan_date = data.get('scan_date', None)   # "YYYY-MM-DD" veya None
        scan_type = data.get('scan_type', 'BISTTUM')
        manual_list_raw = data.get('manual_list', '')
        manual_list = [t.strip() for t in manual_list_raw.split(',') if t.strip()] if manual_list_raw else []

        # ── GEÇMİŞ TARİH: backtest motorunu kullan (batch download, aynı mantık) ──
        if scan_date:
            _set_progress(2, 'Tarama başlatılıyor...')
            today_str = datetime.now().strftime('%Y-%m-%d')
            bt = MinerviniBacktest(scan_date, today_str)
            scan_dt = pd.Timestamp(scan_date)

            if market in ['BIST', 'BOTH']:
                scanner_tmp = bt.scanner
                bist_list = scanner_tmp.get_tickers_by_scan_type(scan_type, manual_list)
            else:
                bist_list = []

            if market == 'US':
                tickers_override = list(bt._us_tickers)
            elif market == 'BIST':
                tickers_override = bist_list
            else:
                tickers_override = list(bt._us_tickers) + bist_list

            total = len(tickers_override)
            _set_progress(5, f'Veriler indiriliyor ({total} hisse)...')

            effective_cutoff = _last_business_day(scan_dt)
            results = _scan_with_progress(bt, scan_dt, market, tickers_override)

            _set_progress(100, f'Tamamlandı — {len(results)} hisse bulundu')
            return _safe_jsonify({
                'success': True,
                'count': len(results),
                'results': results,
                'market': market,
                'scan_date': scan_date,
                'effective_cutoff': effective_cutoff.strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat()
            })

        # ── BUGÜN: canlı tarama (klasik sistem) ──
        scanner = UniversalStockScanner()

        if market == 'US':
            us_results = []
            import io, contextlib
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                sp500 = yf.Ticker("^GSPC").history(period="1y")
            for ticker in scanner.us_tickers:
                result = scanner.scan_us_stock(ticker, sp500)
                if result:
                    us_results.append(result)
            # Cross-validation (Breakout + Pivot Near hisseler için)
            if _VALIDATOR_AVAILABLE and us_results:
                print("🔍 Cross-validation başlıyor (US)...", flush=True)
                us_results = validate_scan_results(us_results, is_bist=False)
            return _safe_jsonify({
                'success': True, 'count': len(us_results), 'results': us_results,
                'market': 'US', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            })

        elif market == 'BIST':
            bist_results = []
            import io, contextlib
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                xu100 = yf.Ticker("XU100.IS").history(period="1y")
            bist_list = scanner.get_tickers_by_scan_type(scan_type, manual_list)
            for ticker in bist_list:
                result = scanner.scan_bist_stock(ticker, xu100)
                if result:
                    bist_results.append(result)
            # Cross-validation (Breakout + Pivot Near hisseler için)
            if _VALIDATOR_AVAILABLE and bist_results:
                print("🔍 Cross-validation başlıyor (BIST)...", flush=True)
                bist_results = validate_scan_results(bist_results, is_bist=True)
            return _safe_jsonify({
                'success': True, 'count': len(bist_results), 'results': bist_results,
                'market': 'BIST', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            })

        else:  # BOTH
            results = scanner.run_universal_scan()
            if _VALIDATOR_AVAILABLE and results:
                print("🔍 Cross-validation başlıyor (BOTH)...", flush=True)
                is_bist = any(r.get('Market') == 'BIST' for r in results[:5])
                results = validate_scan_results(results, is_bist=False)
            return _safe_jsonify({
                'success': True, 'count': len(results), 'results': results,
                'market': 'BOTH', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stock/<ticker>', methods=['GET'])
def api_stock_detail(ticker):
    """Hisse detayları"""
    try:
        market = request.args.get('market', 'US')
        yahoo_ticker = f"{ticker}.IS" if market == 'BIST' else ticker
        
        stock = yf.Ticker(yahoo_ticker)
        info = stock.info
        df = stock.history(period="1y")
        
        if len(df) == 0:
            return jsonify({
                'success': False,
                'error': 'Veri bulunamadı'
            }), 404
        
        # Teknik göstergeler
        current = df['Close'].iloc[-1]
        sma_50 = df['Close'].rolling(50).mean().iloc[-1]
        sma_200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Pivot
        pivot = df['High'].tail(20).max()
        
        return jsonify({
            'success': True,
            'ticker': ticker,
            'market': market,
            'current_price': float(current),
            'sma_50': float(sma_50),
            'sma_200': float(sma_200),
            'pivot': float(pivot),
            'name': info.get('longName', ticker),
            'sector': info.get('sector', 'N/A'),
            'volume': int(df['Volume'].iloc[-1]),
            'avg_volume': int(df['Volume'].mean()),
            'chart_data': {
                'dates': df.index.strftime('%Y-%m-%d').tolist()[-90:],
                'prices': df['Close'].tail(90).tolist(),
                'volumes': df['Volume'].tail(90).tolist()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

PORTFOLIOS_DIR = os.path.join(os.path.dirname(__file__), 'portfolios')
os.makedirs(PORTFOLIOS_DIR, exist_ok=True)

# Eski my_portfolio.csv varsa "Varsayılan" olarak taşı
_legacy = os.path.join(os.path.dirname(__file__), 'my_portfolio.csv')
if os.path.exists(_legacy):
    _dest = os.path.join(PORTFOLIOS_DIR, 'Varsayılan.csv')
    if not os.path.exists(_dest):
        import shutil
        shutil.copy(_legacy, _dest)

def _portfolio_path(name):
    name_stripped = name.strip()
    try:
        for fname in os.listdir(PORTFOLIOS_DIR):
            if fname.endswith('.csv') and fname[:-4] == name_stripped:
                return os.path.join(PORTFOLIOS_DIR, fname)
    except Exception:
        pass
    safe = "".join(c for c in name_stripped if c.isalnum() or c in (' ', '_', '-', 'ğüşıöçĞÜŞİÖÇ')).strip()
    return os.path.join(PORTFOLIOS_DIR, f"{safe}.csv")

@app.route('/api/portfolios/summary', methods=['GET'])
def api_portfolios_summary():
    """Tüm portföylerin özet istatistiklerini döndür"""
    try:
        summaries = []
        names = storage.list_portfolios()
        for name in names:
            rows = storage.get_portfolio(name)
            if not rows:
                summaries.append({'name': name, 'total_value': 0, 'total_cost': 0,
                                  'total_profit': 0, 'total_pct': 0, 'win_rate': 0, 'count': 0})
                continue
            total_cost = total_value = 0.0
            winners = 0
            count = len(rows)
            for row in rows:
                entry = float(row['maliyet'])
                qty   = float(row['adet']) if row['adet'] else 0
                cost  = entry * qty
                total_cost += cost
                try:
                    yf_ticker = row['ticker'] + '.IS' if row['market'] == 'BIST' else row['ticker']
                    hist = yf.Ticker(yf_ticker).history(period='1d')
                    cur_price = float(hist['Close'].iloc[-1]) if len(hist) > 0 else entry
                except Exception:
                    cur_price = entry
                cur_val = cur_price * qty
                total_value += cur_val
                if cur_val > cost:
                    winners += 1
            profit   = total_value - total_cost
            pct      = (profit / total_cost * 100) if total_cost > 0 else 0
            win_rate = (winners / count * 100) if count > 0 else 0
            summaries.append({
                'name': name, 'count': count,
                'total_value':  round(total_value, 2),
                'total_cost':   round(total_cost,  2),
                'total_profit': round(profit, 2),
                'total_pct':    round(pct, 2),
                'win_rate':     round(win_rate, 1),
            })
        return jsonify({'success': True, 'summaries': summaries})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolios', methods=['GET'])
def api_list_portfolios():
    """Tüm portföyleri listele"""
    try:
        return jsonify({'success': True, 'portfolios': storage.list_portfolios()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolios', methods=['POST'])
def api_create_portfolio():
    """Yeni portföy oluştur"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Portföy adı boş olamaz'}), 400
        if storage.portfolio_exists(name):
            return jsonify({'success': False, 'error': 'Bu isimde portföy zaten var'}), 400
        storage.create_portfolio(name)
        return jsonify({'success': True, 'name': name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolios/rename', methods=['POST'])
def api_rename_portfolio():
    """Portföy yeniden adlandır"""
    try:
        old_name = request.args.get('old', '').strip()
        new_name = request.args.get('new', '').strip()
        if not old_name or not new_name:
            return jsonify({'success': False, 'error': 'Eski ve yeni ad gerekli'}), 400
        if not storage.portfolio_exists(old_name):
            return jsonify({'success': False, 'error': 'Portföy bulunamadı'}), 404
        if storage.portfolio_exists(new_name):
            return jsonify({'success': False, 'error': 'Bu isimde portföy zaten var'}), 400
        storage.rename_portfolio(old_name, new_name)
        return jsonify({'success': True, 'name': new_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolios/delete', methods=['DELETE'])
def api_delete_portfolio():
    """Portföy sil"""
    try:
        name = request.args.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Portföy adı gerekli'}), 400
        storage.delete_portfolio(name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolio', methods=['GET'])
def api_get_portfolio():
    """Portföy getir"""
    try:
        name = request.args.get('name', 'Varsayılan')
        rows = storage.get_portfolio(name)
        if not rows:
            return jsonify({'success': True, 'positions': [], 'summary': {'total_value': 0, 'total_profit': 0, 'total_positions': 0, 'win_rate': 0}})

        positions = []
        total_value = 0
        total_cost = 0

        for row in rows:
            ticker      = row['ticker']
            entry_price = float(row['maliyet'])
            quantity    = float(row['adet']) if row['adet'] else 0
            stop_loss   = float(row['stop_seviyesi']) if row['stop_seviyesi'] else entry_price * 0.93
            market      = row['market']

            try:
                yf_ticker = f"{ticker}.IS" if market == 'BIST' else ticker
                stock = yf.Ticker(yf_ticker)
                current_price = None
                try:
                    fi = stock.fast_info
                    p = fi.get('last_price') or fi.get('regularMarketPrice')
                    if p and float(p) > 0:
                        current_price = float(p)
                except Exception:
                    pass
                if not current_price:
                    hist = stock.history(period='5d')
                    if len(hist) > 0:
                        current_price = float(hist['Close'].iloc[-1])
                if not current_price:
                    current_price = entry_price
            except Exception as e:
                print(f"⚠️ Fiyat çekme hatası {ticker}: {e}", flush=True)
                current_price = entry_price

            cost_basis    = entry_price * quantity
            current_value = current_price * quantity
            total_cost   += cost_basis
            total_value  += current_value

            positions.append({
                'ticker':        ticker,
                'market':        market,
                'entry_price':   entry_price,
                'current_price': current_price,
                'quantity':      quantity,
                'stop_loss':     stop_loss,
                'cost_basis':    cost_basis,
                'current_value': current_value,
                'purchase_date': row.get('alis_tarihi', 'N/A')
            })

        total_profit = total_value - total_cost
        winning  = sum(1 for p in positions if p['current_value'] > p['cost_basis'])
        win_rate = (winning / len(positions) * 100) if positions else 0

        summary = {
            'total_value':     total_value,
            'total_cost':      total_cost,
            'total_profit':    total_profit,
            'total_positions': len(positions),
            'win_rate':        win_rate
        }
        return jsonify({'success': True, 'positions': positions, 'summary': summary})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolio', methods=['POST'])
def api_add_to_portfolio():
    """Portföye ekle"""
    try:
        data = request.get_json()
        name  = data.get('portfolio_name', 'Varsayılan').strip() or 'Varsayılan'
        ticker     = str(data['ticker']).upper().strip()
        market     = data.get('market', 'US')
        entry      = float(data['entry_price'])
        quantity   = float(data['quantity'])
        stop_loss  = float(data['stop_loss'])
        buy_date   = data.get('buy_date', datetime.now().strftime('%Y-%m-%d'))
        storage.add_position(name, ticker, market, entry, quantity, buy_date, stop_loss)
        return jsonify({'success': True, 'message': f'{ticker} portföye eklendi ({name})'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolio/history', methods=['GET'])
def api_portfolio_history():
    """Portföy günlük değer geçmişi — grafik için"""
    try:
        name = request.args.get('name', 'Varsayılan')
        rows = storage.get_portfolio(name)
        if not rows:
            return jsonify({'success': True, 'dates': [], 'values': [], 'costs': []})

        purchase_dates = {}
        earliest_purchase = None
        for row in rows:
            d_str = str(row.get('alis_tarihi', '')).strip()
            try:
                d = pd.to_datetime(d_str)
                purchase_dates[row['ticker']] = d
                if earliest_purchase is None or d < earliest_purchase:
                    earliest_purchase = d
            except Exception:
                pass

        if earliest_purchase is None:
            earliest_purchase = datetime.now() - timedelta(days=90)

        chart_start = earliest_purchase - timedelta(days=90)
        end_date    = datetime.now()
        date_range  = pd.bdate_range(start=chart_start, end=end_date)

        if len(date_range) == 0:
            return jsonify({'success': True, 'dates': [], 'values': [], 'costs': []})

        ticker_prices = {}
        for row in rows:
            ticker    = row['ticker']
            yf_ticker = f"{ticker}.IS" if row['market'] == 'BIST' else ticker
            try:
                hist = yf.download(yf_ticker, start=chart_start.strftime('%Y-%m-%d'),
                                   end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                                   progress=False, auto_adjust=True)
                if not hist.empty:
                    close = hist['Close'][yf_ticker] if isinstance(hist.columns, pd.MultiIndex) and yf_ticker in hist['Close'].columns else hist['Close']
                    ticker_prices[ticker] = close
            except Exception as e:
                print(f"⚠️ Grafik veri hatası {ticker}: {e}", flush=True)

        total_cost = sum(float(r['maliyet']) * float(r['adet'] or 0) for r in rows)

        dates_out = []
        values_out = []
        costs_out  = []
        for day in date_range:
            day_value = 0
            for row in rows:
                ticker      = row['ticker']
                quantity    = float(row['adet'] or 0)
                entry_price = float(row['maliyet'])
                try:
                    purchase_date = pd.to_datetime(str(row.get('alis_tarihi', '')).strip())
                except Exception:
                    purchase_date = earliest_purchase
                if day < purchase_date:
                    day_value += entry_price * quantity
                    continue
                if ticker in ticker_prices:
                    avail = ticker_prices[ticker]
                    avail = avail[avail.index <= day]
                    price = float(avail.iloc[-1]) if len(avail) > 0 else entry_price
                else:
                    price = entry_price
                day_value += price * quantity
            dates_out.append(day.strftime('%Y-%m-%d'))
            values_out.append(round(day_value, 2))
            costs_out.append(round(total_cost, 2))

        return jsonify({'success': True, 'dates': dates_out, 'values': values_out, 'costs': costs_out,
                        'purchase_date': earliest_purchase.strftime('%Y-%m-%d') if earliest_purchase else None})
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolio/<ticker>', methods=['DELETE'])
def api_delete_from_portfolio(ticker):
    """Portföyden sil"""
    try:
        name = request.args.get('name', 'Varsayılan')
        storage.delete_position(name, ticker)
        return jsonify({'success': True, 'message': f'{ticker} portföyden silindi'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/top-picks', methods=['GET'])
def api_list_top_picks():
    try:
        return jsonify({'success': True, 'picks': storage.list_top_picks()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/top-picks', methods=['POST'])
def api_save_top_picks():
    try:
        data      = request.get_json()
        scan_date = data.get('scan_date', datetime.now().strftime('%Y-%m-%d'))
        market    = data.get('market', 'BIST')
        picks     = data.get('picks', [])
        engine    = data.get('engine', 'classic')
        storage.save_top_picks(scan_date, market, picks, engine)
        return jsonify({'success': True, 'saved': len(picks)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/top-picks/<int:pick_id>', methods=['DELETE'])
def api_delete_top_pick(pick_id):
    try:
        storage.delete_top_pick(pick_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/top-picks/session', methods=['DELETE'])
def api_delete_top_picks_session():
    try:
        data      = request.get_json()
        scan_date = data.get('scan_date', '')
        market    = data.get('market', '')
        engine    = data.get('engine', 'classic')
        storage.delete_top_picks_session(scan_date, market, engine)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/signals/history', methods=['GET'])
def api_signals_history():
    """Sinyal geçmişi"""
    try:
        signals = storage.list_signals()
        return jsonify({'success': True, 'signals': signals})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

_market_status_cache = {'data': None, 'ts': 0}

@app.route('/api/market-status', methods=['GET'])
def api_market_status():
    """BIST ve ABD piyasasının yatırım durumunu hesapla"""
    import time as _time

    force = request.args.get('force', '0') == '1'
    if not force and _market_status_cache['data'] and (_time.time() - _market_status_cache['ts']) < 900:
        return jsonify(_market_status_cache['data'])

    # Twelvedata sembol eşlemeleri (yfinance sembolü → Twelvedata sembolü)
    _TD_SYMBOLS = {
        'XU100.IS': 'XU100:BIST',
        '^GSPC':    'SPX',
        '^VIX':     'VIX',
    }

    def _fetch(symbol, period='14mo'):
        """1) Twelvedata  2) yf.Ticker.history  3) yf.download"""
        # -- Twelvedata --
        try:
            import twelvedata_client as td
            td_sym = _TD_SYMBOLS.get(symbol, symbol)
            outputsize = 400 if period in ('14mo', '1y', '2y') else 100
            df_td = td.get_time_series(td_sym, interval='1day', outputsize=outputsize)
            if df_td is not None and len(df_td) >= 200:
                return df_td['close'].astype(float).squeeze()
        except Exception:
            pass
        # -- yf.Ticker.history --
        try:
            t  = yf.Ticker(symbol)
            df = t.history(period=period, auto_adjust=True)
            if df is not None and len(df) >= 200:
                return df['Close'].squeeze()
        except Exception:
            pass
        # -- yf.download --
        try:
            df = yf.download(symbol, period=period, auto_adjust=True, progress=False, timeout=30)
            if df is not None and not df.empty and len(df) >= 200:
                return df['Close'].squeeze()
        except Exception:
            pass
        return None

    def analyze(symbol, label):
        try:
            close = _fetch(symbol)
            if close is None:
                return {'symbol': symbol, 'label': label, 'error': 'Veri indirilemedi'}
            price        = float(close.iloc[-1])
            sma50        = float(close.rolling(50).mean().iloc[-1])
            sma200       = float(close.rolling(200).mean().iloc[-1])
            sma200_30ago = float(close.rolling(200).mean().iloc[-31]) if len(close) >= 231 else sma200
            high52       = float(close.tail(252).max())
            low52        = float(close.tail(252).min())
            score = 0; criteria = []
            ok = price > sma50;  score += 1 if ok else 0
            criteria.append({'label': 'Fiyat > 50G SMA', 'ok': ok, 'detail': f'{price:.1f} vs {sma50:.1f}'})
            ok = price > sma200; score += 1 if ok else 0
            criteria.append({'label': 'Fiyat > 200G SMA', 'ok': ok, 'detail': f'{price:.1f} vs {sma200:.1f}'})
            ok = sma50 > sma200; score += 1 if ok else 0
            criteria.append({'label': '50G SMA > 200G SMA', 'ok': ok, 'detail': f'{sma50:.1f} vs {sma200:.1f}'})
            ok = sma200 > sma200_30ago; score += 1 if ok else 0
            slope_pct = ((sma200 - sma200_30ago) / sma200_30ago * 100) if sma200_30ago else 0
            criteria.append({'label': '200G SMA yükselen trend', 'ok': ok, 'detail': f'{slope_pct:+.2f}% (30 gün)'})
            dist_from_high = ((price - high52) / high52) * 100
            ok = dist_from_high >= -15; score += 1 if ok else 0
            criteria.append({'label': '52H zirveden ≤%15 uzakta', 'ok': ok, 'detail': f'{dist_from_high:.1f}% (zirve: {high52:.1f})'})
            if score == 5:   status, color, action = 'GÜÇLÜ BOĞA', 'green',  'SİSTEM AKTİF — Tam pozisyon al'
            elif score == 4: status, color, action = 'BOĞA',       'green',  'SİSTEM AKTİF — Normal pozisyon al'
            elif score == 3: status, color, action = 'KARMA',       'yellow', 'DİKKATLİ — Yarım pozisyon düşün'
            elif score == 2: status, color, action = 'ZAYIF',       'yellow', 'TEMKİNLİ — Mevcut pozisyonları koru'
            else:            status, color, action = 'AY PİYASASI', 'red',    'NAKİTTE KAL — Yeni alım yapma'
            returns = close.pct_change().dropna()
            vol20    = float(returns.tail(20).std() * (252 ** 0.5) * 100)
            vol_high = vol20 > 25; trend_ok = score >= 4
            if trend_ok and not vol_high:
                combined = {'icon': '🟢', 'text': 'Tam gaz yatırım yap', 'sub': 'Trend güçlü, volatilite normal — sistemi tam kapasite çalıştır.', 'color': '#15803d', 'bg': '#dcfce7'}
            elif trend_ok and vol_high:
                combined = {'icon': '🟡', 'text': 'Yatırım yap — pozisyon büyüklüğünü %50 azalt', 'sub': 'Trend güçlü ama piyasa sert sallanıyor. Her hisseye normal sermayenin yarısını koy.', 'color': '#92400e', 'bg': '#fef9c3'}
            else:
                combined = {'icon': '🔴', 'text': 'Nakitte kal — yeni alım yapma', 'sub': 'Trend bozuk. Mevcut döngü kapanana kadar bekle.', 'color': '#b91c1c', 'bg': '#fee2e2'}
            result = {'symbol': symbol, 'label': label, 'price': price, 'sma50': sma50, 'sma200': sma200,
                      'high52': high52, 'low52': low52, 'score': score, 'max_score': 5,
                      'status': status, 'color': color, 'action': action, 'criteria': criteria,
                      'vol20': round(vol20, 1), 'combined_decision': combined}
            if symbol == '^GSPC':
                try:
                    vc = _fetch('^VIX', period='3mo')
                    if vc is not None:
                        vix = float(vc.iloc[-1]); v5 = float(vc.tail(5).mean()); v20 = float(vc.tail(20).mean())
                        trend = 'YÜKSELIYOR' if vix > v5 else 'DÜŞÜYOR'
                        if vix < 15:   vlevel, vcomment = 'DÜŞÜK',  'Piyasa sakin'
                        elif vix < 20: vlevel, vcomment = 'NORMAL', 'Normal volatilite'
                        elif vix < 28: vlevel, vcomment = 'YÜKSEK', 'Dikkat — pozisyon küçült'
                        elif vix < 40: vlevel, vcomment = 'ALARM',  'Yüksek korku'
                        else:          vlevel, vcomment = 'PANİK',  'Panik satışı'
                        result['vix'] = {'value': round(vix,2), 'vix_5d': round(v5,2), 'vix_20d': round(v20,2), 'trend': trend, 'level': vlevel, 'comment': vcomment}
                        vix_ok = vix < 28
                        if trend_ok and not vol_high and vix_ok:
                            result['combined_decision'] = {'icon': '🟢', 'text': 'Tam gaz yatırım yap', 'sub': 'Trend güçlü, volatilite normal, VIX sakin.', 'color': '#15803d', 'bg': '#dcfce7'}
                        elif trend_ok and (vol_high or not vix_ok):
                            reasons = (['yüksek volatilite'] if vol_high else []) + ([f'VIX {vix:.0f}'] if not vix_ok else [])
                            reason_str = ', '.join(reasons)
                            result['combined_decision'] = {'icon': '🟡', 'text': 'Yatırım yap — pozisyon büyüklüğünü %50 azalt', 'sub': f'Trend güçlü ama dikkat: {reason_str}.', 'color': '#92400e', 'bg': '#fef9c3'}
                        else:
                            result['combined_decision'] = {'icon': '🔴', 'text': 'Nakitte kal — yeni alım yapma', 'sub': 'Trend bozuk.', 'color': '#b91c1c', 'bg': '#fee2e2'}
                except Exception:
                    result['vix'] = None
            return result
        except Exception as e:
            return {'symbol': symbol, 'label': label, 'error': str(e)}

    bist = analyze('XU100.IS', 'BIST (XU100)')
    us   = analyze('^GSPC', 'ABD (S&P 500)')
    payload = {'success': True, 'bist': bist, 'us': us}
    payload = _sanitize(payload)
    _market_status_cache['data'] = payload
    _market_status_cache['ts']   = _time.time()
    return jsonify(payload)



@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Genel istatistikler"""
    try:
        stats = {
            'total_scans': 0,
            'active_positions': 0,
            'total_signals': 0,
            'last_scan': None
        }
        
        # Tarama geçmişi
        scan_files = [f for f in os.listdir('.') if f.startswith('universal_scan_')]
        stats['total_scans'] = len(scan_files)
        
        if scan_files:
            latest = sorted(scan_files)[-1]
            stats['last_scan'] = latest.replace('universal_scan_', '').replace('.csv', '')
        
        # Aktif pozisyonlar
        if os.path.exists('my_portfolio.csv'):
            df = pd.read_csv('my_portfolio.csv')
            stats['active_positions'] = len(df)
        
        # Sinyaller
        if os.path.exists('sepa_signal_history.json'):
            with open('sepa_signal_history.json', 'r') as f:
                signals = json.load(f)
            stats['total_signals'] = len(signals)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'success': False, 'error': 'Server error'}), 500

# ============================================================================
# MAIN
# ============================================================================

def _sanitize(obj):
    """numpy / pandas tiplerini JSON-safe Python tiplerine çevirir. NaN → None."""
    import math
    import numpy as np
    import pandas as pd
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Series, pd.DataFrame)):
        return _sanitize(obj.to_dict())
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    # pd.NA, pd.NaT ve diğer pandas özel değerler
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass
    return obj


def _safe_jsonify(data):
    """NaN/Inf içeren veriyi güvenli JSON response'a çevirir."""
    import math
    import numpy as np

    class SafeEncoder(json.JSONEncoder):
        def default(self, obj):
            import numpy as np
            import pandas as pd
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, (pd.Series, pd.DataFrame)):
                return obj.to_dict()
            return super().default(obj)

        def encode(self, obj):
            # NaN ve Inf değerlerini null'a çevir
            result = super().encode(obj)
            return result

        def iterencode(self, obj, _one_shot=False):
            for chunk in super().iterencode(obj, _one_shot=_one_shot):
                yield chunk

    sanitized = _sanitize(data)
    resp_str = json.dumps(sanitized, cls=SafeEncoder, allow_nan=False, ensure_ascii=False)
    from flask import Response
    return Response(resp_str, mimetype='application/json')

@app.route('/api/data_source_status', methods=['GET'])
def api_data_source_status():
    """Veri kaynağı durumunu döndür"""
    try:
        import twelvedata_client as td
        usage = td.get_api_usage()
        return jsonify({
            'primary': 'Twelvedata',
            'fallback': 'Yahoo Finance',
            'usage': usage
        })
    except Exception:
        return jsonify({
            'primary': 'Yahoo Finance',
            'fallback': None,
            'usage': {}
        })

import uuid
import threading

# Aktif backtest görevleri: task_id → {status, result, error}
_backtest_tasks = {}
_backtest_lock  = threading.Lock()


def _run_backtest_task(task_id, start_date, end_date, initial_capital, market, method, frequency, portfolio_size=7):
    """Arka planda backtest çalıştır, sonucu _backtest_tasks'a yaz."""
    try:
        backtest = MinerviniBacktest(start_date, end_date, initial_capital)
        report   = backtest.run_backtest(market, method=method, frequency=frequency, portfolio_size=portfolio_size)
        report   = _sanitize(report)

        bt_id         = str(uuid.uuid4())[:8]
        freq_labels   = {'monthly': 'Aylık', 'biweekly': '15 Günlük', 'weekly': 'Haftalık'}
        method_labels = {'rs': 'RS', 'minervini': 'Minervini'}
        name = (f"{market} • {method_labels.get(method, method)} • "
                f"{freq_labels.get(frequency, frequency)} • {portfolio_size} hisse • {start_date} → {end_date}")
        params = {'start_date': start_date, 'end_date': end_date,
                  'market': market, 'method': method,
                  'frequency': frequency, 'initial_capital': initial_capital,
                  'portfolio_size': portfolio_size}
        storage.save_backtest(bt_id, name, params, report)

        with _backtest_lock:
            _backtest_tasks[task_id] = {
                'status': 'done', 'report': report,
                'saved_id': bt_id, 'saved_name': name, 'duplicate': False
            }
    except Exception as e:
        with _backtest_lock:
            _backtest_tasks[task_id] = {'status': 'error', 'error': str(e)}


@app.route('/api/backtest', methods=['POST'])
def api_run_backtest():
    """Backtest başlat — hemen task_id döndür, sonuç polling ile alınır."""
    try:
        data            = request.get_json()
        start_date      = data.get('start_date')
        end_date        = data.get('end_date')
        initial_capital = data.get('initial_capital', 100000)
        market          = data.get('market', 'US')
        method          = data.get('method', 'rs')
        frequency       = data.get('frequency', 'monthly')
        portfolio_size  = int(data.get('portfolio_size', 7))
        engine          = data.get('engine', 'classic')

        # ── Duplicate kontrolü ──────────────────────────────────────────────
        params_key  = f"{market}_{method}_{frequency}_{start_date}_{end_date}_{initial_capital}_{portfolio_size}"
        existing_id = storage.find_duplicate_backtest(params_key)
        if existing_id:
            existing = storage.get_backtest(existing_id)
            return jsonify({
                'success': True, 'status': 'done',
                'report':     existing['report'],
                'saved_id':   existing_id,
                'saved_name': existing['name'],
                'duplicate':  True,
                'message':    'Bu parametrelerle daha önce kaydedilmiş backtest bulundu.'
            })

        # ── Yeni backtest: arka planda başlat ───────────────────────────────
        task_id = str(uuid.uuid4())[:12]
        with _backtest_lock:
            _backtest_tasks[task_id] = {'status': 'running'}

        t = threading.Thread(
            target=_run_backtest_task,
            args=(task_id, start_date, end_date, initial_capital, market, method, frequency, portfolio_size),
            daemon=True
        )
        t.start()

        return jsonify({'success': True, 'status': 'running', 'task_id': task_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtest/status/<task_id>', methods=['GET'])
def api_backtest_status(task_id):
    """Backtest görev durumunu sorgula."""
    with _backtest_lock:
        task = _backtest_tasks.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Görev bulunamadı'}), 404
    if task['status'] == 'running':
        return jsonify({'success': True, 'status': 'running'})
    if task['status'] == 'error':
        return jsonify({'success': False, 'status': 'error', 'error': task['error']})
    # done
    result = dict(task)
    result['success'] = True
    # Tamamlanan görevi bellekten temizle
    with _backtest_lock:
        _backtest_tasks.pop(task_id, None)
    return jsonify(result)


@app.route('/api/backtests', methods=['GET'])
def api_list_backtests():
    """Kaydedilmiş backtestleri listele"""
    try:
        items = storage.list_backtests()
        return jsonify({'success': True, 'backtests': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backtests/<bt_id>', methods=['GET'])
def api_get_backtest(bt_id):
    """Kaydedilmiş backtest'i yükle"""
    try:
        data = storage.get_backtest(bt_id)
        if not data:
            return jsonify({'success': False, 'error': 'Backtest bulunamadı'}), 404
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backtests/<bt_id>', methods=['DELETE'])
def api_delete_backtest(bt_id):
    """Kaydedilmiş backtest'i sil"""
    try:
        storage.delete_backtest(bt_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _clean_data_cache(max_age_days=30):
    """data_cache/ klasöründe 30 günden eski .pkl dosyalarını temizler."""
    import time as _t
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_cache')
    if not os.path.isdir(cache_dir):
        return
    now = _t.time()
    removed = 0
    for fname in os.listdir(cache_dir):
        if not fname.endswith('.pkl'):
            continue
        fpath = os.path.join(cache_dir, fname)
        age_days = (now - os.path.getmtime(fpath)) / 86400
        if age_days > max_age_days:
            try:
                os.remove(fpath)
                removed += 1
            except Exception:
                pass
    if removed:
        print(f'🗑️  data_cache temizlendi: {removed} eski dosya silindi', flush=True)


if __name__ == '__main__':
    storage.init_db()
    _clean_data_cache(max_age_days=30)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)

    print("=" * 80)
    print("🚀 MARK MINERVINI TRADING PLATFORM")
    print("=" * 80)
    port = int(os.environ.get('PORT', 5555))
    host = '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1'
    print(f"\n✅ Server başlatılıyor...")
    print(f"📡 URL: http://localhost:{port}")
    print(f"📊 Dashboard: http://localhost:{port}")
    print(f"🔍 Scanner: http://localhost:{port}/scanner")
    print(f"💼 Portfolio: http://localhost:{port}/portfolio")
    print("\n⚠️  Durdurmak için Ctrl+C\n")

    app.run(debug=False, host=host, port=port, use_reloader=False)
