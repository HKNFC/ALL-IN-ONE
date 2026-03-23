import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  FlaskConical,
  ScanSearch,
  Briefcase,
  TrendingUp,
  Bell,
  Settings,
  ChevronRight,
} from 'lucide-react'
import { useMarketStore } from '../stores/marketStore'

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/backtest', label: 'Backtest', icon: FlaskConical },
  { path: '/scanner', label: 'Scanner', icon: ScanSearch },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase },
]

export function Layout() {
  const location = useLocation()
  const { marketStatus } = useMarketStore()

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)' }}>
      {/* Sidebar */}
      <aside style={{
        width: '240px',
        minWidth: '240px',
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        position: 'fixed',
        top: 0,
        left: 0,
        bottom: 0,
        zIndex: 50,
      }}>
        {/* Logo */}
        <div style={{ padding: '24px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '36px',
              height: '36px',
              background: 'linear-gradient(135deg, #00D084, #00A86B)',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <TrendingUp size={20} color="#000" />
            </div>
            <div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '1px' }}>VERDENT</div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '2px' }}>TRADING PLATFORM</div>
            </div>
          </div>
        </div>

        {/* Market Status */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: marketStatus === 'open' ? 'var(--green)' : 'var(--red)',
              boxShadow: marketStatus === 'open' ? '0 0 8px var(--green)' : 'none',
            }} />
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {marketStatus === 'open' ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ padding: '16px 12px', flex: 1 }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '1.5px', marginBottom: '8px', paddingLeft: '8px' }}>NAVIGATION</div>
          {navItems.map(({ path, label, icon: Icon }) => {
            const isActive = location.pathname === path
            return (
              <NavLink
                key={path}
                to={path}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  marginBottom: '4px',
                  color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                  background: isActive ? 'rgba(0,208,132,0.1)' : 'transparent',
                  border: isActive ? '1px solid rgba(0,208,132,0.2)' : '1px solid transparent',
                  transition: 'all 0.15s ease',
                  fontSize: '14px',
                  fontWeight: isActive ? 600 : 400,
                  textDecoration: 'none',
                }}
              >
                <Icon size={18} />
                <span style={{ flex: 1 }}>{label}</span>
                {isActive && <ChevronRight size={14} />}
              </NavLink>
            )
          })}
        </nav>

        {/* Bottom */}
        <div style={{ padding: '16px 12px', borderTop: '1px solid var(--border)' }}>
          <button className="btn-secondary" style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
            <Settings size={16} />
            Settings
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div style={{ flex: 1, marginLeft: '240px', display: 'flex', flexDirection: 'column' }}>
        {/* Top Bar */}
        <header style={{
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border)',
          padding: '0 24px',
          height: '60px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}>
          <div style={{ display: 'flex', gap: '24px' }}>
            <TickerItem symbol="SPY" price="482.34" change="+1.2%" positive />
            <TickerItem symbol="QQQ" price="412.88" change="-0.4%" positive={false} />
            <TickerItem symbol="BTC" price="67,420" change="+2.8%" positive />
            <TickerItem symbol="EUR/USD" price="1.0892" change="-0.1%" positive={false} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button className="btn-secondary" style={{ padding: '6px 10px' }}>
              <Bell size={16} />
            </button>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #00D084, #0066FF)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '12px', fontWeight: 700, color: '#fff', cursor: 'pointer',
            }}>HF</div>
          </div>
        </header>

        {/* Page Content */}
        <main style={{ flex: 1, padding: '24px', overflow: 'auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function TickerItem({ symbol, price, change, positive }: { symbol: string; price: string; change: string; positive: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>{symbol}</span>
      <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>{price}</span>
      <span style={{ fontSize: '11px', fontWeight: 600, color: positive ? 'var(--green)' : 'var(--red)' }}>{change}</span>
    </div>
  )
}
