-- CreateEnum
CREATE TYPE "BacktestStatus" AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "AlertType" AS ENUM ('PRICE_ABOVE', 'PRICE_BELOW', 'PERCENT_CHANGE', 'VOLUME_SPIKE', 'PATTERN_DETECTED');

-- CreateTable
CREATE TABLE "stocks" (
    "id" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "sector" TEXT,
    "marketCap" DOUBLE PRECISION,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "stocks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "stock_prices" (
    "id" TEXT NOT NULL,
    "stockId" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "open" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" DOUBLE PRECISION NOT NULL,
    "rsi14" DOUBLE PRECISION,
    "macd" DOUBLE PRECISION,
    "macdSignal" DOUBLE PRECISION,
    "ema20" DOUBLE PRECISION,
    "ema50" DOUBLE PRECISION,
    "ema200" DOUBLE PRECISION,
    "sma50" DOUBLE PRECISION,
    "sma200" DOUBLE PRECISION,
    "atr14" DOUBLE PRECISION,
    "obv" DOUBLE PRECISION,
    "vwap" DOUBLE PRECISION,
    "bbUpper" DOUBLE PRECISION,
    "bbLower" DOUBLE PRECISION,
    "bbMiddle" DOUBLE PRECISION,
    "adx14" DOUBLE PRECISION,
    "stochK" DOUBLE PRECISION,
    "stochD" DOUBLE PRECISION,
    "pe" DOUBLE PRECISION,
    "pb" DOUBLE PRECISION,
    "roe" DOUBLE PRECISION,
    "debtEquity" DOUBLE PRECISION,
    "revenueGrowth" DOUBLE PRECISION,
    "earningsGrowth" DOUBLE PRECISION,
    "freeCashFlow" DOUBLE PRECISION,

    CONSTRAINT "stock_prices_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "market_conditions" (
    "id" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "market" TEXT NOT NULL,
    "condition" TEXT NOT NULL,
    "vixLevel" DOUBLE PRECISION,
    "breadthIndex" DOUBLE PRECISION,
    "sp500Trend" TEXT,
    "bistTrend" TEXT,
    "confidence" DOUBLE PRECISION NOT NULL,
    "indicators" JSONB NOT NULL,

    CONSTRAINT "market_conditions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "criteria" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "displayName" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "rules" JSONB NOT NULL,
    "scoringWeights" JSONB NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "criteria_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scan_results" (
    "id" TEXT NOT NULL,
    "scanDate" TIMESTAMP(3) NOT NULL,
    "criteriaId" TEXT NOT NULL,
    "stockId" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL,
    "rank" INTEGER NOT NULL,
    "signals" JSONB NOT NULL,
    "entryPrice" DOUBLE PRECISION NOT NULL,
    "targetPrice" DOUBLE PRECISION,
    "stopLoss" DOUBLE PRECISION,

    CONSTRAINT "scan_results_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "backtests" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "criteriaType" TEXT NOT NULL,
    "criteriaId" TEXT,
    "startDate" TIMESTAMP(3) NOT NULL,
    "endDate" TIMESTAMP(3) NOT NULL,
    "rebalancePeriod" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "initialCapital" DOUBLE PRECISION NOT NULL DEFAULT 100000,
    "status" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "isDeleted" BOOLEAN NOT NULL DEFAULT false,
    "totalReturn" DOUBLE PRECISION,
    "annualizedReturn" DOUBLE PRECISION,
    "maxDrawdown" DOUBLE PRECISION,
    "sharpeRatio" DOUBLE PRECISION,
    "winRate" DOUBLE PRECISION,
    "totalTrades" INTEGER,

    CONSTRAINT "backtests_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "backtest_snapshots" (
    "id" TEXT NOT NULL,
    "backtestId" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "portfolioValue" DOUBLE PRECISION NOT NULL,
    "holdings" JSONB NOT NULL,
    "criteriaUsed" TEXT NOT NULL,
    "marketCondition" TEXT NOT NULL,

    CONSTRAINT "backtest_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "backtest_trades" (
    "id" TEXT NOT NULL,
    "backtestId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "price" DOUBLE PRECISION NOT NULL,
    "shares" DOUBLE PRECISION NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "reason" TEXT NOT NULL,

    CONSTRAINT "backtest_trades_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "name" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "backtest_runs" (
    "id" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "strategy" TEXT NOT NULL,
    "period" TEXT NOT NULL,
    "initialCapital" DOUBLE PRECISION NOT NULL,
    "finalValue" DOUBLE PRECISION,
    "totalReturn" DOUBLE PRECISION,
    "sharpeRatio" DOUBLE PRECISION,
    "maxDrawdown" DOUBLE PRECISION,
    "winRate" DOUBLE PRECISION,
    "totalTrades" INTEGER,
    "profitFactor" DOUBLE PRECISION,
    "params" JSONB NOT NULL DEFAULT '{}',
    "equityCurve" JSONB,
    "trades" JSONB,
    "status" "BacktestStatus" NOT NULL DEFAULT 'PENDING',
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),
    "userId" TEXT,

    CONSTRAINT "backtest_runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "watchlists" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL DEFAULT 'Default',
    "symbols" TEXT[],
    "userId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "watchlists_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "alerts" (
    "id" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "type" "AlertType" NOT NULL,
    "condition" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "message" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "triggeredAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "userId" TEXT NOT NULL,

    CONSTRAINT "alerts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "market_data_cache" (
    "id" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "period" TEXT NOT NULL,
    "data" JSONB NOT NULL,
    "cachedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "market_data_cache_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "stocks_symbol_key" ON "stocks"("symbol");

-- CreateIndex
CREATE INDEX "stocks_market_idx" ON "stocks"("market");

-- CreateIndex
CREATE INDEX "stocks_sector_idx" ON "stocks"("sector");

-- CreateIndex
CREATE INDEX "stock_prices_stockId_idx" ON "stock_prices"("stockId");

-- CreateIndex
CREATE INDEX "stock_prices_date_idx" ON "stock_prices"("date");

-- CreateIndex
CREATE UNIQUE INDEX "stock_prices_stockId_date_key" ON "stock_prices"("stockId", "date");

-- CreateIndex
CREATE UNIQUE INDEX "market_conditions_date_key" ON "market_conditions"("date");

-- CreateIndex
CREATE INDEX "market_conditions_market_idx" ON "market_conditions"("market");

-- CreateIndex
CREATE INDEX "market_conditions_condition_idx" ON "market_conditions"("condition");

-- CreateIndex
CREATE INDEX "criteria_market_idx" ON "criteria"("market");

-- CreateIndex
CREATE INDEX "criteria_isActive_idx" ON "criteria"("isActive");

-- CreateIndex
CREATE INDEX "scan_results_scanDate_idx" ON "scan_results"("scanDate");

-- CreateIndex
CREATE INDEX "scan_results_criteriaId_idx" ON "scan_results"("criteriaId");

-- CreateIndex
CREATE INDEX "scan_results_stockId_idx" ON "scan_results"("stockId");

-- CreateIndex
CREATE INDEX "scan_results_score_idx" ON "scan_results"("score");

-- CreateIndex
CREATE UNIQUE INDEX "scan_results_scanDate_criteriaId_stockId_key" ON "scan_results"("scanDate", "criteriaId", "stockId");

-- CreateIndex
CREATE INDEX "backtests_status_idx" ON "backtests"("status");

-- CreateIndex
CREATE INDEX "backtests_criteriaType_idx" ON "backtests"("criteriaType");

-- CreateIndex
CREATE INDEX "backtests_market_idx" ON "backtests"("market");

-- CreateIndex
CREATE INDEX "backtests_isDeleted_idx" ON "backtests"("isDeleted");

-- CreateIndex
CREATE INDEX "backtest_snapshots_backtestId_idx" ON "backtest_snapshots"("backtestId");

-- CreateIndex
CREATE INDEX "backtest_snapshots_date_idx" ON "backtest_snapshots"("date");

-- CreateIndex
CREATE INDEX "backtest_trades_backtestId_idx" ON "backtest_trades"("backtestId");

-- CreateIndex
CREATE INDEX "backtest_trades_symbol_idx" ON "backtest_trades"("symbol");

-- CreateIndex
CREATE INDEX "backtest_trades_date_idx" ON "backtest_trades"("date");

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE INDEX "backtest_runs_symbol_idx" ON "backtest_runs"("symbol");

-- CreateIndex
CREATE INDEX "backtest_runs_strategy_idx" ON "backtest_runs"("strategy");

-- CreateIndex
CREATE INDEX "alerts_symbol_idx" ON "alerts"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "market_data_cache_symbol_period_key" ON "market_data_cache"("symbol", "period");

-- AddForeignKey
ALTER TABLE "stock_prices" ADD CONSTRAINT "stock_prices_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "stocks"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scan_results" ADD CONSTRAINT "scan_results_criteriaId_fkey" FOREIGN KEY ("criteriaId") REFERENCES "criteria"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scan_results" ADD CONSTRAINT "scan_results_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "stocks"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "backtests" ADD CONSTRAINT "backtests_criteriaId_fkey" FOREIGN KEY ("criteriaId") REFERENCES "criteria"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "backtest_snapshots" ADD CONSTRAINT "backtest_snapshots_backtestId_fkey" FOREIGN KEY ("backtestId") REFERENCES "backtests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "backtest_trades" ADD CONSTRAINT "backtest_trades_backtestId_fkey" FOREIGN KEY ("backtestId") REFERENCES "backtests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "backtest_runs" ADD CONSTRAINT "backtest_runs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "watchlists" ADD CONSTRAINT "watchlists_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "alerts" ADD CONSTRAINT "alerts_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
