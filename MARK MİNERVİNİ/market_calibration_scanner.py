"""
Market Calibration Scanner
==========================
BIST ve USA için piyasa bazlı kalibrasyon ile ikinci tarama motoru.
Mevcut universal_scanner.py / sepa_scanner.py'ye DOKUNULMAZ.

Çıktı formatı mevcut scan_bist_stock / scan_us_stock ile aynı:
    {Ticker, Market, Status, RS, RS_Divergence_%, Score, ...}
Böylece backtest'in select_top_stocks() direkt çalışır.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import logging

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

# Mevcut scanner'dan yardımcı fonksiyonlar import et (değiştirme yok)
from universal_scanner import UniversalStockScanner

# ──────────────────────────────────────────────────────────────────────────────
# MARKET PROFILES
# ──────────────────────────────────────────────────────────────────────────────

BIST_PROFILE = {
    "name":      "BIST Profile",
    "benchmark": "XU100.IS",
    "weights": {
        "rs":          0.45,
        "trend":       0.35,
        "vcp":         0.20,
        "debt_equity": 0.0,
        "roic":        0.0,
    },
    "roic_bands": [
        # (üst_eşik, puan) — küçükten büyüğe sıralı
        (10,  20),
        (20,  50),
        (35,  80),
        (999, 100),
    ],
    "roic_label": "<10→20p / 10-20→50p / 20-35→80p / 35+→100p",
    "de_label":   "D/E ağırlık %20 (BIST'te borçluluk kritik)",
    "peg_weight": 0,
}

USA_PROFILE = {
    "name":      "USA Profile",
    "benchmark": "SPY",
    "weights": {
        "rs":    0.40,
        "trend": 0.30,
        "vcp":   0.20,
        "peg":   0.0,
        "roic":  0.0,
    },
    "roic_bands": [
        (8,   20),
        (12,  50),
        (20,  80),
        (999, 100),
    ],
    "roic_label": "<8→20p / 8-12→50p / 12-20→80p / 20+→100p",
    "de_label":   "D/E ağırlık yok (kurumsal kalite PEG ile ölçülür)",
    "peg_weight": 0.30,
}


def get_profile(market: str) -> dict:
    """BIST veya USA profilini döndür."""
    if market in ('BIST', 'BISTTUM', 'BIST100', 'BIST100X', 'BISTXUTUM', 'BISTXTUMY'):
        return BIST_PROFILE
    return USA_PROFILE


# ──────────────────────────────────────────────────────────────────────────────
# PUANLAMA FONKSİYONLARI
# ──────────────────────────────────────────────────────────────────────────────

def score_roic(roic_val, bands: list) -> float:
    """
    Kademeli ROIC puanı — HARD FILTER YOK.
    Düşük ROIC hisse düşük puanla listede kalır.
    """
    if roic_val is None or (isinstance(roic_val, float) and np.isnan(roic_val)):
        return 30.0  # veri yoksa nötr puan
    try:
        roic = float(roic_val)
    except Exception:
        return 30.0
    for upper, point in bands:
        if roic < upper:
            return float(point)
    return float(bands[-1][1])


def score_peg(peg_val) -> float:
    """PEG oranı puanı (USA için). PEG < 1 mükemmel, > 3 zayıf."""
    if peg_val is None or (isinstance(peg_val, float) and np.isnan(peg_val)):
        return 30.0
    try:
        peg = float(peg_val)
    except Exception:
        return 30.0
    if peg <= 0:
        return 30.0
    if peg < 1.0:
        return 100.0
    if peg < 1.5:
        return 80.0
    if peg < 2.0:
        return 60.0
    if peg < 3.0:
        return 40.0
    return 20.0


def score_debt_equity(de_val) -> float:
    """Debt/Equity puanı (BIST için). Düşük borç = yüksek puan."""
    if de_val is None or (isinstance(de_val, float) and np.isnan(de_val)):
        return 40.0
    try:
        de = float(de_val)
    except Exception:
        return 40.0
    if de < 0.3:
        return 100.0
    if de < 0.6:
        return 80.0
    if de < 1.0:
        return 60.0
    if de < 2.0:
        return 40.0
    return 20.0


def score_rs(rs_value) -> float:
    """
    RS skorunu 0-100 puanına çevir.
    Ham RS değeri (örn: 250) → normalize puan.
    """
    if rs_value is None:
        return 0.0
    try:
        rs = float(rs_value)
    except Exception:
        return 0.0
    # 0-100 bandına normalize (100+ → 100, negatif → 0)
    return max(0.0, min(100.0, (rs + 50) * (100 / 150)))


def score_trend(ind: dict) -> float:
    """Trend Template kriterlerine göre puan."""
    checks = 0
    total = 5
    price  = ind.get('price', 0)
    sma50  = ind.get('sma50_v', 0)
    sma150 = ind.get('sma150_v', 0)
    sma200 = ind.get('sma200_v', 0)
    sma200_past = ind.get('sma200_past', sma200)
    high52 = ind.get('high52_v', 0)
    low52  = ind.get('low52_v', 0)

    if price > sma150 and price > sma200:
        checks += 1
    if sma150 > sma200:
        checks += 1
    if sma200 > sma200_past:
        checks += 1
    if sma50 > sma150 and sma50 > sma200:
        checks += 1
    if low52 > 0 and price >= low52 * 1.25:
        checks += 1

    return (checks / total) * 100


def score_vcp(vcp_result) -> float:
    """VCP pattern puanı."""
    if vcp_result is None:
        return 0.0
    pattern = vcp_result.get('pattern', '')
    if pattern == 'TIGHT':
        return 100.0
    if pattern == 'FORMING':
        return 60.0
    return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# ANA SKOR FONKSİYONU
# ──────────────────────────────────────────────────────────────────────────────

def _safe_float(val):
    if isinstance(val, pd.Series):
        val = val.iloc[0] if len(val) > 0 else 0.0
    try:
        return float(val)
    except Exception:
        return 0.0


def calculate_calibrated_score(ticker, market, stock_df, benchmark_df, scanner):
    """
    Pazar bazlı kalibrasyon skoru hesapla.
    Çıktı mevcut scan_bist_stock / scan_us_stock formatıyla uyumlu.
    """
    profile = get_profile(market)
    is_bist = market in ('BIST', 'BISTTUM', 'BIST100', 'BIST100X', 'BISTXUTUM', 'BISTXTUMY')

    if len(stock_df) < 200:
        return None

    # ── Teknik göstergeler ──
    try:
        ind = scanner._compute_indicators(stock_df)
    except Exception:
        return None

    # Temel Trend Template kontrolü (en az 4/5 gerekli)
    trend_pct = score_trend(ind)
    if trend_pct < 60:
        return None

    # ── RS skoru ──
    if is_bist:
        rs_raw = scanner.calculate_rs_bist(stock_df, benchmark_df)
    else:
        rs_raw = scanner.calculate_rs_us(stock_df, benchmark_df)

    if rs_raw is None:
        return None

    # ── VCP ──
    vcp = scanner.detect_vcp_pattern(stock_df)
    pivot, dist_to_pivot = scanner.find_pivot_point(stock_df)
    _, spike_ratio = scanner.check_volume_spike(stock_df)
    status = scanner.determine_status(dist_to_pivot, vcp, spike_ratio)

    if status == 'WATCHING':
        return None

    # ── Temel veriler: nötr puan (look-ahead bias'ı önlemek için yf.info KULLANILMIYOR) ──
    # Tarihsel fundamental data mevcut olmadığından sabit nötr puan atanır.
    # Bu şekilde backtest ve scanner deterministik ve tutarlı çalışır.
    roic_val  = None
    de_val    = None
    peg_val   = None
    roic_score = 50.0
    de_score   = 50.0
    peg_score  = 50.0

    # ── Puanlama ──
    rs_score    = score_rs(rs_raw)
    trend_score = trend_pct
    vcp_score   = score_vcp(vcp)
    weights     = profile['weights']

    total_score = (
        weights.get('rs',    0) * rs_score    +
        weights.get('trend', 0) * trend_score +
        weights.get('vcp',   0) * vcp_score
    )

    price = ind.get('price', 0)

    # ── Sonuç paketi (mevcut formatla uyumlu) ──
    result = {
        'Ticker':           ticker.replace('.IS', ''),
        'Market':           'BIST' if is_bist else 'US',
        'Status':           status,
        'Score':            round(total_score, 2),
        'RS_Score':         round(total_score, 2),  # select_top_stocks için
        'RS':               round(rs_raw, 2),
        'RS_Divergence_%':  round(rs_raw, 2) if is_bist else None,
        'Price':            round(price, 2),
        'current_price':    round(price, 2),
        'current_price_tl': round(price, 2) if is_bist else None,
        'Pivot':            round(pivot, 2) if pivot else None,
        'Distance_to_Pivot_%': round(dist_to_pivot, 2) if dist_to_pivot is not None else None,
        'VCP':              vcp is not None,
        'VCP_Pattern':      vcp.get('pattern', '') if vcp else '',
        # Debug bilgisi
        '_calibration': {
            'engine':     'calibrated',
            'profile':    profile['name'],
            'benchmark':  profile['benchmark'],
            'weights':    weights,
            'roic_label': 'nötr (50p) — tarihsel fundamental data yok',
            'roic_val':   None,
            'de_val':     None,
            'peg_val':    None,
            'scores': {
                'rs':    round(rs_score, 1),
                'trend': round(trend_score, 1),
                'roic':  50.0,
                'vcp':   round(vcp_score, 1),
                'de':    50.0,
                'peg':   50.0,
            }
        }
    }
    return result


# ──────────────────────────────────────────────────────────────────────────────
# ANA TARAMA FONKSİYONU
# ──────────────────────────────────────────────────────────────────────────────

def scan_with_calibration(tickers: list, market: str, cutoff=None,
                           cache=None, progress_cb=None) -> list:
    """
    Pazar bazlı kalibrasyon ile tarama yap.

    Args:
        tickers:     Taranacak ticker listesi (Yahoo format, örn: AKBNK.IS)
        market:      'BIST' | 'US' | 'BISTTUM' vs.
        cutoff:      pd.Timestamp veya None (None → bugün)
        cache:       MarketDataCache instance (backtest'ten gelebilir)
        progress_cb: (i, total) çağrısı yapan fonksiyon (opsiyonel)

    Returns:
        calculate_calibrated_score ile uyumlu dict listesi
    """
    is_bist = market in ('BIST', 'BISTTUM', 'BIST100', 'BIST100X', 'BISTXUTUM', 'BISTXTUMY')
    profile = get_profile(market)
    benchmark_ticker = profile['benchmark']

    scanner = UniversalStockScanner()

    if cutoff is None:
        cutoff = pd.Timestamp(datetime.now().date())

    period = '2y'

    # ── Benchmark ver ──
    def _dl(sym):
        try:
            df = yf.Ticker(sym).history(period=period)
            if df is None or df.empty:
                df = yf.download(sym, period=period, progress=False, auto_adjust=True)
            return df
        except Exception:
            return pd.DataFrame()

    if cache is not None:
        benchmark_df = cache.get_slice(benchmark_ticker, cutoff)
        if benchmark_df is None or benchmark_df.empty:
            print(f"⚠️  Benchmark {benchmark_ticker} cache'de yok — doğrudan indiriliyor...", flush=True)
            benchmark_df = _dl(benchmark_ticker)
            if not benchmark_df.empty:
                try:
                    cache._store(benchmark_ticker, benchmark_df)
                except Exception:
                    pass
    else:
        benchmark_df = _dl(benchmark_ticker)

    if benchmark_df is None or benchmark_df.empty:
        print(f"❌ Benchmark {benchmark_ticker} indirilemedi — tarama iptal.", flush=True)
        return []

    # cutoff'a göre benchmark'ı kısıtla
    if cutoff is not None and not benchmark_df.empty:
        benchmark_df = benchmark_df[benchmark_df.index <= cutoff]

    results = []
    total = len(tickers)

    def _process(ticker):
        try:
            if cache is not None:
                stock_df = cache.get_slice(ticker, cutoff)
            else:
                stock_df = _dl(ticker)

            if stock_df is None or len(stock_df) < 200:
                return None

            # cutoff'u geçmeyen verilere kısıt
            if cutoff is not None and not stock_df.empty:
                stock_df = stock_df[stock_df.index <= cutoff]
                if len(stock_df) < 200:
                    return None

            return calculate_calibrated_score(ticker, market, stock_df, benchmark_df, scanner)
        except Exception as e:
            return None

    workers = min(8, max(1, total))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process, t): i for i, t in enumerate(tickers)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if progress_cb:
                progress_cb(done, total)
            res = fut.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x.get('Score', 0), reverse=True)
    print(f"  ✅ Kalibrasyon taraması: {len(results)}/{total} hisse kriterleri geçti", flush=True)
    return results
