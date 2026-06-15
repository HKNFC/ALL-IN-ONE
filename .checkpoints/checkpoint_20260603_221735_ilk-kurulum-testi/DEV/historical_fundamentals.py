"""
Historical Fundamentals Module

Backtest sırasında her rebalance tarihinde, o tarihe kadar mevcut olan
en son yıllık bilanço verilerini döndürür.

- USA hisseleri: FMP annual reports (5 yıl, 24s cache)
- BIST hisseleri: boş dict (data_fetcher'daki Yahoo verisi kullanılır)
"""

import os
import json
import time
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)

# FMP API
FMP_API_KEY = os.environ.get("FMP_API_KEY") or ""
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

# Disk cache dizini
HIST_CACHE_DIR = Path(os.path.expanduser("~/.cache/fmp_hist"))
HIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 24 saatlik TTL
HIST_CACHE_TTL_HOURS = 24
_PARALLEL_WORKERS = 10


# ---------------------------------------------------------------------------
# Cache yardımcıları
# ---------------------------------------------------------------------------

def _cache_path(symbol: str) -> Path:
    safe = symbol.replace(".", "_").replace("/", "_").replace(":", "_")
    return HIST_CACHE_DIR / f"{safe}.json"


def _load_cache(symbol: str) -> Optional[dict]:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("_ts", 0) < HIST_CACHE_TTL_HOURS * 3600:
            return data
    except Exception:
        pass
    return None


