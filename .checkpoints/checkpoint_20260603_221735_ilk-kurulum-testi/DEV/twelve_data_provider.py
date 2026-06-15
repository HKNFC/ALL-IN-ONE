import time
import hashlib
import logging
import pandas as pd
import numpy as np
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from price_provider import PriceProvider
from config import CACHE_TTL_HISTORY, CACHE_TTL_QUOTE, API_REQUEST_TIMEOUT, API_MAX_RETRIES, API_RETRY_DELAY
from disk_cache import get_cached_or_fetch, needs_refresh, read_cache, OHLCV_COLUMNS

logger = logging.getLogger("stock_screener.twelve_data")

_CACHE: Dict[str, Dict[str, Any]] = {}

REQUEST_TIMEOUT = API_REQUEST_TIMEOUT


def _cache_key(prefix: str, **kwargs) -> str:
    """Build a deterministic cache key from prefix and keyword args."""
    parts = [prefix] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Any]:
    """Retrieve a value from cache if it exists and hasn't expired."""
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if time.time() > entry["expires"]:
        del _CACHE[key]
        return None
    return entry["value"]


def _cache_set(key: str, value: Any, ttl: int) -> None:
    """Store a value in cache with a TTL in seconds."""
    _CACHE[key] = {"value": value, "expires": time.time() + ttl}


def clear_cache() -> int:
    """Clear the entire cache. Returns the number of entries removed."""
    count = len(_CACHE)
    _CACHE.clear()
    return count


def get_cache_stats() -> dict:
    """Return cache size and number of expired entries."""
    now = time.time()
    expired = sum(1 for e in _CACHE.values() if now > e["expires"])
    return {"total": len(_CACHE), "expired": expired, "active": len(_CACHE) - expired}


