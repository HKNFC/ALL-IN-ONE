import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, FlaskConical, ScanSearch, Briefcase,
  Activity, Settings, Bell, ChevronRight
} from 'lucide-react';
import { useAppStore } from '../../stores/appStore';

const NAV_ITEMS = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard',  id: 'dashboard' },
  { to: '/backtest',  icon: FlaskConical,    label: 'Backtest',   id: 'backtest'  },
  { to: '/scanner',   icon: ScanSearch,      label: 'Scanner',    id: 'scanner'   },
  { to: '/portfolio', icon: Briefcase,       label: 'Portfolio',  id: 'portfolio' },
];

export default function Sidebar() {
  const { isLive, toggleLive } = useAppStore();

  return (
    <aside
      style={{ background: 'var(--surface)', borderRight: '1px solid var(--border)', width: 220, minWidth: 220 }}
      className="flex flex-col h-full"
    >
      {/* Logo */}
      <div style={{ borderBottom: '1px solid var(--border)' }} className="px-5 py-4 flex items-center gap-3">
        <div
          style={{ background: 'var(--accent)', width: 28, height: 28, borderRadius: 6 }}
          className="flex items-center justify-center flex-shrink-0"
        >
          <Activity size={15} color="#000" strokeWidth={2.5} />
        </div>
        <div>
          <div style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 15, letterSpacing: '0.08em' }} className="text-glow">
            VERDENT
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 10 }}>TRADING PLATFORM</div>
        </div>
      </div>

      {/* Live indicator */}
      <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={toggleLive}
          className="flex items-center gap-2 w-full"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <span
            className="pulse-dot"
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: isLive ? 'var(--accent)' : 'var(--text-3)',
              display: 'inline-block',
              boxShadow: isLive ? '0 0 8px var(--accent)' : 'none',
            }}
          />
          <span style={{ color: isLive ? 'var(--accent)' : 'var(--text-3)', fontSize: 11, fontWeight: 600 }}>
            {isLive ? 'LIVE' : 'OFFLINE'}
          </span>
          <span style={{ color: 'var(--text-3)', fontSize: 10, marginLeft: 'auto' }}>
            {isLive ? 'CONNECTED' : 'PAUSED'}
          </span>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-3">
        <div style={{ color: 'var(--text-3)', fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', marginBottom: 8, paddingLeft: 8 }}>
          NAVIGATION
        </div>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 10px',
              borderRadius: 6,
              marginBottom: 2,
              textDecoration: 'none',
              background: isActive ? 'rgba(0,208,132,0.08)' : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              border: isActive ? '1px solid rgba(0,208,132,0.18)' : '1px solid transparent',
              transition: 'all 0.15s ease',
              fontSize: 12,
              fontWeight: isActive ? 600 : 400,
            })}
          >
            {({ isActive }) => (
              <>
                <Icon size={15} />
                <span style={{ flex: 1 }}>{label}</span>
                {isActive && <ChevronRight size={12} />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom */}
      <div style={{ borderTop: '1px solid var(--border)' }} className="px-3 py-3 flex items-center gap-2">
        <button className="btn-ghost flex items-center gap-2 flex-1" style={{ justifyContent: 'flex-start', fontSize: 11 }}>
          <Bell size={13} />
          Alerts
        </button>
        <button className="btn-ghost" style={{ padding: '7px 10px' }}>
          <Settings size={13} />
        </button>
      </div>
    </aside>
  );
}
