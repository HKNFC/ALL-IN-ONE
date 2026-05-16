import { useAppStore } from '../stores/appStore';
import { formatCurrency, formatPercent } from '../utils';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { generateEquityCurve } from '../utils';
import { TrendingUp, Plus, Trash2, DollarSign, BarChart2, Percent } from 'lucide-react';

const COLORS = ['#00D084', '#409CFF', '#FFC700', '#FF4757', '#B45FFF', '#FF8C42'];

const PERFORMANCE_DATA = generateEquityCurve(90);

export default function Portfolio() {
  const { portfolio } = useAppStore();

  const totalValue  = portfolio.reduce((s, p) => s + p.value, 0);
  const totalCost   = portfolio.reduce((s, p) => s + p.shares * p.avgCost, 0);
  const totalPnL    = portfolio.reduce((s, p) => s + p.pnl, 0);
  const totalPnLPct = (totalPnL / totalCost) * 100;

  const pieData = portfolio.map(p => ({ name: p.symbol, value: p.value }));

  return (
    <div className="p-4 h-full flex flex-col gap-4 min-h-0" style={{ overflow: 'auto' }}>

      {/* Header stats */}
      <div className="grid grid-cols-4 gap-3 fade-in">
        {[
          { icon: DollarSign, label: 'TOTAL VALUE',   value: formatCurrency(totalValue),       color: 'var(--accent)', up: true },
          { icon: TrendingUp, label: 'TOTAL P&L',     value: formatCurrency(totalPnL),          color: totalPnL >= 0 ? 'var(--accent)' : 'var(--red)', up: totalPnL >= 0 },
          { icon: Percent,    label: 'RETURN %',      value: formatPercent(totalPnLPct),        color: totalPnLPct >= 0 ? 'var(--accent)' : 'var(--red)', up: totalPnLPct >= 0 },
          { icon: BarChart2,  label: 'POSITIONS',     value: String(portfolio.length),           color: 'var(--blue)', up: true },
        ].map(({ icon: Icon, label, value, color }, i) => (
          <div key={label} className={`card p-4 fade-in-d${i + 1}`}>
            <div className="flex items-center gap-2 mb-3">
              <Icon size={13} style={{ color: 'var(--accent)' }} />
              <span style={{ color: 'var(--text-3)', fontSize: 10, fontWeight: 600, letterSpacing: '0.08em' }}>{label}</span>
            </div>
            <div style={{ color, fontSize: 20, fontWeight: 700 }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-3 flex-1 min-h-0">

        {/* Left: Allocation pie */}
        <div className="card flex flex-col fade-in-d2" style={{ width: 300, minWidth: 300 }}>
          <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>ALLOCATION</span>
          </div>
          <div style={{ padding: '12px 0', height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%" cy="50%"
                  innerRadius={55} outerRadius={90}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="var(--surface)" strokeWidth={2} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--surface-el)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11, fontFamily: 'inherit' }}
                  formatter={(v: any) => [formatCurrency(v), '']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Legend */}
          <div className="px-4 pb-4 flex flex-col gap-2">
            {portfolio.map((p, i) => (
              <div key={p.id} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: COLORS[i % COLORS.length] }} />
                  <span style={{ color: 'var(--text-2)', fontSize: 11 }}>{p.symbol}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{p.weight}%</span>
                  <span style={{ color: formatCurrency(p.value).startsWith('-') ? 'var(--red)' : 'var(--text-2)', fontSize: 11 }}>{formatCurrency(p.value)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Center: Positions table */}
        <div className="card flex-1 flex flex-col min-w-0 fade-in-d3">
          <div className="px-4 py-3 flex items-center gap-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>POSITIONS</span>
            <button className="btn-accent flex items-center gap-1 ml-auto" style={{ padding: '5px 12px', fontSize: 11 }}>
              <Plus size={11} /> ADD POSITION
            </button>
          </div>

          <div style={{ overflowY: 'auto', flex: 1 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0 }}>
                <tr style={{ background: 'var(--surface-el)' }}>
                  {['SYMBOL', 'SHARES', 'AVG COST', 'CURR PRICE', 'VALUE', 'P&L', 'P&L %', 'WEIGHT', ''].map(h => (
                    <th key={h} style={{ padding: '8px 14px', color: 'var(--text-3)', fontSize: 10, fontWeight: 600, textAlign: 'left', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {portfolio.map((pos, i) => (
                  <tr
                    key={pos.id}
                    style={{ borderBottom: '1px solid rgba(30,34,52,0.5)', animation: `fadeInUp 0.3s ease-out ${i * 0.05}s both` }}
                  >
                    <td style={{ padding: '12px 14px' }}>
                      <div>
                        <div style={{ color: 'var(--text)', fontSize: 12, fontWeight: 700 }}>{pos.symbol}</div>
                        <div style={{ color: 'var(--text-3)', fontSize: 10 }}>{pos.name}</div>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)', fontSize: 12 }}>{pos.shares}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)', fontSize: 12 }}>${pos.avgCost.toFixed(2)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>${pos.currentPrice.toFixed(2)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>{formatCurrency(pos.value)}</td>
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{ color: pos.pnl >= 0 ? 'var(--accent)' : 'var(--red)', fontSize: 12, fontWeight: 700 }}>
                        {pos.pnl >= 0 ? '+' : ''}{formatCurrency(pos.pnl)}
                      </span>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <span className={pos.pnlPct >= 0 ? 'tag-up' : 'tag-down'}>
                        {formatPercent(pos.pnlPct)}
                      </span>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <div className="flex items-center gap-2">
                        <div style={{ width: 60, height: 4, background: 'var(--border)', borderRadius: 2 }}>
                          <div style={{ width: `${pos.weight}%`, height: '100%', background: 'var(--accent)', borderRadius: 2, opacity: 0.7 }} />
                        </div>
                        <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{pos.weight}%</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', lineHeight: 0 }}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: Performance chart */}
        <div className="card flex flex-col fade-in-d4" style={{ width: 260, minWidth: 260 }}>
          <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>90D PERFORMANCE</span>
          </div>
          <div style={{ padding: '12px 0', height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={PERFORMANCE_DATA} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <defs>
                  <linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#00D084" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#00D084" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,52,0.8)" />
                <XAxis dataKey="date" tick={{ fontSize: 8, fill: '#414860' }} tickLine={false} axisLine={false} interval={20} />
                <YAxis tick={{ fontSize: 8, fill: '#414860' }} tickLine={false} axisLine={false} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ background: 'var(--surface-el)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 10, fontFamily: 'inherit' }}
                  formatter={(v: any) => [formatCurrency(v), 'Value']}
                />
                <Area type="monotone" dataKey="value" stroke="#00D084" strokeWidth={1.5} fill="url(#perfGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Risk metrics */}
          <div className="px-4 flex-1 flex flex-col gap-3 pb-4">
            <div style={{ color: 'var(--text-3)', fontSize: 10, fontWeight: 600, letterSpacing: '0.06em' }}>RISK METRICS</div>
            {[
              { label: 'Beta',        value: '1.24',  color: 'var(--text)' },
              { label: 'Volatility',  value: '18.4%', color: 'var(--yellow)' },
              { label: 'Sharpe',      value: '1.65',  color: 'var(--accent)' },
              { label: 'Max DD',      value: '-12.3%', color: 'var(--red)' },
              { label: 'Win Rate',    value: '62.5%', color: 'var(--accent)' },
            ].map(m => (
              <div key={m.label} className="flex items-center justify-between">
                <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{m.label}</span>
                <span style={{ color: m.color, fontSize: 12, fontWeight: 600 }}>{m.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