class TwelveDataProvider(PriceProvider):
    """
    Twelve Data API implementation of the PriceProvider interface.

    Supports US tickers (e.g., AAPL) and BIST tickers. For BIST, the provider
    maps bare tickers to their exchange-suffixed form automatically.

    Rate limiting: Twelve Data free tier allows 8 requests/minute and 800/day.
    The provider logs warnings when approaching limits.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com"):
        if not api_key:
            raise ValueError("TWELVE_DATA_API_KEY is required but empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._request_count = 0
        self._request_timestamps: list[float] = []

    def _resolve_symbol(self, ticker: str, market: Optional[str] = None) -> str:
        from symbol_mapper import resolve_twelve_symbol
        return resolve_twelve_symbol(ticker, market)

    def _api_request(self, endpoint: str, params: dict) -> Optional[dict]:
        """
        Make a request to the Twelve Data API with error handling and logging.

        Returns the parsed JSON response, or None on failure.
        """
        url = f"{self._base_url}/{endpoint}"
        params["apikey"] = self._api_key

        self._track_rate()

        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.warning("Rate limit hit — waiting %ds before retry", API_RETRY_DELAY)
                time.sleep(API_RETRY_DELAY)
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()
            data = response.json()

            if "status" in data and data["status"] == "error":
                msg = data.get("message", "Unknown API error")
                code = data.get("code", 0)
                logger.warning(
                    "Twelve Data API error for %s (endpoint=%s): [%s] %s",
                    params.get("symbol", "?"), endpoint, code, msg,
                )
                return None

            return data

        except requests.Timeout:
            logger.warning("Timeout fetching %s for ticker %s", endpoint, params.get("symbol", "?"))
            return None
        except requests.ConnectionError:
            logger.error("Connection error to Twelve Data API (endpoint=%s)", endpoint)
            return None
        except requests.HTTPError as e:
            logger.warning(
                "HTTP %s error for %s (endpoint=%s)",
                e.response.status_code if e.response else "?",
                params.get("symbol", "?"),
                endpoint,
            )
            return None
        except (ValueError, KeyError) as e:
            logger.warning("Failed to parse Twelve Data response for %s: %s", params.get("symbol", "?"), type(e).__name__)
            return None

    def _track_rate(self) -> None:
        """Track request rate and warn if approaching limits."""
        now = time.time()
        self._request_count += 1
        self._request_timestamps.append(now)

        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60]
        recent = len(self._request_timestamps)

        if recent >= 7:
            logger.warning("Approaching Twelve Data rate limit: %d requests in last 60s", recent)

    def _fetch_from_api(self, symbol: str, outputsize: int = 300, start_date: Optional[str] = None) -> pd.DataFrame:
        params = {
            "symbol": symbol,
            "interval": "1day",
        }
        if start_date:
            params["start_date"] = start_date
            params["outputsize"] = 5000
        else:
            params["outputsize"] = outputsize

        data = self._api_request("time_series", params)

        if data is None or "values" not in data:
            df = self._yahoo_fallback(symbol, outputsize)
            if not df.empty:
                df["data_source"] = "yahoo"
            return df

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("datetime").reset_index(drop=True)
        df["data_source"] = "twelve_data"
        return df

    def _yahoo_fallback(self, symbol: str, outputsize: int = 300) -> pd.DataFrame:
        try:
            from yahoo_provider import fetch_yahoo_history
            from symbol_mapper import canonical_ticker
            market = "BIST" if ":BIST" in symbol else None
            bare = canonical_ticker(symbol)
            logger.info("Twelve Data failed for %s — trying Yahoo Finance fallback", symbol)
            df = fetch_yahoo_history(bare, period="2y", market=market)
            if not df.empty:
                logger.info("Yahoo Finance fallback succeeded for %s (%d rows)", symbol, len(df))
                if outputsize and len(df) > outputsize:
                    df = df.tail(outputsize).reset_index(drop=True)
            return df
        except Exception as e:
            logger.error("Yahoo Finance fallback error for %s: %s", symbol, e)
            return pd.DataFrame(columns=OHLCV_COLUMNS)

    def get_daily_history(
        self,
        ticker: str,
        outputsize: int = 300,
        market: Optional[str] = None,
    ) -> pd.DataFrame:
        # BIST stocks: Twelve Data's BIST data is unreliable (returns mixed/wrong
        # prices for many symbols).  Always use Yahoo Finance directly and skip
        # the Twelve Data disk-cache pipeline entirely for this market.
        if market and market.upper() == "BIST":
            df = self._yahoo_fallback(f"{ticker}:BIST", outputsize)
            if not df.empty:
                return df
            logger.warning("Yahoo fallback empty for BIST ticker %s", ticker)
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        symbol = self._resolve_symbol(ticker, market)
        ck = _cache_key("history", symbol=symbol, outputsize=outputsize)

        mem_cached = _cache_get(ck)
        if mem_cached is not None:
            return mem_cached.copy()

        def _disk_fetch(sym, outputsize=300, start_date=None):
            return self._fetch_from_api(sym, outputsize=outputsize, start_date=start_date)

        df = get_cached_or_fetch(symbol, _disk_fetch, outputsize=outputsize)

        if df is not None and not df.empty:
            _cache_set(ck, df, ttl=CACHE_TTL_HISTORY)
            return df.copy()

        logger.warning("No history data for %s — returning empty DataFrame", ticker)
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    def get_quote(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Fetch the latest real-time quote from Twelve Data.

        Results are cached using TTL from config.CACHE_TTL_QUOTE.
        """
        symbol = self._resolve_symbol(ticker, market)
        ck = _cache_key("quote", symbol=symbol)

        cached = _cache_get(ck)
        if cached is not None:
            return dict(cached)

        data = self._api_request("quote", {"symbol": symbol})

        if data is None or "close" not in data:
            logger.warning("No quote data for %s", ticker)
            return None

        # Twelve Data /quote: "price" = current real-time price, "close" = previous close
        current_price = _safe_float(data.get("price")) or _safe_float(data.get("close"))
        result = {
            "price": current_price,
            "open": _safe_float(data.get("open")),
            "high": _safe_float(data.get("high")),
            "low": _safe_float(data.get("low")),
            "volume": _safe_float(data.get("volume")),
            "change": _safe_float(data.get("change")),
            "percent_change": _safe_float(data.get("percent_change")),
            "previous_close": _safe_float(data.get("previous_close") or data.get("close")),
            "fifty_two_week_high": _safe_float(data.get("fifty_two_week", {}).get("high")),
            "fifty_two_week_low": _safe_float(data.get("fifty_two_week", {}).get("low")),
            "name": data.get("name", ticker),
            "exchange": data.get("exchange", ""),
        }

        _cache_set(ck, result, ttl=CACHE_TTL_QUOTE)
        return dict(result)

    def get_52w_high(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """
        Get the 52-week high, preferring quote data, falling back to history.
        """
        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("fifty_two_week_high") is not None:
            return quote["fifty_two_week_high"]

        return super().get_52w_high(ticker, market=market)

    def enrich_record(self, record: dict) -> dict:
        """
        Enrich a stock record with all price-derived fields from Twelve Data.

        Fetches history once and derives all fields from it.
        """
        ticker = record.get("ticker", "")
        market = record.get("market")
        if not ticker:
            return record

        result = dict(record)

        history = self.get_daily_history(ticker, outputsize=300, market=market)
        result["price_data"] = history

        result["data_source"] = "twelve_data"
        if "data_source" in history.columns and not history.empty:
            src = history["data_source"].iloc[-1]
            if src == "yahoo":
                result["data_source"] = "yahoo"

        if history.empty:
            logger.warning("No history for %s — skipping enrichment", ticker)
            return result

        closes = history["close"].values
        history_last_close = float(closes[-1])

        # Try real-time quote first; fall back to last historical close
        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("price") is not None:
            current = quote["price"]
            result["price"] = round(float(current), 2)
            logger.debug("Price for %s from quote: %.2f", ticker, current)
        else:
            current = history_last_close
            result["price"] = round(float(current), 2)
            logger.debug("Price for %s from history close: %.2f", ticker, current)

        periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
        for field, days in periods.items():
            if len(closes) >= days and closes[-days] != 0:
                result[field] = round((current / closes[-days] - 1) * 100, 2)

        if "volume" in history.columns and len(history) >= 20:
            result["avg_volume_20d"] = round(float(history["volume"].tail(20).mean()), 0)

        if "high" in history.columns and len(history) >= 21:
            high_52w = float(history["high"].tail(min(252, len(history))).max())
            if high_52w > 0:
                result["distance_to_52w_high"] = round((current / high_52w - 1) * 100, 2)

        return result


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _sf(value) -> float:
    v = _safe_float(value)
    return v if v is not None else np.nan


def fetch_twelve_fundamentals(
    ticker: str,
    api_key: str,
    base_url: str = "https://api.twelvedata.com",
    market: Optional[str] = None,
) -> dict:
    from symbol_mapper import resolve_twelve_symbol
    symbol = resolve_twelve_symbol(ticker, market)

    result: Dict[str, Any] = {"ticker": ticker, "data_provider": "twelve_data"}

    def _api_get(endpoint: str, extra_params: Optional[dict] = None) -> Optional[dict]:
        params = {"symbol": symbol, "apikey": api_key}
        if extra_params:
            params.update(extra_params)
        try:
            resp = requests.get(
                f"{base_url}/{endpoint}",
                params=params,
                timeout=API_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(API_RETRY_DELAY)
                resp = requests.get(
                    f"{base_url}/{endpoint}",
                    params=params,
                    timeout=API_REQUEST_TIMEOUT,
                )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("status") == "error":
                logger.debug("TD %s error for %s: %s", endpoint, symbol, data.get("message", ""))
                return None
            return data
        except Exception as e:
            logger.debug("TD %s failed for %s: %s", endpoint, symbol, e)
            return None

    stats = _api_get("statistics")
    if stats and isinstance(stats, dict) and "statistics" in stats:
        s = stats["statistics"]
        val = s.get("valuations_metrics", {})
        fin = s.get("financials", {})
        bal = fin.get("balance_sheet", {})
        inc = fin.get("income_statement", {})

        result["company_name"] = stats.get("meta", {}).get("name", ticker)
        result["market_cap"] = _sf(val.get("market_capitalization"))
        result["pe"] = _sf(val.get("trailing_pe"))
        result["pb"] = _sf(val.get("price_to_book"))
        result["peg"] = _sf(val.get("peg_ratio"))
        result["ev_ebitda"] = _sf(val.get("enterprise_to_ebitda"))

        result["revenue"] = _sf(inc.get("revenue_ttm"))
        result["net_income"] = _sf(inc.get("net_income_ttm"))
        result["ebitda"] = _sf(inc.get("ebitda"))
        result["gross_profit"] = _sf(inc.get("gross_profit_ttm"))
        result["eps"] = _sf(inc.get("diluted_eps_ttm"))

        result["total_assets"] = _sf(bal.get("total_assets"))
        result["total_debt"] = _sf(bal.get("total_debt"))
        result["equity"] = _sf(bal.get("total_shareholder_equity"))
        result["cash"] = _sf(bal.get("cash_and_short_term_investments"))

    profile = _api_get("profile")
    if profile and isinstance(profile, dict):
        result.setdefault("company_name", profile.get("name", ticker))
        result["sector"] = profile.get("sector", "")
        result["industry"] = profile.get("industry", "")

    if "sector" not in result:
        result["sector"] = ""
    if "industry" not in result:
        result["industry"] = ""

    inc_data = _api_get("income_statement", {"period": "annual"})
    if inc_data and isinstance(inc_data, dict):
        items = inc_data.get("income_statement", [])
        if isinstance(items, list) and len(items) >= 2:
            curr = items[0]
            prev = items[1]
            if "revenue" not in result or np.isnan(result.get("revenue", np.nan)):
                result["revenue"] = _sf(curr.get("revenue") or curr.get("sales"))
            if "net_income" not in result or np.isnan(result.get("net_income", np.nan)):
                result["net_income"] = _sf(curr.get("net_income"))
            result["revenue_prev_year"] = _sf(prev.get("revenue") or prev.get("sales"))
            result["net_income_prev_year"] = _sf(prev.get("net_income"))
            if "gross_profit" not in result or np.isnan(result.get("gross_profit", np.nan)):
                result["gross_profit"] = _sf(curr.get("gross_profit"))
            if "ebitda" not in result or np.isnan(result.get("ebitda", np.nan)):
                result["ebitda"] = _sf(curr.get("ebitda"))
            oi = _sf(curr.get("operating_income"))
            if not np.isnan(oi):
                result["operating_income"] = oi

    bal_data = _api_get("balance_sheet", {"period": "annual"})
    if bal_data and isinstance(bal_data, dict):
        items = bal_data.get("balance_sheet", [])
        if isinstance(items, list) and len(items) >= 1:
            curr = items[0]
            if "total_assets" not in result or np.isnan(result.get("total_assets", np.nan)):
                result["total_assets"] = _sf(curr.get("total_assets"))
            if "total_debt" not in result or np.isnan(result.get("total_debt", np.nan)):
                td = _sf(curr.get("total_debt"))
                if np.isnan(td):
                    ltd = _sf(curr.get("long_term_debt"))
                    std = _sf(curr.get("short_term_debt") or curr.get("current_debt"))
                    if not np.isnan(ltd):
                        td = ltd + (std if not np.isnan(std) else 0)
                result["total_debt"] = td
            if "equity" not in result or np.isnan(result.get("equity", np.nan)):
                result["equity"] = _sf(
                    curr.get("total_shareholder_equity") or curr.get("total_equity")
                )
            if "cash" not in result or np.isnan(result.get("cash", np.nan)):
                result["cash"] = _sf(
                    curr.get("cash_and_short_term_investments") or curr.get("cash_and_equivalents")
                )

    rev = result.get("revenue", np.nan)
    ni = result.get("net_income", np.nan)
    eq = result.get("equity", np.nan)
    td_val = result.get("total_debt", np.nan)
    ta = result.get("total_assets", np.nan)

    if not np.isnan(ni) and not np.isnan(rev) and rev != 0:
        result.setdefault("net_margin", ni / rev)
    if not np.isnan(td_val) and not np.isnan(eq) and eq > 0:
        result.setdefault("debt_to_equity", td_val / eq)
    if not np.isnan(ni) and not np.isnan(eq) and eq > 0:
        result.setdefault("roe", ni / eq)
    if not np.isnan(ni) and not np.isnan(ta) and ta > 0:
        result.setdefault("roa", ni / ta)
    if not np.isnan(eq) and not np.isnan(ta) and ta > 0:
        result.setdefault("equity_to_assets", eq / ta)

    has_financials = any(
        not np.isnan(result.get(f, np.nan))
        for f in ["revenue", "net_income", "equity"]
    )
    if has_financials:
        logger.info(
            "TD fundamentals OK for %s: revenue=%s, net_income=%s, equity=%s",
            ticker, result.get("revenue"), result.get("net_income"), result.get("equity"),
        )
    else:
        logger.info("TD fundamentals: no financial data for %s", ticker)

    return result
