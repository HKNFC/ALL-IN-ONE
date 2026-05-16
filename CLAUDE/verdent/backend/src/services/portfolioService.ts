// PortfolioService — in-memory store (replace with Prisma in production)

interface Position {
  id: string;
  symbol: string;
  name?: string;
  shares: number;
  avgCost: number;
  currentPrice?: number;
}

let store: Position[] = [
  { id: '1', symbol: 'AAPL', name: 'Apple Inc.',     shares: 50,  avgCost: 165.20 },
  { id: '2', symbol: 'NVDA', name: 'NVIDIA Corp.',   shares: 15,  avgCost: 620.00 },
  { id: '3', symbol: 'MSFT', name: 'Microsoft',      shares: 20,  avgCost: 390.00 },
  { id: '4', symbol: 'TSLA', name: 'Tesla Inc.',     shares: 30,  avgCost: 280.00 },
  { id: '5', symbol: 'META', name: 'Meta Platforms', shares: 8,   avgCost: 470.00 },
];

const MOCK_PRICES: Record<string, number> = {
  AAPL: 189.30, NVDA: 875.40, MSFT: 415.20, TSLA: 248.50, META: 516.80,
};

export class PortfolioService {

  async getAll() {
    return store.map(pos => {
      const currentPrice = MOCK_PRICES[pos.symbol] ?? pos.avgCost;
      const value = currentPrice * pos.shares;
      const cost  = pos.avgCost * pos.shares;
      return {
        ...pos,
        currentPrice,
        value,
        pnl:    +(value - cost).toFixed(2),
        pnlPct: +((value - cost) / cost * 100).toFixed(2),
      };
    });
  }

  async addPosition(data: { symbol: string; shares: number; avgCost: number }) {
    const id  = String(Date.now());
    const pos = { id, ...data };
    store.push(pos);
    return pos;
  }

  async updatePosition(id: string, data: Partial<Position>) {
    const idx = store.findIndex(p => p.id === id);
    if (idx === -1) throw new Error('Position not found');
    store[idx] = { ...store[idx], ...data };
    return store[idx];
  }

  async deletePosition(id: string) {
    const idx = store.findIndex(p => p.id === id);
    if (idx === -1) throw new Error('Position not found');
    store.splice(idx, 1);
    return true;
  }

  async getSummary() {
    const positions = await this.getAll();
    const totalValue = positions.reduce((s, p) => s + p.value, 0);
    const totalCost  = positions.reduce((s, p) => s + p.avgCost * p.shares, 0);
    const totalPnL   = totalValue - totalCost;
    return {
      totalValue: +totalValue.toFixed(2),
      totalCost:  +totalCost.toFixed(2),
      totalPnL:   +totalPnL.toFixed(2),
      totalPnLPct: +((totalPnL / totalCost) * 100).toFixed(2),
      positionCount: positions.length,
    };
  }
}
