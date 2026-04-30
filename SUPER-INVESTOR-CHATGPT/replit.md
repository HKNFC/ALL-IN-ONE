# Overview

This is a pnpm workspace monorepo utilizing TypeScript and a Python Streamlit stock screening application. The primary goal is to provide a production-ready stock screening web app that ranks stocks using a custom RS Score based on Financial Strength, Growth, Margin Quality, Valuation, and Momentum. It supports both BIST (Turkey) and US stock markets. The project aims to offer a robust and extensible platform for financial analysis and stock selection.

# User Preferences

I prefer iterative development and want to be involved in the decision-making process for major changes. Please ask for my approval before implementing significant architectural shifts or feature alterations. I appreciate clear, concise explanations and well-documented code.

# System Architecture

## Stock Screener (Python / Streamlit)

The stock screener is built with Streamlit for the UI and Python for the backend logic. It implements a sophisticated RS Score engine for stock ranking.

### Core Components:
- **Data Model:** A unified DataFrame schema ensures consistent data handling across the application, including validation, type coercion, and derived field computation.
- **Data Providers:** Abstract `PriceProvider` interface allows for different market data sources. `Twelve Data` and `Yahoo Finance` are integrated for price and fundamental data, respectively, with caching mechanisms. USA universe: 903 stocks (S&P 500 + S&P MidCap 400). Segments: Tüm USA, S&P 500, S&P MidCap 400.
- **Symbol Mapping:** A centralized `symbol_mapper.py` handles provider-agnostic symbol resolution and caching.
- **Disk Cache:** A Parquet-based disk cache (`disk_cache.py`) optimizes EOD OHLCV data retrieval, featuring daily refresh, incremental updates, and atomic writes.
- **Indicators:** A consolidated `indicators.py` module provides various technical indicators (MA, RSI, MACD, etc.) for enriching the DataFrame.
- **Data Fetching:** `data_fetcher.py` orchestrates data retrieval with an EOD cache-first architecture. Fundamentals routing: USA → Twelve Data (`/statistics`, `/income_statement`, `/balance_sheet`, `/profile`) with Yahoo fallback; BIST → Yahoo only. Both normalize to common columns (revenue, net_income, equity, etc.). `FetchDiagnostics` tracks `fundamentals_with_data`, `provider_distribution`.
- **Twelve Data Fundamentals:** `twelve_data_provider.py` includes `fetch_twelve_fundamentals()` for US stocks — fetches from `/statistics` (PE/PB/market cap/financials), `/income_statement` (revenue/net_income YoY), `/balance_sheet` (equity/debt/assets), `/profile` (sector/industry). Derives net_margin, D/E, ROE, ROA from raw data.
- **Scoring Engine:** `scoring_engine.py` calculates percentile-based RS Scores with 0-100 scaling, winsorization, reverse-scoring for certain metrics, and NaN-aware weight redistribution across five dimensions: Financial Strength, Growth, Margin Quality, Valuation, and Momentum. It categorizes stocks into Elite, Strong, Watchlist, Weak, and Avoid. Also orchestrates Technical Score and Institutional Score.
- **Technical Signals:** `technical_signals.py` computes a Technical Signal Score based on Trend, Momentum, Breakout, Volume Flow, and Risk/Stability. Combined Score = 0.50*RS + 0.50*Tech.
- **Institutional Score:** `institutional_score.py` computes a 0-100 Institutional Score from 5 sub-scores: Quality (25%), Growth (20%), Valuation (15%), Momentum (25%), Flow (15%). Uses independent percentile ranking, winsorization, adaptive block-level weighting. Features: Selection Score (Quality+Growth+Valuation), Timing Score (Momentum+Flow), 5 strategy profiles (Standard, Quality Compounders, Growth Leaders, Smart Money Breakout, Value+Confirmation) with different block weights, and per-stock debug panel showing used/missing metrics per block. Categories: Elit 85+, Güçlü 70+, İzleme 55+, Zayıf <55.
- **Price Spike Filter:** `_filter_price_spikes()` in `data_fetcher.py` — four-stage data quality filter for BIST stocks that handles interleaved nominal/adjusted prices: (1) K-means clustering (initializes from jump-point extremes, iterative mean convergence, removes minority cluster when ratio > 1.8), (2) Reversion outlier detection (gap=[1,2,3,5,7,10], checks if price deviates >35% from both sides, 8 iterative passes), (3) Regime shift detection (finds >35% jumps, compares segment medians, removes minority segment when ratio > 1.45, 3 passes). Applied in `fetch_backtest_data` and `_enrich_via_yahoo`. Reduces >100% daily spikes from 433 to 0 across 611 BIST stocks in ~6s.
- **Filters:** `filters.py` provides pre-ranking quality filters with configurable presets.
- **Backtest Engine:** `backtest_engine.py` enables historical strategy backtesting using cached price data plus Yahoo-fetched fundamentals (parallel batch via `_fetch_fundamentals_batch`). Uses the same `inst_profile` (strategy profile) as the screener for consistent scoring. Fundamentals are cached in-memory (20h TTL) so subsequent runs are fast. Non-standard profiles auto-sort by `institutional_score`. Scan modes (Standart/Akıllı Para/Erken Accumulation) are optional filters.
- **Watchlist:** `watchlist.py` manages a local JSON-backed watchlist.
- **Scan History:** `scan_history.py` manages a JSON-backed history of scan and backtest runs. Records scan parameters, top stocks, and backtest metrics (return, Sharpe, drawdown). Entries are stored newest-first with unique IDs. Functions: `add_scan_entry()`, `add_backtest_entry()`, `get_history()`, `delete_entry()`, `clear_history()`. The "Geçmiş" tab displays all entries with expandable detail cards and individual/bulk delete.

