# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **Python version**: 3.11
- **API framework**: Express 5
- **Dashboard**: Streamlit + yfinance + Plotly (modular architecture)
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Structure

```text
artifacts-monorepo/
├── artifacts/              # Deployable applications
│   └── api-server/         # Express API server
├── lib/                    # Shared libraries
│   ├── api-spec/           # OpenAPI spec + Orval codegen config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas from OpenAPI
│   └── db/                 # Drizzle ORM schema + DB connection
├── scripts/                # Utility scripts (single workspace package)
│   └── src/                # Individual .ts scripts
├── pnpm-workspace.yaml
├── tsconfig.base.json
├── tsconfig.json
└── package.json
```

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references.

- **Always typecheck from the root** — run `pnpm run typecheck`
- **`emitDeclarationOnly`** — only `.d.ts` files during typecheck
- **Project references** — when package A depends on B, A's `tsconfig.json` must list B in references

## Root Scripts

- `pnpm run build` — runs `typecheck` then recursively `build` in all packages
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly`

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes in `src/routes/`, uses `@workspace/api-zod` and `@workspace/db`.

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL.

### `lib/api-spec` (`@workspace/api-spec`)

OpenAPI 3.1 spec + Orval config. Run: `pnpm --filter @workspace/api-spec run codegen`

### `scripts` (`@workspace/scripts`)

Utility scripts. Run: `pnpm --filter @workspace/scripts run <script>`

### Borsa Analiz Dashboard (Streamlit) — Modular Architecture

Python Streamlit dashboard for market timing decision support. Located at root level.

**Modular File Structure:**
- `app.py` — Main Streamlit UI, sidebar, charts, layout
- `config.py` — Weights, thresholds, tickers, sector maps, risk profiles, verdict/regime styles
- `utils.py` — Formatting helpers, HTML card builders, signal color/icon functions
- `indicators.py` — Technical indicators: RSI, SMA, MACD, ADX, OBV, volatility, breadth, new high/low, sector breadth, relative strength
- `data_fetcher.py` — Data fetching: yfinance, Twelve Data API, TCMB EVDS API (policy rate, inflation), CDS scraping (curl_cffi), SPY options chain, multi-ticker batch download, mock data generator
- `market_regime.py` — Regime detection (Risk-On/Neutral/Risk-Off/Crisis) for both BIST and USA
- `scoring_bist.py` — 3-layer BIST scoring: Macro (CDS, real rate, BIST/USD, USDTRY vol) + Market Health (breadth SMA50/200, new high/low, sector leadership) + Timing (SMA position/slope, RSI, MACD, ADX, volatility)
- `scoring_usa.py` — 3-layer USA scoring: Risk (VIX, Treasury 10Y, DXY, credit spread, yield curve) + Market Internals (breadth, new high/low, equal vs cap weight, relative strength, put/call) + Timing (SMA200, SMA50 slope, MACD, RSI, volume+OBV)
- `decision_engine.py` — Final verdict determination with natural language explanation, risk profile adjustment, override logic (CDS>500, VIX>25)
- `backtest.py` — Backtesting engine: equity curve, Sharpe ratio, max drawdown, strategy vs buy-and-hold comparison

**Config:** `.streamlit/config.toml` — server config
**Dependencies:** streamlit, twelvedata, yfinance, plotly, requests, pandas, numpy, beautifulsoup4, curl_cffi, evds (in requirements.txt)
**Run:** `streamlit run app.py --server.port 23183`
**API Keys:** TWELVEDATA_API_KEY (USA mode), TCMB_EVDS_API_KEY (BIST auto-fetch: policy rate, inflation)

**Features:**
- 3-layer weighted scoring system for both BIST and USA markets
- Market regime detection (Risk-On/Neutral/Risk-Off/Crisis)
- Risk profile selection (Korumacı/Dengeli/Agresif)
- Sub-score display cards (Macro, Health/Internals, Timing)
- Full indicator breakdown table with points, thresholds, descriptions
- Natural language explanation for each verdict
- Backtest module with equity curve (toggle via sidebar)
- CDS auto-fetch from investing.com with curl_cffi Cloudflare bypass
- SPY options chain P/C ratio auto-fetch via yfinance
- VIX/DXY/Treasury/USDTRY charts and analysis
- BIST/USD dollar-based analysis with SMA200

**BIST Verdicts:** UYGUN, KADEMELİ ALIM, DİKKATLİ, BEKLE, GİRMEYİN, RİSKLİ/BEKLE (CDS override)
**USA Verdicts:** AGRESİF ALIM UYGUN, KADEMELİ/DİKKATLİ İŞLEM, NÖTR/BEKLE, GİRMEYİN/KORUMACI MOD, RİSKLİ/NAKİTTE BEKLE (VIX override)
