'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV = [
  { href: '/',          icon: '◈', label: 'Market', sub: 'Genel Bakış' },
  { href: '/analyzer',  icon: '⚡', label: 'Breakout', sub: 'Patlama Analizi' },
  { href: '/scanner',   icon: '⌖', label: 'Tarama', sub: 'Hisse Tarayıcı' },
  { href: '/backtest',  icon: '↺', label: 'Backtest', sub: 'Geçmiş Test' },
  { href: '/watchlist', icon: '◎', label: 'İzleme', sub: 'Watchlist' },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside style={{
      width: 200,
      background: 'var(--bg-card)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Subtle vertical glow */}
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 1,
        background: 'linear-gradient(to bottom, transparent, var(--accent), transparent)',
        opacity: 0.3,
      }} />

      {/* Logo */}
      <div style={{ padding: '24px 20px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, var(--accent), #00a865)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 700, color: '#000',
            boxShadow: '0 0 16px var(--accent-glow)',
          }}>V</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em' }}>VERDENT</div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.12em', marginTop: -1 }}>BREAKOUT</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ padding: '8px 10px', flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(n => {
          const active = n.href === '/' ? path === '/' : path.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} style={{ textDecoration: 'none' }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '9px 12px', borderRadius: 6, cursor: 'pointer',
                background: active ? 'var(--accent-dim)' : 'transparent',
                border: active ? '1px solid rgba(0,208,132,0.2)' : '1px solid transparent',
                transition: 'all 0.15s ease',
              }}>
                <span style={{ fontSize: 16, color: active ? 'var(--accent)' : 'var(--text-3)', width: 20, textAlign: 'center' }}>{n.icon}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: active ? 600 : 400, color: active ? 'var(--text)' : 'var(--text-2)' }}>{n.label}</div>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 1 }}>{n.sub}</div>
                </div>
                {active && (
                  <div style={{
                    marginLeft: 'auto', width: 4, height: 4, borderRadius: '50%',
                    background: 'var(--accent)', boxShadow: '0 0 6px var(--accent)',
                  }} />
                )}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6 }}>VERİ KAYNAĞI</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['BIST', 'TWELVE', 'API'].map(t => (
            <span key={t} className="badge badge-blue" style={{ fontSize: 8 }}>{t}</span>
          ))}
        </div>
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse-dot 2s ease infinite' }} />
          <span style={{ fontSize: 9, color: 'var(--text-3)' }}>API Bağlantı Aktif</span>
        </div>
      </div>
    </aside>
  );
}