### UI/UX:
- The Streamlit application provides an interactive UI with market selectors, filters, results tables, and detailed stock information tabs.
- **Historical Screening:** Sidebar "Geçmiş Tarihte Tara" checkbox + date picker. When enabled, uses `fetch_backtest_data` (cache-only OHLCV + Yahoo fundamentals), truncates price_data to the selected date, recomputes momentum fields with truncated benchmark, then scores normally. Results show an info banner with the selected date.
- The Streamlit server runs on port 5000.

## TypeScript Stack

The TypeScript part of the monorepo leverages `pnpm workspaces` for package management and `TypeScript 5.9`.

### Core Technologies:
- **API Framework:** Express 5 is used for building the API server.
- **Database:** PostgreSQL with Drizzle ORM for database interactions.
- **Validation:** Zod is integrated for data validation, with `drizzle-zod` for Drizzle schema integration.
- **API Codegen:** Orval generates API clients and Zod schemas from an OpenAPI specification.
- **Build System:** esbuild is used for CJS bundle creation.

### Monorepo Structure:
- **`artifacts/api-server`:** An Express 5 API server handling business logic and data persistence via Drizzle ORM.
- **`lib/db`:** Encapsulates the Drizzle ORM setup and database schema.
- **`lib/api-spec`:** Contains the OpenAPI 3.1 specification and Orval configuration for API client and schema generation.
- **`lib/api-zod`:** Stores generated Zod schemas for API validation.
- **`lib/api-client-react`:** Provides generated React Query hooks and a fetch client for frontend integration.
- **`scripts`:** A package for utility scripts.

### TypeScript & Composite Projects:
The monorepo uses TypeScript's composite projects feature, allowing for efficient type-checking and build processes across interdependent packages. `tsc --build --emitDeclarationOnly` is used for type-checking and declaration file generation.

# External Dependencies

## Python:
- **Streamlit:** For building the interactive web application.
- **Pandas, NumPy:** For data manipulation and numerical operations.
- **Requests, Python-dotenv:** For API calls and environment variable management.
- **Pyarrow:** For Parquet file operations in the disk cache.
- **yfinance:** For fetching Yahoo Finance data.

## TypeScript:
- **Express:** Web application framework for the API server.
- **PostgreSQL:** Relational database management system.
- **Drizzle ORM:** TypeScript ORM for database interaction.
- **Zod:** Schema declaration and validation library.
- **Orval:** OpenAPI client code generator.
- **Esbuild:** Fast JavaScript bundler.