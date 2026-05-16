import type { OHLCVData } from '../types';

export function generateOHLCV(days: number = 365, startPrice: number = 150): OHLCVData[] {
  const data: OHLCVData[] = [];
  let price = startPrice;
  const now = Date.now();
  const msPerDay = 86400 * 1000;

  for (let i = days; i >= 0; i--) {
    const date = now - i * msPerDay;
    const open = price;
    const change = (Math.random() - 0.48) * price * 0.025;
    const close = Math.max(open + change, 1);
    const high = Math.max(open, close) * (1 + Math.random() * 0.01);
    const low  = Math.min(open, close) * (1 - Math.random() * 0.01);
    const volume = Math.floor(Math.random() * 50000000 + 10000000);
    data.push({ time: Math.floor(date / 1000), open: +open.toFixed(2), high: +high.toFixed(2), low: +low.toFixed(2), close: +close.toFixed(2), volume });
    price = close;
  }
  return data;
}

export function formatNumber(n: number, decimals: number = 2): string {
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3)  return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(decimals);
}

export function formatCurrency(n: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(n);
}

export function formatPercent(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function generateEquityCurve(days: number = 252) {
  const data = [];
  let equity = 100000;
  let bench = 100000;
  const now = Date.now();
  for (let i = days; i >= 0; i--) {
    const date = new Date(now - i * 86400000).toISOString().split('T')[0];
    equity = equity * (1 + (Math.random() - 0.44) * 0.015);
    bench  = bench  * (1 + (Math.random() - 0.47) * 0.012);
    data.push({ date, value: +equity.toFixed(2), benchmark: +bench.toFixed(2) });
  }
  return data;
}
