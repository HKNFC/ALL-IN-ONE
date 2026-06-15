import pandas as pd
import numpy as np
from typing import List, Optional

IDENTITY_COLUMNS = [
    "ticker",
    "company_name",
    "market",
    "sector",
    "industry",
]

PRICE_COLUMNS = [
    "price",
    "market_cap",
    "avg_volume_20d",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_12m",
    "distance_to_52w_high",
    "relative_return_vs_index",
]

FUNDAMENTAL_COLUMNS = [
    "revenue",
    "revenue_prev_year",
    "revenue_3y_ago",
    "net_income",
    "net_income_prev_year",
    "eps",
    "eps_3y_ago",
    "gross_profit",
    "operating_income",
    "ebitda",
    "total_assets",
    "total_debt",
    "equity",
    "cash",
    "invested_capital",
    "pe",
    "pb",
    "ev_ebitda",
    "peg",
]

META_COLUMNS = ["data_source", "data_provider"]

ALL_COLUMNS = IDENTITY_COLUMNS + PRICE_COLUMNS + FUNDAMENTAL_COLUMNS + META_COLUMNS

NUMERIC_COLUMNS = PRICE_COLUMNS + FUNDAMENTAL_COLUMNS


def create_empty_dataframe() -> pd.DataFrame:
    """Create an empty DataFrame with all required columns and correct dtypes."""
    df = pd.DataFrame(columns=ALL_COLUMNS)
    for col in NUMERIC_COLUMNS:
        df[col] = df[col].astype(float)
    for col in IDENTITY_COLUMNS:
        df[col] = df[col].astype(object)
    return df


def validate_dataframe(df: pd.DataFrame) -> dict:
    """
    Validate a stock DataFrame against the expected schema.

    Returns a dict with:
      - valid (bool): whether all required columns are present
      - missing_columns (list): columns not found in the DataFrame
      - extra_columns (list): columns present but not in the schema
      - row_count (int): number of rows
      - null_summary (dict): count of nulls per column
    """
    missing = [c for c in ALL_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in ALL_COLUMNS and c != "price_data"]
    null_counts = {}
    for col in ALL_COLUMNS:
        if col in df.columns:
            null_counts[col] = int(df[col].isna().sum())

    return {
        "valid": len(missing) == 0,
        "missing_columns": missing,
        "extra_columns": extra,
        "row_count": len(df),
        "null_summary": null_counts,
    }


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Safely coerce all numeric columns to float, replacing non-numeric values with NaN.
    """
    result = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure all required columns exist in the DataFrame.
    Missing columns are added with NaN (numeric) or empty string (identity).
    """
    result = df.copy()
    for col in IDENTITY_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    for col in NUMERIC_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan
    for col in META_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    return result


