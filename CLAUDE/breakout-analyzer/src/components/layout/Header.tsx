'use client';
import { useState, useEffect } from 'react';

const MOCK_INDICES = [
  { name: 'BIST 100', value: 9842.35, change: 1.24 },
  { name: 'BIST 30', value: 12156.80, change: 0.87 },
  { name: 'USD/TRY', value: 32.45, change: -0.12 },
  { name: 'EUR/TRY', value: 35.18, change: 0.23 },
  { name: 'XAU/TRY', value: 2485.60, change: 0.56 },
  { name: 'S&P 500', value: 5248.90, change: 0.34 },
];

export function Header() {
  const [time, setTime] = useState('');
  const [isMarketOpen, setIsMarketOpen] = useState(false);

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      const h = now.getHours(), m = now.getMinutes();
      setIsMarketOpen(h >= 10 && (h < 18 || (h === 18 && m === 0)));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header style={{
      height: 48,
      background: 'var(--bg-card)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      flexShrink: 0,
      overflow: 'hidden',
    }}>
      {/* Market status */}
      <div style={{ padding: '0 16px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, borderRight: '1px solid var(--border)' }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: isMarketOpen ? 'var(--bull)' : 'var(--bear)',
          animation: isMarketOpen ? 'pulse-dot 1.5s ease infinite' : 'none',
        }} />
        <span style={{ fontSize: 10, color: 'var(--text-2)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
          {isMarketOpen ? 'PİYASA AÇIK' : 'PİYASA KAPALI'}
        </span>
      </div>

      {/* Scrolling ticker */}
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        <div style={{
          display: 'flex', gap: 0, whiteSpace: 'nowrap',
          animation: 'ticker 30s linear infinite',
          width: 'max-content',
        }}>
          {[...MOCK_INDICES, ...MOCK_INDICES].map((idx, i) => (
            <div key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '0 20px', borderRight: '1px solid var(--border)',
            }}>
              <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{idx.name}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
                {idx.value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
              </span>
              <span style={{ fontSize: 10, color: idx.change >= 0 ? 'var(--bull)' : 'var(--bear)', fontFamily: 'var(--font-mono)' }}>
                {idx.change >= 0 ? '+' : ''}{idx.change.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Clock */}
      <div style={{ padding: '0 16px', borderLeft: '1px solid var(--border)', flexShrink: 0 }}>
        <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{time}</span>
      </div>
    </header>
  );
}
