"""
Price Cross-Validator
=====================
Twelvedata ve Yahoo Finance fiyatlarını karşılaştırır.
İki kaynak arasında %3'ten fazla fark varsa uyarı üretir.
Tarama sonuçlarına 'data_warning' alanı eklenir.
"""

import yfinance as yf
import requests
import time
from datetime import datetime, timedelta
from typing import Optional

# Hız sınırlaması için basit throttle
_last_td_call = 0
_TD_MIN_INTERVAL = 0.15  # saniye


def _td_price(ticker: str, is_bist: bool) -> Optional[float]:
    """Twelvedata'dan anlık kapanış fiyatı çek."""
    global _last_td_call
    try:
        elapsed = time.time() - _last_td_call
        if elapsed < _TD_MIN_INTERVAL:
            time.sleep(_TD_MIN_INTERVAL - elapsed)

        symbol = f"{ticker}:BIST" if is_bist else ticker
        url = "https://api.twelvedata.com/price"
        params = {
            "symbol": symbol,
            "apikey": TWELVEDATA_API_KEY,
            "outputsize": 1,
        }
        r = requests.get(url, params=params, timeout=8)
        _last_td_call = time.time()
        data = r.json()
        price = data.get("price")
        if price:
            return float(price)
    except Exception:
        pass
    return None


def _yf_price(ticker: str, is_bist: bool) -> Optional[float]:
    """Yahoo Finance'den anlık fiyat çek."""
    try:
        yt = f"{ticker}.IS" if is_bist else ticker
        t = yf.Ticker(yt)
        fi = t.fast_info
        p = getattr(fi, 'last_price', None) or getattr(fi, 'previous_close', None)
        if p and float(p) > 0:
            return float(p)
        hist = t.history(period="5d", auto_adjust=True, progress=False)
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass
    return None


def validate_price(ticker: str, is_bist: bool, threshold_pct: float = 3.0) -> dict:
    """
    İki kaynaktan fiyat çekip karşılaştır.

    Returns:
        {
            'valid': bool,          # True = fiyatlar tutarlı
            'td_price': float|None,
            'yf_price': float|None,
            'diff_pct': float|None, # fark yüzdesi
            'warning': str|None,    # uyarı mesajı
            'best_price': float|None  # güvenilir fiyat (önce TD, sonra YF)
        }
    """
    td = _td_price(ticker, is_bist)
    yf_p = _yf_price(ticker, is_bist)

    result = {
        'valid': True,
        'td_price': td,
        'yf_price': yf_p,
        'diff_pct': None,
        'warning': None,
        'best_price': td or yf_p,
    }

    if td and yf_p:
        diff_pct = abs(td - yf_p) / ((td + yf_p) / 2) * 100
        result['diff_pct'] = round(diff_pct, 2)

        if diff_pct > threshold_pct:
            result['valid'] = False
            result['warning'] = (
                f"⚠️ Veri uyuşmazlığı: TD={td:.2f} / YF={yf_p:.2f} "
                f"(fark %{diff_pct:.1f}) — manuel teyit önerilir"
            )
    elif td is None and yf_p is None:
        result['valid'] = False
        result['warning'] = "❌ Her iki kaynaktan da fiyat alınamadı"
    elif td is None:
        result['warning'] = "⚠️ Twelvedata fiyatı alınamadı, sadece Yahoo kullanıldı"
    elif yf_p is None:
        result['warning'] = "⚠️ Yahoo Finance fiyatı alınamadı, sadece Twelvedata kullanıldı"

    return result


def validate_scan_results(results: list, is_bist: bool,
                           threshold_pct: float = 3.0,
                           max_checks: int = 30) -> list:
    """
    Tarama sonuçlarındaki hisseleri cross-validate et.
    Sadece Breakout ve Pivot Near statüsündeki ilk max_checks hisseyi kontrol eder
    (kredi tasarrufu için).

    Her sonuca 'data_warning' ve 'data_valid' alanları eklenir.
    """
    # Öncelik: Breakout > Pivot Near > Setup
    priority = {'Breakout': 0, 'Pivot Near': 1, 'Setup': 2}
    sorted_results = sorted(results, key=lambda x: priority.get(x.get('Status', 'Setup'), 2))

    checked = 0
    for stock in sorted_results:
        ticker = stock.get('Ticker') or stock.get('ticker', '')
        status = stock.get('Status', '')

        # Setup için doğrulama yapma — zaten alım için uygun değil
        if status == 'Setup' or checked >= max_checks:
            stock['data_valid'] = None   # kontrol edilmedi
            stock['data_warning'] = None
            continue

        v = validate_price(ticker, is_bist, threshold_pct)
        stock['data_valid'] = v['valid']
        stock['data_warning'] = v['warning']
        if v['best_price']:
            # Fiyatı güvenilir kaynaktan güncelle
            stock['Validated_Price'] = v['best_price']
        checked += 1
        print(
            f"  ✓ {ticker}: TD={v['td_price']} YF={v['yf_price']} "
            f"diff=%{v['diff_pct']} {'⚠️' if not v['valid'] else '✅'}",
            flush=True
        )

    print(f"  🔍 Cross-validation tamamlandı: {checked} hisse kontrol edildi", flush=True)
    return sorted_results