def safe_ratio(numerator, denominator, default=np.nan) -> float:
    """Compute a ratio safely, returning default if division is invalid."""
    try:
        if numerator is None or denominator is None:
            return default
        n = float(numerator)
        d = float(denominator)
        if d == 0 or not np.isfinite(n) or not np.isfinite(d):
            return default
        result = n / d
        return result if np.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def safe_float(value, default=np.nan) -> float:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def compute_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all derived financial metrics from raw fundamental data.

    Delegates to `financial_metrics.append_all_derived_metrics` which computes:
      - Balance sheet ratios: debt_to_equity, equity_to_assets, net_income_to_assets
      - Return metrics: roe, roa, roic (NOPAT-based)
      - Margins: gross_margin, operating_margin, net_margin, ebitda_margin
      - Growth: revenue_growth (YoY), earnings_growth (YoY),
                revenue_cagr_3y, eps_cagr_3y
    """
    from financial_metrics import append_all_derived_metrics
    return append_all_derived_metrics(df)


MOCK_DATA_USA = [
    {
        "ticker": "AAPL", "company_name": "Apple Inc.", "market": "USA",
        "sector": "Technology", "industry": "Consumer Electronics",
        "price": 189.84, "market_cap": 2.95e12, "avg_volume_20d": 54_200_000,
        "return_1m": 3.2, "return_3m": 8.5, "return_6m": 15.1, "return_12m": 28.4,
        "distance_to_52w_high": -2.1, "relative_return_vs_index": 5.3,
        "revenue": 383_285e6, "revenue_prev_year": 394_328e6, "revenue_3y_ago": 365_817e6,
        "net_income": 96_995e6, "net_income_prev_year": 99_803e6,
        "eps": 6.42, "eps_3y_ago": 5.61,
        "gross_profit": 169_148e6, "operating_income": 114_301e6, "ebitda": 125_820e6,
        "total_assets": 352_583e6, "total_debt": 111_088e6, "equity": 62_146e6,
        "cash": 29_965e6, "invested_capital": 173_234e6,
        "pe": 29.5, "pb": 47.6, "ev_ebitda": 23.5, "peg": 2.1,
    },
    {
        "ticker": "MSFT", "company_name": "Microsoft Corp.", "market": "USA",
        "sector": "Technology", "industry": "Software - Infrastructure",
        "price": 378.91, "market_cap": 2.81e12, "avg_volume_20d": 22_100_000,
        "return_1m": 4.1, "return_3m": 10.2, "return_6m": 18.7, "return_12m": 35.6,
        "distance_to_52w_high": -1.5, "relative_return_vs_index": 8.2,
        "revenue": 211_915e6, "revenue_prev_year": 198_270e6, "revenue_3y_ago": 168_088e6,
        "net_income": 72_361e6, "net_income_prev_year": 72_738e6,
        "eps": 9.72, "eps_3y_ago": 8.05,
        "gross_profit": 146_204e6, "operating_income": 88_523e6, "ebitda": 104_000e6,
        "total_assets": 411_976e6, "total_debt": 59_965e6, "equity": 206_223e6,
        "cash": 80_015e6, "invested_capital": 266_188e6,
        "pe": 35.2, "pb": 12.8, "ev_ebitda": 26.1, "peg": 1.8,
    },
    {
        "ticker": "GOOGL", "company_name": "Alphabet Inc.", "market": "USA",
        "sector": "Technology", "industry": "Internet Content & Information",
        "price": 141.80, "market_cap": 1.77e12, "avg_volume_20d": 25_800_000,
        "return_1m": 2.8, "return_3m": 7.4, "return_6m": 12.9, "return_12m": 22.1,
        "distance_to_52w_high": -5.3, "relative_return_vs_index": 3.1,
        "revenue": 307_394e6, "revenue_prev_year": 282_836e6, "revenue_3y_ago": 257_637e6,
        "net_income": 73_795e6, "net_income_prev_year": 59_972e6,
        "eps": 5.80, "eps_3y_ago": 4.56,
        "gross_profit": 174_062e6, "operating_income": 84_293e6, "ebitda": 97_850e6,
        "total_assets": 402_392e6, "total_debt": 28_504e6, "equity": 283_379e6,
        "cash": 110_916e6, "invested_capital": 311_883e6,
        "pe": 24.5, "pb": 6.2, "ev_ebitda": 17.1, "peg": 1.2,
    },
    {
        "ticker": "AMZN", "company_name": "Amazon.com Inc.", "market": "USA",
        "sector": "Consumer Cyclical", "industry": "Internet Retail",
        "price": 178.25, "market_cap": 1.85e12, "avg_volume_20d": 42_300_000,
        "return_1m": 5.6, "return_3m": 14.2, "return_6m": 22.8, "return_12m": 45.3,
        "distance_to_52w_high": -3.8, "relative_return_vs_index": 12.5,
        "revenue": 574_785e6, "revenue_prev_year": 513_983e6, "revenue_3y_ago": 469_822e6,
        "net_income": 30_425e6, "net_income_prev_year": 21_331e6,
        "eps": 2.90, "eps_3y_ago": -0.27,
        "gross_profit": 270_046e6, "operating_income": 36_852e6, "ebitda": 85_500e6,
        "total_assets": 527_854e6, "total_debt": 67_150e6, "equity": 201_875e6,
        "cash": 73_387e6, "invested_capital": 269_025e6,
        "pe": 61.5, "pb": 9.2, "ev_ebitda": 21.4, "peg": 1.5,
    },
    {
        "ticker": "NVDA", "company_name": "NVIDIA Corp.", "market": "USA",
        "sector": "Technology", "industry": "Semiconductors",
        "price": 495.22, "market_cap": 1.22e12, "avg_volume_20d": 48_500_000,
        "return_1m": 12.4, "return_3m": 35.8, "return_6m": 68.2, "return_12m": 210.5,
        "distance_to_52w_high": -0.8, "relative_return_vs_index": 45.2,
        "revenue": 60_922e6, "revenue_prev_year": 26_974e6, "revenue_3y_ago": 16_675e6,
        "net_income": 29_760e6, "net_income_prev_year": 4_368e6,
        "eps": 11.93, "eps_3y_ago": 1.74,
        "gross_profit": 44_803e6, "operating_income": 32_972e6, "ebitda": 35_200e6,
        "total_assets": 65_728e6, "total_debt": 11_056e6, "equity": 42_978e6,
        "cash": 25_984e6, "invested_capital": 54_034e6,
        "pe": 65.2, "pb": 28.4, "ev_ebitda": 34.2, "peg": 0.9,
    },
    {
        "ticker": "JPM", "company_name": "JPMorgan Chase & Co.", "market": "USA",
        "sector": "Financial Services", "industry": "Banks - Diversified",
        "price": 172.30, "market_cap": 498.5e9, "avg_volume_20d": 9_800_000,
        "return_1m": 1.9, "return_3m": 5.8, "return_6m": 11.3, "return_12m": 18.7,
        "distance_to_52w_high": -7.2, "relative_return_vs_index": -1.4,
        "revenue": 158_104e6, "revenue_prev_year": 128_695e6, "revenue_3y_ago": 121_685e6,
        "net_income": 49_552e6, "net_income_prev_year": 37_676e6,
        "eps": 16.23, "eps_3y_ago": 12.09,
        "gross_profit": 158_104e6, "operating_income": 62_580e6, "ebitda": 70_200e6,
        "total_assets": 3_875_393e6, "total_debt": 482_051e6, "equity": 327_878e6,
        "cash": 567_258e6, "invested_capital": 809_929e6,
        "pe": 10.6, "pb": 1.7, "ev_ebitda": 8.2, "peg": 1.1,
    },
    {
        "ticker": "JNJ", "company_name": "Johnson & Johnson", "market": "USA",
        "sector": "Healthcare", "industry": "Drug Manufacturers",
        "price": 156.74, "market_cap": 378.2e9, "avg_volume_20d": 7_200_000,
        "return_1m": -1.2, "return_3m": -3.5, "return_6m": 2.1, "return_12m": -8.4,
        "distance_to_52w_high": -14.8, "relative_return_vs_index": -18.2,
        "revenue": 85_159e6, "revenue_prev_year": 79_990e6, "revenue_3y_ago": 93_775e6,
        "net_income": 14_613e6, "net_income_prev_year": 17_941e6,
        "eps": 6.04, "eps_3y_ago": 7.81,
        "gross_profit": 58_358e6, "operating_income": 20_053e6, "ebitda": 25_400e6,
        "total_assets": 167_558e6, "total_debt": 30_598e6, "equity": 68_774e6,
        "cash": 23_546e6, "invested_capital": 99_372e6,
        "pe": 25.9, "pb": 5.5, "ev_ebitda": 15.2, "peg": 3.8,
    },
    {
        "ticker": "XOM", "company_name": "Exxon Mobil Corp.", "market": "USA",
        "sector": "Energy", "industry": "Oil & Gas Integrated",
        "price": 104.85, "market_cap": 430.2e9, "avg_volume_20d": 15_600_000,
        "return_1m": 2.1, "return_3m": 4.5, "return_6m": 8.9, "return_12m": 5.2,
        "distance_to_52w_high": -9.5, "relative_return_vs_index": -10.8,
        "revenue": 344_582e6, "revenue_prev_year": 398_675e6, "revenue_3y_ago": 285_640e6,
        "net_income": 36_010e6, "net_income_prev_year": 55_740e6,
        "eps": 8.89, "eps_3y_ago": 5.38,
        "gross_profit": 107_628e6, "operating_income": 51_015e6, "ebitda": 68_300e6,
        "total_assets": 376_317e6, "total_debt": 40_559e6, "equity": 204_802e6,
        "cash": 31_498e6, "invested_capital": 245_361e6,
        "pe": 11.8, "pb": 2.1, "ev_ebitda": 6.4, "peg": 2.5,
    },
    {
        "ticker": "V", "company_name": "Visa Inc.", "market": "USA",
        "sector": "Financial Services", "industry": "Credit Services",
        "price": 261.44, "market_cap": 530.8e9, "avg_volume_20d": 6_800_000,
        "return_1m": 3.5, "return_3m": 9.1, "return_6m": 14.6, "return_12m": 24.8,
        "distance_to_52w_high": -3.2, "relative_return_vs_index": 4.9,
        "revenue": 32_653e6, "revenue_prev_year": 29_310e6, "revenue_3y_ago": 24_105e6,
        "net_income": 17_273e6, "net_income_prev_year": 15_844e6,
        "eps": 8.28, "eps_3y_ago": 5.63,
        "gross_profit": 25_798e6, "operating_income": 20_556e6, "ebitda": 22_100e6,
        "total_assets": 90_499e6, "total_debt": 20_463e6, "equity": 36_118e6,
        "cash": 16_286e6, "invested_capital": 56_581e6,
        "pe": 31.6, "pb": 14.7, "ev_ebitda": 24.2, "peg": 2.0,
    },
    {
        "ticker": "HD", "company_name": "The Home Depot Inc.", "market": "USA",
        "sector": "Consumer Cyclical", "industry": "Home Improvement Retail",
        "price": 312.58, "market_cap": 312.5e9, "avg_volume_20d": 3_900_000,
        "return_1m": 0.8, "return_3m": 2.4, "return_6m": 7.5, "return_12m": 12.1,
        "distance_to_52w_high": -11.2, "relative_return_vs_index": -5.8,
        "revenue": 152_669e6, "revenue_prev_year": 157_403e6, "revenue_3y_ago": 151_157e6,
        "net_income": 15_143e6, "net_income_prev_year": 17_105e6,
        "eps": 15.11, "eps_3y_ago": 15.53,
        "gross_profit": 51_152e6, "operating_income": 22_841e6, "ebitda": 25_600e6,
        "total_assets": 76_445e6, "total_debt": 42_779e6, "equity": -1_696e6,
        "cash": 1_736e6, "invested_capital": 41_083e6,
        "pe": 20.7, "pb": np.nan, "ev_ebitda": 13.8, "peg": 2.9,
    },
]

MOCK_DATA_BIST = [
    {
        "ticker": "THYAO", "company_name": "Turk Hava Yollari", "market": "BIST",
        "sector": "Industrials", "industry": "Airlines",
        "price": 262.50, "market_cap": 362.1e9, "avg_volume_20d": 145_000_000,
        "return_1m": 6.8, "return_3m": 18.4, "return_6m": 42.5, "return_12m": 85.2,
        "distance_to_52w_high": -1.2, "relative_return_vs_index": 22.3,
        "revenue": 282_915e6, "revenue_prev_year": 248_570e6, "revenue_3y_ago": 132_450e6,
        "net_income": 62_480e6, "net_income_prev_year": 53_210e6,
        "eps": 45.30, "eps_3y_ago": 18.75,
        "gross_profit": 84_875e6, "operating_income": 68_250e6, "ebitda": 78_500e6,
        "total_assets": 425_890e6, "total_debt": 148_560e6, "equity": 185_420e6,
        "cash": 52_340e6, "invested_capital": 333_980e6,
        "pe": 5.8, "pb": 1.95, "ev_ebitda": 4.6, "peg": 0.4,
    },
    {
        "ticker": "GARAN", "company_name": "Garanti BBVA", "market": "BIST",
        "sector": "Financial Services", "industry": "Banks",
        "price": 112.30, "market_cap": 472.5e9, "avg_volume_20d": 210_000_000,
        "return_1m": 4.2, "return_3m": 12.5, "return_6m": 28.7, "return_12m": 65.4,
        "distance_to_52w_high": -4.5, "relative_return_vs_index": 15.6,
        "revenue": 145_620e6, "revenue_prev_year": 118_350e6, "revenue_3y_ago": 62_480e6,
        "net_income": 48_750e6, "net_income_prev_year": 35_280e6,
        "eps": 11.59, "eps_3y_ago": 4.82,
        "gross_profit": 145_620e6, "operating_income": 62_340e6, "ebitda": 68_900e6,
        "total_assets": 1_285_400e6, "total_debt": 345_600e6, "equity": 182_450e6,
        "cash": 285_670e6, "invested_capital": 528_050e6,
        "pe": 9.7, "pb": 2.59, "ev_ebitda": 7.8, "peg": 0.6,
    },
    {
        "ticker": "EREGL", "company_name": "Eregli Demir Celik", "market": "BIST",
        "sector": "Basic Materials", "industry": "Steel",
        "price": 52.85, "market_cap": 186.2e9, "avg_volume_20d": 85_000_000,
        "return_1m": 1.5, "return_3m": -2.8, "return_6m": 5.4, "return_12m": 12.3,
        "distance_to_52w_high": -18.5, "relative_return_vs_index": -12.8,
        "revenue": 98_450e6, "revenue_prev_year": 112_380e6, "revenue_3y_ago": 72_150e6,
        "net_income": 18_920e6, "net_income_prev_year": 28_450e6,
        "eps": 5.37, "eps_3y_ago": 4.12,
        "gross_profit": 24_613e6, "operating_income": 18_250e6, "ebitda": 24_800e6,
        "total_assets": 185_670e6, "total_debt": 32_450e6, "equity": 128_560e6,
        "cash": 18_920e6, "invested_capital": 161_010e6,
        "pe": 9.8, "pb": 1.45, "ev_ebitda": 8.1, "peg": 3.2,
    },
    {
        "ticker": "BIMAS", "company_name": "BIM Birlesik Magazalar", "market": "BIST",
        "sector": "Consumer Defensive", "industry": "Discount Stores",
        "price": 395.00, "market_cap": 240.3e9, "avg_volume_20d": 18_000_000,
        "return_1m": 3.8, "return_3m": 11.2, "return_6m": 25.4, "return_12m": 52.8,
        "distance_to_52w_high": -5.8, "relative_return_vs_index": 10.5,
        "revenue": 168_540e6, "revenue_prev_year": 128_920e6, "revenue_3y_ago": 62_450e6,
        "net_income": 8_425e6, "net_income_prev_year": 6_350e6,
        "eps": 13.85, "eps_3y_ago": 5.42,
        "gross_profit": 42_135e6, "operating_income": 11_798e6, "ebitda": 15_200e6,
        "total_assets": 72_840e6, "total_debt": 28_650e6, "equity": 22_180e6,
        "cash": 8_540e6, "invested_capital": 50_830e6,
        "pe": 28.5, "pb": 10.83, "ev_ebitda": 16.6, "peg": 1.1,
    },
    {
        "ticker": "ASELS", "company_name": "Aselsan Elektronik", "market": "BIST",
        "sector": "Industrials", "industry": "Aerospace & Defense",
        "price": 68.45, "market_cap": 274.8e9, "avg_volume_20d": 125_000_000,
        "return_1m": 8.2, "return_3m": 22.5, "return_6m": 48.3, "return_12m": 92.1,
        "distance_to_52w_high": -2.5, "relative_return_vs_index": 28.4,
        "revenue": 72_850e6, "revenue_prev_year": 52_340e6, "revenue_3y_ago": 24_560e6,
        "net_income": 15_480e6, "net_income_prev_year": 10_250e6,
        "eps": 3.86, "eps_3y_ago": 1.24,
        "gross_profit": 25_498e6, "operating_income": 16_542e6, "ebitda": 19_800e6,
        "total_assets": 142_560e6, "total_debt": 42_350e6, "equity": 68_450e6,
        "cash": 22_180e6, "invested_capital": 110_800e6,
        "pe": 17.7, "pb": 4.01, "ev_ebitda": 12.8, "peg": 0.5,
    },
    {
        "ticker": "TUPRS", "company_name": "Tupras Rafineri", "market": "BIST",
        "sector": "Energy", "industry": "Oil & Gas Refining",
        "price": 148.20, "market_cap": 185.4e9, "avg_volume_20d": 32_000_000,
        "return_1m": -2.5, "return_3m": -8.4, "return_6m": -5.2, "return_12m": 8.5,
        "distance_to_52w_high": -22.5, "relative_return_vs_index": -18.6,
        "revenue": 285_640e6, "revenue_prev_year": 312_450e6, "revenue_3y_ago": 195_820e6,
        "net_income": 22_350e6, "net_income_prev_year": 38_480e6,
        "eps": 89.40, "eps_3y_ago": 42.15,
        "gross_profit": 34_277e6, "operating_income": 28_564e6, "ebitda": 35_200e6,
        "total_assets": 168_450e6, "total_debt": 62_840e6, "equity": 72_350e6,
        "cash": 15_420e6, "invested_capital": 135_190e6,
        "pe": 8.3, "pb": 2.56, "ev_ebitda": 6.6, "peg": 1.8,
    },
    {
        "ticker": "KCHOL", "company_name": "Koc Holding", "market": "BIST",
        "sector": "Industrials", "industry": "Conglomerates",
        "price": 185.60, "market_cap": 470.2e9, "avg_volume_20d": 42_000_000,
        "return_1m": 3.1, "return_3m": 9.8, "return_6m": 22.4, "return_12m": 48.6,
        "distance_to_52w_high": -8.2, "relative_return_vs_index": 8.8,
        "revenue": 458_920e6, "revenue_prev_year": 385_640e6, "revenue_3y_ago": 215_480e6,
        "net_income": 42_580e6, "net_income_prev_year": 35_120e6,
        "eps": 16.80, "eps_3y_ago": 8.45,
        "gross_profit": 91_784e6, "operating_income": 55_070e6, "ebitda": 68_400e6,
        "total_assets": 982_450e6, "total_debt": 285_640e6, "equity": 342_180e6,
        "cash": 85_420e6, "invested_capital": 627_820e6,
        "pe": 11.0, "pb": 1.37, "ev_ebitda": 9.4, "peg": 0.9,
    },
    {
        "ticker": "SAHOL", "company_name": "Sabanci Holding", "market": "BIST",
        "sector": "Financial Services", "industry": "Conglomerates",
        "price": 72.15, "market_cap": 295.8e9, "avg_volume_20d": 68_000_000,
        "return_1m": 5.4, "return_3m": 15.2, "return_6m": 32.8, "return_12m": 72.5,
        "distance_to_52w_high": -3.8, "relative_return_vs_index": 18.2,
        "revenue": 285_420e6, "revenue_prev_year": 228_560e6, "revenue_3y_ago": 125_840e6,
        "net_income": 38_420e6, "net_income_prev_year": 28_650e6,
        "eps": 9.38, "eps_3y_ago": 3.85,
        "gross_profit": 71_355e6, "operating_income": 42_813e6, "ebitda": 52_800e6,
        "total_assets": 1_425_680e6, "total_debt": 485_240e6, "equity": 285_640e6,
        "cash": 125_840e6, "invested_capital": 770_880e6,
        "pe": 7.7, "pb": 1.04, "ev_ebitda": 7.2, "peg": 0.5,
    },
    {
        "ticker": "FROTO", "company_name": "Ford Otosan", "market": "BIST",
        "sector": "Consumer Cyclical", "industry": "Auto Manufacturers",
        "price": 892.50, "market_cap": 312.8e9, "avg_volume_20d": 8_500_000,
        "return_1m": 2.8, "return_3m": 7.5, "return_6m": 18.2, "return_12m": 38.4,
        "distance_to_52w_high": -6.5, "relative_return_vs_index": 5.2,
        "revenue": 225_480e6, "revenue_prev_year": 182_560e6, "revenue_3y_ago": 98_450e6,
        "net_income": 28_560e6, "net_income_prev_year": 22_480e6,
        "eps": 81.50, "eps_3y_ago": 32.15,
        "gross_profit": 40_586e6, "operating_income": 31_567e6, "ebitda": 38_200e6,
        "total_assets": 185_640e6, "total_debt": 52_480e6, "equity": 95_620e6,
        "cash": 28_450e6, "invested_capital": 148_100e6,
        "pe": 10.9, "pb": 3.27, "ev_ebitda": 7.5, "peg": 0.8,
    },
    {
        "ticker": "TCELL", "company_name": "Turkcell Iletisim", "market": "BIST",
        "sector": "Communication Services", "industry": "Telecom Services",
        "price": 82.30, "market_cap": 181.5e9, "avg_volume_20d": 52_000_000,
        "return_1m": 1.8, "return_3m": 6.2, "return_6m": 14.5, "return_12m": 32.8,
        "distance_to_52w_high": -12.4, "relative_return_vs_index": -2.8,
        "revenue": 72_840e6, "revenue_prev_year": 58_420e6, "revenue_3y_ago": 35_280e6,
        "net_income": 12_580e6, "net_income_prev_year": 8_450e6,
        "eps": 5.70, "eps_3y_ago": 2.85,
        "gross_profit": 36_420e6, "operating_income": 18_210e6, "ebitda": 28_400e6,
        "total_assets": 142_850e6, "total_debt": 38_560e6, "equity": 62_480e6,
        "cash": 18_250e6, "invested_capital": 101_040e6,
        "pe": 14.4, "pb": 2.91, "ev_ebitda": 7.1, "peg": 0.7,
    },
]


def get_mock_data(market: str) -> pd.DataFrame:
    """
    Return mock stock data for the given market as a validated DataFrame.

    Includes at least 10 stocks per market with all required columns populated.
    """
    if market == "USA":
        raw = MOCK_DATA_USA
    elif market == "BIST":
        raw = MOCK_DATA_BIST
    else:
        return create_empty_dataframe()

    df = pd.DataFrame(raw)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)
    return df
