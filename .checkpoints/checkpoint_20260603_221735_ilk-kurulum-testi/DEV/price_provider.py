import pandas as pd
import numpy as np
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict

logger = logging.getLogger("stock_screener.provider")


class PriceProvider(ABC):
    """
    Abstract base class for market data providers.

    Subclass this to add a new data source (e.g., Yahoo Finance, Alpha Vantage).
    Each method must handle its own errors and return sensible defaults on failure.

    All methods accept an optional `market` parameter for exchange-specific
    ticker resolution (e.g., BIST tickers may need an exchange suffix).
    """

    @abstractmethod
    def get_daily_history(
        self,
        ticker: str,
        outputsize: int = 252,
        market: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV history for a ticker.

        Returns a DataFrame sorted by date ascending with columns:
            datetime, open, high, low, close, volume

        Returns an empty DataFrame on failure.
        """
        ...

    @abstractmethod
    def get_quote(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Fetch the latest real-time quote for a ticker.

        Returns a dict with at minimum:
            price, volume, change, percent_change

        Returns None on failure.
        """
        ...

    def get_latest_price(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """
        Get the most recent closing/last price for a ticker.

        Tries the quote endpoint first, falls back to the last row of daily history.
        """
        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("price") is not None:
            return quote["price"]

        history = self.get_daily_history(ticker, outputsize=5, market=market)
        if not history.empty:
            return float(history["close"].iloc[-1])

        return None

    def get_52w_high(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """Calculate the 52-week high from daily history."""
        history = self.get_daily_history(ticker, outputsize=252, market=market)
        if history.empty or "high" not in history.columns:
            return None
        return float(history["high"].max())

    def get_distance_to_52w_high(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """Calculate the percentage distance from current price to 52-week high."""
        high = self.get_52w_high(ticker, market=market)
        price = self.get_latest_price(ticker, market=market)
        if high is None or price is None or high == 0:
            return None
        return round((price / high - 1) * 100, 2)

    def get_period_returns(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Dict[str, Optional[float]]:
        """
        Calculate 1M, 3M, 6M, and 12M returns from daily history.

        Returns a dict with keys return_1m, return_3m, return_6m, return_12m.
        Values are percentages (e.g., 5.2 means +5.2%). None if insufficient data.
        """
        history = self.get_daily_history(ticker, outputsize=252, market=market)
        results: Dict[str, Optional[float]] = {
            "return_1m": None,
            "return_3m": None,
            "return_6m": None,
            "return_12m": None,
        }

        if history.empty or "close" not in history.columns:
            return results

        closes = history["close"].values
        current = closes[-1]

        periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
        for field, days in periods.items():
            if len(closes) >= days and closes[-days] != 0:
                results[field] = round((current / closes[-days] - 1) * 100, 2)

        return results

    def get_avg_volume_20d(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """Calculate the 20-day average trading volume."""
        history = self.get_daily_history(ticker, outputsize=30, market=market)
        if history.empty or "volume" not in history.columns or len(history) < 20:
            return None
        return round(float(history["volume"].tail(20).mean()), 0)

    def enrich_record(self, record: dict) -> dict:
        """
        Enrich a stock record dict with all price-derived fields.

        Pulls daily history once, then computes all derived fields from it.
        Attaches the raw price_data DataFrame to the record.
        """
        ticker = record.get("ticker", "")
        market = record.get("market")
        if not ticker:
            return record

        result = dict(record)
        history = self.get_daily_history(ticker, outputsize=252, market=market)
        result["price_data"] = history.copy()

        if history.empty:
            logger.warning("No price data for %s — skipping enrichment", ticker)
            return result

        closes = history["close"].values
        history_last_close = float(closes[-1])

        # Try real-time quote first; fall back to last historical close
        current = history_last_close
        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("price") is not None:
            current = float(quote["price"])
            logger.debug("Price for %s from quote: %.2f", ticker, current)
        result["price"] = round(current, 2)

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
