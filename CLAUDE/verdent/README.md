# VERDENT — Algorithmic Trading Platform

A full-stack financial trading application featuring automated stock screening, market condition analysis, and backtesting with three adaptive criteria sets (ALFA / BETA / DELTA).

---

## Tech Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Frontend   | React 18 + TypeScript + Vite            |
| Styling    | Tailwind CSS + custom dark design system |
| Charts     | Recharts + TradingView Lightweight Charts |
| State      | Zustand                                 |
| Backend    | Node.js + Express + TypeScript          |
| Database   | PostgreSQL + Prisma ORM                 |
| Cache      | Redis (optional)                        |
| Real-time  | WebSocket (ws)                          |
| API Docs   | Swagger UI (`/api/docs`)                |

---

## Installation

### Prerequisites

- Node.js ≥ 18
- PostgreSQL ≥ 14
- Redis ≥ 6 (optional)

### 1. Clone & install

```bash
git clone <repo-url>
cd verdent

# Backend
cd backend
npm install
cp .env.example .env   # fill in your values

# Frontend
cd ../frontend
npm install
```

### 2. Database setup

```bash
cd backend

# Apply schema migrations
npx prisma migrate dev --name init

# (Optional) seed with sample BIST stocks
npx prisma db seed
```

### 3. Start development servers

```bash
# Terminal 1 — backend (port 4000)
cd backend
npm run dev

# Terminal 2 — frontend (port 3000)
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

API docs: [http://localhost:4000/api/docs](http://localhost:4000/api/docs)

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable              | Required | Description                              |
|-----------------------|----------|------------------------------------------|
| `DATABASE_URL`        | ✅       | PostgreSQL connection string             |
| `PORT`                | ✅       | API server port (default 4000)           |
| `JWT_SECRET`          | ✅       | Random 64-byte hex secret                |
| `FRONTEND_URL`        | ✅       | Frontend origin for CORS                 |
| `REDIS_URL`           | ⬜       | Redis connection string (caching)        |
| `ALPHA_VANTAGE_API_KEY` | ⬜     | US market data (5 req/min free tier)     |
| `POLYGON_API_KEY`     | ⬜       | US market data (fallback)                |
| `IS_YATIRIM_API_KEY`  | ⬜       | BIST data from İş Yatırım                |
| `BIGPARA_API_KEY`     | ⬜       | BIST data fallback                       |

> Without API keys the application uses deterministic mock data, which is sufficient for testing all features.

---

## Criteria Systems

VERDENT dynamically switches between three screening engines based on market conditions:

### ALFA — Bull Market (Momentum/Growth)

Activated when market score > +3. Finds stocks with strong upward momentum.

**Key filters:**
- Price > 200 EMA + 50 EMA (uptrend confirmation)
- Golden Cross (50 EMA > 200 EMA)
- RSI(14) between 50–70 (momentum, not overbought)
- Volume > 1.5× 20-day average
- ADX(14) > 25 (strong trend)
- Revenue growth YoY > 15%, ROE > 15%

### BETA — Bear Market (Defensive/Value)

Activated when market score < -3. Finds outperformers and value plays.

**Key filters:**
- Relative strength vs index > 1.0 (outperforming)
- Beta < 0.8 (defensive, low-volatility)
- Stochastic(14,3,3) < 20 crossing up (oversold reversal)
- Dividend yield > 2%, P/E < 15, D/E < 0.5

### DELTA — Sideways Market (Mean Reversion)

Activated when market score between -3 and +3. Finds range-bound opportunities.

**Key filters:**
- ADX(14) < 20 (no strong trend)
- Price near Bollinger lower band
- RSI(14) between 30–45 (oversold recovering)
- VWAP proximity, volume capitulation signal

### HYBRID Mode

In HYBRID backtests, VERDENT detects the market condition at each rebalance date and automatically selects the appropriate criteria (ALFA/BETA/DELTA). This is the recommended mode for long-term backtests.

---

## Running Backtests

### Via the UI

1. Go to **Backtest** page
2. Select criteria type (ALFA / BETA / DELTA / HYBRID)
3. Set date range, rebalance period (Weekly / Monthly), market (BIST / US)
4. Click **RUN BACKTEST**
5. Progress is streamed via WebSocket in real time

### Via API

```bash
curl -X POST http://localhost:4000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "name": "HYBRID 2022-2024",
    "criteriaType": "HYBRID",
    "startDate": "2022-01-01",
    "endDate": "2024-01-01",
    "rebalancePeriod": "MONTHLY",
    "market": "BIST",
    "initialCapital": 100000
  }'
# Returns: { backtestId, status: "PENDING" }

# Poll progress
curl http://localhost:4000/api/backtest/status/<backtestId>

