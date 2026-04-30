import pandas as pd
import numpy as np


def format_number(value, decimals: int = 2, prefix: str = "", suffix: str = "") -> str:
    """Format a number for display, handling None and NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    return f"{prefix}{value:,.{decimals}f}{suffix}"


def format_percentage(value, decimals: int = 2) -> str:
    """Format a value as a percentage string (value already in decimal form)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    return f"{value * 100:,.{decimals}f}%"


def format_pct_value(value, decimals: int = 1) -> str:
    """Format a value that is already a percentage (e.g., return_1m = 3.2 means 3.2%)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    return f"{value:+.{decimals}f}%"


def format_market_cap(value) -> str:
    """Format market cap into human-readable form (B/M/T)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    if value >= 1e12:
        return f"${value / 1e12:,.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:,.2f}M"
    return f"${value:,.0f}"


def format_large_number(value) -> str:
    """Format a large number (revenue, assets, etc.) into human-readable form."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e12:
        return f"{sign}${abs_val / 1e12:,.2f}T"
    if abs_val >= 1e9:
        return f"{sign}${abs_val / 1e9:,.2f}B"
    if abs_val >= 1e6:
        return f"{sign}${abs_val / 1e6:,.1f}M"
    return f"{sign}${abs_val:,.0f}"


def is_na(value) -> bool:
    """Check if a value is missing or non-finite (None, NaN, pd.NA, inf)."""
    if value is None:
        return True
    try:
        return not np.isfinite(float(value))
    except (ValueError, TypeError):
        return True
