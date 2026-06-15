"""
FMP (Financial Modeling Prep) PriceProvider implementasyonu.
USA hisseleri için TwelveData yerine bu provider öncelikli kullanılır.
BIST hisseleri (.IS) otomatik olarak bu provider'dan HARİÇ tutulur.

API: https://financialmodelingprep.com/stable  |  Plan: Premium
"""
import sys, os, time, logging
import pandas as pd
import requests
from typing import Optional
from price_provider import PriceProvider
from disk_cache import OHLCV_COLUMNS

sys.path.insert(0, '/Users/hakanficicilar/Documents/Aİ')

logger = logging.getLogger("stock_screener.fmp")

FMP_API_KEY  = os.environ.get("FMP_API_KEY", "xCRBWz7ql4frQUP81nYkHl3uWb2fWBON")
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
TIMEOUT      = 12


def _fmp_get(endpoint, params=None):
    p = dict(params or {})
    p["apikey"] = FMP_API_KEY
    try:
        r = requests.get(f"{FMP_BASE_URL}/{endpoint}", params=p, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"FMP {endpoint} → {r.status_code}")
    except Exception as e:
        logger.error(f"FMP isteği başarısız {endpoint}: {e}")
    return None


class FMPDataProvider(PriceProvider):
    """
    FMP tabanlı veri sağlayıcı — sadece USA hisseleri.
    .IS uzantılı BIST hisselerinde hemen None/boş döner.
    """

    def _is_bist(self, ticker: str) -> bool:
        return ticker.upper().endswith(".IS")

    def get_daily_history(self, ticker: str, outputsize: int = 252, market=None) -> pd.DataFrame:
        empty = pd.DataFrame(columns=OHLCV_COLUMNS)
        if self._is_bist(ticker):
            return empty

        from datetime import datetime, timedelta
        days_back = max(outputsize + 30, 365)
        from_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date   = datetime.today().strftime("%Y-%m-%d")

        data = _fmp_get("historical-price-eod/full", {
            "symbol": ticker,
            "from": from_date,
            "to": to_date,
        })
        if not data:
            return empty

        try:
            df = pd.DataFrame(data)
            df["datetime"] = pd.to_datetime(df["date"])
            df = df.rename(columns={
                "open":   "open",
                "high":   "high",
                "low":    "low",
                "close":  "close",
                "volume": "volume",
            })
            df = df[["datetime", "open", "high", "low", "close", "volume"]].dropna()
            df = df.sort_values("datetime").reset_index(drop=True)
            # outputsize kadar son bar
            if len(df) > outputsize:
                df = df.tail(outputsize).reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"FMP history parse hatası {ticker}: {e}")
            return empty

    def get_quote(self, ticker: str, market=None) -> Optional[dict]:
        if self._is_bist(ticker):
            return None

        data = _fmp_get("profile", {"symbol": ticker})
        if not data or not isinstance(data, list):
            return None
        try:
            d = data[0]
            return {
                "price":          d.get("price"),
                "volume":         d.get("volAvg"),
                "change":         d.get("changes"),
                "percent_change": d.get("changesPercentage"),
            }
        except Exception:
            return None
