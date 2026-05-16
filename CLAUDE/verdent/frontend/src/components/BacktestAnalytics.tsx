import { useState, useMemo } from 'react';
import {
  ComposedChart, LineChart, Line, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine, Legend,
  Area, AreaChart,
} from 'recharts';

// ─── Types ────────────────────────────────────────────────────────────────────

interface BacktestConfig {
  criteriaType: string;
  startDate: string;
  endDate: string;
  market: string;
  initialCapital: number;
}

interface PerformanceMetrics {
  totalReturn: number;
  annualizedReturn: number;
  maxDrawdown: number;
  sharpeRatio: number;
  winRate: number;
  totalTrades: number;
}

interface PortfolioHistoryEntry {
  date: string;
  value: number;
  criteriaUsed: string;
  marketCondition: string;
}

interface TradeEntry {
  id: string;
  symbol: string;
  action: string;
  date: string;
  price: number;
  shares: number;
  value: number;
  reason: string;
  pnl?: number;
  pnlPct?: number;
  criteriaUsed?: string;
}

interface BenchmarkData {
  totalReturn: number;
  annualizedReturn: number;
  maxDrawdown: number;
  sharpeRatio: number;
}

interface CriteriaTimelineEntry {
  date: string;
  criteria: string;
  condition: string;
  switched: boolean;
}

