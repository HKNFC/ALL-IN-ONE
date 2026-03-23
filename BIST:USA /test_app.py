import warnings
warnings.filterwarnings("ignore")

from data_fetcher import fetch_ohlcv
from indicators import compute_all_indicators
from stock_lists import BIST_STOCKS, USA_STOCKS
from screener import _check_bist, _check_usa

print("=" * 60)
print("TEST 1: Indicator Calculations")
print("=" * 60)

df = fetch_ohlcv("AAPL", period="2y")
df = compute_all_indicators(df)
last = df.iloc[-1]
print(f"AAPL  - Close:{last.Close:.2f} EMA50:{last.ema50:.2f} EMA200:{last.ema200:.2f}")
print(f"        RSI:{last.rsi14:.1f}  ADX:{last.adx14:.1f}  MFI:{last.mfi14:.1f}")
print(f"        BB_W:{last.bb_width:.4f}  BB_W_avg:{last.bb_width_avg:.4f}")
assert not df["ema21"].isna().all(), "EMA21 all NaN"
assert not df["rsi14"].isna().all(), "RSI all NaN"
assert not df["mfi14"].isna().all(), "MFI all NaN"
assert not df["adx14"].isna().all(), "ADX all NaN"
print("PASS: All indicators computed\n")

print("=" * 60)
print("TEST 2: BIST Screener (first 30 stocks)")
print("=" * 60)

bist_hits = []
bist_checked = 0
for sym in BIST_STOCKS[:30]:
    df = fetch_ohlcv(sym, period="6mo")
    if df.empty:
        print(f"  {sym:14s} -> NO DATA")
        continue
    bist_checked += 1
    df2 = compute_all_indicators(df)
    last = df2.iloc[-1]
    trend = last.Close > last.ema21 and last.ema21 > last.ema50
    mfi_ok = 50 < last.mfi14 < 80
    vol_ok = last.Volume > last.vol_avg10 * 1.3
    result = _check_bist(sym, fetch_ohlcv(sym, period="6mo"))
    status = "HIT" if result else "---"
    print(f"  {sym:14s} trend={str(trend):<5} mfi={last.mfi14:5.1f}({str(mfi_ok):<5}) vol={last.Volume/last.vol_avg10:.2f}x  -> {status}")
    if result:
        bist_hits.append(result)

print(f"\nChecked:{bist_checked}  Hits:{len(bist_hits)}")
print("PASS: BIST screener ran without errors\n")

print("=" * 60)
print("TEST 3: USA Screener (first 20 stocks)")
print("=" * 60)

usa_hits = []
for sym in USA_STOCKS[:20]:
    df = fetch_ohlcv(sym, period="2y")
    if df.empty:
        print(f"  {sym:10s} -> NO DATA")
        continue
    df2 = compute_all_indicators(df)
    last = df2.iloc[-1]
    trend = last.Close > last.ema50 and last.ema50 > last.ema200
    mom = last.rsi14 > 60 and last.adx14 > 25
    bb = last.bb_width < last.bb_width_avg
    result = _check_usa(sym, fetch_ohlcv(sym, period="2y"))
    status = "HIT" if result else "---"
    print(f"  {sym:8s} trend={str(trend):<5} rsi={last.rsi14:5.1f} adx={last.adx14:5.1f} bb_sq={str(bb):<5} -> {status}")
    if result:
        usa_hits.append(result)

print(f"\nHits:{len(usa_hits)}")
print("PASS: USA screener ran without errors\n")

print("=" * 60)
print("TEST 4: Mini Backtest (USA, 3-month, 1 Ay)")
print("=" * 60)

from backtest_engine import run_backtest

steps = []
def bt_prog(pct, msg):
    steps.append((pct, str(msg)))
    if len(steps) % 5 == 0:
        print(f"  [{pct*100:.0f}%] {msg}")

result = run_backtest(
    market="USA",
    start_date="2024-06-01",
    end_date="2024-12-31",
    interval_label="1 Ay",
    initial_capital=10000.0,
    progress_callback=bt_prog,
)

print(f"\n  Start Capital : ${result['initial_capital']:,.2f}")
print(f"  Final Value   : ${result['final_value']:,.2f}")
print(f"  Total Return  : {result['total_return_pct']:+.2f}%")
print(f"  CAGR          : {result['cagr_pct']:+.2f}%")
print(f"  Sharpe        : {result['sharpe_ratio']:.2f}")
print(f"  Max Drawdown  : {result['max_drawdown_pct']:.2f}%")
print(f"  Benchmark(SPY): {result['benchmark_return_pct']:+.2f}%")
print(f"  Alpha         : {result['alpha_pct']:+.2f}%")
print(f"  Rebalances    : {result['num_rebalances']}")
print(f"  Portfolio rows: {len(result['portfolio_history'])}")
print(f"  Trades        : {len(result['trades_log'])}")

assert result["final_value"] > 0, "Final value must be positive"
assert len(result["portfolio_history"]) > 0, "Portfolio history empty"
print("\nPASS: Backtest completed successfully\n")

print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
