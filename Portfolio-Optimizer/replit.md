# Borsa Portföy Seçici & Backtest

## Overview
A Streamlit-based stock portfolio selector, screening, and backtesting application. Supports both BIST (Borsa İstanbul, appending .IS to symbols) and US markets. Uses yfinance for price data, Twelve Data API for US stock lists, and pandas_ta for technical indicators.

## Recent Changes
- 2026-02-22: Added "Piyasa Analizi" tab with market regime detection (5 regimes: Bull Rally, Late Bull, Sideways, Correction, Bear)
- 2026-02-22: Regime detection uses benchmark SMA200, SMA50, ADX, RS Slope (no lookahead in backtest)
- 2026-02-22: Added "Portföyler" tab for creating/managing stock portfolios with real-time performance tracking
- 2026-02-22: Portfolio stocks stored in PostgreSQL (portfolios, portfolio_stocks tables)
- 2026-02-22: Screening results can be added to portfolios directly from "Hisse Tarama" tab
- 2026-02-22: Portfolio view shows cost/value/P&L metrics, allocation pie chart, performance bar chart
- 2026-02-22: Backtest results can be saved with custom names and loaded later (saved_backtests table)
- 2026-02-22: Saved backtests listed at top of Backtest tab with load/delete functionality
- 2026-02-22: Added regime-based backtest: auto-switches between Alfa/Beta/Delta strategies based on detected regime
- 2026-02-22: Regime backtest shows equity curve with colored regime backgrounds, regime log, trade log
- 2026-02-21: Integrated Twelve Data API for dynamic US stock list (NYSE ~1880, NASDAQ ~3660, total ~5500 stocks)
- 2026-02-21: Added US market pool selection: S&P 500 (Top 30), NYSE, NASDAQ, Tüm US Hisseler
- 2026-02-21: Stock list cached 24h, graceful fallback to 30 hardcoded stocks if API unavailable
- 2026-02-21: Delta rewritten as 'Trend İçi Geri Çekilme (Pullback)' model targeting strong stocks pulling back to SMA50
- 2026-02-21: Delta filters: Price > SMA50, SMA50 proximity ≤3%, RSI 35-50, close > prev high, volume > prev volume
- 2026-02-21: Delta scoring: Relative Strength 3M (50%) + SMA50 Proximity (30%) + MFI (20%)
- 2026-02-21: Delta backtest rules: Take Profit (%10 or RSI≥70), Stop-Loss (close < SMA50), Time Stop (5d no 5% gain)
- 2026-02-21: Added comparative performance chart (Alfa/Beta/Delta cumulative equity curves + benchmark)
- 2026-02-21: Added "Tüm Stratejileri Karşılaştır" button for side-by-side strategy comparison
- 2026-02-21: Added commission (0.2% per trade) and slippage (buy +0.1%, sell -0.1%) to backtest engine
- 2026-02-21: Commission included in effective buy price (cost basis) for accurate P&L
- 2026-02-21: Backtest engine rewritten with real share tracking (actual shares, original buy price preserved)
- 2026-02-21: Fixed P&L calculation bug where continuing stocks had buy price reset each period
- 2026-02-20: Alfa rewritten as 'Dinamik Liderlik' (Adaptive Leadership) model
- 2026-02-20: Hard filters replaced with ranking-based selection (ROE/Earnings top 20% by rank)
- 2026-02-20: Alfa-Beta hybrid trigger: Price > SMA200*1.05 + RS Slope must be rising over 5 days
- 2026-02-20: Volatility filter: stocks >1.5x benchmark vol get score penalty
- 2026-02-20: New scoring: RS Slope 40%, Earnings Growth Rank 30%, ROE Rank 30%
- 2026-02-20: Backtest stop-loss: -15% intra-period triggers immediate sell
- 2026-02-20: Replaced simple backtest with Periodic Rebalancing Backtest Engine
- 2026-02-20: Added 3 screening algorithms (Alfa, Beta, Delta portfolios) with tabbed UI
- 2026-02-20: Migrated from ta to pandas_ta library, upgraded to Python 3.12

