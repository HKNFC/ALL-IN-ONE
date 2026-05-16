'use client';
import { useState } from 'react';

const DEFAULT_WATCHLIST = ['THYAO', 'EREGL', 'GARAN', 'ASELS', 'KCHOL'];

export default function WatchlistPage() {
  const [list, setList] = useState(DEFAULT_WATCHLIST);
  const [input, setInput] = useState('');

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>◎ İzleme Listesi</h1>
      <div className="card" style={{ padding: '14px 16px', display: 'flex', gap: 8 }}>
        <input value={input} onChange={e => setInput(e.target.value.toUpperCase())} placeholder="Sembol ekle..."
          style={{ flex: 1, padding: '7px 12px', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', fontSize: 12, fontFamily: 'var(--font-mono)', outline: 'none' }} />
        <button className="btn-accent" onClick={() => { if (input && !list.includes(input)) { setList(l => [...l, input]); setInput(''); } }}>
          + Ekle
        </button>
      </div>
      <div className="card" style={{ overflow: 'hidden' }}>
        {list.map((sym, i) => (
          <div key={sym} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: i < list.length-1 ? '1px solid var(--border)' : 'none', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{sym}</span>
            <button onClick={() => setList(l => l.filter(s => s !== sym))} className="btn-ghost" style={{ fontSize: 10, color: 'var(--bear)', borderColor: 'rgba(255,71,87,0.2)' }}>✕</button>
          </div>
        ))}
        {list.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>Liste boş — sembol ekleyin</div>}
      </div>
    </div>
  );
}
