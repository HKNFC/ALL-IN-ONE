"""
Backtest Engine

Simulates portfolio performance by replaying the stock screening process
over historical periods. At each rebalance date the system:
  1. Truncates price data to that date (no look-ahead bias)
  2. Re-runs scoring (RS + technical)
  3. Applies quality/scan-mode filters
  4. Selects top-N stocks by chosen sort column
  5. Builds an equal-weight portfolio held until next rebalance

Outputs equity curve, drawdown, per-period holdings, and summary metrics.
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import date, timedelta

from data_fetcher import fetch_backtest_data, get_cached_benchmark, _generate_placeholder_price_data, DataPrepStats
from momentum_metrics import append_momentum_fields
from scoring_engine import compute_rs_scores
from filters import apply_preset_filter, rank_and_limit

logger = logging.getLogger("stock_screener.backtest")

REBALANCE_BUSINESS_DAYS = {
    "1w": 5,
    "15d": 11,
    "1m": 21,
}

PERIODS_PER_YEAR = {
    "1w": 52,
    "15d": 24,
    "1m": 12,
}


@dataclass
class RebalanceRecord:
    date: pd.Timestamp
    tickers: List[str]
    scores: Dict[str, float]
    period_return: float = 0.0
    ticker_returns: Dict[str, float] = None


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    benchmark_curve: pd.DataFrame
    drawdown_series: pd.Series
    benchmark_drawdown_series: pd.Series
    rebalance_history: List[RebalanceRecord]
    total_return: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0
    max_drawdown: float = 0.0
    benchmark_max_drawdown: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    num_periods: int = 0
    avg_stocks_per_period: float = 0.0
    data_prep_stats: Optional[DataPrepStats] = None


def _get_all_trading_dates(raw_data: pd.DataFrame) -> pd.DatetimeIndex:
    all_dates = set()
    for _, row in raw_data.iterrows():
        pd_data = row.get("price_data")
        if isinstance(pd_data, pd.DataFrame) and "datetime" in pd_data.columns:
            all_dates.update(pd_data["datetime"].values)
    if not all_dates:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(all_dates))


def _generate_rebalance_dates(
    trading_dates: pd.DatetimeIndex,
    start_date: date,
    end_date: date,
    freq_key: str,
) -> List[pd.Timestamp]:
    bdays = REBALANCE_BUSINESS_DAYS.get(freq_key, 21)

    mask = (trading_dates >= pd.Timestamp(start_date)) & (
        trading_dates <= pd.Timestamp(end_date)
    )
    available = trading_dates[mask]

    if len(available) < 2:
        return []

    dates = []
    idx = 0
    while idx < len(available):
        dates.append(available[idx])
        idx += bdays

    if len(dates) >= 2 and dates[-1] == dates[-2]:
        dates.pop()

    last_available = available[-1]
    if dates and dates[-1] < last_available:
        dates.append(last_available)

    return dates


def _truncate_price_data(
    raw_data: pd.DataFrame, cutoff: pd.Timestamp
) -> pd.DataFrame:
    result = raw_data.copy()
    truncated = []
    for _, row in result.iterrows():
        pd_data = row.get("price_data")
        if isinstance(pd_data, pd.DataFrame) and "datetime" in pd_data.columns:
            sliced = pd_data[pd_data["datetime"] <= cutoff].copy()
            if len(sliced) >= 20:
                truncated.append(sliced.reset_index(drop=True))
            else:
                truncated.append(None)
        else:
            truncated.append(None)
    result["price_data"] = truncated
    result = result[result["price_data"].notna()].reset_index(drop=True)
    return result


def _get_forward_return(
    price_data: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> Optional[float]:
    if price_data is None or not isinstance(price_data, pd.DataFrame):
        return None
    if "datetime" not in price_data.columns or "close" not in price_data.columns:
        return None

    after_start = price_data[price_data["datetime"] >= start_date]
    if after_start.empty:
        return None
    start_price = float(after_start.iloc[0]["close"])

    before_end = price_data[price_data["datetime"] <= end_date]
    if before_end.empty:
        return None
    end_price = float(before_end.iloc[-1]["close"])

    if start_price <= 0 or not np.isfinite(start_price):
        return None
    if not np.isfinite(end_price):
        return None

    return (end_price / start_price) - 1.0


def _apply_scan_mode_filter(
    df: pd.DataFrame, scan_mode: str
) -> pd.DataFrame:
    if scan_mode == "standard" or df.empty:
        return df

    if scan_mode == "smart_money":
        mask = pd.Series(True, index=df.index)
        if "mfi" in df.columns:
            mask &= df["mfi"].fillna(0) > 55
        if "obv_trend_positive" in df.columns:
            mask &= df["obv_trend_positive"].fillna(False)
        if "relative_return_vs_index" in df.columns:
            mask &= df["relative_return_vs_index"].fillna(-999) > 0
        if "volume_ratio" in df.columns:
            mask &= df["volume_ratio"].fillna(0) > 1.10
        if "technical_score" in df.columns:
            mask &= df["technical_score"].fillna(0) >= 55
        if "rs_score" in df.columns:
            mask &= df["rs_score"].fillna(0) >= 60
        return df[mask].reset_index(drop=True)

    if scan_mode == "early_accumulation":
        mask = pd.Series(True, index=df.index)
        if "mfi" in df.columns:
            mfi_col = df["mfi"].fillna(0)
            mask &= (mfi_col >= 50) & (mfi_col <= 65)
        if "obv_trend_positive" in df.columns:
            mask &= df["obv_trend_positive"].fillna(False)
        if "distance_to_52w_high" in df.columns:
            d52 = df["distance_to_52w_high"].fillna(-999)
            mask &= (d52 >= -35) & (d52 <= -10)
        if "return_1m" in df.columns:
            mask &= df["return_1m"].fillna(-999) > -3
        if "return_3m" in df.columns:
            mask &= df["return_3m"].fillna(-999) > 0
        if "rs_score" in df.columns:
            mask &= df["rs_score"].fillna(0) >= 55
        return df[mask].reset_index(drop=True)

    return df


def _apply_universe_filter(
    df: pd.DataFrame, market: str, universe: str
) -> pd.DataFrame:
    from config import BIST100_TICKERS, SP500_TICKERS, MIDCAP400_TICKERS

    if market == "BIST" and universe != "BISTTUM" and "ticker" in df.columns:
        if universe == "BIST100":
            return df[df["ticker"].isin(BIST100_TICKERS)].reset_index(drop=True)
        elif universe == "BIST100_DISI":
            return df[~df["ticker"].isin(BIST100_TICKERS)].reset_index(drop=True)

    if market == "USA" and universe != "USA_ALL" and "ticker" in df.columns:
        if universe == "SP500":
            return df[df["ticker"].isin(SP500_TICKERS)].reset_index(drop=True)
        elif universe == "MIDCAP400":
            return df[df["ticker"].isin(MIDCAP400_TICKERS)].reset_index(drop=True)

    return df


def _compute_metrics(
    equity: pd.Series,
    benchmark_equity: pd.Series,
    periods_per_year: int = 12,
) -> Dict:
    total_ret = (equity.iloc[-1] / equity.iloc[0]) - 1.0 if len(equity) > 1 else 0.0
    bench_ret = (
        (benchmark_equity.iloc[-1] / benchmark_equity.iloc[0]) - 1.0
        if len(benchmark_equity) > 1
        else 0.0
    )

    period_returns = equity.pct_change().dropna()
    ann_factor = np.sqrt(periods_per_year)
    vol = float(period_returns.std() * ann_factor) if len(period_returns) > 1 else 0.0

    mean_ret = period_returns.mean() if len(period_returns) > 0 else 0.0
    std_ret = period_returns.std() if len(period_returns) > 1 else 0.0
    sharpe = float(mean_ret / std_ret * ann_factor) if std_ret > 0 else 0.0

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = float(drawdown.min())

    bench_running_max = benchmark_equity.cummax()
    bench_dd = (benchmark_equity - bench_running_max) / bench_running_max
    bench_max_dd = float(bench_dd.min())

    return {
        "total_return": total_ret,
        "benchmark_return": bench_ret,
        "alpha": total_ret - bench_ret,
        "max_drawdown": max_dd,
        "benchmark_max_drawdown": bench_max_dd,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "drawdown_series": drawdown,
        "benchmark_drawdown_series": bench_dd,
    }


def run_backtest(
    market: str,
    universe: str,
    scan_mode: str,
    quality_preset: str,
    sort_by: str,
    top_n: int,
    rebalance_freq: str,
    start_date: date,
    end_date: date,
    min_avg_volume: Optional[float] = None,
    progress_callback=None,
    inst_profile: str = "standard",
) -> BacktestResult:
    def _data_progress(pct, text):
        if progress_callback:
            progress_callback(pct * 0.3, text)

    raw_data, prep_stats = fetch_backtest_data(
        market, progress_callback=_data_progress, skip_momentum=True,
    )

    raw_data = _apply_universe_filter(raw_data, market, universe)

    full_price_lookup: Dict[str, pd.DataFrame] = {}
    for _, row in raw_data.iterrows():
        ticker = row.get("ticker")
        pd_data = row.get("price_data")
        if ticker and isinstance(pd_data, pd.DataFrame):
            full_price_lookup[ticker] = pd_data.copy()

    trading_dates = _get_all_trading_dates(raw_data)
    rebalance_dates = _generate_rebalance_dates(
        trading_dates, start_date, end_date, rebalance_freq
    )

    if len(rebalance_dates) < 2:
        return BacktestResult(
            equity_curve=pd.DataFrame({"date": [], "value": []}),
            benchmark_curve=pd.DataFrame({"date": [], "value": []}),
            drawdown_series=pd.Series(dtype=float),
            benchmark_drawdown_series=pd.Series(dtype=float),
            rebalance_history=[],
            data_prep_stats=prep_stats,
        )

    benchmark_history = get_cached_benchmark(market)

    benchmark_prices = None
    if benchmark_history is not None and not benchmark_history.empty:
        if "datetime" in benchmark_history.columns and "close" in benchmark_history.columns:
            benchmark_prices = benchmark_history.copy()

    portfolio_value = 100.0
    rebalance_records: List[RebalanceRecord] = []
    equity_points: List[Tuple[pd.Timestamp, float]] = []
    bench_points: List[Tuple[pd.Timestamp, float]] = []

    bench_start_price = None
    if benchmark_prices is not None:
        after_start = benchmark_prices[
            benchmark_prices["datetime"] >= pd.Timestamp(start_date)
        ]
        if not after_start.empty:
            bench_start_price = float(after_start.iloc[0]["close"])

    equity_points.append((rebalance_dates[0], portfolio_value))
    bench_points.append((rebalance_dates[0], 100.0))

    total_steps = len(rebalance_dates) - 1

    for i in range(total_steps):
        reb_date = rebalance_dates[i]
        next_reb_date = rebalance_dates[i + 1]

        if progress_callback:
            sim_pct = 0.3 + ((i + 1) / total_steps) * 0.7
            progress_callback(sim_pct, f"Simülasyon: dönem {i+1}/{total_steps}")

        truncated = _truncate_price_data(raw_data, reb_date)

        if truncated.empty:
            equity_points.append((next_reb_date, portfolio_value))
            _append_bench_point(
                bench_points, benchmark_prices, next_reb_date,
                bench_start_price,
            )
            rebalance_records.append(
                RebalanceRecord(date=reb_date, tickers=[], scores={}, period_return=0.0)
            )
            continue

        bench_trunc = None
        if benchmark_history is not None and not benchmark_history.empty:
            if "datetime" in benchmark_history.columns:
                bench_trunc = benchmark_history[
                    benchmark_history["datetime"] <= reb_date
                ].copy()
                if bench_trunc.empty:
                    bench_trunc = None
        truncated = append_momentum_fields(truncated, benchmark_history=bench_trunc)

        scored = compute_rs_scores(truncated, market=market, inst_profile=inst_profile)

        filtered = apply_preset_filter(
            scored, preset=quality_preset, min_avg_volume=min_avg_volume,
        )

        filtered = _apply_scan_mode_filter(filtered, scan_mode)

        if inst_profile != "standard":
            effective_sort = "institutional_score"
        elif scan_mode != "standard":
            effective_sort = "combined_score"
        else:
            effective_sort = sort_by
        selected = rank_and_limit(filtered, top_n=top_n, sort_by=effective_sort)

        if selected.empty:
            equity_points.append((next_reb_date, portfolio_value))
            _append_bench_point(
                bench_points, benchmark_prices, next_reb_date,
                bench_start_price,
            )
            rebalance_records.append(
                RebalanceRecord(date=reb_date, tickers=[], scores={}, period_return=0.0)
            )
            continue

        tickers = selected["ticker"].tolist()
        scores = {}
        for _, row in selected.iterrows():
            t = row.get("ticker", "")
            scores[t] = round(float(row.get(effective_sort, 0) or 0), 2)

        stock_returns = []
        ticker_returns = {}
        for ticker in tickers:
            full_pd = full_price_lookup.get(ticker)
            fwd = _get_forward_return(full_pd, reb_date, next_reb_date)
            if fwd is not None:
                stock_returns.append(fwd)
                ticker_returns[ticker] = round(fwd * 100, 2)

        if stock_returns:
            period_return = np.mean(stock_returns)
        else:
            period_return = 0.0

        portfolio_value *= 1.0 + period_return

        equity_points.append((next_reb_date, portfolio_value))
        _append_bench_point(
            bench_points, benchmark_prices, next_reb_date,
            bench_start_price,
        )
        rebalance_records.append(
            RebalanceRecord(
                date=reb_date,
                tickers=tickers,
                scores=scores,
                period_return=round(period_return * 100, 2),
                ticker_returns=ticker_returns,
            )
        )

    eq_df = pd.DataFrame(equity_points, columns=["date", "value"])
    bench_df = pd.DataFrame(bench_points, columns=["date", "value"])

    eq_series = pd.Series(eq_df["value"].values, index=eq_df["date"])
    bench_series = pd.Series(bench_df["value"].values, index=bench_df["date"])

    ppy = PERIODS_PER_YEAR.get(rebalance_freq, 12)
    metrics = _compute_metrics(eq_series, bench_series, periods_per_year=ppy)

    n_stocks = [len(r.tickers) for r in rebalance_records if r.tickers]
    avg_stocks = np.mean(n_stocks) if n_stocks else 0.0

    return BacktestResult(
        equity_curve=eq_df,
        benchmark_curve=bench_df,
        drawdown_series=metrics["drawdown_series"],
        benchmark_drawdown_series=metrics["benchmark_drawdown_series"],
        rebalance_history=rebalance_records,
        total_return=round(metrics["total_return"] * 100, 2),
        benchmark_return=round(metrics["benchmark_return"] * 100, 2),
        alpha=round(metrics["alpha"] * 100, 2),
        max_drawdown=round(metrics["max_drawdown"] * 100, 2),
        benchmark_max_drawdown=round(metrics["benchmark_max_drawdown"] * 100, 2),
        volatility=round(metrics["volatility"] * 100, 2),
        sharpe_ratio=round(metrics["sharpe_ratio"], 2),
        num_periods=len(rebalance_records),
        avg_stocks_per_period=round(avg_stocks, 1),
        data_prep_stats=prep_stats,
    )


def _append_bench_point(
    bench_points: list,
    benchmark_prices: Optional[pd.DataFrame],
    target_date: pd.Timestamp,
    bench_start_price: Optional[float],
):
    if benchmark_prices is None or bench_start_price is None or bench_start_price <= 0:
        bench_points.append((target_date, bench_points[-1][1] if bench_points else 100.0))
        return

    before_date = benchmark_prices[benchmark_prices["datetime"] <= target_date]
    if before_date.empty:
        bench_points.append((target_date, bench_points[-1][1] if bench_points else 100.0))
        return

    current_price = float(before_date.iloc[-1]["close"])
    bench_value = 100.0 * (current_price / bench_start_price)
    bench_points.append((target_date, bench_value))
