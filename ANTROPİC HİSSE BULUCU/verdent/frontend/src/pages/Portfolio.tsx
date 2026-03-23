import { useState, useMemo } from 'react'
import { Plus, TrendingUp, TrendingDown, DollarSign, PieChart, X, ShieldAlert, AlertTriangle } from 'lucide-react'
import {
  PieChart as RPieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'

const COLORS = ['#00D084', '#4D9FFF', '#F5A623', '#FF4D4D', '#9B59B6', '#1ABC9C', '#E67E22']

const initialPositions = [
  { id: '1', symbol: 'AAPL', name: 'Apple Inc.', shares: 50, avgPrice: 165.20, currentPrice: 189.45, sector: 'Technology' },
  { id: '2', symbol: 'NVDA', name: 'NVIDIA', shares: 15, avgPrice: 480.00, currentPrice: 875.32, sector: 'Technology' },
  { id: '3', symbol: 'MSFT', name: 'Microsoft', shares: 30, avgPrice: 380.00, currentPrice: 412.88, sector: 'Technology' },
  { id: '4', symbol: 'JPM', name: 'JPMorgan', shares: 40, avgPrice: 175.00, currentPrice: 196.45, sector: 'Finance' },
  { id: '5', symbol: 'AMZN', name: 'Amazon', shares: 25, avgPrice: 175.00, currentPrice: 187.63, sector: 'Consumer' },
  { id: '6', symbol: 'V', name: 'Visa', shares: 20, avgPrice: 250.00, currentPrice: 274.58, sector: 'Finance' },
]

const performanceHistory = [
  { month: 'Jul', value: 108000 }, { month: 'Aug', value: 104000 },
  { month: 'Sep', value: 115000 }, { month: 'Oct', value: 122000 },
  { month: 'Nov', value: 118000 }, { month: 'Dec', value: 131450 },
]

export default function Portfolio() {
  const [positions, setPositions] = useState(initialPositions)
  const [showAddModal, setShowAddModal] = useState(false)
  const [newPos, setNewPos] = useState({ symbol: '', shares: '', avgPrice: '', currentPrice: '' })

  const enriched = positions.map((p) => ({
    ...p,
    value: p.shares * p.currentPrice,
    pnl: p.shares * (p.currentPrice - p.avgPrice),
    pnlPct: ((p.currentPrice - p.avgPrice) / p.avgPrice) * 100,
  }))

  const totalValue = enriched.reduce((s, p) => s + p.value, 0)
  const totalCost = positions.reduce((s, p) => s + p.shares * p.avgPrice, 0)
  const totalPnl = totalValue - totalCost
  const totalPnlPct = (totalPnl / totalCost) * 100

  const sectorAlloc = Object.entries(
    enriched.reduce((acc, p) => {
      acc[p.sector] = (acc[p.sector] || 0) + p.value
      return acc
    }, {} as Record<string, number>)
  ).map(([name, value]) => ({ name, value: Math.round((value / totalValue) * 100) }))

  const removePosition = (id: string) => setPositions((prev) => prev.filter((p) => p.id !== id))

  const addPosition = () => {
    if (!newPos.symbol || !newPos.shares || !newPos.avgPrice || !newPos.currentPrice) return
    setPositions((prev) => [...prev, {
      id: Date.now().toString(),
      symbol: newPos.symbol.toUpperCase(),
      name: newPos.symbol.toUpperCase(),
      shares: parseFloat(newPos.shares),
      avgPrice: parseFloat(newPos.avgPrice),
      currentPrice: parseFloat(newPos.currentPrice),
      sector: 'Other',
    }])
    setNewPos({ symbol: '', shares: '', avgPrice: '', currentPrice: '' })
    setShowAddModal(false)
  }

  // Risk calculations
  const riskMetrics = useMemo(() => {
    const stopLossPct = 0.05 // assume 5% stop loss per position
    const positionsWithRisk = enriched.map((p) => ({
      ...p,
      stopLoss: p.currentPrice * (1 - stopLossPct),
      maxLoss:  p.value * stopLossPct,
      weight:   (p.value / totalValue) * 100,
    }))
    const totalMaxLoss = positionsWithRisk.reduce((s, p) => s + p.maxLoss, 0)
    const maxLossPct   = (totalMaxLoss / totalValue) * 100
    const topHeavy     = positionsWithRisk.some((p) => p.weight > 25)

    const radarData = [
      { metric: 'Diversification', value: Math.min(100, positions.length * 14) },
      { metric: 'Profitability',   value: Math.min(100, Math.max(0, 50 + totalPnlPct * 2)) },
      { metric: 'Risk Control',    value: Math.max(0, 100 - maxLossPct * 3) },
      { metric: 'Balance',         value: topHeavy ? 40 : 80 },
      { metric: 'Liquidity',       value: 75 },
      { metric: 'Momentum',        value: Math.min(100, Math.max(0, 50 + totalPnlPct)) },
    ]

    return { positionsWithRisk, totalMaxLoss, maxLossPct, topHeavy, radarData }
  }, [enriched, totalValue, positions.length, totalPnlPct])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>Portfolio</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--text-secondary)', fontSize: '14px' }}>
            Track and manage your investment positions
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowAddModal(true)} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Plus size={16} />
          Add Position
        </button>
      </div>

      {/* Summary Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
        <SummaryCard title="Total Value" value={`$${totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}`} icon={<DollarSign size={20} />} />
        <SummaryCard title="Total P&L" value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toLocaleString('en-US', { maximumFractionDigits: 0 })}`} positive={totalPnl >= 0} icon={totalPnl >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />} />
        <SummaryCard title="Return %" value={`${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(2)}%`} positive={totalPnlPct >= 0} icon={<TrendingUp size={20} />} />
        <SummaryCard title="Positions" value={positions.length.toString()} icon={<PieChart size={20} />} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '20px' }}>
        {/* Positions Table */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 600 }}>Open Positions</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr>
                {['Symbol', 'Shares', 'Avg Cost', 'Current', 'Value', 'P&L', 'P&L %', ''].map((h) => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 500, borderBottom: '1px solid var(--border)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {enriched.map((p) => (
                <tr key={p.id} style={{ borderBottom: '1px solid rgba(30,45,69,0.4)' }}>
                  <td style={{ padding: '12px 12px' }}>
                    <div style={{ fontWeight: 700, color: 'var(--primary)' }}>{p.symbol}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{p.name}</div>
                  </td>
                  <td style={{ padding: '12px 12px', color: 'var(--text-secondary)' }}>{p.shares}</td>
                  <td style={{ padding: '12px 12px', color: 'var(--text-secondary)' }}>${p.avgPrice.toFixed(2)}</td>
                  <td style={{ padding: '12px 12px', fontWeight: 600 }}>${p.currentPrice.toFixed(2)}</td>
                  <td style={{ padding: '12px 12px', fontWeight: 600 }}>${p.value.toLocaleString('en-US', { maximumFractionDigits: 0 })}</td>
                  <td style={{ padding: '12px 12px', color: p.pnl >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}
                  </td>
                  <td style={{ padding: '12px 12px' }}>
                    <span style={{ color: p.pnlPct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%
                    </span>
                  </td>
                  <td style={{ padding: '12px 12px' }}>
                    <button onClick={() => removePosition(p.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '4px' }}>
                      <X size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Allocation Chart */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 600 }}>Sector Allocation</h3>
          <ResponsiveContainer width="100%" height={200}>
            <RPieChart>
              <Pie data={sectorAlloc} cx="50%" cy="50%" innerRadius={55} outerRadius={80} dataKey="value" paddingAngle={3}>
                {sectorAlloc.map((_, idx) => (
                  <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
                formatter={(v) => [`${Number(v)}%`, '']}
              />
            </RPieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
            {sectorAlloc.map((s, idx) => (
              <div key={s.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: COLORS[idx % COLORS.length] }} />
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{s.name}</span>
                </div>
                <span style={{ fontSize: '12px', fontWeight: 600 }}>{s.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Performance Chart */}
      <div className="card" style={{ padding: '20px' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: 600 }}>Portfolio Value (6M)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={performanceHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,45,69,0.5)" />
            <XAxis dataKey="month" tick={{ fill: '#8A9BBE', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#8A9BBE', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px' }}
              formatter={(v) => [`$${Number(v).toLocaleString()}`, 'Value']}
            />
            <Line type="monotone" dataKey="value" stroke="#00D084" strokeWidth={2.5} dot={{ fill: '#00D084', r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Add Position Modal */}
      {/* ── Portfolio Risk Panel ──────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Risk Metrics */}
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <ShieldAlert size={18} color="var(--yellow)" />
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Portfolio Risk</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--bg-hover)', borderRadius: '10px', border: '1px solid var(--border)' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Max Loss (5% stop each)</span>
              <span style={{ fontWeight: 700, color: 'var(--red)' }}>-${riskMetrics.totalMaxLoss.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--bg-hover)', borderRadius: '10px', border: '1px solid var(--border)' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Max Loss %</span>
              <span style={{ fontWeight: 700, color: riskMetrics.maxLossPct > 10 ? 'var(--red)' : 'var(--yellow)' }}>-{riskMetrics.maxLossPct.toFixed(1)}%</span>
            </div>
            {riskMetrics.topHeavy && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', background: 'rgba(255,165,2,0.08)', borderRadius: '10px', border: '1px solid rgba(255,165,2,0.25)' }}>
                <AlertTriangle size={14} color="var(--yellow)" />
                <span style={{ fontSize: '12px', color: 'var(--yellow)' }}>One position exceeds 25% of portfolio — concentration risk</span>
              </div>
            )}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', marginTop: '4px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Symbol', 'Weight', 'Stop Loss', 'Max Loss'].map((h) => (
                    <th key={h} style={{ padding: '6px 8px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {riskMetrics.positionsWithRisk.map((p) => (
                  <tr key={p.id} style={{ borderBottom: '1px solid rgba(30,45,74,0.3)' }}>
                    <td style={{ padding: '7px 8px', fontWeight: 700 }}>{p.symbol}</td>
                    <td style={{ padding: '7px 8px', color: p.weight > 25 ? 'var(--yellow)' : 'var(--text-secondary)' }}>{p.weight.toFixed(1)}%</td>
                    <td style={{ padding: '7px 8px', color: 'var(--text-secondary)' }}>${p.stopLoss.toFixed(2)}</td>
                    <td style={{ padding: '7px 8px', color: 'var(--red)' }}>-${p.maxLoss.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Portfolio Health Radar */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 700 }}>Portfolio Health</h3>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={riskMetrics.radarData}>
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
              <Radar name="Portfolio" dataKey="value" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.15} strokeWidth={2} />
              <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Add Position Modal */}
      {showAddModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}>
          <div className="card" style={{ width: '400px', padding: '28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>Add Position</h3>
              <button onClick={() => setShowAddModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={20} /></button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {[
                { label: 'Symbol', key: 'symbol', placeholder: 'AAPL' },
                { label: 'Shares', key: 'shares', placeholder: '10' },
                { label: 'Avg Price ($)', key: 'avgPrice', placeholder: '150.00' },
                { label: 'Current Price ($)', key: 'currentPrice', placeholder: '189.45' },
              ].map(({ label, key, placeholder }) => (
                <div key={key}>
                  <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>{label}</label>
                  <input
                    value={newPos[key as keyof typeof newPos]}
                    onChange={(e) => setNewPos((prev) => ({ ...prev, [key]: e.target.value }))}
                    placeholder={placeholder}
                    style={{ width: '100%', padding: '10px 12px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text-primary)', fontSize: '14px', outline: 'none' }}
                  />
                </div>
              ))}
              <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
                <button className="btn-secondary" onClick={() => setShowAddModal(false)} style={{ flex: 1 }}>Cancel</button>
                <button className="btn-primary" onClick={addPosition} style={{ flex: 1 }}>Add Position</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SummaryCard({ title, value, icon, positive }: { title: string; value: string; icon: React.ReactNode; positive?: boolean }) {
  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{title}</span>
        <div style={{ padding: '6px', background: 'rgba(0,208,132,0.1)', borderRadius: '8px', color: 'var(--primary)' }}>{icon}</div>
      </div>
      <div style={{ fontSize: '22px', fontWeight: 700, color: positive === undefined ? 'var(--text-primary)' : positive ? 'var(--green)' : 'var(--red)' }}>{value}</div>
    </div>
  )
}
