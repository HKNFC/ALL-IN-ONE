import os
import logging
import time
import tempfile
import threading
import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime, date

logger = logging.getLogger("stock_screener.disk_cache")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")
OHLCV_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]
DEFAULT_OUTPUTSIZE = 300
CACHE_REFRESH_HOURS = 20

os.makedirs(CACHE_DIR, exist_ok=True)

_write_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(symbol: str) -> threading.Lock:
    with _locks_lock:
        if symbol not in _write_locks:
            _write_locks[symbol] = threading.Lock()
        return _write_locks[symbol]


def _clean_price_outliers(df: pd.DataFrame, gap_ratio: float = 2.5) -> pd.DataFrame:
    """
    Remove rows whose close price belongs to a spurious price cluster.

    Algorithm:
    1. Sort valid prices and detect natural cluster boundaries where
       consecutive sorted values jump by > gap_ratio.
    2. Among all detected clusters, pick the one with the LOWEST log-space
       standard deviation (most internally consistent = real prices).
    3. Remove rows that fall outside the winning cluster range.

    This correctly handles cases where an API mixes two or more different
    stocks' prices in the same time series, even when the spurious cluster
    contains more rows than the true cluster.

    Example: ASGYO true price ~10-11 TL (log_std≈0.05, 229 rows)
             spurious data ~50-200 TL (log_std≈0.60, 272 rows)
             → picks ASGYO cluster because log_std is lower.
    """
    if df.empty or "close" not in df.columns or len(df) < 10:
        return df

    closes = df["close"].values.astype(float)
    valid = closes[closes > 0]
    if len(valid) < 10:
        return df

    sorted_v = np.sort(valid)

    # Detect cluster boundaries
    boundaries = [0]
    for i in range(len(sorted_v) - 1):
        ratio = sorted_v[i + 1] / sorted_v[i]
        if ratio > gap_ratio:
            boundaries.append(i + 1)
    boundaries.append(len(sorted_v))

    if len(boundaries) == 2:
        # Single cluster — nothing to remove
        return df

    # Build clusters and compute log-space std (lower = more consistent)
    clusters = []
    for lo_i, hi_i in zip(boundaries[:-1], boundaries[1:]):
        segment = sorted_v[lo_i:hi_i]
        log_std = float(np.std(np.log(segment))) if len(segment) >= 2 else float("inf")
        clusters.append({
            "lo": float(segment.min()),
            "hi": float(segment.max()),
            "count": len(segment),
            "log_std": log_std,
        })

    # Pick the most internally consistent cluster
    best = min(clusters, key=lambda c: c["log_std"])

    lo_bound = best["lo"] / gap_ratio
    hi_bound = best["hi"] * gap_ratio

    mask = np.ones(len(df), dtype=bool)
    for i, c in enumerate(closes):
        if c > 0 and not (lo_bound <= c <= hi_bound):
            mask[i] = False

    removed = int((~mask).sum())
    if removed > 0:
        logger.info(
            "Price cluster filter: removed %d/%d rows "
            "(best cluster lo=%.2f hi=%.2f log_std=%.3f count=%d)",
            removed, len(df), best["lo"], best["hi"], best["log_std"], best["count"],
        )
    return df[mask].reset_index(drop=True)


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _safe_filename(symbol: str) -> str:
    return symbol.replace(":", "_").replace("/", "_").replace("\\", "_").replace(".", "_") + ".parquet"


def _cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, _safe_filename(symbol))


def _is_cache_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        mtime = os.path.getmtime(path)
        age_hours = (time.time() - mtime) / 3600
        return age_hours < CACHE_REFRESH_HOURS
    except OSError:
        return False


