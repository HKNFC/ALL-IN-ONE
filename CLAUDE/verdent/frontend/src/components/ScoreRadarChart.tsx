/**
 * ScoreRadarChart — 6-axis radar showing stock signal breakdown.
 * Axes: Trend, Momentum, Volume, Volatility, Fundamental, Relative Strength
 */
import { useMemo } from 'react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';

interface SignalScores {
  trend?:           number;  // 0–100
  momentum?:        number;
  volume?:          number;
  volatility?:      number;
  fundamental?:     number;
  relativeStrength?: number;
}

interface Props {
  symbol:  string;
  scores:  SignalScores;
  score:   number;   // overall 0–100
  size?:   number;
}

const AXES = [
  { key: 'trend',           label: 'Trend'        },
  { key: 'momentum',        label: 'Momentum'     },
  { key: 'volume',          label: 'Hacim'        },
  { key: 'volatility',      label: 'Volatilite'   },
  { key: 'fundamental',     label: 'Temel'        },
  { key: 'relativeStrength',label: 'Rel. Güç'     },
] as const;

function scoreColor(s: number): string {
  if (s >= 70) return '#00D084';
  if (s >= 45) return '#FFC700';
  return '#FF4757';
}

export function ScoreRadarChart({ symbol, scores, score, size = 220 }: Props) {
  const data = useMemo(() =>
    AXES.map(({ key, label }) => ({
      axis:  label,
      value: scores[key] ?? 50,
    })),
    [scores],
  );

  const color = scoreColor(score);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      {/* Score badge */}
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 11, color: 'var(--text-3)', letterSpacing: '0.08em' }}>{symbol}</div>
        <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1.1 }}>{score}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>/ 100</div>
      </div>

      <ResponsiveContainer width={size} height={size}>
        <RadarChart data={data} margin={{ top: 8, right: 20, bottom: 8, left: 20 }}>
          <PolarGrid stroke="rgba(255,255,255,0.07)" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'inherit' }}
          />
          <PolarRadiusAxis
            angle={90} domain={[0, 100]}
            tick={false} axisLine={false}
            tickCount={5}
          />
          <Radar
            dataKey="value"
            stroke={color}
            fill={color}
            fillOpacity={0.18}
            strokeWidth={1.5}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--surface-el)', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 11, fontFamily: 'inherit',
            }}
            labelStyle={{ color: 'var(--text-2)' }}
            formatter={(v: number) => [`${v.toFixed(0)} / 100`, '']}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