def _save_cache(symbol: str, data: dict) -> None:
    data["_ts"] = time.time()
    try:
        with open(_cache_path(symbol), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FMP API
# ---------------------------------------------------------------------------

def _fmp_get(endpoint: str, params: dict = None):
    """FMP stable API'den veri çeker."""
    if not FMP_API_KEY:
        return None
    p = dict(params or {})
    p["apikey"] = FMP_API_KEY
    try:
        r = requests.get(f"{FMP_BASE_URL}/{endpoint}", params=p, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug("FMP request failed (%s): %s", endpoint, e)
    return None


# ---------------------------------------------------------------------------
# Veri çekme ve hazırlama
# ---------------------------------------------------------------------------

def _fetch_symbol_data(symbol: str) -> dict:
    """FMP'den bir sembolün 5 yıllık yıllık verilerini çekip cache'e yazar."""
    cached = _load_cache(symbol)
    if cached:
        return cached

    income_raw = _fmp_get("income-statement", {"symbol": symbol, "period": "annual", "limit": 6}) or []
    balance_raw = _fmp_get("balance-sheet-statement", {"symbol": symbol, "period": "annual", "limit": 6}) or []
    metrics_raw = _fmp_get("key-metrics", {"symbol": symbol, "period": "annual", "limit": 6}) or []

    if not income_raw:
        empty = {"reports": []}
        _save_cache(symbol, empty)
        return empty

    # Tarih bazlı lookup
    income_by_date = {r["date"]: r for r in income_raw if r.get("date")}
    balance_by_date = {r["date"]: r for r in balance_raw if r.get("date")}
    metrics_by_date = {r["date"]: r for r in metrics_raw if r.get("date")}

    all_dates = sorted(income_by_date.keys(), reverse=True)

    reports = []
    for i, d in enumerate(all_dates):
        inc = income_by_date.get(d, {})
        bal = balance_by_date.get(d, {})
        met = metrics_by_date.get(d, {})
        prev_inc = income_by_date.get(all_dates[i + 1]) if i + 1 < len(all_dates) else None

        revenue = _safe(inc.get("revenue"))
        net_income = _safe(inc.get("netIncome"))
        prev_revenue = _safe(prev_inc.get("revenue")) if prev_inc else None
        prev_net_income = _safe(prev_inc.get("netIncome")) if prev_inc else None
        eps = _safe(inc.get("eps"))
        prev_eps = _safe(prev_inc.get("eps")) if prev_inc else None

        revenue_growth = None
        if revenue is not None and prev_revenue and prev_revenue != 0:
            revenue_growth = (revenue - prev_revenue) / abs(prev_revenue)

        earnings_growth = None
        if net_income is not None and prev_net_income and prev_net_income != 0:
            earnings_growth = (net_income - prev_net_income) / abs(prev_net_income)

        gross_profit = _safe(inc.get("grossProfit"))
        operating_income = _safe(inc.get("operatingIncome"))
        ebitda = _safe(inc.get("ebitda"))
        equity = _safe(bal.get("totalEquity") or bal.get("stockholdersEquity"))
        total_debt = _safe(bal.get("totalDebt"))
        total_assets = _safe(bal.get("totalAssets"))

        report = {
            "date": d,
            # Gelir tablosu ham
            "revenue": revenue,
            "net_income": net_income,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebitda": ebitda,
            "eps": eps,
            # Bilanço ham
            "equity": equity,
            "total_debt": total_debt,
            "total_assets": total_assets,
            # Geçen yıl (büyüme için)
            "revenue_prev_year": prev_revenue,
            "net_income_prev_year": prev_net_income,
            # Büyüme oranları (YoY)
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            # FMP key metrics (önceden hesaplanmış)
            "roe": _safe(met.get("roe")),
            "roic": _safe(met.get("roic")),
            "pe": _safe(met.get("peRatio")),
            "pb": _safe(met.get("priceToBookRatio")),
            "ev_ebitda": _safe(met.get("evToEbitda") or met.get("enterpriseValueOverEBITDA")),
            "peg": _safe(met.get("pegRatio")),
            "gross_margin": _safe(met.get("grossProfitMargin")),
            "net_margin": _safe(met.get("netProfitMargin")),
            "debt_to_equity": _safe(met.get("debtToEquity")),
            "current_ratio": _safe(met.get("currentRatio")),
        }
        reports.append(report)

    # 3 yıllık CAGR hesapla (4 rapor gerekli)
    for i, r in enumerate(reports):
        if i + 3 < len(reports):
            old = reports[i + 3]
            rev_now = r.get("revenue")
            rev_old = old.get("revenue")
            eps_now = r.get("eps")
            eps_old = old.get("eps")
            if rev_now and rev_old and rev_old > 0:
                r["revenue_cagr_3y"] = (rev_now / rev_old) ** (1 / 3) - 1
            if eps_now and eps_old and eps_old > 0:
                r["eps_cagr_3y"] = (eps_now / eps_old) ** (1 / 3) - 1

    result = {"reports": reports}
    _save_cache(symbol, result)
    return result


def _safe(val):
    """None/NaN/sonsuz olmayan float döner, yoksa None."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Dışa açık API
# ---------------------------------------------------------------------------

def get_snapshot(symbol: str, market: str, as_of_date) -> dict:
    """
    as_of_date tarihinde mevcut olan en son yıllık temel veri snapshotını döner.

    BIST için boş dict döner (yfinance current data kullanılır).
    FMP_API_KEY yoksa boş dict döner.
    """
    if not FMP_API_KEY:
        return {}

    is_bist = (market or "").upper() == "BIST"
    if is_bist:
        return {}  # BIST için historical FMP verisi yok

    as_of_ts = pd.Timestamp(as_of_date)
    data = _fetch_symbol_data(symbol)
    reports = data.get("reports", [])

    # Azalan tarih sırası — as_of_date'e kadar olan en son raporu bul
    for report in reports:
        rep_date_str = report.get("date")
        if not rep_date_str:
            continue
        try:
            rep_ts = pd.Timestamp(rep_date_str)
            if rep_ts <= as_of_ts:
                return {k: v for k, v in report.items() if k != "date"}
        except Exception:
            continue

    return {}


def batch_prefetch(symbols: list, market: str, progress_callback=None) -> None:
    """Tüm sembollerin tarihsel temel verilerini paralel olarak önceden çeker ve cache'ler."""
    if not FMP_API_KEY:
        return
    if (market or "").upper() == "BIST":
        return

    to_fetch = [s for s in symbols if _load_cache(s) is None]
    if not to_fetch:
        logger.info("Historical fundamentals: all %d symbols already cached", len(symbols))
        return

    total = len(to_fetch)
    logger.info("Historical fundamentals: prefetching %d/%d symbols...", total, len(symbols))
    done = 0

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(_fetch_symbol_data, s): s for s in to_fetch}
        for future in as_completed(futures):
            done += 1
            sym = futures[future]
            if progress_callback:
                progress_callback(done / total, f"Tarihsel temel veri: {done}/{total}")
            try:
                future.result()
            except Exception as e:
                logger.warning("Historical fundamentals failed for %s: %s", sym, e)

    logger.info("Historical fundamentals: prefetch complete (%d symbols)", total)


def inject_fundamentals_at_date(
    df: pd.DataFrame,
    as_of_date,
    market: str,
) -> pd.DataFrame:
    """
    Her satır (hisse) için as_of_date tarihindeki tarihsel temel veriyi
    DataFrame'e enjekte eder.

    - Mevcut NaN olmayan sütunlara dokunmaz (zaten BIST verisi var vs).
    - Sadece NaN olan sütunları doldurur.
    """
    if not FMP_API_KEY:
        return df

    is_bist = (market or "").upper() == "BIST"
    if is_bist:
        return df  # BIST: zaten data_fetcher'dan Yahoo verisi geldi

    FUND_FIELDS = [
        "revenue", "net_income", "gross_profit", "operating_income", "ebitda",
        "equity", "total_debt", "total_assets",
        "revenue_prev_year", "net_income_prev_year",
        "revenue_growth", "earnings_growth",
        "roe", "roic", "pe", "pb", "ev_ebitda", "peg",
        "gross_margin", "net_margin", "debt_to_equity", "current_ratio",
    ]

    result = df.copy()

    # Eksik sütunları NaN olarak ekle
    for field in FUND_FIELDS:
        if field not in result.columns:
            result[field] = np.nan

    for idx, row in result.iterrows():
        ticker = row.get("ticker")
        if not ticker:
            continue

        snapshot = get_snapshot(ticker, market, as_of_date)
        if not snapshot:
            continue

        for field in FUND_FIELDS:
            val = snapshot.get(field)
            if val is None:
                continue
            # Sadece mevcut değer NaN ise yaz
            current = row.get(field)
            is_nan = current is None or (isinstance(current, float) and np.isnan(current))
            if is_nan:
                try:
                    result.at[idx, field] = float(val)
                except (TypeError, ValueError):
                    pass

    return result
