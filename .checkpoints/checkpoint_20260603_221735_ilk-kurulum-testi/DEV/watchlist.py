"""
Watchlist Manager

Persistent JSON-backed watchlist for tracking stocks of interest.
Supports add, remove, clear, score updates, and CSV export.
Stored in watchlist.json (local file, not version-controlled).
"""

import json
import os
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("stock_screener.watchlist")

WATCHLIST_FILE = "watchlist.json"


def _load_raw() -> Dict[str, Any]:
    """Load the raw watchlist JSON from disk, returning an empty structure on failure."""
    if not os.path.exists(WATCHLIST_FILE):
        return {"stocks": {}, "updated_at": 0}
    try:
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        if "stocks" not in data:
            data = {"stocks": {}, "updated_at": 0}
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read watchlist file: %s", e)
        return {"stocks": {}, "updated_at": 0}


def _save_raw(data: Dict[str, Any]) -> bool:
    """Persist watchlist data to disk. Returns True on success, False on IO error."""
    data["updated_at"] = time.time()
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except IOError as e:
        logger.error("Failed to write watchlist file: %s", e)
        return False


def get_watchlist() -> List[Dict[str, Any]]:
    """Return all watchlist entries sorted by ticker, each as a dict."""
    data = _load_raw()
    items = []
    for ticker, info in sorted(data["stocks"].items()):
        entry = {"ticker": ticker}
        entry.update(info)
        items.append(entry)
    return items


def get_watchlist_tickers() -> List[str]:
    """Return a sorted list of ticker symbols currently in the watchlist."""
    data = _load_raw()
    return sorted(data["stocks"].keys())


def is_in_watchlist(ticker: str) -> bool:
    """Check whether a ticker is already in the watchlist."""
    data = _load_raw()
    return ticker in data["stocks"]


def add_to_watchlist(
    ticker: str,
    rs_score: Optional[float] = None,
    rs_category: Optional[str] = None,
    price: Optional[float] = None,
    company_name: Optional[str] = None,
    market: Optional[str] = None,
) -> bool:
    """Add or update a stock in the watchlist. Returns True on success."""
    data = _load_raw()
    data["stocks"][ticker] = {
        "rs_score": rs_score,
        "rs_category": rs_category,
        "price": price,
        "company_name": company_name or ticker,
        "market": market or "",
        "added_at": time.time(),
    }
    ok = _save_raw(data)
    if ok:
        logger.info("Added %s to watchlist", ticker)
    return ok


def remove_from_watchlist(ticker: str) -> bool:
    """Remove a stock from the watchlist. Returns False if ticker not found."""
    data = _load_raw()
    if ticker not in data["stocks"]:
        return False
    del data["stocks"][ticker]
    ok = _save_raw(data)
    if ok:
        logger.info("Removed %s from watchlist", ticker)
    return ok


def clear_watchlist() -> int:
    """Remove all stocks from the watchlist. Returns the count of items removed."""
    data = _load_raw()
    count = len(data["stocks"])
    data["stocks"] = {}
    ok = _save_raw(data)
    if ok:
        logger.info("Cleared watchlist (%d items)", count)
    return count if ok else 0


def update_watchlist_scores(scored_rows: List[Dict[str, Any]]) -> int:
    """Bulk-update RS scores and prices for watchlist stocks from scored data."""
    data = _load_raw()
    updated = 0
    for row in scored_rows:
        ticker = row.get("ticker", "")
        if ticker in data["stocks"]:
            data["stocks"][ticker]["rs_score"] = row.get("rs_score")
            data["stocks"][ticker]["rs_category"] = row.get("rs_category")
            data["stocks"][ticker]["price"] = row.get("price")
            updated += 1
    if updated > 0:
        _save_raw(data)
        logger.info("Updated scores for %d watchlist stocks", updated)
    return updated


def export_watchlist_csv() -> str:
    """Export the watchlist as a CSV string using proper csv escaping."""
    import io
    import csv as csv_mod
    items = get_watchlist()
    columns = ["ticker", "company_name", "rs_score", "rs_category", "price", "market"]
    output = io.StringIO()
    writer = csv_mod.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({c: item.get(c, "") for c in columns})
    return output.getvalue()
