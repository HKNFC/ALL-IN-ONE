export interface Stock {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
  volume: number;
  marketCap: number;
  sector: string;
}

export interface OHLCVData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PortfolioPosition {
  id: string;
  symbol: string;
  name: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  pnl: number;
  pnlPct: number;
  value: number;
  weight: number;
}

export interface BacktestResult {
  totalReturn: number;
  annualizedReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  totalTrades: number;
  profitFactor: number;
  equityCurve: { date: string; value: number; benchmark: number }[];
  trades: Trade[];
}

export interface Trade {
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

export interface ScanResult {
  symbol: string;
  name: string;
  price: number;
  change: number;
  volume: number;
  signal: string;
  strength: number;
  pattern: string;
  sector: string;
}

export interface MarketData {
  index: string;
  value: number;
  change: number;
  changePct: number;
}
