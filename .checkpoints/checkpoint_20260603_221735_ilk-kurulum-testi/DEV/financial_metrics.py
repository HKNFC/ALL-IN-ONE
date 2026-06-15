"""
Financial Metrics Engine

Individual metric functions for computing derived financial ratios, margins,
growth rates, and return metrics from raw fundamental data.

Each function:
  - Handles division by zero safely (returns NaN)
  - Handles missing values explicitly (returns NaN)
  - Handles negative denominators where mathematically inappropriate (returns NaN)
  - Returns float (or NaN when metric is not meaningful)

The `append_all_derived_metrics` function appends every derived metric
as new columns to the master DataFrame.
"""

import pandas as pd
import numpy as np
from data_model import safe_float


# ---------------------------------------------------------------------------
# Balance Sheet Ratios
# ---------------------------------------------------------------------------

def calc_debt_to_equity(total_debt, equity) -> float:
    """
    Debt-to-Equity = total_debt / equity

    Measures financial leverage. A higher ratio means more debt-financed operations.

    Returns NaN when:
      - Either input is missing or non-finite
      - Equity is zero (undefined ratio)
      - Equity is negative (ratio loses meaning as a leverage indicator)
    """
    td = safe_float(total_debt)
    eq = safe_float(equity)
    if np.isnan(td) or np.isnan(eq):
        return np.nan
    if eq <= 0:
        return np.nan
    return td / eq


def calc_equity_to_assets(equity, total_assets) -> float:
    """
    Equity-to-Assets = equity / total_assets

    Measures the proportion of assets financed by shareholders' equity.
    Higher values indicate less reliance on debt.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative (not meaningful)
    """
    eq = safe_float(equity)
    ta = safe_float(total_assets)
    if np.isnan(eq) or np.isnan(ta):
        return np.nan
    if ta <= 0:
        return np.nan
    return eq / ta


def calc_net_income_to_assets(net_income, total_assets) -> float:
    """
    Net Income to Assets = net_income / total_assets

    A simplified return-on-assets measure using net income directly.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative
    """
    ni = safe_float(net_income)
    ta = safe_float(total_assets)
    if np.isnan(ni) or np.isnan(ta):
        return np.nan
    if ta <= 0:
        return np.nan
    return ni / ta


# ---------------------------------------------------------------------------
# Return Metrics
# ---------------------------------------------------------------------------

def calc_roe(net_income, equity) -> float:
    """
    Return on Equity = net_income / equity

    Measures how efficiently equity capital generates profit.

    Returns NaN when:
      - Either input is missing or non-finite
      - Equity is zero (undefined)
      - Equity is negative (ROE sign becomes misleading)
    """
    ni = safe_float(net_income)
    eq = safe_float(equity)
    if np.isnan(ni) or np.isnan(eq):
        return np.nan
    if eq <= 0:
        return np.nan
    return ni / eq


def calc_roa(net_income, total_assets) -> float:
    """
    Return on Assets = net_income / total_assets

    Measures how efficiently total assets generate profit.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative
    """
    return calc_net_income_to_assets(net_income, total_assets)


def calc_roic(operating_income, invested_capital, tax_rate: float = 0.25) -> float:
    """
    Return on Invested Capital = NOPAT / invested_capital

    Where NOPAT = operating_income * (1 - tax_rate).
    Measures how well a company generates returns on capital deployed.

    Args:
        operating_income: Operating income (EBIT)
        invested_capital: Total invested capital (equity + debt - cash, or as reported)
        tax_rate: Assumed effective tax rate for NOPAT calculation (default 25%)

    Returns NaN when:
      - Either input is missing or non-finite
      - Invested capital is zero or negative
      - Operating income is missing (NOPAT cannot be computed)
    """
    oi = safe_float(operating_income)
    ic = safe_float(invested_capital)
    if np.isnan(oi) or np.isnan(ic):
        return np.nan
    if ic <= 0:
        return np.nan
    nopat = oi * (1 - tax_rate)
    return nopat / ic


# ---------------------------------------------------------------------------
# Margin Metrics
# ---------------------------------------------------------------------------

def calc_gross_margin(gross_profit, revenue) -> float:
    """
    Gross Margin = gross_profit / revenue

    Measures the percentage of revenue retained after cost of goods sold.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero (undefined)
      - Revenue is negative (not meaningful)
    """
    gp = safe_float(gross_profit)
    rev = safe_float(revenue)
    if np.isnan(gp) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return gp / rev


