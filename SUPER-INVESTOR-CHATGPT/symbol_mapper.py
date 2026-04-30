import os
import json
import logging
from typing import Optional

logger = logging.getLogger("stock_screener.symbol_mapper")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "symbol_map.json")

_symbol_cache: Optional[dict] = None

YAHOO_BENCHMARK_MAP = {
    "XU100": "XU100.IS",
    "SPX": "^GSPC",
    "^GSPC": "^GSPC",
}

TWELVE_BENCHMARK_MAP = {
    "XU100": "XU100:BIST",
    "SPX": "SPX",
}


def load_symbol_cache() -> dict:
    global _symbol_cache
    if _symbol_cache is not None:
        return _symbol_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                _symbol_cache = json.load(f)
                logger.info("Loaded symbol cache with %d entries", len(_symbol_cache))
                return _symbol_cache
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load symbol cache: %s", e)
    _symbol_cache = {}
    return _symbol_cache


def save_symbol_cache() -> None:
    global _symbol_cache
    if _symbol_cache is None:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(_symbol_cache, f, indent=2)
        logger.debug("Saved symbol cache with %d entries", len(_symbol_cache))
    except OSError as e:
        logger.error("Failed to save symbol cache: %s", e)


def _cache_key(ticker: str, market: str, provider: str) -> str:
    return f"{provider}:{market}:{ticker}"


def get_cached_mapping(ticker: str, market: str, provider: str) -> Optional[str]:
    cache = load_symbol_cache()
    return cache.get(_cache_key(ticker, market, provider))


def set_cached_mapping(ticker: str, market: str, provider: str, resolved: str) -> None:
    cache = load_symbol_cache()
    cache[_cache_key(ticker, market, provider)] = resolved
    save_symbol_cache()


def resolve_yahoo_symbol(ticker: str, market: Optional[str] = None) -> str:
    if ticker.endswith(".IS") or ticker.startswith("^"):
        return ticker
    clean = ticker.replace(":BIST", "")
    if market and market.upper() == "BIST":
        return f"{clean}.IS"
    return clean


def resolve_twelve_symbol(ticker: str, market: Optional[str] = None) -> str:
    clean = ticker.replace(":BIST", "").replace(".IS", "")
    if market and market.upper() == "BIST":
        return f"{clean}:BIST"
    return clean


def resolve_yahoo_benchmark(index_ticker: str) -> str:
    return YAHOO_BENCHMARK_MAP.get(index_ticker, index_ticker)


def resolve_twelve_benchmark(index_ticker: str, market: Optional[str] = None) -> str:
    if index_ticker in TWELVE_BENCHMARK_MAP:
        return TWELVE_BENCHMARK_MAP[index_ticker]
    return resolve_twelve_symbol(index_ticker, market)


def map_symbol_for_provider(
    ticker: str,
    market: Optional[str] = None,
    provider: str = "twelve_data",
) -> str:
    market_key = (market or "").upper()

    cached = get_cached_mapping(ticker, market_key, provider)
    if cached:
        return cached

    if provider == "yahoo":
        resolved = resolve_yahoo_symbol(ticker, market_key)
    elif provider == "twelve_data":
        resolved = resolve_twelve_symbol(ticker, market_key)
    else:
        resolved = ticker

    set_cached_mapping(ticker, market_key, provider, resolved)
    return resolved


def canonical_ticker(symbol: str) -> str:
    return symbol.replace(":BIST", "").replace(".IS", "").strip().upper()
