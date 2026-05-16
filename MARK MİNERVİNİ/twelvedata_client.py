"""
Twelvedata API Client
- Birincil veri kaynağı: Twelvedata
- Fallback: Yahoo Finance
- BIST hisseleri: TICKER:BIST formatı
- US hisseleri: TICKER:NASDAQ veya TICKER:NYSE
"""

import requests
import pandas as pd
import time
import io
import contextlib
from datetime import datetime, timedelta
from config import TWELVEDATA_API_KEY

BASE_URL = "https://api.twelvedata.com"

# Önbellek — aynı istek tekrar gelmez
_cache = {}


def _cache_key(symbol, start, end, interval):
    return f"{symbol}_{start}_{end}_{interval}"


def _to_df(raw_values, symbol):
    """Twelvedata time_series JSON → OHLCV DataFrame"""
    if not raw_values:
        return pd.DataFrame()
    rows = []
    for v in raw_values:
        try:
            rows.append({
                'Open':   float(v['open']),
                'High':   float(v['high']),
                'Low':    float(v['low']),
                'Close':  float(v['close']),
                'Volume': float(v['volume']),
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    dates = [pd.Timestamp(v['datetime']) for v in raw_values[:len(rows)]]
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    df.index.name = 'Date'
    return df.sort_index()


def _yf_fallback(symbol, start_str, end_str):
    """Yahoo Finance fallback"""
    try:
        import yfinance as yf
        yf_sym = symbol.replace(':BIST', '.IS').split(':')[0] if ':' in symbol else symbol
        with contextlib.redirect_stderr(io.StringIO()), \
             contextlib.redirect_stdout(io.StringIO()):
            df = yf.download(yf_sym, start=start_str, end=end_str,
                             auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return pd.DataFrame()


def get_time_series(symbol, start_date, end_date, interval='1day'):
    """
    Tek hisse için OHLCV DataFrame döndür.
    symbol örnekleri:
      'AAPL', 'MSFT'           → US hissesi
      'THYAO:BIST', 'GARAN'    → BIST hissesi (.IS uzantısı kaldırılır)
    """
    # .IS uzantısını kaldır, :BIST ekle
    if symbol.endswith('.IS'):
        symbol = symbol[:-3] + ':BIST'

    start_str = pd.Timestamp(start_date).strftime('%Y-%m-%d')
    end_str   = pd.Timestamp(end_date).strftime('%Y-%m-%d')
    key = _cache_key(symbol, start_str, end_str, interval)

    if key in _cache:
        return _cache[key]

    try:
        params = {
            'symbol':     symbol,
            'interval':   interval,
            'start_date': start_str + ' 00:00:00',
            'end_date':   end_str   + ' 23:59:59',
            'outputsize': 800,
            'apikey':     TWELVEDATA_API_KEY,
            'format':     'JSON',
        }
        r = requests.get(f"{BASE_URL}/time_series", params=params, timeout=15)
        data = r.json()

        if data.get('status') == 'ok' and 'values' in data:
            df = _to_df(data['values'], symbol)
            if not df.empty:
                _cache[key] = df
                return df

        # API hatası — fallback
        yf_sym = symbol.replace(':BIST', '.IS') if ':BIST' in symbol else symbol
        df = _yf_fallback(yf_sym, start_str, end_str)
        if not df.empty:
            _cache[key] = df
        return df

    except Exception:
        yf_sym = symbol.replace(':BIST', '.IS') if ':BIST' in symbol else symbol
        df = _yf_fallback(yf_sym, start_str, end_str)
        if not df.empty:
            _cache[key] = df
        return df


def get_batch_time_series(symbols, start_date, end_date, interval='1day',
                          batch_size=55, sleep_sec=0.2):
    """
    Birden fazla hisse için toplu veri çek.
    Twelvedata Growth plan: 55 sembol/istek
    Returns: {symbol: DataFrame}
    """
    start_str = pd.Timestamp(start_date).strftime('%Y-%m-%d')
    end_str   = pd.Timestamp(end_date).strftime('%Y-%m-%d')

    # Önbellekte olmayanları bul
    results = {}
    missing = []
    for sym in symbols:
        clean = sym[:-3] + ':BIST' if sym.endswith('.IS') else sym
        key = _cache_key(clean, start_str, end_str, interval)
        if key in _cache:
            results[sym] = _cache[key]
        else:
            missing.append(sym)

    if not missing:
        return results

    # Batch olarak çek
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i + batch_size]
        clean_batch = [s[:-3] + ':BIST' if s.endswith('.IS') else s for s in batch]
        sym_str = ','.join(clean_batch)

        try:
            params = {
                'symbol':     sym_str,
                'interval':   interval,
                'start_date': start_str + ' 00:00:00',
                'end_date':   end_str   + ' 23:59:59',
                'outputsize': 800,
                'apikey':     TWELVEDATA_API_KEY,
                'format':     'JSON',
            }
            r = requests.get(f"{BASE_URL}/time_series", params=params, timeout=30)
            data = r.json()

            if len(batch) == 1:
                # Tek sembol → doğrudan dönüyor
                orig = batch[0]
                clean = clean_batch[0]
                if data.get('status') == 'ok' and 'values' in data:
                    df = _to_df(data['values'], clean)
                    key = _cache_key(clean, start_str, end_str, interval)
                    _cache[key] = df
                    results[orig] = df
                else:
                    results[orig] = pd.DataFrame()  # fallback yok — hızlı geç
            else:
                # Çoklu sembol → dict dönüyor
                for orig, clean in zip(batch, clean_batch):
                    sym_data = data.get(clean, {})
                    if sym_data.get('status') == 'ok' and 'values' in sym_data:
                        df = _to_df(sym_data['values'], clean)
                        key = _cache_key(clean, start_str, end_str, interval)
                        if not df.empty:
                            _cache[key] = df
                        results[orig] = df
                    else:
                        results[orig] = pd.DataFrame()  # fallback yok — hızlı geç

        except Exception as e:
            # Hata durumunda boş DataFrame — yavaş fallback yok
            for orig in batch:
                results[orig] = pd.DataFrame()

        if i + batch_size < len(missing):
            time.sleep(sleep_sec)

    return results


def get_bist_tickers():
    """Twelvedata'dan tüm BIST hisselerini çek"""
    try:
        r = requests.get(
            f"{BASE_URL}/stocks",
            params={'exchange': 'BIST', 'apikey': TWELVEDATA_API_KEY, 'format': 'JSON'},
            timeout=15
        )
        data = r.json()
        stocks = data.get('data', [])
        if len(stocks) > 100:
            # Yahoo Finance formatına çevir (SYMBOL.IS)
            tickers = [f"{s['symbol']}.IS" for s in stocks]
            print(f"✅ Twelvedata BIST: {len(tickers)} hisse yüklendi!")
            return tickers
    except Exception as e:
        print(f"⚠️ Twelvedata BIST liste hatası: {e}")
    return []


def get_us_tickers():
    """Twelvedata'dan S&P500 + NASDAQ100 hisselerini çek (sadece büyük endeksler)"""
    try:
        # Twelvedata'nın endeks bileşenlerini kullan — sadece major index üyeleri
        # S&P 500 = exchange NASDAQ/NYSE + country US + type='Common Stock'
        tickers = set()
        for exchange in ['NASDAQ', 'NYSE']:
            r = requests.get(
                f"{BASE_URL}/stocks",
                params={
                    'exchange': exchange,
                    'apikey': TWELVEDATA_API_KEY,
                    'format': 'JSON',
                    'country': 'United States',
                    'type': 'Common Stock',
                },
                timeout=15
            )
            data = r.json()
            stocks = data.get('data', [])
            for s in stocks:
                sym = s.get('symbol', '')
                # Sadece 1-5 harf, saf hisse (warrant/preferred değil)
                if sym and 1 <= len(sym) <= 5 and sym.replace('-','').isalpha():
                    tickers.add(sym)

        # Wikipedia S&P500 ile kesişim alarak sadece endeks üyelerini seç
        try:
            import bs4, requests as _req
            r2 = _req.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                         headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            soup = bs4.BeautifulSoup(r2.content, 'html.parser')
            table = soup.find('table', {'id': 'constituents'})
            sp500 = set()
            if table:
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all('td')
                    if cells:
                        sp500.add(cells[0].text.strip().replace('.', '-'))
            # S&P500 üyeleri + Twelvedata'da olanlar
            result = sorted(tickers & sp500) if sp500 else sorted(tickers)
            # S&P500'de olmayan ama önemli NASDAQ hisselerini ekle
            nasdaq_extra = {'AAPL','MSFT','GOOGL','AMZN','META','NVDA','TSLA','AVGO',
                           'COST','NFLX','AMD','QCOM','AMAT','CRWD','PANW','MRVL',
                           'PLTR','APP','TTD','CELH','AXON','FICO','DDOG','NET',
                           'SMCI','ARM','MELI','SE','SHOP','UBER','ABNB','COIN'}
            result = sorted(set(result) | nasdaq_extra)
        except Exception:
            result = sorted(tickers)

        if len(result) > 100:
            print(f"✅ Twelvedata US: {len(result)} hisse yüklendi!")
            return result

    except Exception as e:
        print(f"⚠️ Twelvedata US liste hatası: {e}")
    return []


def get_api_usage():
    """API kullanım durumunu döndür"""
    try:
        r = requests.get(f"{BASE_URL}/api_usage",
                         params={'apikey': TWELVEDATA_API_KEY}, timeout=10)
        return r.json()
    except Exception as e:
        return {'error': str(e)}
