from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_fetcher import fetch_ohlcv_range
from screener import screen_bist_on_date, screen_usa_on_date
from typing import Optional, Callable
from stock_lists import BIST_STOCKS, USA_STOCKS


INTERVAL_DAYS = {
    "1 Hafta": 7,
    "15 Gün": 15,
    "1 Ay": 30,
}


def _generate_rebalance_dates(start: datetime, end: datetime, interval_days: int) -> list:
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=interval_days)
    return dates


def _next_trading_close(df: pd.DataFrame, target_date) -> Optional[float]:
    future = df[df.index >= target_date]
    if future.empty:
        return None
    return future.iloc[0]["Close"]


def run_backtest(
    market: str,
    start_date: str,
    end_date: str,
    interval_label: str,
    initial_capital: float = 100_000.0,
    progress_callback=None,
    symbols: list = None,
) -> dict:
    interval_days = INTERVAL_DAYS[interval_label]
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    if market == "BIST":
        symbols = symbols if symbols is not None else BIST_STOCKS
        screen_fn = screen_bist_on_date
        fetch_period_extra = "2y"
    else:
        symbols = symbols if symbols is not None else USA_STOCKS
        screen_fn = screen_usa_on_date
        fetch_period_extra = "3y"

    fetch_start = (start_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    fetch_end = (end_dt + timedelta(days=10)).strftime("%Y-%m-%d")

    if progress_callback:
        progress_callback(0.0, f"{len(symbols)} hisse verisi indiriliyor...")

    df_dict = {}
    for i, sym in enumerate(symbols):
        df = fetch_ohlcv_range(sym, start=fetch_start, end=fetch_end)
        if not df.empty and len(df) >= 50:
            df_dict[sym] = df
        if progress_callback and i % 10 == 0:
            progress_callback(i / len(symbols) * 0.4, f"Veri: {sym}")

    rebalance_dates = _generate_rebalance_dates(start_dt, end_dt, interval_days)

    portfolio = {}
    cash = initial_capital
    portfolio_history = []
    trades_log = []

    for ri, rebal_date in enumerate(rebalance_dates):
        if progress_callback:
            progress_callback(0.4 + ri / len(rebalance_dates) * 0.6, f"Rebalance: {rebal_date.date()}")

        hits = screen_fn(df_dict, rebal_date, params={"use_divergence": False})
        hits = hits[:5]

        total_value = cash
        for sym, shares in portfolio.items():
            price = _next_trading_close(df_dict.get(sym, pd.DataFrame()), rebal_date)
            if price:
                total_value += shares * price

        for sym, shares in list(portfolio.items()):
            price = _next_trading_close(df_dict.get(sym, pd.DataFrame()), rebal_date)
            if price:
                proceeds = shares * price
                cash += proceeds
                trades_log.append({
                    "Date": rebal_date.date(),
                    "Action": "SELL",
                    "Symbol": sym,
                    "Shares": round(shares, 4),
                    "Price": round(price, 2),
                    "Value": round(proceeds, 2),
                })
        portfolio = {}

        if hits:
            alloc_per_stock = cash / len(hits)
            for sym in hits:
                price = _next_trading_close(df_dict.get(sym, pd.DataFrame()), rebal_date)
                if price and price > 0:
                    shares = alloc_per_stock / price
                    portfolio[sym] = shares
                    cash -= shares * price
                    trades_log.append({
                        "Date": rebal_date.date(),
                        "Action": "BUY",
                        "Symbol": sym,
                        "Shares": round(shares, 4),
                        "Price": round(price, 2),
                        "Value": round(alloc_per_stock, 2),
                    })

        pv = cash
        for sym, shares in portfolio.items():
            price = _next_trading_close(df_dict.get(sym, pd.DataFrame()), rebal_date)
            if price:
                pv += shares * price

        portfolio_history.append({
            "Date": rebal_date.date(),
            "Portfolio Value": round(pv, 2),
            "Holdings": len(portfolio),
            "Cash": round(cash, 2),
        })

    final_value = cash
    for sym, shares in portfolio.items():
        price = _next_trading_close(df_dict.get(sym, pd.DataFrame()), end_dt)
        if price:
            final_value += shares * price

    pv_series = pd.DataFrame(portfolio_history).set_index("Date")["Portfolio Value"]

    total_return = (final_value - initial_capital) / initial_capital * 100
    days_total = (end_dt - start_dt).days
    years = days_total / 365
    cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    daily_returns = pv_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0

    rolling_max = pv_series.cummax()
    drawdown = (pv_series - rolling_max) / rolling_max
    max_drawdown = drawdown.min() * 100

    benchmark_symbol = "XU100.IS" if market == "BIST" else "SPY"
    bench_df = fetch_ohlcv_range(benchmark_symbol, start=start_date, end=end_date)
    benchmark_return = 0.0
    if not bench_df.empty:
        bench_start = _next_trading_close(bench_df, start_dt)
        bench_end = bench_df.iloc[-1]["Close"]
        if bench_start and bench_start > 0:
            benchmark_return = (bench_end - bench_start) / bench_start * 100

    return {
        "market": market,
        "start_date": start_date,
        "end_date": end_date,
        "interval": interval_label,
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "benchmark_return_pct": round(benchmark_return, 2),
        "num_rebalances": len(rebalance_dates),
        "portfolio_history": pd.DataFrame(portfolio_history),
        "trades_log": pd.DataFrame(trades_log) if trades_log else pd.DataFrame(),
        "alpha_pct": round(total_return - benchmark_return, 2),
    }
