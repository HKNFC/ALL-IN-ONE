/**
 * MarketConditionHistory — timeline chart showing BULL/BEAR/SIDEWAYS periods
 * with color-coded background bands on a price series.
 */
import { useMemo } from 'react';
import {
  ComposedChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceArea, CartesianGrid,
} from 'recharts';

export type MarketState = 'BULL' | 'BEAR' | 'SIDEWAYS';

export interface ConditionPoint {
  date:      string;       // YYYY-MM-DD
  condition: MarketState;
  score:     number;
}

export interface PricePoint {
  date:  string;
  close: number;
}

interface Props {
  prices:     PricePoint[];
  conditions: ConditionPoint[];
  height?:    number;
}

const COND_COLOR: Record<MarketState, string> = {
  BULL:     'rgba(0,208,132,0.10)',
  BEAR:     'rgba(255,71,87,0.10)',
  SIDEWAYS: 'rgba(255,165,2,0.08)',
};

const COND_STROKE: Record<MarketState, string> = {
  BULL:     '#00D084',
  BEAR:     '#FF4757',
  SIDEWAYS: '#FFA502',
};

interface Band { start: string; end: string; condition: MarketState }

function buildBands(conditions: ConditionPoint[]): Band[] {
  if (conditions.length === 0) return [];
  const bands: Band[] = [];
  let cur: Band = { start: conditions[0].date, end: conditions[0].date, condition: conditions[0].condition };
  for (let i = 1; i < conditions.length; i++) {
    if (conditions[i].condition === cur.condition) {
      cur.end = conditions[i].date;
    } else {
      bands.push({ ...cur });
      cur = { start: conditions[i].date, end: conditions[i].date, condition: conditions[i].condition };
    }
  }
  bands.push(cur);
  return bands;
}

function fmtDate(d: string) { return d.slice(2, 7); }

export function MarketConditionHistory({ prices, conditions, height = 260 }: Props) {
  const bands = useMemo(() => buildBands(conditions), [conditions]);

  // Merge price + condition score onto same timeline
  const data = useMemo(() => {
    const condMap = new Map(conditions.map(c => [c.date, c]));
    return prices.map(p => ({
      date:  p.date,
      close: p.close,
      score: condMap.get(p.date)?.score ?? null,
      cond:  condMap.get(p.date)?.condition ?? null,
    }));
  }, [prices, conditions]);

  const domain = useMemo(() => {
    const vals = prices.map(p => p.close);
    const min  = Math.min(...vals);
    const max  = Math.max(...vals);
    const pad  = (max - min) * 0.05;
    return [min - pad, max + pad];
  }, [prices]);

  // Legend summary
  const summary = useMemo(() => {
    const count: Record<MarketState, number> = { BULL: 0, BEAR: 0, SIDEWAYS: 0 };
    conditions.forEach(c => { count[c.condition] = (count[c.condition] || 0) + 1; });
    const total = conditions.length || 1;
    return Object.entries(count).map(([k, v]) => ({ condition: k as MarketState, pct: (v / total * 100).toFixed(0) }));
  }, [conditions]);

  if (prices.length === 0) {
    return <div style={{ color: 'var(--text-3)', fontSize: 12, padding: 16 }}>Veri yükleniyor...</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {summary.map(({ condition, pct }) => (
          <div key={condition} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10 }}>
            <span style={{
              width: 10, height: 10, borderRadius: 2,
              background: COND_COLOR[condition], border: `1px solid ${COND_STROKE[condition]}`,
              display: 'inline-block',
            }} />
            <span style={{ color: COND_STROKE[condition], fontWeight: 600 }}>{condition}</span>
            <span style={{ color: 'var(--text-3)' }}>{pct}%</span>
          </div>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />

          {/* Condition background bands */}
          {bands.map((b, i) => (
            <ReferenceArea
              key={i}
              x1={b.start} x2={b.end}
              fill={COND_COLOR[b.condition]}
              strokeOpacity={0}
            />
          ))}

          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: 'var(--text-3)' }}
            tickFormatter={fmtDate}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 9, fill: 'var(--text-3)' }}
            domain={domain}
            tickFormatter={v => v.toFixed(0)}
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--surface-el)', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 11, fontFamily: 'inherit',
            }}
            formatter={(v: number, key: string) => {
              if (key === 'close') return [v.toFixed(2), 'Fiyat'];
              return [v, key];
            }}
            labelFormatter={l => String(l)}
          />
          <Area
            dataKey="close"
            stroke="#409CFF"
            fill="rgba(64,156,255,0.06)"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Period list */}
      {bands.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {bands.map((b, i) => (
            <div key={i} style={{
              fontSize: 9, padding: '2px 7px', borderRadius: 4,
              background: COND_COLOR[b.condition], border: `1px solid ${COND_STROKE[b.condition]}30`,
              color: COND_STROKE[b.condition],
            }}>
              {b.start.slice(0,7)} → {b.end.slice(0,7)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
