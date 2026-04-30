import pandas as pd
import numpy as np
from indicators import calc_sma, calc_rsi, calc_macd, calc_volatility, calc_roc


def run_backtest(hist, market="BIST", lookback_years=2):
    if hist is None or hist.empty or len(hist) < 252:
        return None

    close = hist["Close"]
    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200)
    rsi = calc_rsi(close)
    _, _, macd_hist = calc_macd(close)
    vol = calc_volatility(close)

    signals = pd.DataFrame(index=hist.index)
    signals["close"] = close
    signals["signal"] = 0
    signals["score"] = 0.0

    for i in range(200, len(hist)):
        score = 0
        s50 = sma50.iloc[i] if sma50 is not None else None
        s200 = sma200.iloc[i] if sma200 is not None else None
        r = rsi.iloc[i] if rsi is not None and i < len(rsi) else None
        mh = macd_hist.iloc[i] if macd_hist is not None and i < len(macd_hist) else None
        v = vol.iloc[i] if vol is not None and i < len(vol) else None

        c = close.iloc[i]

        if s50 is not None and s200 is not None:
            if c > s50 and c > s200:
                score += 2
            elif c > s200:
                score += 1
            elif c < s50 and c < s200:
                score -= 2
            else:
                score -= 1

        if r is not None and not np.isnan(r):
            if 45 <= r <= 65:
                score += 1
            elif r > 70:
                score -= 1

        if mh is not None and not np.isnan(mh):
            if mh > 0:
                score += 1
            else:
                score -= 1

        signals.iloc[i, signals.columns.get_loc("score")] = score

        # Market-specific entry/exit thresholds
        entry_threshold = 3 if market == "BIST" else 2
        exit_threshold = -2 if market == "BIST" else -1
        
        if score >= entry_threshold:
            signals.iloc[i, signals.columns.get_loc("signal")] = 1
        elif score <= exit_threshold:
            signals.iloc[i, signals.columns.get_loc("signal")] = -1

    signals["position"] = signals["signal"].replace(0, np.nan).ffill().fillna(0)
    signals["position"] = signals["position"].clip(lower=0)

    signals["returns"] = close.pct_change()
    signals["strategy_returns"] = signals["position"].shift(1) * signals["returns"]
    signals["buy_hold_equity"] = (1 + signals["returns"]).cumprod()
    signals["strategy_equity"] = (1 + signals["strategy_returns"].fillna(0)).cumprod()

    stats = calculate_stats(signals)

    return {
        "signals": signals,
        "stats": stats,
    }


def calculate_stats(signals):
    if signals is None or signals.empty:
        return {}

    strat_ret = signals["strategy_returns"].dropna()
    bh_ret = signals["returns"].dropna()

    strat_total = (signals["strategy_equity"].iloc[-1] - 1) * 100 if len(signals) > 0 else 0
    bh_total = (signals["buy_hold_equity"].iloc[-1] - 1) * 100 if len(signals) > 0 else 0

    strat_annual = strat_ret.mean() * 252 * 100 if len(strat_ret) > 0 else 0
    bh_annual = bh_ret.mean() * 252 * 100 if len(bh_ret) > 0 else 0

    strat_vol = strat_ret.std() * np.sqrt(252) * 100 if len(strat_ret) > 0 else 0
    bh_vol = bh_ret.std() * np.sqrt(252) * 100 if len(bh_ret) > 0 else 0

    strat_sharpe = (strat_ret.mean() / strat_ret.std() * np.sqrt(252)) if strat_ret.std() > 0 else 0
    bh_sharpe = (bh_ret.mean() / bh_ret.std() * np.sqrt(252)) if bh_ret.std() > 0 else 0

    strat_dd = calculate_max_drawdown(signals["strategy_equity"])
    bh_dd = calculate_max_drawdown(signals["buy_hold_equity"])

    position_changes = signals["position"].diff().abs()
    total_trades = int(position_changes[position_changes > 0].count())
    days_in_market = int((signals["position"] > 0).sum())
    total_days = len(signals)
    in_market_pct = (days_in_market / total_days * 100) if total_days > 0 else 0

    return {
        "strat_total_return": strat_total,
        "bh_total_return": bh_total,
        "strat_annual_return": strat_annual,
        "bh_annual_return": bh_annual,
        "strat_volatility": strat_vol,
        "bh_volatility": bh_vol,
        "strat_sharpe": strat_sharpe,
        "bh_sharpe": bh_sharpe,
        "strat_max_dd": strat_dd,
        "bh_max_dd": bh_dd,
        "total_trades": total_trades,
        "days_in_market": days_in_market,
        "in_market_pct": in_market_pct,
    }


def calculate_max_drawdown(equity_series):
    if equity_series is None or len(equity_series) < 2:
        return 0
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    return drawdown.min() * 100