def calc_operating_margin(operating_income, revenue) -> float:
    """
    Operating Margin = operating_income / revenue

    Measures operational efficiency after operating expenses.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    oi = safe_float(operating_income)
    rev = safe_float(revenue)
    if np.isnan(oi) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return oi / rev


def calc_net_margin(net_income, revenue) -> float:
    """
    Net Margin = net_income / revenue

    Measures the percentage of revenue that becomes profit after all expenses.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    ni = safe_float(net_income)
    rev = safe_float(revenue)
    if np.isnan(ni) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return ni / rev


def calc_ebitda_margin(ebitda, revenue) -> float:
    """
    EBITDA Margin = ebitda / revenue

    Measures operating profitability before depreciation, amortization, interest, and taxes.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    eb = safe_float(ebitda)
    rev = safe_float(revenue)
    if np.isnan(eb) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return eb / rev


# ---------------------------------------------------------------------------
# Growth Metrics
# ---------------------------------------------------------------------------

def calc_yoy_growth(current, previous) -> float:
    """
    Year-over-Year Growth = (current - previous) / abs(previous)

    Computes percentage change from previous period to current.
    Uses abs(previous) so that growth from a negative base is directionally correct.

    Returns NaN when:
      - Either input is missing or non-finite
      - Previous value is zero (growth from zero is undefined)
    """
    c = safe_float(current)
    p = safe_float(previous)
    if np.isnan(c) or np.isnan(p):
        return np.nan
    if p == 0:
        return np.nan
    return (c - p) / abs(p)


def calc_revenue_growth_yoy(revenue, revenue_prev_year) -> float:
    """
    Revenue Growth YoY = (revenue - revenue_prev_year) / abs(revenue_prev_year)

    Returns NaN if either value is missing/zero.
    """
    return calc_yoy_growth(revenue, revenue_prev_year)


def calc_net_income_growth_yoy(net_income, net_income_prev_year) -> float:
    """
    Net Income Growth YoY = (net_income - net_income_prev_year) / abs(net_income_prev_year)

    Returns NaN if either value is missing/zero.
    """
    return calc_yoy_growth(net_income, net_income_prev_year)


def calc_cagr(ending_value, beginning_value, years: float = 3.0) -> float:
    """
    Compound Annual Growth Rate = (ending / beginning)^(1/years) - 1

    Computes the annualized growth rate over the specified number of years.

    Returns NaN when:
      - Either input is missing or non-finite
      - Beginning value is zero (division by zero)
      - The ratio ending/beginning is negative (cannot take fractional root of negative)
      - Years is zero or negative
    """
    end = safe_float(ending_value)
    beg = safe_float(beginning_value)
    if np.isnan(end) or np.isnan(beg):
        return np.nan
    if beg == 0 or years <= 0:
        return np.nan

    ratio = end / beg

    # CAGR is undefined for negative ratios (e.g., profit turned to loss)
    # because we cannot raise a negative number to a fractional power
    if ratio <= 0:
        return np.nan

    return ratio ** (1.0 / years) - 1.0


def calc_revenue_cagr_3y(revenue, revenue_3y_ago) -> float:
    """
    Revenue 3-Year CAGR = (revenue / revenue_3y_ago)^(1/3) - 1

    Annualized revenue growth rate over a 3-year period.

    Returns NaN when:
      - Either value is missing or zero
      - The ratio is negative (e.g., revenue turned negative)
    """
    return calc_cagr(revenue, revenue_3y_ago, years=3.0)


def calc_eps_cagr_3y(eps, eps_3y_ago) -> float:
    """
    EPS 3-Year CAGR = (eps / eps_3y_ago)^(1/3) - 1

    Annualized earnings-per-share growth rate over a 3-year period.

    Returns NaN when:
      - Either value is missing or zero
      - The ratio is negative (e.g., EPS went from positive to negative)
    """
    return calc_cagr(eps, eps_3y_ago, years=3.0)


# ---------------------------------------------------------------------------
# Master DataFrame Enrichment
# ---------------------------------------------------------------------------

DERIVED_METRIC_COLUMNS = [
    "debt_to_equity",
    "equity_to_assets",
    "net_income_to_assets",
    "roe",
    "roa",
    "roic",
    "roic_approx",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "ebitda_margin",
    "revenue_growth",
    "earnings_growth",
    "revenue_cagr_3y",
    "eps_cagr_3y",
    "quality_profitable",
    "quality_growing",
    "quality_solvent",
]


def _calc_roic_approx(row) -> float:
    ni = safe_float(row.get("net_income"))
    eq = safe_float(row.get("equity"))
    td = safe_float(row.get("total_debt"))
    cash = safe_float(row.get("cash"))
    if np.isnan(ni):
        return np.nan
    invested = 0.0
    if not np.isnan(eq):
        invested += eq
    if not np.isnan(td):
        invested += td
    if not np.isnan(cash):
        invested -= cash
    if invested <= 0:
        return np.nan
    return ni / invested


def _calc_quality_flags(row) -> dict:
    ni = safe_float(row.get("net_income"))
    nm = safe_float(row.get("net_margin"))
    eq = safe_float(row.get("equity"))
    de = safe_float(row.get("debt_to_equity"))
    rg = safe_float(row.get("revenue_growth"))

    profitable = (not np.isnan(ni) and ni > 0 and not np.isnan(nm) and nm > 0)
    growing = (not np.isnan(rg) and rg > 0)
    solvent = True
    if not np.isnan(eq) and eq <= 0:
        solvent = False
    if not np.isnan(de) and de > 3.0:
        solvent = False

    return {
        "quality_profitable": profitable,
        "quality_growing": growing,
        "quality_solvent": solvent,
    }


def append_all_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append all derived financial metrics as new columns to the master DataFrame.

    All derived metrics are computed from normalize base columns:
      revenue, revenue_prev_year, net_income, net_income_prev_year,
      equity, total_debt, total_assets, pe, pb, peg

    This ensures scoring/filtering is provider-agnostic regardless
    of whether data_provider is 'yahoo' or 'twelve'.
    """
    result = df.copy()

    def _prefer_existing(row, col, calc_fn, *args):
        existing = row.get(col)
        if existing is not None and not (isinstance(existing, float) and np.isnan(existing)):
            return existing
        return calc_fn(*[row.get(a) for a in args])

    result["debt_to_equity"] = result.apply(
        lambda r: _prefer_existing(r, "debt_to_equity", calc_debt_to_equity, "total_debt", "equity"),
        axis=1,
    )
    result["equity_to_assets"] = result.apply(
        lambda r: calc_equity_to_assets(r.get("equity"), r.get("total_assets")),
        axis=1,
    )
    result["net_income_to_assets"] = result.apply(
        lambda r: calc_net_income_to_assets(r.get("net_income"), r.get("total_assets")),
        axis=1,
    )

    result["roe"] = result.apply(
        lambda r: _prefer_existing(r, "roe", calc_roe, "net_income", "equity"),
        axis=1,
    )
    result["roa"] = result.apply(
        lambda r: _prefer_existing(r, "roa", calc_roa, "net_income", "total_assets"),
        axis=1,
    )
    result["roic"] = result.apply(
        lambda r: _prefer_existing(r, "roic", calc_roic, "operating_income", "invested_capital"),
        axis=1,
    )
    result["roic_approx"] = result.apply(_calc_roic_approx, axis=1)

    result["gross_margin"] = result.apply(
        lambda r: _prefer_existing(r, "gross_margin", calc_gross_margin, "gross_profit", "revenue"),
        axis=1,
    )
    result["operating_margin"] = result.apply(
        lambda r: _prefer_existing(r, "operating_margin", calc_operating_margin, "operating_income", "revenue"),
        axis=1,
    )
    result["net_margin"] = result.apply(
        lambda r: _prefer_existing(r, "net_margin", calc_net_margin, "net_income", "revenue"),
        axis=1,
    )
    result["ebitda_margin"] = result.apply(
        lambda r: calc_ebitda_margin(r.get("ebitda"), r.get("revenue")),
        axis=1,
    )

    result["revenue_growth"] = result.apply(
        lambda r: calc_revenue_growth_yoy(r.get("revenue"), r.get("revenue_prev_year")),
        axis=1,
    )
    result["earnings_growth"] = result.apply(
        lambda r: calc_net_income_growth_yoy(r.get("net_income"), r.get("net_income_prev_year")),
        axis=1,
    )
    result["revenue_cagr_3y"] = result.apply(
        lambda r: calc_revenue_cagr_3y(r.get("revenue"), r.get("revenue_3y_ago")),
        axis=1,
    )
    result["eps_cagr_3y"] = result.apply(
        lambda r: calc_eps_cagr_3y(r.get("eps"), r.get("eps_3y_ago")),
        axis=1,
    )

    flags_df = result.apply(_calc_quality_flags, axis=1, result_type="expand")
    for col in ["quality_profitable", "quality_growing", "quality_solvent"]:
        result[col] = flags_df[col]

    return result
