interface BacktestParams {
  symbol: string;
  strategy: string;
  period: string;
  initialCapital: number;
  params: Record<string, number>;
}

interface TradeResult {
  id: string;
  symbol: string;
  type: 'LONG' | 'SHORT';
  entry: number;
  exit: number;
  entryDate: string;
  exitDate: string;
  pnl: number;
  pnlPct: number;
}

export class BacktestService {

  private history: any[] = [];

  async run(params: BacktestParams) {
    const { symbol, strategy, period, initialCapital } = params;

    // Simulate backtest (replace with real engine)
    const trades: TradeResult[] = [];
    const equityCurve: { date: string; value: number; benchmark: number }[] = [];

    let equity    = initialCapital;
    let benchmark = initialCapital;
    const days    = period === '3M' ? 90 : period === '6M' ? 180 : period === '2Y' ? 504 : 252;
    const now     = Date.now();

    for (let i = days; i >= 0; i--) {
      const date = new Date(now - i * 86400000).toISOString().split('T')[0];
      equity    *= (1 + (Math.random() - 0.44) * 0.015);
      benchmark *= (1 + (Math.random() - 0.47) * 0.012);
      equityCurve.push({ date, value: +equity.toFixed(2), benchmark: +benchmark.toFixed(2) });
    }

    const numTrades = Math.floor(days / 10);
    for (let i = 0; i < numTrades; i++) {
      const entryPrice = 150 + Math.random() * 100;
      const pnl        = (Math.random() - 0.4) * initialCapital * 0.03;
      const exitPrice  = entryPrice + pnl / 10;
      const entryDate  = equityCurve[i * 10]?.date ?? '';
      const exitDate   = equityCurve[Math.min(i * 10 + 8, days)]?.date ?? '';
      trades.push({
        id: String(i),
        symbol,
        type: Math.random() > 0.5 ? 'LONG' : 'SHORT',
        entry:     +entryPrice.toFixed(2),
        exit:      +exitPrice.toFixed(2),
        entryDate, exitDate,
        pnl:       +pnl.toFixed(2),
        pnlPct:    +((pnl / (entryPrice * 10)) * 100).toFixed(2),
      });
    }

    const winners  = trades.filter(t => t.pnl > 0);
    const finalVal = equityCurve[equityCurve.length - 1]?.value ?? initialCapital;
    const result   = {
      id:               String(Date.now()),
      symbol, strategy, period, initialCapital,
      finalValue:        +finalVal.toFixed(2),
      totalReturn:       +((finalVal / initialCapital - 1) * 100).toFixed(2),
      annualizedReturn:  +((Math.pow(finalVal / initialCapital, 252 / days) - 1) * 100).toFixed(2),
      sharpeRatio:       +(1 + Math.random() * 1.5).toFixed(2),
      maxDrawdown:       +((Math.random() * 0.2 + 0.05) * -100).toFixed(2),
      winRate:           +((winners.length / trades.length) * 100).toFixed(1),
      totalTrades:       trades.length,
      profitFactor:      +(1.5 + Math.random() * 1.5).toFixed(2),
      equityCurve, trades,
      createdAt: new Date().toISOString(),
    };

    this.history.unshift(result);
    if (this.history.length > 20) this.history.pop();
    return result;
  }

  async getHistory() {
    return this.history;
  }
}
