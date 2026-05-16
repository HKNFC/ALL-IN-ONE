// Mock data for UI development (until Python API is ready)

export function generateMockBreakouts(count = 20) {
  const symbols = [
    'THYAO','EREGL','SISE','AKBNK','TUPRS','GARAN','ISCTR','KCHOL','SAHOL','BIMAS',
    'TOASO','FROTO','AEFES','ARCLK','ASELS','TKFEN','PETKM','KOZAL','YKBNK','TAVHL',
    'MGROS','ULKER','VESTL','TTRAK','EKGYO','SODA','OTKAR','PGSUS','TCELL','HALKB',
  ];

  const patterns = ['Kupa Sapı', 'Yükselen Üçgen', 'Bayrak', 'Boğa Bayrağı', 'Pivot Kırılımı', 'VCP', 'Daralan Çevre'];
  const sectors = ['Havacılık', 'Çelik', 'Cam', 'Bankacılık', 'Petrol', 'Perakende', 'Otomotiv', 'Savunma'];

  return symbols.slice(0, count).map((sym, i) => ({
    symbol: sym,
    name: sym + ' A.Ş.',
    sector: sectors[i % sectors.length],
    price: +(50 + Math.random() * 450).toFixed(2),
    change1d: +((Math.random() - 0.3) * 8).toFixed(2),
    change1w: +((Math.random() - 0.2) * 15).toFixed(2),
    change1m: +((Math.random() - 0.1) * 30).toFixed(2),
    volume: Math.floor(50_000_000 + Math.random() * 500_000_000),
    volumeRatio: +(1.2 + Math.random() * 4).toFixed(2),
    breakoutScore: Math.floor(55 + Math.random() * 45),
    pattern: patterns[i % patterns.length],
    adx: +(18 + Math.random() * 35).toFixed(1),
    rsi: +(40 + Math.random() * 40).toFixed(1),
    distFrom52wHigh: +((Math.random() - 0.5) * 20).toFixed(1),
    aboveEma200: Math.random() > 0.3,
    aboveEma50: Math.random() > 0.2,
    isBreakingOut: Math.random() > 0.4,
    targetPrice: null as number | null,
    stopLoss: null as number | null,
  })).map(s => ({
    ...s,
    targetPrice: +(s.price * (1 + 0.08 + Math.random() * 0.25)).toFixed(2),
    stopLoss: +(s.price * (1 - 0.04 - Math.random() * 0.06)).toFixed(2),
  })).sort((a, b) => b.breakoutScore - a.breakoutScore);
}

export function generateMockPriceHistory(days = 252) {
  const data = [];
  let price = 100 + Math.random() * 200;
  const now = Date.now();
  for (let i = days; i >= 0; i--) {
    const date = new Date(now - i * 86400000);
    if (date.getDay() === 0 || date.getDay() === 6) continue;
    const change = (Math.random() - 0.46) * price * 0.025;
    const open = price;
    const close = Math.max(1, price + change);
    const high = Math.max(open, close) * (1 + Math.random() * 0.012);
    const low = Math.min(open, close) * (1 - Math.random() * 0.012);
    const vol = Math.floor(1_000_000 + Math.random() * 10_000_000);
    data.push({
      date: date.toISOString().split('T')[0],
      open: +open.toFixed(2), high: +high.toFixed(2),
      low: +low.toFixed(2), close: +close.toFixed(2), volume: vol,
    });
    price = close;
  }
  return data;
}

export type BreakoutStock = ReturnType<typeof generateMockBreakouts>[0];
export type PriceBar = ReturnType<typeof generateMockPriceHistory>[0];