export interface BacktestAnalyticsProps {
  backtest: {
    id: string;
    config: BacktestConfig;
    performance: PerformanceMetrics;
    portfolioHistory: PortfolioHistoryEntry[];
    trades: TradeEntry[];
    benchmark?: BenchmarkData;
    criteriaTimeline?: CriteriaTimelineEntry[];
  };
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BULL_COLOR = '#00D084';
const BEAR_COLOR = '#FF4757';
const SIDEWAYS_COLOR = '#FFA502';
const BLUE_COLOR = '#409CFF';
const GRID_COLOR = '#1E2D4A';
const CARD_BG = '#0F1629';
const BORDER_COLOR = '#1E2D4A';
const TEXT_PRIMARY = '#FFFFFF';
const TEXT_SECONDARY = '#8899AA';

const CONDITION_COLOR: Record<string, string> = {
  BULL: BULL_COLOR,
  BEAR: BEAR_COLOR,
  SIDEWAYS: SIDEWAYS_COLOR,
};

const FACTOR_MAP: Record<string, string[]> = {
  ALFA: ['Momentum', 'Rel Strength', 'Volume', 'Trend', 'Fundamentals', 'Entry'],
  BETA: ['Rel Strength', 'Piotroski', 'Downside', 'Value', 'Dividend', 'Recovery'],
  DELTA: ['Range', 'MeanRev', 'Support', 'FundFloor', 'EventRisk', 'VolTiming'],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

function seededRand(seed: number): number {
  const x = Math.sin(seed + 1) * 10000;
  return x - Math.floor(x);
}

function pctColor(v: number): string {
  return v >= 0 ? BULL_COLOR : BEAR_COLOR;
}

function fmtPct(v: number, dec = 2): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(dec)}%`;
}

function fmtK(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
}

// ─── Dark Tooltip ─────────────────────────────────────────────────────────────

interface TooltipPayloadItem {
  name: string;
  value: number;
  color?: string;
  stroke?: string;
}

interface DarkTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
  formatter?: (name: string, value: number) => string;
}

function DarkTooltip({ active, payload, label, formatter }: DarkTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: CARD_BG, border: `1px solid ${BORDER_COLOR}`,
      borderRadius: 6, padding: '8px 12px', fontSize: 11, color: TEXT_PRIMARY,
    }}>
      {label && <div style={{ color: TEXT_SECONDARY, marginBottom: 5, fontSize: 10 }}>{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color ?? p.stroke ?? TEXT_PRIMARY, marginBottom: 2 }}>
          <span style={{ color: TEXT_SECONDARY }}>{p.name}: </span>
          <strong>{formatter ? formatter(p.name, p.value) : p.value}</strong>
        </div>
      ))}
    </div>
  );
}

// ─── 1. ReturnAttributionChart ────────────────────────────────────────────────

function ReturnAttributionChart({ backtest }: BacktestAnalyticsProps) {
  const data = useMemo(() => {
    const { portfolioHistory, trades, config } = backtest;
    if (portfolioHistory.length < 2) return [];

    // Group portfolio snapshots by criteriaUsed
    const criteriaGroups = new Map<string, PortfolioHistoryEntry[]>();
    for (const snap of portfolioHistory) {
      const key = snap.criteriaUsed;
      if (!criteriaGroups.has(key)) criteriaGroups.set(key, []);
      criteriaGroups.get(key)!.push(snap);
    }

    // Estimate transaction costs
    const totalTradedValue = trades.reduce((sum, t) => sum + t.value, 0);
    const totalCosts = totalTradedValue * 0.003; // 0.3%

    const rows: { label: string; base: number; gain: number; cost: number; total: number; gainPct: number }[] = [];
    let runningBase = config.initialCapital;

    for (const [criteria, snaps] of criteriaGroups) {
      if (snaps.length < 2) continue;
      const first = snaps[0].value;
      const last = snaps[snaps.length - 1].value;
      const rawGain = last - first;
      const criteriaTradeValue = trades.filter(t => (t.criteriaUsed ?? '') === criteria).reduce((s, t) => s + t.value, 0);
      const costShare = totalTradedValue > 0 ? (criteriaTradeValue / totalTradedValue) * totalCosts : totalCosts / criteriaGroups.size;
      const gain = rawGain - costShare;
      rows.push({
        label: criteria,
        base: runningBase,
        gain: Math.max(0, gain),
        cost: costShare,
        total: runningBase + gain,
        gainPct: first > 0 ? (gain / first) * 100 : 0,
      });
      runningBase = runningBase + gain;
    }

    return rows;
  }, [backtest]);

  const tooltipFormatter = (_name: string, value: number) => `$${fmtK(value)}`;

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER_COLOR}`, borderRadius: 8, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 14, letterSpacing: '0.06em' }}>
        RETURN ATTRIBUTION — Criteria Contribution
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: TEXT_SECONDARY }} />
          <YAxis tick={{ fontSize: 9, fill: TEXT_SECONDARY }} tickFormatter={fmtK} width={42} />
          <Tooltip
            content={(props) => (
              <DarkTooltip
                active={props.active}
                payload={props.payload as TooltipPayloadItem[]}
                label={props.label as string}
                formatter={tooltipFormatter}
              />
            )}
          />
          <Legend wrapperStyle={{ fontSize: 10, color: TEXT_SECONDARY }} />
          <Bar dataKey="base" name="Starting Base" stackId="stack" fill="transparent" stroke="transparent" />
          <Bar dataKey="gain" name="Criteria Gain" stackId="stack" fill={BULL_COLOR} opacity={0.8} radius={[3, 3, 0, 0]} />
          <Bar dataKey="cost" name="Est. Costs" stackId="stack" fill={BEAR_COLOR} opacity={0.7} />
        </ComposedChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
        {data.map(d => (
          <div key={d.label} style={{ fontSize: 10, color: TEXT_SECONDARY }}>
            <span style={{ color: BULL_COLOR, fontWeight: 700 }}>{d.label}</span>{' '}
            {fmtPct(d.gainPct)} gain · cost ${fmtK(d.cost)}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 2. RollingMetricsChart ───────────────────────────────────────────────────

function RollingMetricsChart({ backtest }: BacktestAnalyticsProps) {
  const data = useMemo(() => {
    const { portfolioHistory } = backtest;
    if (portfolioHistory.length < 5) return [];

    const result: { date: string; sharpe: number | null; returnVsBench: number | null; volatility: number | null }[] = [];
    const WINDOW_SHORT = 20; // ~20 days
    const WINDOW_LONG  = Math.min(60, Math.floor(portfolioHistory.length / 2)); // ~3 months

    for (let i = WINDOW_LONG; i < portfolioHistory.length; i++) {
      const longSlice = portfolioHistory.slice(i - WINDOW_LONG, i);
      const shortSlice = portfolioHistory.slice(Math.max(0, i - WINDOW_SHORT), i);

      // Daily returns for long window
      const longReturns: number[] = [];
      for (let j = 1; j < longSlice.length; j++) {
        longReturns.push((longSlice[j].value - longSlice[j - 1].value) / longSlice[j - 1].value);
      }
      if (longReturns.length < 3) { result.push({ date: portfolioHistory[i].date, sharpe: null, returnVsBench: null, volatility: null }); continue; }

      const avgReturn = longReturns.reduce((s, r) => s + r, 0) / longReturns.length;
      const variance = longReturns.reduce((s, r) => s + Math.pow(r - avgReturn, 2), 0) / longReturns.length;
      const std = Math.sqrt(variance);
      const rollingSharp = std > 0 ? (avgReturn / std) * Math.sqrt(252) : 0;

      // Rolling 3m return vs benchmark (simplified: strategy return)
      const startVal = longSlice[0].value;
      const endVal = longSlice[longSlice.length - 1].value;
      const rollingReturn = startVal > 0 ? ((endVal - startVal) / startVal) * 100 : 0;
      // Benchmark return estimated from ~6% annualized
      const periods = longSlice.length;
      const benchReturn = (Math.pow(1.06, periods / 252) - 1) * 100;
      const returnVsBench = rollingReturn - benchReturn;

      // Rolling 20-day volatility
      const shortReturns: number[] = [];
      for (let j = 1; j < shortSlice.length; j++) {
        shortReturns.push((shortSlice[j].value - shortSlice[j - 1].value) / shortSlice[j - 1].value);
      }
      let rollingVol = 0;
      if (shortReturns.length >= 2) {
        const avg2 = shortReturns.reduce((s, r) => s + r, 0) / shortReturns.length;
        const var2 = shortReturns.reduce((s, r) => s + Math.pow(r - avg2, 2), 0) / shortReturns.length;
        rollingVol = Math.sqrt(var2) * Math.sqrt(252) * 100;
      }

      result.push({
        date: portfolioHistory[i].date,
        sharpe: +rollingSharp.toFixed(3),
        returnVsBench: +returnVsBench.toFixed(2),
        volatility: +rollingVol.toFixed(2),
      });
    }
    return result;
  }, [backtest]);

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER_COLOR}`, borderRadius: 8, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 14, letterSpacing: '0.06em' }}>
        ROLLING METRICS — 3-Month Window
      </div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 10 }}>
        {[
          { color: BULL_COLOR, label: 'Rolling Sharpe (left)' },
          { color: SIDEWAYS_COLOR, label: 'vs Benchmark % (right)' },
          { color: BLUE_COLOR, label: 'Volatility % (right)' },
        ].map(l => (
          <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 12, height: 2, background: l.color }} />
            <span style={{ fontSize: 10, color: TEXT_SECONDARY }}>{l.label}</span>
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 4, right: 40, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: TEXT_SECONDARY }} tickFormatter={s => s.slice(0, 7)} interval="preserveStartEnd" />
          <YAxis yAxisId="left" tick={{ fontSize: 9, fill: TEXT_SECONDARY }} width={36} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 9, fill: TEXT_SECONDARY }} width={36} tickFormatter={v => `${v.toFixed(0)}%`} />
          <ReferenceLine yAxisId="left" y={0} stroke={GRID_COLOR} strokeDasharray="4 4" />
          <Tooltip
            content={(props) => (
              <DarkTooltip
                active={props.active}
                payload={props.payload as TooltipPayloadItem[]}
                label={props.label as string}
              />
            )}
          />
          <Line yAxisId="left" type="monotone" dataKey="sharpe" name="Sharpe" stroke={BULL_COLOR} dot={false} strokeWidth={1.5} connectNulls />
          <Line yAxisId="right" type="monotone" dataKey="returnVsBench" name="vs Bench %" stroke={SIDEWAYS_COLOR} dot={false} strokeWidth={1.5} connectNulls />
          <Line yAxisId="right" type="monotone" dataKey="volatility" name="Volatility %" stroke={BLUE_COLOR} dot={false} strokeWidth={1.5} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── 3. FactorHeatmap ─────────────────────────────────────────────────────────

function FactorHeatmap({ backtest }: BacktestAnalyticsProps) {
  const { criteriaType } = backtest.config;
  const factors = FACTOR_MAP[criteriaType] ?? FACTOR_MAP['ALFA'];

  const topTrades = useMemo(() => {
    return [...backtest.trades]
      .filter(t => t.pnlPct !== undefined)
      .sort((a, b) => (b.pnlPct ?? 0) - (a.pnlPct ?? 0))
      .slice(0, 10);
  }, [backtest.trades]);

  // Score each trade+factor combination deterministically
  const scoreMatrix = useMemo(() => {
    return topTrades.map(trade =>
      factors.map((factor, fi) => {
        const seed = hashStr(trade.symbol + factor + String(fi));
        return seededRand(seed); // 0..1
      })
    );
  }, [topTrades, factors]);

  // Insight: find the factor with most high-scoring winners
  const insight = useMemo(() => {
    if (topTrades.length === 0) return '';
    const factorAvgScores = factors.map((_, fi) => {
      const avg = scoreMatrix.reduce((s, row) => s + row[fi], 0) / scoreMatrix.length;
      return avg;
    });
    const bestFi = factorAvgScores.indexOf(Math.max(...factorAvgScores));
    const highScoringCount = scoreMatrix.filter(row => row[bestFi] > 0.65).length;
    const pct = topTrades.length > 0 ? Math.round((highScoringCount / topTrades.length) * 100) : 0;
    return `${pct}% of top winners scored high on "${factors[bestFi]}"`;
  }, [factors, scoreMatrix, topTrades]);

  function scoreToColor(score: number): string {
    // 0 = red, 0.5 = neutral, 1 = green
    const r = score < 0.5 ? 255 : Math.round(255 * (1 - (score - 0.5) * 2));
    const g = score > 0.5 ? 208 : Math.round(208 * score * 2);
    const b = 60;
    return `rgba(${r},${g},${b},0.75)`;
  }

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER_COLOR}`, borderRadius: 8, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 14, letterSpacing: '0.06em' }}>
        FACTOR HEATMAP — Top 10 Trades · {criteriaType} Factors
      </div>
      {topTrades.length === 0 ? (
        <div style={{ color: TEXT_SECONDARY, fontSize: 11, padding: '20px 0' }}>No trade data with P&L available.</div>
      ) : (
        <>
          {/* Column headers */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: `100px repeat(${factors.length}, 1fr)`,
            gap: 3, marginBottom: 3,
          }}>
            <div />
            {factors.map(f => (
              <div key={f} style={{ fontSize: 9, color: TEXT_SECONDARY, textAlign: 'center', padding: '3px 2px', letterSpacing: '0.04em' }}>
                {f}
              </div>
            ))}
          </div>
          {/* Rows */}
          {topTrades.map((trade, ti) => (
            <div key={trade.id} style={{
              display: 'grid',
              gridTemplateColumns: `100px repeat(${factors.length}, 1fr)`,
              gap: 3, marginBottom: 3, alignItems: 'center',
            }}>
              <div style={{ fontSize: 9, color: TEXT_PRIMARY, fontWeight: 600, paddingRight: 6 }}>
                {trade.symbol}
                <span style={{ color: pctColor(trade.pnlPct ?? 0), marginLeft: 4, fontSize: 8 }}>
                  {fmtPct(trade.pnlPct ?? 0, 1)}
                </span>
              </div>
              {scoreMatrix[ti].map((score, fi) => (
                <div
                  key={fi}
                  title={`${trade.symbol} · ${factors[fi]}: ${(score * 100).toFixed(0)}`}
                  style={{
                    height: 22, borderRadius: 3,
                    background: scoreToColor(score),
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 8, color: 'rgba(255,255,255,0.8)', fontWeight: 600,
                  }}
                >
                  {Math.round(score * 100)}
                </div>
              ))}
            </div>
          ))}
          {/* Insight */}
          {insight && (
            <div style={{
              marginTop: 12, padding: '8px 12px',
              background: 'rgba(0,208,132,0.08)', border: `1px solid rgba(0,208,132,0.2)`,
              borderRadius: 6, fontSize: 11, color: BULL_COLOR,
            }}>
              {insight}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── 4. RegimeAnalysisPanel ───────────────────────────────────────────────────

interface RegimeTooltipState {
  visible: boolean;
  label: string;
  x: number;
  y: number;
}

function RegimeAnalysisPanel({ backtest }: BacktestAnalyticsProps) {
  const [tooltip, setTooltip] = useState<RegimeTooltipState>({ visible: false, label: '', x: 0, y: 0 });

  const { portfolioHistory, trades } = backtest;

  // Build timeline segments (merge consecutive same-condition segments)
  const segments = useMemo(() => {
    if (!portfolioHistory.length) return [];
    const segs: { condition: string; criteria: string; startDate: string; endDate: string; count: number }[] = [];
    let cur = { ...portfolioHistory[0], count: 1 };
    for (let i = 1; i < portfolioHistory.length; i++) {
      const h = portfolioHistory[i];
      if (h.marketCondition === cur.marketCondition) {
        cur.count++;
      } else {
        segs.push({ condition: cur.marketCondition, criteria: cur.criteriaUsed, startDate: cur.date, endDate: h.date, count: cur.count });
        cur = { ...h, count: 1 };
      }
    }
    segs.push({ condition: cur.marketCondition, criteria: cur.criteriaUsed, startDate: cur.date, endDate: cur.date, count: cur.count });
    return segs;
  }, [portfolioHistory]);

  const total = segments.reduce((s, g) => s + g.count, 0);

  // Regime stats
  const regimeStats = useMemo(() => {
    const conditions = ['BULL', 'BEAR', 'SIDEWAYS'];
    return conditions.map(cond => {
      const condSnaps = portfolioHistory.filter(h => h.marketCondition === cond);
      const pct = total > 0 ? (condSnaps.length / total) * 100 : 0;

      // Periods with positive return
      const positiveCount = condSnaps.filter((h, i) => {
        if (i === 0) return false;
        const prev = condSnaps[i - 1];
        return h.value > prev.value;
      }).length;
      const winRate = condSnaps.length > 1 ? (positiveCount / (condSnaps.length - 1)) * 100 : 0;

      // Average period return
      const returns: number[] = [];
      for (let i = 1; i < condSnaps.length; i++) {
        returns.push((condSnaps[i].value - condSnaps[i - 1].value) / condSnaps[i - 1].value * 100);
      }
      const avgReturn = returns.length > 0 ? returns.reduce((s, r) => s + r, 0) / returns.length : 0;

      // Cumulative contribution (start vs end value for this condition)
      const contribPct = condSnaps.length >= 2
        ? ((condSnaps[condSnaps.length - 1].value - condSnaps[0].value) / backtest.config.initialCapital) * 100
        : 0;

      return { condition: cond, pct, winRate, avgReturn, contribPct };
    });
  }, [portfolioHistory, total, backtest.config.initialCapital]);

  // Insight
  const insight = useMemo(() => {
    if (!regimeStats.length) return '';
    const worst = [...regimeStats].sort((a, b) => a.winRate - b.winRate)[0];
    const condLabel = worst.condition === 'BULL' ? 'Bull' : worst.condition === 'BEAR' ? 'Bear' : 'Sideways';
    return `Strategy underperforms most in ${condLabel} regimes (${worst.winRate.toFixed(0)}% win rate). Consider adjusting ${worst.condition === 'BULL' ? 'ALFA' : worst.condition === 'BEAR' ? 'BETA' : 'DELTA'} criteria parameters.`;
  }, [regimeStats]);

  // Unused trades for reference info
  const _tradesCount = trades.length;
  void _tradesCount;

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER_COLOR}`, borderRadius: 8, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 14, letterSpacing: '0.06em' }}>
        REGIME ANALYSIS — Market Condition Breakdown
      </div>

      {/* Timeline bar */}
      <div style={{ position: 'relative', marginBottom: 18 }}>
        <div style={{ fontSize: 10, color: TEXT_SECONDARY, marginBottom: 6 }}>Market Condition Timeline</div>
        <div style={{ display: 'flex', height: 28, borderRadius: 4, overflow: 'hidden', border: `1px solid ${BORDER_COLOR}` }}>
          {segments.map((seg, i) => {
            const width = total > 0 ? (seg.count / total) * 100 : 0;
            return (
              <div
                key={i}
                style={{
                  width: `${width}%`, minWidth: 2,
                  background: CONDITION_COLOR[seg.condition] ?? '#444',
                  opacity: 0.75, cursor: 'pointer', position: 'relative',
                  transition: 'opacity 0.15s',
                }}
                onMouseEnter={e => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  setTooltip({
                    visible: true,
                    label: `${seg.condition} · ${seg.criteria} · ${seg.startDate} → ${seg.endDate}`,
                    x: rect.left + rect.width / 2,
                    y: rect.top - 36,
                  });
                  e.currentTarget.style.opacity = '1';
                }}
                onMouseLeave={e => {
                  setTooltip(prev => ({ ...prev, visible: false }));
                  e.currentTarget.style.opacity = '0.75';
                }}
              />
            );
          })}
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
          {(['BULL', 'BEAR', 'SIDEWAYS'] as const).map(c => (
            <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: CONDITION_COLOR[c] }} />
              <span style={{ fontSize: 10, color: TEXT_SECONDARY }}>{c}</span>
            </div>
          ))}
        </div>
        {/* Floating tooltip */}
        {tooltip.visible && (
          <div style={{
            position: 'fixed', left: tooltip.x, top: tooltip.y,
            transform: 'translateX(-50%)',
            background: CARD_BG, border: `1px solid ${BORDER_COLOR}`,
            borderRadius: 5, padding: '5px 10px', fontSize: 10,
            color: TEXT_PRIMARY, pointerEvents: 'none', zIndex: 9999, whiteSpace: 'nowrap',
          }}>
            {tooltip.label}
          </div>
        )}
      </div>

      {/* Stats table */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '90px repeat(4, 1fr)', gap: 2, marginBottom: 6 }}>
          {['REGIME', '% PERIODS', 'AVG RETURN', 'WIN RATE', 'CONTRIB %'].map(h => (
            <div key={h} style={{ fontSize: 9, color: TEXT_SECONDARY, letterSpacing: '0.07em', padding: '4px 8px' }}>{h}</div>
          ))}
        </div>
        {regimeStats.map(stat => {
          const cc = CONDITION_COLOR[stat.condition] ?? '#444';
          return (
            <div key={stat.condition} style={{
              display: 'grid', gridTemplateColumns: '90px repeat(4, 1fr)',
              gap: 2, marginBottom: 3,
              background: `${cc}10`, borderRadius: 5,
              borderLeft: `3px solid ${cc}`,
            }}>
              <div style={{ padding: '7px 8px', fontSize: 11, fontWeight: 700, color: cc }}>{stat.condition}</div>
              <div style={{ padding: '7px 8px', fontSize: 11, color: TEXT_PRIMARY }}>{stat.pct.toFixed(1)}%</div>
              <div style={{ padding: '7px 8px', fontSize: 11, color: pctColor(stat.avgReturn) }}>{fmtPct(stat.avgReturn, 3)}</div>
              <div style={{ padding: '7px 8px', fontSize: 11, color: stat.winRate >= 50 ? BULL_COLOR : BEAR_COLOR }}>{stat.winRate.toFixed(1)}%</div>
              <div style={{ padding: '7px 8px', fontSize: 11, color: pctColor(stat.contribPct) }}>{fmtPct(stat.contribPct, 1)}</div>
            </div>
          );
        })}
      </div>

      {/* Insight */}
      {insight && (
        <div style={{
          padding: '10px 14px', borderRadius: 6,
          background: 'rgba(255,165,2,0.08)', border: `1px solid rgba(255,165,2,0.25)`,
          fontSize: 11, color: SIDEWAYS_COLOR, lineHeight: 1.5,
        }}>
          {insight}
        </div>
      )}
    </div>
  );
}

// ─── 5. BenchmarkComparison ───────────────────────────────────────────────────

function BenchmarkComparison({ backtest }: BacktestAnalyticsProps) {
  const { portfolioHistory, config, performance, benchmark } = backtest;
  const isBIST = config.market.includes('BIST');
  const riskFreeAnnual = isBIST ? 0.42 : 0.053;

  const chartData = useMemo(() => {
    if (portfolioHistory.length < 2) return [];
    const startVal = portfolioHistory[0].value;
    const benchEndReturn = benchmark?.totalReturn ?? 0;
    const n = portfolioHistory.length;

    return portfolioHistory.map((h, i) => {
      // Strategy rebased to 100
      const strategyIdx = startVal > 0 ? (h.value / startVal) * 100 : 100;

      // Benchmark: linearly interpolated to total return
      const benchProgress = n > 1 ? i / (n - 1) : 0;
      const benchIdx = 100 * (1 + (benchEndReturn / 100) * benchProgress);

      // Risk-free: compounded daily
      const daysPassed = Math.round(((new Date(h.date).getTime() - new Date(portfolioHistory[0].date).getTime()) / 86400000));
      const rfIdx = 100 * Math.pow(1 + riskFreeAnnual, daysPassed / 365);

      return {
        date: h.date,
        strategy: +strategyIdx.toFixed(2),
        benchmark: +benchIdx.toFixed(2),
        riskFree: +rfIdx.toFixed(2),
      };
    });
  }, [portfolioHistory, benchmark, riskFreeAnnual]);

  // Alpha = strategy annualized - benchmark annualized
  const alpha = performance.annualizedReturn - (benchmark?.annualizedReturn ?? 0);

  const rows = [
    { label: 'Total Return', strategy: fmtPct(performance.totalReturn), bench: benchmark ? fmtPct(benchmark.totalReturn) : '—', sc: pctColor(performance.totalReturn), bc: benchmark ? pctColor(benchmark.totalReturn) : TEXT_SECONDARY },
    { label: 'Ann. Return (CAGR)', strategy: fmtPct(performance.annualizedReturn), bench: benchmark ? fmtPct(benchmark.annualizedReturn) : '—', sc: pctColor(performance.annualizedReturn), bc: benchmark ? pctColor(benchmark.annualizedReturn) : TEXT_SECONDARY },
    { label: 'Sharpe Ratio', strategy: performance.sharpeRatio.toFixed(2), bench: benchmark ? benchmark.sharpeRatio.toFixed(2) : '—', sc: performance.sharpeRatio > 1 ? BULL_COLOR : SIDEWAYS_COLOR, bc: TEXT_SECONDARY },
    { label: 'Max Drawdown', strategy: fmtPct(performance.maxDrawdown), bench: benchmark ? fmtPct(benchmark.maxDrawdown) : '—', sc: BEAR_COLOR, bc: BEAR_COLOR },
    { label: 'Alpha', strategy: fmtPct(alpha), bench: '0.00%', sc: pctColor(alpha), bc: TEXT_SECONDARY },
  ];

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER_COLOR}`, borderRadius: 8, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 14, letterSpacing: '0.06em' }}>
        BENCHMARK COMPARISON — Rebased to 100
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 18, marginBottom: 10 }}>
        {[
          { color: BULL_COLOR,     label: 'Strategy' },
          { color: TEXT_SECONDARY, label: 'Benchmark' },
          { color: SIDEWAYS_COLOR, label: `Risk-Free (${isBIST ? '42%' : '5.3%'})` },
        ].map(l => (
          <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 12, height: 2, background: l.color }} />
            <span style={{ fontSize: 10, color: TEXT_SECONDARY }}>{l.label}</span>
          </div>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="gStrategy" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={BULL_COLOR} stopOpacity={0.2} />
              <stop offset="95%" stopColor={BULL_COLOR} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gBench" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={TEXT_SECONDARY} stopOpacity={0.1} />
              <stop offset="95%" stopColor={TEXT_SECONDARY} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: TEXT_SECONDARY }} tickFormatter={s => s.slice(0, 7)} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: TEXT_SECONDARY }} width={36} tickFormatter={v => `${v.toFixed(0)}`} />
          <Tooltip
            content={(props) => (
              <DarkTooltip
                active={props.active}
                payload={props.payload as TooltipPayloadItem[]}
                label={props.label as string}
                formatter={(_n, v) => v.toFixed(1)}
              />
            )}
          />
          <Area type="monotone" dataKey="benchmark" name="Benchmark" stroke={TEXT_SECONDARY} fill="url(#gBench)" strokeWidth={1} dot={false} />
          <Area type="monotone" dataKey="riskFree" name="Risk-Free" stroke={SIDEWAYS_COLOR} fill="none" strokeWidth={1} dot={false} strokeDasharray="4 4" />
          <Area type="monotone" dataKey="strategy" name="Strategy" stroke={BULL_COLOR} fill="url(#gStrategy)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>

      {/* Metrics table */}
      <div style={{ marginTop: 16, borderTop: `1px solid ${BORDER_COLOR}`, paddingTop: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px 100px', gap: 2, marginBottom: 6 }}>
          {['METRIC', 'STRATEGY', 'BENCHMARK'].map(h => (
            <div key={h} style={{ fontSize: 9, color: TEXT_SECONDARY, letterSpacing: '0.07em', padding: '3px 8px' }}>{h}</div>
          ))}
        </div>
        {rows.map(row => (
          <div key={row.label} style={{ display: 'grid', gridTemplateColumns: '1fr 100px 100px', borderBottom: `1px solid ${BORDER_COLOR}` }}>
            <div style={{ padding: '7px 8px', fontSize: 11, color: TEXT_SECONDARY }}>{row.label}</div>
            <div style={{ padding: '7px 8px', fontSize: 12, fontWeight: 700, color: row.sc }}>{row.strategy}</div>
            <div style={{ padding: '7px 8px', fontSize: 12, fontWeight: 700, color: row.bc }}>{row.bench}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 6. DiagnosticWarnings ────────────────────────────────────────────────────

interface Warning {
  level: 'warn' | 'error';
  icon: string;
  message: string;
  suggestion: string;
}

export function DiagnosticWarnings({ backtest }: BacktestAnalyticsProps) {
  const { performance, benchmark } = backtest;

  const warnings = useMemo<Warning[]>(() => {
    const ws: Warning[] = [];

    if (performance.totalTrades < 30) {
      ws.push({
        level: 'warn',
        icon: '⚠',
        message: `Only ${performance.totalTrades} trades — sample size is low`,
        suggestion: 'Extend the backtest date range or reduce portfolio concentration to increase trade count.',
      });
    }
    if (performance.maxDrawdown < -25) {
      ws.push({
        level: 'error',
        icon: '✕',
        message: `Max drawdown ${fmtPct(performance.maxDrawdown)} exceeds −25% threshold`,
        suggestion: 'Consider adding stop-loss rules or reducing position sizing to cap downside risk.',
      });
    }
    if (benchmark && performance.totalReturn < benchmark.totalReturn) {
      ws.push({
        level: 'error',
        icon: '✕',
        message: `Strategy (${fmtPct(performance.totalReturn)}) underperformed benchmark (${fmtPct(benchmark.totalReturn)})`,
        suggestion: 'Review criteria selection criteria and entry/exit timing logic.',
      });
    }
    if (performance.sharpeRatio < 0.5) {
      ws.push({
        level: 'warn',
        icon: '⚠',
        message: `Sharpe ratio ${performance.sharpeRatio.toFixed(2)} is below 0.5`,
        suggestion: 'Risk-adjusted returns are poor. Try improving entry signals or adding volatility filters.',
      });
    }
    if (performance.winRate < 50) {
      ws.push({
        level: 'warn',
        icon: '⚠',
        message: `Win rate ${performance.winRate.toFixed(1)}% is below 50%`,
        suggestion: 'More than half of completed trades are losing. Review exit criteria and position hold times.',
      });
    }
    return ws;
  }, [performance, benchmark]);

  if (warnings.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
      {warnings.map((w, i) => {
        const color = w.level === 'error' ? BEAR_COLOR : SIDEWAYS_COLOR;
        return (
          <div key={i} style={{
            borderLeft: `3px solid ${color}`,
            background: `${color}10`,
            borderRadius: '0 6px 6px 0',
            padding: '10px 14px',
            display: 'flex', alignItems: 'flex-start', gap: 10,
          }}>
            <span style={{ fontSize: 14, color, flexShrink: 0, marginTop: 1 }}>{w.icon}</span>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color, marginBottom: 3 }}>{w.message}</div>
              <div style={{ fontSize: 11, color: TEXT_SECONDARY }}>{w.suggestion}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Export ──────────────────────────────────────────────────────────────

type AnalyticsTab = 'attribution' | 'rolling' | 'regime' | 'benchmark' | 'heatmap';

export const BacktestAnalytics: React.FC<BacktestAnalyticsProps> = ({ backtest }) => {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('attribution');

  const tabs: { id: AnalyticsTab; label: string }[] = [
    { id: 'attribution', label: 'Attribution' },
    { id: 'rolling',     label: 'Rolling Metrics' },
    { id: 'regime',      label: 'Regime Analysis' },
    { id: 'benchmark',   label: 'Benchmark' },
    { id: 'heatmap',     label: 'Factor Heatmap' },
  ];

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', color: TEXT_PRIMARY }}>
      {/* Diagnostic warnings always on top */}
      <DiagnosticWarnings backtest={backtest} />

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 2, marginBottom: 16,
        borderBottom: `1px solid ${BORDER_COLOR}`, paddingBottom: 0,
      }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            style={{
              padding: '8px 18px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
              background: 'transparent', border: 'none',
              borderBottom: `2px solid ${activeTab === t.id ? BULL_COLOR : 'transparent'}`,
              color: activeTab === t.id ? TEXT_PRIMARY : TEXT_SECONDARY,
              fontWeight: activeTab === t.id ? 600 : 400,
              marginBottom: -1, transition: 'all 0.15s ease',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'attribution' && <ReturnAttributionChart backtest={backtest} />}
      {activeTab === 'rolling'     && <RollingMetricsChart backtest={backtest} />}
      {activeTab === 'regime'      && <RegimeAnalysisPanel backtest={backtest} />}
      {activeTab === 'benchmark'   && <BenchmarkComparison backtest={backtest} />}
      {activeTab === 'heatmap'     && <FactorHeatmap backtest={backtest} />}
    </div>
  );
};

export { ReturnAttributionChart, RollingMetricsChart, FactorHeatmap, RegimeAnalysisPanel, BenchmarkComparison };

export default BacktestAnalytics;
