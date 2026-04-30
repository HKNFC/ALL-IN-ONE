"""
Filter Engine

Provides preset and custom quality filters for screening stocks before
scoring. Presets apply threshold-based rules (e.g., ROIC > 5%, D/E < 2.5)
to remove low-quality or speculative stocks from the universe.

Presets:
  - none:   No filter — show all stocks
  - basic:  Profitable companies with positive equity and reasonable leverage
  - strict: High-quality companies with strong returns and positive momentum
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List


FILTER_PRESETS = {
    "none": {
        "label": "Filtre Yok",
        "description": "Tüm hisseleri ön eleme yapmadan göster",
        "rules": {},
    },
    "basic": {
        "label": "Temel Kalite",
        "description": "Kârlı, pozitif özkaynaklı ve makul kaldıraçlı şirketler",
        "rules": {
            "equity_gt": 0,
            "net_income_gt": 0,
            "net_margin_gt": 0,
            "debt_to_equity_lt": 2.5,
        },
    },
    "strict": {
        "label": "Sıkı Kalite",
        "description": "Güçlü getiri, düşük kaldıraç ve pozitif momentum ile yüksek kaliteli şirketler",
        "rules": {
            "equity_gt": 0,
            "net_income_gt": 0,
            "roic_gt": 0.10,
            "net_margin_gt": 0.05,
            "debt_to_equity_lt": 1.5,
            "return_12m_gt": 0,
        },
    },
}


def _safe_check(value, op: str, threshold: float, strict: bool = False) -> bool:
    """Check if a value passes a comparison against a threshold, handling NaN/None safely.
    When strict=False (default), NaN/None values pass the check (data absence is not a failure).
    When strict=True, NaN/None values fail the check."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return not strict
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(v):
        return False
    if op == "gt":
        return v > threshold
    elif op == "lt":
        return v < threshold
    elif op == "gte":
        return v >= threshold
    elif op == "lte":
        return v <= threshold
    return False


_RULE_COLUMN_MAP = {
    "equity_gt": ("equity", "gt"),
    "net_income_gt": ("net_income", "gt"),
    "roic_gt": ("roic", "gt"),
    "revenue_growth_gt": ("revenue_growth", "gt"),
    "net_margin_gt": ("net_margin", "gt"),
    "debt_to_equity_lt": ("debt_to_equity", "lt"),
    "peg_gt": ("peg", "gt"),
    "pe_gt": ("pe", "gt"),
    "return_12m_gt": ("return_12m", "gt"),
    "avg_volume_20d_gte": ("avg_volume_20d", "gte"),
}


def apply_preset_filter(
    df: pd.DataFrame,
    preset: str = "none",
    min_avg_volume: Optional[float] = None,
) -> pd.DataFrame:
    """Apply a named preset filter to the DataFrame, returning only passing rows."""
    if preset not in FILTER_PRESETS:
        preset = "none"

    rules = dict(FILTER_PRESETS[preset]["rules"])

    if min_avg_volume is not None and min_avg_volume > 0:
        rules["avg_volume_20d_gte"] = min_avg_volume

    if not rules:
        return df.copy()

    mask = pd.Series(True, index=df.index)

    for rule_key, threshold in rules.items():
        if rule_key not in _RULE_COLUMN_MAP:
            continue
        col, op = _RULE_COLUMN_MAP[rule_key]
        if col not in df.columns:
            continue
        rule_mask = df[col].apply(lambda v, o=op, t=threshold: _safe_check(v, o, t))
        mask = mask & rule_mask

    return df[mask].reset_index(drop=True)


def apply_custom_filter(
    df: pd.DataFrame,
    rules: Dict[str, float],
) -> pd.DataFrame:
    """Apply a custom set of filter rules to the DataFrame."""
    if not rules:
        return df.copy()

    mask = pd.Series(True, index=df.index)

    for rule_key, threshold in rules.items():
        if rule_key not in _RULE_COLUMN_MAP:
            continue
        col, op = _RULE_COLUMN_MAP[rule_key]
        if col not in df.columns:
            continue
        rule_mask = df[col].apply(lambda v, o=op, t=threshold: _safe_check(v, o, t))
        mask = mask & rule_mask

    return df[mask].reset_index(drop=True)


def rank_and_limit(
    df: pd.DataFrame,
    top_n: Optional[int] = None,
    sort_by: str = "rs_score",
) -> pd.DataFrame:
    """Sort by the chosen score column descending, assign rank, and optionally limit to top N."""
    if df.empty:
        return df

    sort_col = sort_by if sort_by in df.columns else "rs_score"
    if sort_col not in df.columns:
        return df

    ranked = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    ranked["rank"] = range(1, len(ranked) + 1)

    if top_n is not None and top_n > 0:
        ranked = ranked.head(top_n).reset_index(drop=True)

    return ranked


def top_n_results(
    df: pd.DataFrame,
    n: int = 10,
    preset: str = "none",
    min_avg_volume: Optional[float] = None,
) -> pd.DataFrame:
    """Convenience: apply preset filter, then rank and limit to top N."""
    filtered = apply_preset_filter(df, preset=preset, min_avg_volume=min_avg_volume)
    return rank_and_limit(filtered, top_n=n)


def filter_by_score(
    df: pd.DataFrame,
    min_rs_score: float = 0,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Filter stocks by minimum RS Score and optionally limit results."""
    filtered = df[df["rs_score"] >= min_rs_score].copy()
    if top_n is not None and top_n > 0:
        filtered = filtered.head(top_n)
    return filtered.reset_index(drop=True)


def filter_by_category_score(
    df: pd.DataFrame,
    category: str,
    min_score: float = 50,
) -> pd.DataFrame:
    """Filter stocks by minimum sub-score in a specific category."""
    valid = [
        "financial_strength", "growth", "margin_quality",
        "valuation", "momentum",
    ]
    if category not in valid:
        raise ValueError(f"Invalid category '{category}'. Choose from {valid}")
    if category not in df.columns:
        return df
    mask = df[category].apply(
        lambda x: x is not None and np.isfinite(x) and float(x) >= min_score
    )
    return df[mask].reset_index(drop=True)


def filter_by_sector(df: pd.DataFrame, sectors: list) -> pd.DataFrame:
    """Filter stocks to include only the specified sectors."""
    if not sectors or "sector" not in df.columns:
        return df
    return df[df["sector"].isin(sectors)].reset_index(drop=True)


def filter_by_market(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Filter stocks to include only those from the specified market."""
    if "market" not in df.columns:
        return df
    return df[df["market"] == market].reset_index(drop=True)


def get_preset_names() -> List[str]:
    """Return the list of available filter preset keys."""
    return list(FILTER_PRESETS.keys())


def get_preset_info(preset: str) -> Dict[str, Any]:
    """Return the label, description, and rules for a named preset."""
    return FILTER_PRESETS.get(preset, FILTER_PRESETS["none"])
