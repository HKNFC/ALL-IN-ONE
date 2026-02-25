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

def _scan_with_progress(bt, scan_dt, market, tickers_override):
    """BacktestEngine taramasını ilerleme takibi ile çalıştırır."""
    cutoff  = pd.Timestamp(scan_dt).normalize()
    total   = len(tickers_override)

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
            bt = MinerviniBacktest(scan_date, scan_date)
            scan_dt = pd.Timestamp(scan_date)

            # BIST için scan_type'a uygun ticker listesi belirle
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

            # Gerçek zamanlı ilerleme için scan_market_at_date'i aşamalı çalıştır
            results = _scan_with_progress(bt, scan_dt, market, tickers_override)

            _set_progress(100, f'Tamamlandı — {len(results)} hisse bulundu')
            return jsonify(_sanitize({
                'success': True,
                'count': len(results),
                'results': results,
                'market': market,
                'scan_date': scan_date,
                'timestamp': datetime.now().isoformat()
            }))

        # ── BUGÜN: canlı tarama (mevcut mantık) ──
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
            return jsonify(_sanitize({
                'success': True, 'count': len(us_results), 'results': us_results,
                'market': 'US', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            }))

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
            return jsonify(_sanitize({
                'success': True, 'count': len(bist_results), 'results': bist_results,
                'market': 'BIST', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            }))

        else:  # BOTH
            results = scanner.run_universal_scan()
            return jsonify(_sanitize({
                'success': True, 'count': len(results), 'results': results,
                'market': 'BOTH', 'scan_date': 'today', 'timestamp': datetime.now().isoformat()
            }))

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
    safe = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-', 'ğüşıöçĞÜŞİÖÇ')).strip()
    return os.path.join(PORTFOLIOS_DIR, f"{safe}.csv")

@app.route('/api/portfolios/summary', methods=['GET'])
def api_portfolios_summary():
    """Tüm portföylerin özet istatistiklerini döndür"""
    try:
        summaries = []
        files = sorted(f[:-4] for f in os.listdir(PORTFOLIOS_DIR) if f.endswith('.csv'))
        for name in files:
            path = _portfolio_path(name)
            try:
                df = pd.read_csv(path)
                if df.empty:
                    summaries.append({'name': name, 'total_value': 0, 'total_cost': 0,
                                      'total_profit': 0, 'total_pct': 0, 'win_rate': 0, 'count': 0})
                    continue

                total_cost = total_value = 0.0
                winners = 0
                count = len(df)

                for _, row in df.iterrows():
                    entry  = float(row['Maliyet'])
                    qty    = float(row['Adet']) if not pd.isna(row['Adet']) else 0
                    cost   = entry * qty
                    total_cost += cost
                    try:
                        ticker     = str(row['Ticker'])
                        yf_ticker  = ticker + '.IS' if (str(row.get('Market','US')) == 'BIST') else ticker
                        hist       = yf.Ticker(yf_ticker).history(period='1d')
                        cur_price  = float(hist['Close'].iloc[-1]) if len(hist) > 0 else entry
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
                    'total_value': round(total_value, 2),
                    'total_cost':  round(total_cost,  2),
                    'total_profit': round(profit, 2),
                    'total_pct':   round(pct, 2),
                    'win_rate':    round(win_rate, 1),
                })
            except Exception:
                summaries.append({'name': name, 'total_value': 0, 'total_cost': 0,
                                  'total_profit': 0, 'total_pct': 0, 'win_rate': 0, 'count': 0})

        return jsonify({'success': True, 'summaries': summaries})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolios', methods=['GET'])