## Project Architecture
- `app.py` - Main Streamlit application (single file)
- `.streamlit/config.toml` - Streamlit server configuration (port 5000)
- Python 3.12, packages: streamlit, yfinance, pandas_ta, plotly, numpy, pandas, scipy, psycopg2-binary
- PostgreSQL database for portfolio storage (portfolios, portfolio_stocks tables)

## Features
- Market selection: BIST / US
- Screening pool selection: BIST 100, BIST TÜM (XUTUM, 455+ hisse), BIST 100 DIŞI (XTUMY, 346+ hisse)
- Hardcoded BIST100 and BIST TÜM stock lists (Şubat 2026, KAP/Borsa İstanbul kaynağı)
- Screening algorithms:
  - Alfa Portföyü (Dinamik Liderlik / Adaptive):
    - Alfa-Beta Hybrid: RS Slope > 0 AND rising over 5 days + Price > SMA200*1.05
    - OBV 5-day rising trend (linear slope > 0)
    - Ranking-based quality: ROE and Earnings Growth ranked, top 20% qualify
    - Volatility filter: >1.5x benchmark vol → score penalty (up to 50%)
    - Scoring: RS Slope (40%) + Earnings Growth Rank (30%) + ROE Rank (30%)
  - Beta Portföyü: ADX > 25, Price > EMA(50), MFI > 70 (Momentum)
  - Delta Portföyü (Trend İçi Geri Çekilme / Pullback):
    - Price > SMA(50) (uptrend confirmed)
    - Price within +3% of SMA(50) (near support, high reward/risk)
    - RSI(14) between 35-50 (cooling zone)
    - Close > yesterday's High (candle confirmation)
    - Volume today > yesterday's volume (volume confirmation)
    - Scoring: Relative Strength 3M (50%) + SMA50 Proximity (30%) + MFI (20%)
    - Take Profit: +10% gain or RSI ≥ 70
    - Stop-Loss: close < SMA(50)
    - Time Stop: 5 trading days without 5% gain → sell
- **Periodic Rebalancing Backtest Engine:**
  - Real share tracking with original buy price preservation
  - Commission (0.2% per trade) and slippage (buy +0.1%, sell -0.1%)
  - User inputs: start date, initial capital, rebalance period (weekly/15-day/monthly), top N stocks
  - Alfa Stop-loss: -15% intra-period drop triggers sell
  - Delta rules: Take Profit, Stop-Loss (SMA50), Time Stop
  - Equal-weight rebalancing with proper share adjustment
  - Equity curve chart comparing strategy vs benchmark
  - Statistics table: total return, annualized return, Sharpe ratio, max drawdown, alpha
  - Trade log with buy/sell records, actual shares, scores, P/L, stop events, CSV export
- **Strategy Comparison**: "Tüm Stratejileri Karşılaştır" runs all 3 strategies and shows overlaid equity curves + comparison table
- Tabbed UI: "Hisse Tarama" and "Backtest" tabs
- CSV download for screening results and trade log
- Interactive Plotly candlestick + volume + OBV charts for screened stocks (180-day)
- Fundamental data cards per stock: F/K, PD/DD, Piyasa Değeri, Beta, 52H Yüksek/Düşük, Sektör
- Scoring Engine: normalized 0-100 scores with configurable weight sliders, color-coded heat map

## Key Functions
- `calc_rs_slope(close_series, bench_close_series, period=20)` - RS Line + linear regression slope
- `calc_alfa_score(rs_slope_norm, eg_rank_pct, roe_rank_pct, weights, vol_penalty)` - Adaptive Alfa scoring
- `calc_delta_score(rs_3m_excess, sma50_proximity_pct, mfi_val, mfi_rising, weights)` - Pullback scoring
- `_screen_alfa_backtest(ticker, name, df_slice, bench_close_slice, bench_ann_vol)` - Backtest Alfa screening
- `get_alfa_fundamental_data(ticker)` - Fetch ROE, earnings growth, PEG, sector
- `run_rebalancing_backtest(...)` - Main backtest engine with commission/slippage/stops

## User Preferences
- Language: Turkish UI