# Get full results
curl http://localhost:4000/api/backtest/results/<backtestId>
```

### Performance Metrics

| Metric            | Description                              |
|-------------------|------------------------------------------|
| Total Return      | Overall % gain/loss                      |
| Annualised Return | CAGR over backtest period                |
| Max Drawdown      | Largest peak-to-trough decline           |
| Sharpe Ratio      | Risk-adjusted return (Rf = 5%)           |
| Sortino Ratio     | Downside-deviation adjusted              |
| Win Rate          | % of closed trades with positive P&L    |
| Calmar Ratio      | CAGR / |Max Drawdown|                   |
| Profit Factor     | Gross profit / gross loss                |

---

## Data Sources

### BIST (Turkish Market)

1. **İş Yatırım API** (primary) — requires `IS_YATIRIM_API_KEY`
2. **Bigpara API** (fallback) — requires `BIGPARA_API_KEY`
3. **Mock data** (development fallback, no key needed)

### US Markets

1. **Yahoo Finance v8** (primary) — no API key required
2. **Alpha Vantage** (fallback) — requires `ALPHA_VANTAGE_API_KEY` (free: 5 req/min)
3. **Polygon.io** (fallback) — requires `POLYGON_API_KEY`

### Data Sync Job

A daily cron job (`dataSyncJob.ts`) runs after market close to:
- Update OHLCV prices for all tracked stocks
- Recalculate all technical indicators
- Update market condition analysis
- Store everything in PostgreSQL

---

## API Reference

Full interactive documentation: [http://localhost:4000/api/docs](http://localhost:4000/api/docs)

### Key Endpoints

```
GET  /api/market/condition/:market          Current market condition
GET  /api/market/history/:market            Historical conditions (paginated)
GET  /api/market/breadth/:market            Advance/decline, % above 200 SMA

POST /api/scanner/scan                      Run a stock scan
GET  /api/scanner/results                   Saved scan history

POST /api/backtest/run                      Start a backtest (async)
GET  /api/backtest/status/:id               Poll backtest progress
GET  /api/backtest/results                  All backtests
GET  /api/backtest/results/:id              Full result detail
DELETE /api/backtest/:id                    Soft-delete

GET  /api/stocks/search?q=THYAO            Search stocks
GET  /api/stocks/:symbol/price             OHLCV price history
GET  /api/stocks/:symbol/indicators        Technical indicators

GET  /api/consistency/check?criteria=&date=&market=   Verify scanner ↔ backtest consistency

WS   ws://localhost:4000/ws                 Real-time events
```

### WebSocket Events

```jsonc
// Subscribe to a channel
{ "subscribe": "backtest" }

// Backtest progress
{ "event": "backtest:progress", "payload": { "id": "...", "stage": "portfolio", "progress": 45, "currentDate": "2023-06-01" } }

// Backtest complete
{ "event": "backtest:complete", "payload": { "id": "...", "result": { ... } } }

// Scan complete
{ "event": "scan:complete", "payload": { "id": "...", "result": { ... } } }
```

---

## Running Tests

```bash
cd backend

# All tests
npm test

# With coverage
npm run test:coverage

# Watch mode
npx jest --watch
```

Test files are in `backend/src/__tests__/`:

| File                      | Coverage                                     |
|---------------------------|----------------------------------------------|
| `criteriaEngine.test.ts`  | ALFA/BETA/DELTA scoring, sorting, trade levels |
| `marketCondition.test.ts` | BULL/BEAR/SIDEWAYS detection, determinism     |
| `backtestEngine.test.ts`  | Metrics, rebalance dates, progress callback   |
| `consistency.test.ts`     | Scanner ↔ backtest result equality           |

---

## Project Structure

```
verdent/
├── frontend/
│   ├── src/
│   │   ├── pages/          Dashboard, Backtest, Scanner, Portfolio
│   │   ├── components/     Shared UI (VirtualTradeList, BacktestProgress, ScoreRadarChart, …)
│   │   ├── hooks/          useToast, useDebounce, useWebSocket
│   │   ├── stores/         Zustand state (appStore)
│   │   └── services/       API client
├── backend/
│   ├── src/
│   │   ├── routes/         Express routers
│   │   ├── services/       Business logic (criteriaEngine, backtestEngine, …)
│   │   ├── jobs/           dataSyncJob (cron)
│   │   ├── middleware.ts   Zod validation, rate limiting, error handling
│   │   ├── ws.ts           WebSocket server
│   │   └── swagger.ts      OpenAPI spec
│   └── prisma/
│       └── schema.prisma   Database schema
└── database/
    └── schema.prisma       (canonical schema copy)
```

---

## License

MIT