def api_list_portfolios():
    """Tüm portföyleri listele"""
    try:
        files = [f[:-4] for f in os.listdir(PORTFOLIOS_DIR) if f.endswith('.csv')]
        return jsonify({'success': True, 'portfolios': sorted(files)})
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
        path = _portfolio_path(name)
        if os.path.exists(path):
            return jsonify({'success': False, 'error': 'Bu isimde portföy zaten var'}), 400
        df = pd.DataFrame(columns=['Ticker','Maliyet','Adet','Alış_Tarihi','Stop_Seviyesi','Backstop_Aktif'])
        df.to_csv(path, index=False)
        return jsonify({'success': True, 'name': name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolios/<name>', methods=['DELETE'])
def api_delete_portfolio(name):
    """Portföy sil"""
    try:
        path = _portfolio_path(name)
        if os.path.exists(path):
            os.remove(path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolio', methods=['GET'])
def api_get_portfolio():
    """Portföy getir"""
    try:
        name = request.args.get('name', 'Varsayılan')
        path = _portfolio_path(name)
        if not os.path.exists(path):
            return jsonify({'success': True, 'positions': [], 'summary': {'total_value': 0, 'total_profit': 0, 'total_positions': 0, 'win_rate': 0}})

        df = pd.read_csv(path)

        # Güncel fiyatları çek
        positions = []
        total_value = 0
        total_cost = 0

        for _, row in df.iterrows():
            ticker = row['Ticker']
            entry_price = row['Maliyet']
            quantity = row['Adet']
            stop_loss = row['Stop_Seviyesi']

            # NaN kontrolü
            if pd.isna(quantity):
                quantity = 0

            # Güncel fiyat çek
            try:
                # Market sütunu varsa kullan, yoksa heuristic
                if 'Market' in row.index and pd.notna(row['Market']) and str(row['Market']).strip():
                    is_bist = str(row['Market']).upper().strip() == 'BIST'
                else:
                    is_bist = str(ticker).isalpha() and len(str(ticker)) <= 6 and not any(c in str(ticker) for c in ['.', '-'])

                yahoo_ticker = f"{ticker}.IS" if is_bist else str(ticker)
                stock = yf.Ticker(yahoo_ticker)

                # fast_info ile önce dene (hızlı, güvenilir)
                current_price = None
                try:
                    fi = stock.fast_info
                    p = fi.get('last_price') or fi.get('regularMarketPrice')
                    if p and float(p) > 0:
                        current_price = float(p)
                except Exception:
                    pass

                # fast_info başarısız → history dene
                if not current_price:
                    hist = stock.history(period='5d')
                    if len(hist) > 0:
                        current_price = float(hist['Close'].iloc[-1])

                if not current_price:
                    current_price = float(entry_price)

            except Exception as e:
                print(f"⚠️ Fiyat çekme hatası {ticker}: {e}", flush=True)
                current_price = float(entry_price)

            cost_basis = entry_price * quantity
            current_value = current_price * quantity
            total_cost += cost_basis
            total_value += current_value

            positions.append({
                'ticker': ticker,
                'market': str(row['Market']) if 'Market' in row.index and pd.notna(row['Market']) else ('BIST' if str(ticker).isalpha() and len(str(ticker)) <= 6 else 'US'),
                'entry_price': float(entry_price),
                'current_price': float(current_price),
                'quantity': float(quantity),
                'stop_loss': float(stop_loss),
                'cost_basis': float(cost_basis),
                'current_value': float(current_value),
                'purchase_date': row.get('Alış_Tarihi', 'N/A')
            })

        total_profit = total_value - total_cost
        winning = sum(1 for p in positions if p['current_value'] > p['cost_basis'])
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
        name = data.get('portfolio_name', 'Varsayılan').strip() or 'Varsayılan'
        path = _portfolio_path(name)

        if os.path.exists(path):
            df = pd.read_csv(path)
        else:
            df = pd.DataFrame(columns=['Ticker', 'Maliyet', 'Adet', 'Alış_Tarihi', 'Stop_Seviyesi', 'Backstop_Aktif'])

        new_row = {
            'Ticker': data['ticker'],
            'Market': data.get('market', 'US'),
            'Maliyet': data['entry_price'],
            'Adet': data['quantity'],
            'Alış_Tarihi': datetime.now().strftime('%Y-%m-%d'),
            'Stop_Seviyesi': data['stop_loss'],
            'Backstop_Aktif': False
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(path, index=False)

        return jsonify({'success': True, 'message': f'{data["ticker"]} portföye eklendi ({name})'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/portfolio/history', methods=['GET'])
def api_portfolio_history():
    """Portföy günlük değer geçmişi — grafik için"""
    try:
        name = request.args.get('name', 'Varsayılan')
        path = _portfolio_path(name)
        if not os.path.exists(path):
            return jsonify({'success': True, 'dates': [], 'values': [], 'costs': []})

        df = pd.read_csv(path)
        if df.empty:
            return jsonify({'success': True, 'dates': [], 'values': [], 'costs': []})

        # En eski alış tarihi → bugün
        min_date = None
        for _, row in df.iterrows():
            d_str = str(row.get('Alış_Tarihi', '')).strip()
            try:
                d = pd.to_datetime(d_str)
                if min_date is None or d < min_date:
                    min_date = d
            except Exception:
                pass

        if min_date is None:
            min_date = datetime.now() - timedelta(days=90)

        end_date = datetime.now()
        date_range = pd.bdate_range(start=min_date, end=end_date)

        if len(date_range) == 0:
            return jsonify({'success': True, 'dates': [], 'values': [], 'costs': []})

        # Her hisse için tarihi fiyatları çek
        ticker_prices = {}
        for _, row in df.iterrows():
            ticker = str(row['Ticker'])
            if 'Market' in row.index and pd.notna(row['Market']):
                is_bist = str(row['Market']).upper().strip() == 'BIST'
            else:
                is_bist = str(ticker).isalpha() and len(str(ticker)) <= 6

            yahoo_ticker = f"{ticker}.IS" if is_bist else ticker
            try:
                hist = yf.download(
                    yahoo_ticker,
                    start=min_date.strftime('%Y-%m-%d'),
                    end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                    progress=False,
                    auto_adjust=True
                )
                if not hist.empty:
                    if isinstance(hist.columns, pd.MultiIndex):
                        close = hist['Close'][yahoo_ticker] if yahoo_ticker in hist['Close'].columns else hist['Close'].iloc[:, 0]
                    else:
                        close = hist['Close']
                    ticker_prices[ticker] = close
            except Exception as e:
                print(f"⚠️ Grafik veri hatası {ticker}: {e}", flush=True)

        # Günlük portföy değeri hesapla
        dates_out = []
        values_out = []
        costs_out = []

        total_cost = 0
        for _, row in df.iterrows():
            entry_price = float(row['Maliyet'])
            quantity = float(row['Adet']) if not pd.isna(row['Adet']) else 0
            total_cost += entry_price * quantity

        for day in date_range:
            day_value = 0
            for _, row in df.iterrows():
                ticker = str(row['Ticker'])
                quantity = float(row['Adet']) if not pd.isna(row['Adet']) else 0
                entry_price = float(row['Maliyet'])

                # Alış tarihinden önce → maliyet kullan
                try:
                    purchase_date = pd.to_datetime(str(row.get('Alış_Tarihi', '')).strip())
                except Exception:
                    purchase_date = min_date

                if day < purchase_date:
                    day_value += entry_price * quantity
                    continue

                if ticker in ticker_prices:
                    prices = ticker_prices[ticker]
                    # O güne en yakın önceki fiyatı bul
                    available = prices[prices.index <= day]
                    if len(available) > 0:
                        price = float(available.iloc[-1])
                    else:
                        price = entry_price
                else:
                    price = entry_price

                day_value += price * quantity

            dates_out.append(day.strftime('%Y-%m-%d'))
            values_out.append(round(day_value, 2))
            costs_out.append(round(total_cost, 2))

        return jsonify({
            'success': True,
            'dates': dates_out,
            'values': values_out,
            'costs': costs_out
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolio/<ticker>', methods=['DELETE'])
def api_delete_from_portfolio(ticker):
    """Portföyden sil"""
    try:
        name = request.args.get('name', 'Varsayılan')
        path = _portfolio_path(name)
        if not os.path.exists(path):
            return jsonify({'success': False, 'error': 'Portföy bulunamadı'}), 404

        df = pd.read_csv(path)
        df = df[df['Ticker'] != ticker.upper()]
        df.to_csv(path, index=False)

        return jsonify({'success': True, 'message': f'{ticker} portföyden silindi'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/signals/history', methods=['GET'])
def api_signals_history():
    """Sinyal geçmişi"""
    try:
        if os.path.exists('sepa_signal_history.json'):
            with open('sepa_signal_history.json', 'r') as f:
                signals = json.load(f)
            
            return jsonify({
                'success': True,
                'signals': signals
            })
        else:
            return jsonify({
                'success': True,
                'signals': []
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/market-status', methods=['GET'])
def api_market_status():
    """BIST ve ABD piyasasının yatırım durumunu hesapla"""
    def analyze(symbol, label):
        try:
            df = yf.download(symbol, period='14mo', auto_adjust=True, progress=False)
            if df.empty or len(df) < 200:
                return None
            close = df['Close'].squeeze()
            price        = float(close.iloc[-1])
            sma50        = float(close.rolling(50).mean().iloc[-1])
            sma200       = float(close.rolling(200).mean().iloc[-1])
            sma200_30ago = float(close.rolling(200).mean().iloc[-31]) if len(close) >= 231 else sma200
            high52       = float(close.tail(252).max())
            low52        = float(close.tail(252).min())

            score = 0
            criteria = []

            ok = price > sma50
            score += 1 if ok else 0
            criteria.append({'label': 'Fiyat > 50G SMA', 'ok': ok, 'detail': f'{price:.1f} vs {sma50:.1f}'})

            ok = price > sma200
            score += 1 if ok else 0
            criteria.append({'label': 'Fiyat > 200G SMA', 'ok': ok, 'detail': f'{price:.1f} vs {sma200:.1f}'})

            ok = sma50 > sma200
            score += 1 if ok else 0
            criteria.append({'label': '50G SMA > 200G SMA', 'ok': ok, 'detail': f'{sma50:.1f} vs {sma200:.1f}'})

            ok = sma200 > sma200_30ago
            score += 1 if ok else 0
            slope_pct = ((sma200 - sma200_30ago) / sma200_30ago * 100) if sma200_30ago else 0
            criteria.append({'label': '200G SMA yükselen trend', 'ok': ok, 'detail': f'{slope_pct:+.2f}% (30 gün)'})

            dist_from_high = ((price - high52) / high52) * 100
            ok = dist_from_high >= -15
            score += 1 if ok else 0
            criteria.append({'label': '52H zirveden ≤%15 uzakta', 'ok': ok, 'detail': f'{dist_from_high:.1f}% (zirve: {high52:.1f})'})

            if score == 5:
                status = 'GÜÇLÜ BOĞA'; color = 'green'; action = 'SİSTEM AKTİF — Tam pozisyon al'
            elif score == 4:
                status = 'BOĞA'; color = 'green'; action = 'SİSTEM AKTİF — Normal pozisyon al'
            elif score == 3:
                status = 'KARMA'; color = 'yellow'; action = 'DİKKATLİ — Yarım pozisyon düşün'
            elif score == 2:
                status = 'ZAYIF'; color = 'yellow'; action = 'TEMKİNLİ — Mevcut pozisyonları koru'
            else:
                status = 'AY PİYASASI'; color = 'red'; action = 'NAKİTTE KAL — Yeni alım yapma'

            # Volatilite hesapla (20 günlük gerçekleşmiş vol, yıllıklaştırılmış)
            returns = close.pct_change().dropna()
            vol20 = float(returns.tail(20).std() * (252 ** 0.5) * 100)

            result = {
                'symbol': symbol, 'label': label,
                'price': price, 'sma50': sma50, 'sma200': sma200,
                'high52': high52, 'low52': low52,
                'score': score, 'max_score': 5,
                'status': status, 'color': color, 'action': action,
                'criteria': criteria,
                'vol20': round(vol20, 1),
            }

            # Birleşik karar
            vol_high = vol20 > 25
            trend_ok = score >= 4

            if trend_ok and not vol_high:
                combined = {'icon': '🟢', 'text': 'Tam gaz yatırım yap', 'sub': 'Trend güçlü, volatilite normal — sistemi tam kapasite çalıştır.', 'color': '#15803d', 'bg': '#dcfce7'}
            elif trend_ok and vol_high:
                combined = {'icon': '🟡', 'text': 'Yatırım yap — pozisyon büyüklüğünü %50 azalt', 'sub': 'Trend güçlü ama piyasa sert sallanıyor. Her hisseye normal sermayenin yarısını koy.', 'color': '#92400e', 'bg': '#fef9c3'}
            else:
                combined = {'icon': '🔴', 'text': 'Nakitte kal — yeni alım yapma', 'sub': 'Trend bozuk. Mevcut döngü kapanana kadar bekle.', 'color': '#b91c1c', 'bg': '#fee2e2'}

            result['combined_decision'] = combined
            if symbol == '^GSPC':
                try:
                    vdf   = yf.download('^VIX', period='3mo', auto_adjust=True, progress=False)
                    vc    = vdf['Close'].squeeze()
                    vix   = float(vc.iloc[-1])
                    v5    = float(vc.tail(5).mean())
                    v20   = float(vc.tail(20).mean())
                    trend = 'YÜKSELIYOR' if vix > v5 else 'DÜŞÜYOR'
                    if vix < 15:
                        vlevel = 'DÜŞÜK'; vcomment = 'Piyasa sakin'
                    elif vix < 20:
                        vlevel = 'NORMAL'; vcomment = 'Normal volatilite'
                    elif vix < 28:
                        vlevel = 'YÜKSEK'; vcomment = 'Dikkat — pozisyon küçült'
                    elif vix < 40:
                        vlevel = 'ALARM'; vcomment = 'Yüksek korku'
                    else:
                        vlevel = 'PANIK'; vcomment = 'Panik satışı'
                    result['vix'] = {'value': round(vix,2), 'vix_5d': round(v5,2),
                                     'vix_20d': round(v20,2), 'trend': trend,
                                     'level': vlevel, 'comment': vcomment}
                    # ABD için VIX'i de birleşik karara yansıt
                    vix_ok = vix < 28
                    if trend_ok and not vol_high and vix_ok:
                        result['combined_decision'] = {'icon': '🟢', 'text': 'Tam gaz yatırım yap', 'sub': 'Trend güçlü, volatilite normal, VIX sakin — sistemi tam kapasite çalıştır.', 'color': '#15803d', 'bg': '#dcfce7'}
                    elif trend_ok and (vol_high or not vix_ok):
                        reasons = []
                        if vol_high: reasons.append('yüksek volatilite')
                        if not vix_ok: reasons.append(f'VIX {vix:.0f}')
                        result['combined_decision'] = {'icon': '🟡', 'text': 'Yatırım yap — pozisyon büyüklüğünü %50 azalt', 'sub': f'Trend güçlü ama dikkat: {", ".join(reasons)}. Her hisseye normal sermayenin yarısını koy.', 'color': '#92400e', 'bg': '#fef9c3'}
                    else:
                        result['combined_decision'] = {'icon': '🔴', 'text': 'Nakitte kal — yeni alım yapma', 'sub': 'Trend bozuk. Mevcut döngü kapanana kadar bekle.', 'color': '#b91c1c', 'bg': '#fee2e2'}
                except Exception:
                    result['vix'] = None

            return result
        except Exception as e:
            return {'symbol': symbol, 'label': label, 'error': str(e)}

    bist = analyze('XU100.IS', 'BIST (XU100)')
    us   = analyze('^GSPC', 'ABD (S&P 500)')

    return jsonify({'success': True, 'bist': bist, 'us': us})


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
    return obj

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

BACKTESTS_DIR = os.path.join(os.path.dirname(__file__), 'backtests')
os.makedirs(BACKTESTS_DIR, exist_ok=True)

@app.route('/api/backtests', methods=['GET'])
def api_list_backtests():
    """Kaydedilmiş backtestleri listele"""
    try:
        items = []
        for fname in sorted(os.listdir(BACKTESTS_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(BACKTESTS_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                items.append({
                    'id':         meta['id'],
                    'name':       meta['name'],
                    'created_at': meta['created_at'],
                    'params':     meta['params'],
                    'summary':    meta.get('report', {}).get('summary', {})
                })
            except Exception:
                continue
        return jsonify({'success': True, 'backtests': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backtests/<bt_id>', methods=['GET'])
def api_get_backtest(bt_id):
    """Kaydedilmiş backtest'i yükle"""
    try:
        fpath = os.path.join(BACKTESTS_DIR, f"{bt_id}.json")
        if not os.path.exists(fpath):
            return jsonify({'success': False, 'error': 'Backtest bulunamadı'}), 404
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backtests/<bt_id>', methods=['DELETE'])
def api_delete_backtest(bt_id):
    """Kaydedilmiş backtest'i sil"""
    try:
        fpath = os.path.join(BACKTESTS_DIR, f"{bt_id}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backtest', methods=['POST'])
def api_run_backtest():
    """Backtest çalıştır ve otomatik kaydet"""
    try:
        data = request.get_json()
        start_date      = data.get('start_date')
        end_date        = data.get('end_date')
        initial_capital = data.get('initial_capital', 100000)
        market          = data.get('market', 'US')
        method          = data.get('method', 'rs')
        frequency       = data.get('frequency', 'monthly')

        # ── Duplicate kontrolü: aynı parametreli backtest var mı? ──────────
        params_key = f"{market}_{method}_{frequency}_{start_date}_{end_date}_{initial_capital}"
        existing_id = None
        for fname in os.listdir(BACKTESTS_DIR):
            if not fname.endswith('.json'):
                continue
            try:
                with open(os.path.join(BACKTESTS_DIR, fname), encoding='utf-8') as f:
                    rec = json.load(f)
                p = rec.get('params', {})
                k = f"{p.get('market')}_{p.get('method')}_{p.get('frequency')}_{p.get('start_date')}_{p.get('end_date')}_{p.get('initial_capital', 100000)}"
                if k == params_key:
                    existing_id = rec['id']
                    break
            except Exception:
                continue

        if existing_id:
            # Aynı parametreli backtest zaten var — mevcut sonucu döndür
            with open(os.path.join(BACKTESTS_DIR, f"{existing_id}.json"), encoding='utf-8') as f:
                existing = json.load(f)
            return jsonify({
                'success':    True,
                'report':     existing['report'],
                'saved_id':   existing_id,
                'saved_name': existing['name'],
                'duplicate':  True,
                'message':    'Bu parametrelerle daha önce kaydedilmiş backtest bulundu. Mevcut sonuç döndürüldü.'
            })

        # ── Yeni backtest çalıştır ──────────────────────────────────────────
        backtest = MinerviniBacktest(start_date, end_date, initial_capital)
        report   = backtest.run_backtest(market, method=method, frequency=frequency)
        report   = _sanitize(report)

        bt_id   = str(uuid.uuid4())[:8]
        freq_labels   = {'monthly': 'Aylık', 'biweekly': '15 Günlük', 'weekly': 'Haftalık'}
        method_labels = {'rs': 'RS', 'minervini': 'Minervini'}
        name = f"{market} • {method_labels.get(method, method)} • {freq_labels.get(frequency, frequency)} • {start_date} → {end_date}"
        record = {
            'id':         bt_id,
            'name':       name,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'params':     {'start_date': start_date, 'end_date': end_date,
                           'market': market, 'method': method,
                           'frequency': frequency, 'initial_capital': initial_capital},
            'report':     report
        }
        fpath = os.path.join(BACKTESTS_DIR, f"{bt_id}.json")
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False)

        return jsonify({'success': True, 'report': report, 'saved_id': bt_id, 'saved_name': name, 'duplicate': False})

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
    _clean_data_cache(max_age_days=30)
    # Klasörleri oluştur
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("=" * 80)
    print("🚀 MARK MINERVINI TRADING PLATFORM")
    print("=" * 80)
    print("\n✅ Server başlatılıyor...")
    print(f"📡 URL: http://localhost:5555")
    print(f"📊 Dashboard: http://localhost:5555")
    print(f"🔍 Scanner: http://localhost:5555/scanner")
    print(f"💼 Portfolio: http://localhost:5555/portfolio")
    print("\n⚠️  Durdurmak için Ctrl+C\n")
    
    app.run(debug=False, host='127.0.0.1', port=5555, use_reloader=False)