def read_cache(symbol: str) -> Optional[pd.DataFrame]:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty or "datetime" not in df.columns:
            return None
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("datetime").reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning("Corrupted cache for %s, removing: %s", symbol, e)
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def _atomic_write(path: str, df: pd.DataFrame) -> bool:
    _ensure_cache_dir()
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".parquet", dir=CACHE_DIR)
        os.close(fd)
        df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logger.error("Atomic write failed for %s: %s", path, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def write_cache(symbol: str, df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    path = _cache_path(symbol)
    lock = _get_lock(symbol)
    with lock:
        save_df = df[OHLCV_COLUMNS].copy() if all(c in df.columns for c in OHLCV_COLUMNS) else df.copy()
        save_df = save_df.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last").reset_index(drop=True)
        save_df = _clean_price_outliers(save_df)
        return _atomic_write(path, save_df)


def merge_cache(symbol: str, new_data: pd.DataFrame) -> pd.DataFrame:
    lock = _get_lock(symbol)
    with lock:
        existing = read_cache(symbol)
        if existing is None or existing.empty:
            save_df = new_data.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last").reset_index(drop=True)
            save_df = _clean_price_outliers(save_df)
            _atomic_write(_cache_path(symbol), save_df[OHLCV_COLUMNS] if all(c in save_df.columns for c in OHLCV_COLUMNS) else save_df)
            return save_df

        combined = pd.concat([existing, new_data], ignore_index=True)
        combined["datetime"] = pd.to_datetime(combined["datetime"])
        combined = combined.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last").reset_index(drop=True)
        combined = _clean_price_outliers(combined)

        save_df = combined[OHLCV_COLUMNS] if all(c in combined.columns for c in OHLCV_COLUMNS) else combined
        _atomic_write(_cache_path(symbol), save_df)
        return combined


def get_missing_date_range(symbol: str) -> Optional[str]:
    cached = read_cache(symbol)
    if cached is None or cached.empty:
        return None
    last_date = cached["datetime"].max()
    if pd.isna(last_date):
        return None
    today = pd.Timestamp(date.today())
    if last_date.normalize() >= today.normalize():
        return None
    next_day = last_date + pd.Timedelta(days=1)
    return next_day.strftime("%Y-%m-%d")


def needs_refresh(symbol: str) -> bool:
    path = _cache_path(symbol)
    return not _is_cache_fresh(path)


class FetchError(Exception):
    pass


def get_cached_or_fetch(
    symbol: str,
    fetch_fn,
    outputsize: int = DEFAULT_OUTPUTSIZE,
) -> pd.DataFrame:
    path = _cache_path(symbol)
    empty_df = pd.DataFrame(columns=OHLCV_COLUMNS)

    if _is_cache_fresh(path):
        cached = read_cache(symbol)
        if cached is not None and not cached.empty:
            cached = _clean_price_outliers(cached)
            logger.debug("Disk cache hit for %s (%d rows)", symbol, len(cached))
            return cached.tail(outputsize).reset_index(drop=True)

    cached = read_cache(symbol)

    if cached is not None and not cached.empty:
        cached = _clean_price_outliers(cached)
        start_date = get_missing_date_range(symbol)
        if start_date is None:
            logger.debug("Cache for %s is complete up to today", symbol)
            _touch_cache(symbol)
            return cached.tail(outputsize).reset_index(drop=True)

        try:
            logger.info("Incremental fetch for %s from %s", symbol, start_date)
            new_data = fetch_fn(symbol, start_date=start_date)
            if new_data is not None and not new_data.empty:
                merged = merge_cache(symbol, new_data)
                return merged.tail(outputsize).reset_index(drop=True)
            else:
                _touch_cache(symbol)
                return cached.tail(outputsize).reset_index(drop=True)
        except Exception as e:
            logger.warning("Incremental fetch failed for %s: %s — using stale cache", symbol, e)
            return cached.tail(outputsize).reset_index(drop=True)

    try:
        logger.info("Full fetch for %s (outputsize=%d)", symbol, outputsize)
        full_data = fetch_fn(symbol, outputsize=outputsize)
        if full_data is not None and not full_data.empty:
            write_cache(symbol, full_data)
            return full_data.tail(outputsize).reset_index(drop=True)
        return empty_df
    except Exception as e:
        logger.error("Full fetch failed for %s: %s", symbol, e)
        return empty_df


def _touch_cache(symbol: str) -> None:
    path = _cache_path(symbol)
    if os.path.exists(path):
        try:
            os.utime(path, None)
        except OSError:
            pass


def clear_symbol_cache(symbol: str) -> bool:
    path = _cache_path(symbol)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError as e:
            logger.error("Failed to remove cache for %s: %s", symbol, e)
    return False


def clear_all_cache() -> int:
    _ensure_cache_dir()
    count = 0
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith(".parquet"):
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
                count += 1
            except OSError:
                pass
    return count


def get_cache_stats() -> dict:
    _ensure_cache_dir()
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
    total_size = 0
    fresh = 0
    stale = 0
    for fname in files:
        fpath = os.path.join(CACHE_DIR, fname)
        try:
            total_size += os.path.getsize(fpath)
            if _is_cache_fresh(fpath):
                fresh += 1
            else:
                stale += 1
        except OSError:
            stale += 1
    return {
        "total_files": len(files),
        "fresh": fresh,
        "stale": stale,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }
