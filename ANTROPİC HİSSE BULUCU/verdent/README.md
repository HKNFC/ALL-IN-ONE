# VERDENT — Financial Trading Platform

A full-stack financial analysis and backtesting platform for BIST (Turkish) and US markets. Built with React, TypeScript, Node.js, Express, PostgreSQL, and Prisma.

---

## Features

- **Market Condition Engine** — Automatically detects BULL / BEAR / SIDEWAYS conditions using 4 indicator groups (Trend, Momentum, Volatility, Breadth) with a -10 to +10 scoring system
- **Three Screening Criteria**
  - **ALFA** — Bull market: momentum + growth stocks
  - **BETA** — Bear market: defensive + value stocks  
  - **DELTA** — Sideways market: mean-reversion + range-bound stocks
- **HYBRID Mode** — Automatically switches criteria based on real-time market condition
- **Backtesting Engine** — Weekly or monthly rebalance, equal-weight 5-stock portfolio, performance metrics (CAGR, Sharpe, Max Drawdown, Win Rate, etc.)
- **Consistency Guarantee** — Scanner and Backtest use the exact same deterministic scan function; SHA-256 cache key `(criteria|date|market)` guarantees identical results
- **Portfolio Tracker** — Position management with risk display (max loss, weight, stop losses) and portfolio health radar
- **Backtest Comparison** — Side-by-side metrics table and normalised growth chart for up to 3 backtests
- **Market Condition History** — 12-month colour-coded BULL/BEAR/SIDEWAYS timeline with index performance chart

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS + custom design system |
| Charts | Recharts (AreaChart, LineChart, RadarChart) |
| State | Zustand |
| Backend | Node.js + Express 5 |
| Database | PostgreSQL + Prisma ORM |
| Cache | Redis (ioredis) |
| Real-time | WebSocket (ws) |
| Validation | Zod |
| Testing | Jest + ts-jest |

---

## Prerequisites

- Node.js >= 18
- PostgreSQL >= 14
- Redis >= 6
- pnpm or npm

---

## Installation

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-org/verdent.git
cd verdent

# Backend
cd backend
npm install

# Frontend
cd ../frontend
npm install
```

### 2. Configure environment

```bash
cd backend
cp ../env.example .env
# Edit .env and fill in DATABASE_URL, JWT_SECRET, API keys, etc.
```

### 3. Set up the database

```bash
cd backend
npx prisma migrate dev --name init
npx prisma generate
```

### 4. Start development servers

```bash
# Terminal 1 — Backend (port 3001)
cd backend
npm run dev

# Terminal 2 — Frontend (port 5173)
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## API Documentation

After starting the backend, Swagger UI is available at:

```
http://localhost:3001/api/docs
```

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/condition/:market` | Current market condition (BIST or US) |
| POST | `/api/scanner/scan` | Run a stock scan |
| POST | `/api/backtest/run` | Start a new backtest |
| GET | `/api/backtest/results` | List all backtests |
| GET | `/api/backtest/results/:id` | Get backtest detail |
| DELETE | `/api/backtest/:id` | Soft-delete a backtest |
| GET | `/api/stocks/search?q=THYAO` | Search stocks |

### WebSocket Events

Connect to `ws://localhost:3001/ws` for real-time updates:

| Event | Payload | Description |
|-------|---------|-------------|
| `backtest:progress` | `{ jobId, progress, stage, message }` | Backtest progress |
| `backtest:complete` | `{ backtestId, result }` | Backtest finished |
| `market:update` | `{ market, condition }` | Market condition changed |

---

## Screening Criteria

### ALFA — Bull Market

Targets high-momentum growth stocks in uptrending markets.

**Technical**: Price > 200 EMA, Golden Cross (50 > 200 EMA), RSI 50–70, MACD bullish, Volume > 1.5× average, ADX > 25, within 10% of 52-week high.

**Fundamental**: Revenue growth > 15%, Earnings growth > 10%, ROE > 15%, D/E < 1.5, Positive FCF.

### BETA — Bear Market

Targets defensive, low-beta stocks with value characteristics.

**Technical**: Relative strength vs. index > 1.0, Beta < 0.8, RSI > 30, Stochastic < 20 and crossing up, Price near key support.

**Fundamental**: Dividend yield > 2%, P/E < 15, P/B < 1.5, D/E < 0.5, Current ratio > 2.

### DELTA — Sideways Market

Targets range-bound stocks approaching oversold support zones.

**Technical**: ADX < 20 (no trend), Price near lower Bollinger Band, RSI 30–45, Stochastic < 30, Price below VWAP converging upward.

**Fundamental**: Consistent revenue, P/E 10–20, ROE > 10%, low debt.

---

## Running Backtests

1. Navigate to the **Backtest** page
2. Choose criteria type: ALFA / BETA / DELTA / HYBRID
3. Set start date, end date, rebalance period (Weekly or Monthly), and market (BIST / US / Both)
4. Set initial capital (default 100,000)
5. Click **Run Backtest**
6. Progress is streamed via WebSocket; results appear when complete
7. Click the eye icon to view detailed performance, portfolio history, and trades
8. Use the compare button (Git icon) to select 2–3 backtests for side-by-side comparison

---

## Data Sources

| Market | Primary | Backup |
|--------|---------|--------|
| US (NYSE/NASDAQ) | Alpha Vantage | Polygon.io |
| BIST (Turkey) | Is Yatirim API | Bigpara scraper |

Configure API keys in `.env` (see `env.example`).

---

## Running Tests

```bash
cd backend
npm test               # run all tests
npm run test:watch     # watch mode
npm run test:coverage  # with coverage report
```

Test files are in `backend/src/__tests__/`:
- `criteriaEngine.test.ts` — ALFA/BETA/DELTA scoring logic
- `backtestEngine.test.ts` — Metric calculations, rebalance date generation
- `marketCondition.test.ts` — Market condition detection algorithm
- `consistency.test.ts` — Guarantees Scanner and Backtest return identical results

---

## Project Structure

```
verdent/
├── frontend/
│   ├── src/
│   │   ├── pages/          # Dashboard, Backtest, Scanner, Portfolio
│   │   ├── components/     # Layout, shared components
│   │   ├── stores/         # Zustand stores
│   │   └── services/       # API client
├── backend/
│   ├── src/
│   │   ├── routes/         # Express route handlers
│   │   ├── services/       # Business logic
│   │   │   ├── dataService.ts
│   │   │   ├── marketConditionService.ts
│   │   │   ├── criteriaEngine.ts
│   │   │   ├── backtestEngine.ts
│   │   │   ├── consistencyService.ts  ← shared scan function
│   │   │   └── backtestOptimizer.ts
│   │   ├── jobs/           # dataSyncJob (cron)
│   │   ├── utils/          # indicators.ts, helpers
│   │   └── __tests__/      # Jest test suite
│   └── prisma/
│       └── schema.prisma
├── env.example
└── README.md
```

---

## License

MIT
