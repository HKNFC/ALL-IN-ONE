'use client';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

interface Props { data: number[]; color?: string; height?: number; }

export function MiniSparkline({ data, color = '#00D084', height = 32 }: Props) {
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
