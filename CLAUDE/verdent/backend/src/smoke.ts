import { BacktestEngine, generateRebalanceDates } from './services/backtestEngine';

async function main() {
  const engine = new BacktestEngine();
  const result = await engine.runBacktest({
    name: 'Smoke Test',
    criteriaType: 'HYBRID',
    startDate: new Date('2024-01-01'),
    endDate: new Date('2024-03-31'),
    rebalancePeriod: 'MONTHLY',
    market: 'US',
    initialCapital: 100_000,
    transactionCost: 0.001,
    slippage: 0.001,
  });
  console.log('✅ Backtest completed in', result.runtimeMs, 'ms');
  console.log('   Total Return:', result.performance.totalReturn, '%');
  console.log('   Sharpe:', result.performance.sharpeRatio);
  console.log('   Max DD:', result.performance.maxDrawdown, '%');
  console.log('   Trades:', result.performance.totalTrades);
  console.log('   Consistency:', result.consistencyCheck);
  console.log('   Criteria timeline:', result.criteriaTimeline.map(c => `${c.date.toISOString().split('T')[0]}:${c.criteria}(${c.condition})`));

  const dates = generateRebalanceDates(new Date('2024-01-01'), new Date('2024-12-31'), 'MONTHLY');
  console.log('\n✅ Monthly rebalance dates (2024):', dates.length, 'dates');
}

main().catch(console.error);
