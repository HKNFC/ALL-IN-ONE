"""
TEMEL OPTİMİZER — Tarihsel Temel Veri Modülü
==============================================
FMP API'sinden hisse başına çeyreklik tarihsel temel verileri çeker ve
look-ahead bias olmadan "o tarihte bilinebilecek en son raporu" döndürür.

LOOK-AHEAD BIAS ÖNLEMESİ:
  FMP her finansal rapor için iki tarih içerir:
    - date       : dönem sonu   (ör: 2023-03-31)
    - fillingDate: SEC'e teslim (ör: 2023-05-10)
  Kural: get_fundamentals_as_of(ticker, "2023-04-01") çağrıldığında
  fillingDate <= 2023-04-01 olan en son raporu döndürür.
  → Q1 2023 raporu 10 Mayıs'ta açıklandığından 1 Nisan'da KULLANILMAZ.

Cache: ~/.cache/fmp/hist_fund/<ticker>.json  (TTL: 7 gün)
"""

import os, json, logging, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

import requests

# .env dosyasını yükle (app.py'den önce import edilse bile key doğru okunur)
try:
    from dotenv import load_dotenv as _ld
    _ld(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ─── Konfigürasyon ────────────────────────────────────────────────────────────
FMP_BASE     = "https://financialmodelingprep.com/stable"
CACHE_DIR    = Path.home() / ".cache" / "fmp" / "hist_fund"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL    = 7 * 24 * 3600   # 7 gün (temel veri sık değişmez)
STMT_LIMIT   = 40               # Son 40 çeyrek (~10 yıl)

def _get_api_key() -> str:
    """Her çağrıda dinamik oku — .env sonradan yüklense bile çalışır."""
    return os.environ.get("FMP_API_KEY", "")

# ─── Yardımcı: HTTP GET ───────────────────────────────────────────────────────
def _fmp_get(endpoint: str, params: dict = None, timeout: int = 15) -> list:
    """FMP REST çağrısı. Hata durumunda boş liste döner."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("FMP_API_KEY tanımlı değil — temel veri çekilemiyor.")
        return []
    p = {"apikey": api_key, **(params or {})}
    try:
        r = requests.get(f"{FMP_BASE}/{endpoint}", params=p, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"FMP GET '{endpoint}' hata: {e}")
        return []

# ─── Cache yardımcıları ───────────────────────────────────────────────────────
def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.upper()}.json"

def _load_cache(ticker: str) -> Optional[dict]:
    p = _cache_path(ticker)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
        if time.time() - data.get("fetched_at", 0) > CACHE_TTL:
            return None          # Süresi dolmuş
        return data
    except Exception:
        return None

def _save_cache(ticker: str, data: dict):
    try:
        with open(_cache_path(ticker), "w") as f:
            json.dump(data, f, default=str)
    except Exception as e:
        logger.warning(f"Cache yazma hatası {ticker}: {e}")

# ─── Ana veri çekme ───────────────────────────────────────────────────────────
def fetch_historical_fundamentals(ticker: str, force_refresh: bool = False) -> dict:
    """
    FMP'den hisse için tarihsel çeyreklik temel veri çek.
    Cache varsa önce oradan döner; TTL dolmuşsa veya force_refresh=True ise yeniler.

    Döndürülen yapı:
    {
      "income"  : [ { date, fillingDate, eps, revenue, netIncome, grossProfit, ... } ],
      "metrics" : [ { date, fillingDate, roe, freeCashFlowPerShare, peRatio, pbRatio, ... } ],
      "growth"  : [ { date, fillingDate, epsgrowth, revenueGrowth, netIncomeGrowth, ... } ],
      "fetched_at": <unix timestamp>
    }
    """
    if not force_refresh:
        cached = _load_cache(ticker)
        if cached:
            return cached

    t = ticker.upper()
    logger.info(f"FMP tarihsel temel veri çekiliyor: {t}")

    # 1. Gelir tablosu (çeyreklik) — yeni FMP stable API: ?symbol= formatı
    income = _fmp_get(
        "income-statement",
        {"symbol": t, "period": "quarter", "limit": STMT_LIMIT}
    )

    # 2. Anahtar metrikler (çeyreklik)
    metrics = _fmp_get(
        "key-metrics",
        {"symbol": t, "period": "quarter", "limit": STMT_LIMIT}
    )

    # 3. Büyüme oranları (çeyreklik)
    growth = _fmp_get(
        "financial-growth",
        {"symbol": t, "period": "quarter", "limit": STMT_LIMIT}
    )

    # fillingDate eksik kayıtlara date+45gün ata (iyimser tahmim — yine de geç)
    def _fill_date(records: list, fallback_days: int = 45) -> list:
        out = []
        for r in records:
            r = dict(r)
            if not r.get("fillingDate") and r.get("date"):
                try:
                    d = datetime.strptime(r["date"][:10], "%Y-%m-%d")
                    r["fillingDate"] = (d + timedelta(days=fallback_days)).strftime("%Y-%m-%d")
                except Exception:
                    pass
            out.append(r)
        return out

    result = {
        "income"    : _fill_date(income),
        "metrics"   : _fill_date(metrics),
        "growth"    : _fill_date(growth),
        "fetched_at": time.time(),
    }

    _save_cache(ticker, result)
    return result

# ─── Nokta-içinde-zaman filtresi ─────────────────────────────────────────────
def _latest_before(records: list, as_of_date: str) -> Optional[dict]:
    """
    fillingDate <= as_of_date olan en son kaydı döndürür.
    Hiç kayıt yoksa None döner.
    """
    as_of = as_of_date[:10]   # YYYY-MM-DD
    candidates = [
        r for r in records
        if r.get("fillingDate", "") <= as_of
    ]
    if not candidates:
        return None
    # En yeni (en büyük fillingDate) olan
    return max(candidates, key=lambda r: r.get("fillingDate", ""))

def get_fundamentals_as_of(ticker: str, as_of_date: str,
                            force_refresh: bool = False) -> Optional[dict]:
    """
    `as_of_date` (YYYY-MM-DD) tarihi itibarıyla bilinebilecek en son
    çeyreklik temel veriyi döndürür. Look-ahead bias yoktur.

    Döndürülen dict:
      eps_growth     : son çeyrek EPS büyüme (%)
      rev_growth     : son çeyrek gelir büyüme (%)
      net_income_growth: net kâr büyüme (%)
      roe            : özkaynak kârlılığı (%)
      free_cash_flow : FCF / hisse (dolar)
      pe_ratio       : F/K
      pb_ratio       : F/DD
      net_margin     : net marj (%)
      gross_margin   : brüt marj (%)
      debt_equity    : borç/özkaynak
      current_ratio  : cari oran
      filling_date   : kullanılan raporun açıklanma tarihi
      period_date    : dönem sonu tarihi
    """
    raw = fetch_historical_fundamentals(ticker, force_refresh=force_refresh)

    inc = _latest_before(raw.get("income",  []), as_of_date)
    met = _latest_before(raw.get("metrics", []), as_of_date)
    grw = _latest_before(raw.get("growth",  []), as_of_date)

    if inc is None and met is None and grw is None:
        return None

    # Güvenli çekme
    def _f(d, *keys, default=None):
        if d is None:
            return default
        for k in keys:
            v = d.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return default

    # Net marj = net kâr / gelir
    revenue   = _f(inc, "revenue")
    net_inc   = _f(inc, "netIncome")
    gross_p   = _f(inc, "grossProfit")
    net_margin   = (net_inc / revenue * 100) if revenue and net_inc  else None
    gross_margin = (gross_p / revenue * 100) if revenue and gross_p  else None

    # Borç/özkaynak metrikleri
    total_debt  = _f(met, "debtToEquity")      # oran
    curr_ratio  = _f(met, "currentRatio")
    roe         = _f(met, "roe")
    if roe is not None:
        roe = roe * 100                         # 0.18 → 18%

    pe_ratio = _f(met, "peRatio")
    pb_ratio = _f(met, "pbRatio")
    fcf_ps   = _f(met, "freeCashFlowPerShare")

    eps_growth      = _f(grw, "epsgrowth")
    rev_growth      = _f(grw, "revenueGrowth")
    net_inc_growth  = _f(grw, "netIncomeGrowth")
    if eps_growth     is not None: eps_growth     *= 100
    if rev_growth     is not None: rev_growth     *= 100
    if net_inc_growth is not None: net_inc_growth *= 100

    filling_date = (inc  or met or grw or {}).get("fillingDate", "")
    period_date  = (inc  or met or grw or {}).get("date", "")

    return {
        "eps_growth"        : eps_growth,
        "rev_growth"        : rev_growth,
        "net_income_growth" : net_inc_growth,
        "roe"               : roe,
        "free_cash_flow"    : fcf_ps,
        "pe_ratio"          : pe_ratio,
        "pb_ratio"          : pb_ratio,
        "net_margin"        : net_margin,
        "gross_margin"      : gross_margin,
        "debt_equity"       : total_debt,
        "current_ratio"     : curr_ratio,
        "filling_date"      : filling_date,
        "period_date"       : period_date,
    }

# ─── Skor hesaplama ───────────────────────────────────────────────────────────
def _score(val, thresholds: list) -> float:
    """
    thresholds: [(eşik, puan), ...] büyükten küçüğe sıralı.
    Eşiği geçen ilk kuralın puanını döndürür.
    """
    if val is None:
        return 50.0    # Eksik veri → nötr puan
    for threshold, score in thresholds:
        if val >= threshold:
            return float(score)
    return thresholds[-1][1]    # En kötü puan

def calc_historical_fund_score(
    fund: Optional[dict],
    strategy: str = "Alfa"
) -> tuple[float, dict]:
    """
    Look-ahead bias'sız tarihsel temel veriden 0-100 arası skor üretir.

    strategy: "Alfa" | "Beta" | "Delta"
    Döndürür: (score: float, breakdown: dict)
    """
    if fund is None:
        return 50.0, {"not": "Temel veri yok — nötr puan 50"}

    # ── Bileşen skorları ──────────────────────────────────────────────────────

    # EPS büyümesi (%)
    eps_s = _score(fund.get("eps_growth"), [
        (50, 100), (30, 85), (15, 70), (5, 55), (0, 40), (-10, 25), (-999, 10)
    ])

    # Gelir büyümesi (%)
    rev_s = _score(fund.get("rev_growth"), [
        (40, 100), (20, 85), (10, 70), (5, 55), (0, 40), (-5, 25), (-999, 10)
    ])

    # ROE (%)
    roe_s = _score(fund.get("roe"), [
        (30, 100), (20, 85), (15, 70), (10, 55), (5, 40), (0, 25), (-999, 10)
    ])

    # Net marj (%)
    nm_s = _score(fund.get("net_margin"), [
        (25, 100), (15, 85), (10, 70), (5, 55), (0, 40), (-5, 25), (-999, 10)
    ])

    # Borç/özkaynak (düşük = iyi → ters çevir)
    de_val = fund.get("debt_equity")
    de_s = _score(
        None if de_val is None else -de_val,   # negatif → ters sıralama
        [(-0.3, 100), (-0.7, 85), (-1.0, 70), (-1.5, 55), (-2.0, 40), (-3.0, 25), (-999, 10)]
    )

    # FCF pozitif mi?
    fcf_val = fund.get("free_cash_flow")
    fcf_s = _score(fcf_val, [
        (5, 100), (2, 85), (0.5, 70), (0, 55), (-999, 20)
    ])

    # F/K — düşük = iyi (değer), yüksek = büyüme primi (karma yorum)
    pe_val = fund.get("pe_ratio")
    pe_s = 50.0    # nötr default
    if pe_val is not None and pe_val > 0:
        if   pe_val < 15:   pe_s = 85
        elif pe_val < 25:   pe_s = 70
        elif pe_val < 35:   pe_s = 55
        elif pe_val < 50:   pe_s = 40
        else:                pe_s = 25

    # F/DD — düşük = iyi
    pb_val = fund.get("pb_ratio")
    pb_s = 50.0
    if pb_val is not None and pb_val > 0:
        if   pb_val < 1.5:  pb_s = 90
        elif pb_val < 3.0:  pb_s = 75
        elif pb_val < 5.0:  pb_s = 60
        elif pb_val < 8.0:  pb_s = 45
        else:                pb_s = 30

    # Cari oran (>= 1.5 iyi)
    cr_s = _score(fund.get("current_ratio"), [
        (2.5, 100), (2.0, 85), (1.5, 70), (1.0, 50), (0.8, 30), (-999, 15)
    ])

    # ── Strateji bazlı ağırlıklar ─────────────────────────────────────────────
    if strategy == "Beta":
        # Momentum+büyüme odaklı
        weights = {
            "eps"  : (eps_s, 0.30),
            "rev"  : (rev_s, 0.25),
            "roe"  : (roe_s, 0.20),
            "nm"   : (nm_s,  0.15),
            "de"   : (de_s,  0.10),
        }
    elif strategy == "Delta":
        # Değer odaklı
        weights = {
            "pe"   : (pe_s,  0.25),
            "pb"   : (pb_s,  0.25),
            "roe"  : (roe_s, 0.15),
            "nm"   : (nm_s,  0.15),
            "de"   : (de_s,  0.10),
            "cr"   : (cr_s,  0.05),
            "fcf"  : (fcf_s, 0.05),
        }
    else:   # Alfa — büyüme kalitesi odaklı
        weights = {
            "roe"  : (roe_s, 0.25),
            "eps"  : (eps_s, 0.25),
            "rev"  : (rev_s, 0.15),
            "nm"   : (nm_s,  0.15),
            "de"   : (de_s,  0.10),
            "fcf"  : (fcf_s, 0.10),
        }

    total = sum(s * w for s, w in weights.values())

    breakdown = {
        "EPS Büyümesi"  : round(eps_s, 1),
        "Gelir Büyümesi": round(rev_s, 1),
        "ROE"           : round(roe_s, 1),
        "Net Marj"      : round(nm_s,  1),
        "Borç/Özkaynk"  : round(de_s,  1),
        "FCF"           : round(fcf_s, 1),
        "F/K"           : round(pe_s,  1),
        "F/DD"          : round(pb_s,  1),
        "Cari Oran"     : round(cr_s,  1),
        "Strateji"      : strategy,
        "Dönem"         : fund.get("period_date", "?"),
        "Açıklama Tarihi": fund.get("filling_date", "?"),
    }

    return round(min(100.0, max(0.0, total)), 2), breakdown


# ─── Toplu ön-yükleme (backtest öncesi) ──────────────────────────────────────
def prefetch_fundamentals_batch(
    tickers: list,
    progress_callback=None,
) -> Dict[str, dict]:
    """
    Backtest başlamadan önce tüm hisselerin tarihsel temel verilerini indir.
    Döndürür: { ticker: raw_data_dict }
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}
    total = len(tickers)

    with ThreadPoolExecutor(max_workers=8) as ex:
        future_map = {
            ex.submit(fetch_historical_fundamentals, t): t
            for t in tickers
        }
        done = 0
        for fut in as_completed(future_map):
            t = future_map[fut]
            done += 1
            try:
                results[t] = fut.result()
            except Exception as e:
                logger.warning(f"Temel veri alınamadı {t}: {e}")
                results[t] = {}
            if progress_callback:
                progress_callback(done / total, f"Temel veri: {t} ({done}/{total})")

    return results


# ─── CLI test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    date   = sys.argv[2] if len(sys.argv) > 2 else "2023-01-15"

    print(f"\n=== {ticker} | as_of={date} ===")
    fund = get_fundamentals_as_of(ticker, date, force_refresh=True)
    if fund:
        print(f"Dönem      : {fund['period_date']}")
        print(f"Açık.Tarihi: {fund['filling_date']}")
        print(f"EPS büy    : {fund['eps_growth']}")
        print(f"Rev büy    : {fund['rev_growth']}")
        print(f"ROE        : {fund['roe']}")
        print(f"Net Marj   : {fund['net_margin']}")
        score, bd = calc_historical_fund_score(fund, "Alfa")
        print(f"\nALFA TEMEL SKOR: {score}/100")
        for k, v in bd.items():
            print(f"  {k}: {v}")
    else:
        print("Veri bulunamadı.")
