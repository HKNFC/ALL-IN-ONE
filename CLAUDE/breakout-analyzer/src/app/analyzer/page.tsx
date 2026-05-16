'use client';
import { useState, useMemo, useEffect } from 'react';
import { BreakoutTable } from '@/components/breakout/BreakoutTable';
import { StockDetailPanel } from '@/components/breakout/StockDetailPanel';
import { useBreakoutStore } from '@/store/useBreakoutStore';
import { generateMockBreakouts } from '@/lib/mockData';
import type { BreakoutStock } from '@/lib/mockData';

const MARKETS = [
  { id: 'BISTTUM', label: 'BIST Tüm' },
  { id: 'BIST100', label: 'BIST 100' },
  { id: 'BIST30',  label: 'BIST 30' },
];

export default function AnalyzerPage() {
  const { stocks, selectedSymbol, minScore, sortBy, searchQuery, setStocks, setSelected, setMinScore, setSortBy, setSearch } = useBreakoutStore();
  const [market, setMarket] = useState('BISTTUM');
  const [loading, setLoading] = useState(false);
  const [patternFilter, setPatternFilter] = useState('ALL');
  const [breakoutOnly, setBreakoutOnly] = useState(false);

  // Initial load
  useEffect(() => {
    setStocks(generateMockBreakouts(30));
  }, []);

  const handleScan = () => {
    setLoading(true);
    setSelected(null);
    setTimeout(() => {
      setStocks(generateMockBreakouts(30));
      setLoading(false);
    }, 1200);
  };

  const allPatterns = useMemo(() => {
    const p = new Set(stocks.map(s => s.pattern));
    return ['ALL', ...Array.from(p)];
  }, [stocks]);

  const filtered = useMemo(() => {
    let list = stocks.filter(s => s.breakoutScore >= minScore);
    if (patternFilter !== 'ALL') list = list.filter(s => s.pattern === patternFilter);
    if (breakoutOnly) list = list.filter(s => s.isBreakingOut);
    if (searchQuery) list = list.filter(s => s.symbol.includes(searchQuery.toUpperCase()) || s.sector.includes(searchQuery));
    list = [...list].sort((a, b) => {
      if (sortBy === 'score') return b.breakoutScore - a.breakoutScore;
      if (sortBy === 'volume') return b.volume - a.volume;
      if (sortBy === 'change') return b.change1d - a.change1d;
      return 0;
    });
    return list;
  }, [stocks, minScore, sortBy, searchQuery, patternFilter, breakoutOnly]);

  const selectedStock: BreakoutStock | null = stocks.find(s => s.symbol === selectedSymbol) ?? null;
  const breakingOutCount = stocks.filter(s => s.isBreakingOut).length;
  const avgScore = stocks.length > 0 ? Math.round(stocks.reduce((a, s) => a + s.breakoutScore, 0) / stocks.length) : 0;

  return (
    <div style={{ padding: '20px 24px', height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div className="fade-in" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>
            ⚡ Breakout Analyzer
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>
            BIST patlama &amp; kırılım fırsatları · Gerçek zamanlı tarama
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 8 }}>
            {[
              { l: 'TARANAN', v: stocks.length.toString(), c: 'var(--text-2)' },
              { l: 'EŞLEŞEN', v: filtered.length.toString(), c: 'var(--accent)' },
              { l: 'KIRILIM', v: breakingOutCount.toString(), c: 'var(--sideways)' },
              { l: 'ORT.SKOR', v: avgScore.toString(), c: avgScore > 70 ? 'var(--bull)' : 'var(--text-2)' },
            ].map(stat => (
              <div key={stat.l} style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 12px', textAlign: 'center' }}>
                <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em' }}>{stat.l}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: stat.c, fontFamily: 'var(--font-mono)' }}>{stat.v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="fade-in-d1 card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>

        {/* Market selector */}
        <div style={{ display: 'flex', gap: 4 }}>
          {MARKETS.map(m => (
            <button key={m.id} onClick={() => setMarket(m.id)} style={{
              padding: '5px 12px', borderRadius: 5, cursor: 'pointer', fontFamily: 'var(--font-sans)',
              fontSize: 11, transition: 'all 0.12s ease',
              background: market === m.id ? 'var(--accent-dim)' : 'transparent',
              border: `1px solid ${market === m.id ? 'rgba(0,208,132,0.3)' : 'var(--border)'}`,
              color: market === m.id ? 'var(--accent)' : 'var(--text-2)',
              fontWeight: market === m.id ? 600 : 400,
            }}>{m.label}</button>
          ))}
        </div>

        <div style={{ width: 1, height: 24, background: 'var(--border)' }} />

        {/* Sıralama */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>SIRALA:</span>
          {(['score','volume','change'] as const).map(s => (
            <button key={s} onClick={() => setSortBy(s)} style={{
              padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 10,
              background: sortBy === s ? 'rgba(74,158,255,0.12)' : 'transparent',
              border: `1px solid ${sortBy === s ? 'rgba(74,158,255,0.3)' : 'var(--border)'}`,
              color: sortBy === s ? 'var(--blue)' : 'var(--text-3)',
            }}>{s === 'score' ? 'Skor' : s === 'volume' ? 'Hacim' : 'Değişim'}</button>
          ))}
        </div>

        <div style={{ width: 1, height: 24, background: 'var(--border)' }} />

        {/* Min score slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>MİN SKOR:</span>
          <input type="range" min={0} max={100} step={5} value={minScore} onChange={e => setMinScore(Number(e.target.value))}
            style={{ width: 80, accentColor: 'var(--accent)', cursor: 'pointer' }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)', width: 24 }}>{minScore}</span>
        </div>

        <div style={{ width: 1, height: 24, background: 'var(--border)' }} />

        {/* Breakout only toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <div onClick={() => setBreakoutOnly(v => !v)} style={{
            width: 32, height: 16, borderRadius: 8, position: 'relative', cursor: 'pointer',
            background: breakoutOnly ? 'var(--accent)' : 'var(--border)', transition: 'background 0.2s',
          }}>
            <div style={{
              position: 'absolute', top: 2, left: breakoutOnly ? 18 : 2, width: 12, height: 12,
              borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
            }} />
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-2)' }}>Sadece Kırılım</span>
        </label>

        {/* Pattern filter */}
        <select value={patternFilter} onChange={e => setPatternFilter(e.target.value)} style={{
          padding: '5px 10px', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderRadius: 5, color: 'var(--text)', fontSize: 10, fontFamily: 'var(--font-sans)', cursor: 'pointer', outline: 'none',
        }}>
          {allPatterns.map(p => <option key={p} value={p}>{p === 'ALL' ? 'Tüm Patternlar' : p}</option>)}
        </select>

        {/* Search */}
        <input value={searchQuery} onChange={e => setSearch(e.target.value)} placeholder="Sembol / Sektör..."
          style={{
            padding: '5px 10px', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderRadius: 5, color: 'var(--text)', fontSize: 11, fontFamily: 'var(--font-sans)',
            outline: 'none', width: 140,
          }} />

        <div style={{ marginLeft: 'auto' }}>
          <button onClick={handleScan} className="btn-accent" disabled={loading}>
            {loading ? '⟳ Taranıyor...' : '⌖ Tara'}
          </button>
        </div>
      </div>

      {/* Main content: table + detail panel */}
      <div className="fade-in-d2" style={{ flex: 1, display: 'grid', gridTemplateColumns: selectedStock ? '1fr 380px' : '1fr', gap: 14, minHeight: 0 }}>
        <div style={{ overflow: 'hidden' }}>
          {loading ? (
            <div className="card" style={{ padding: 40, textAlign: 'center' }}>
              <div style={{ fontSize: 24, marginBottom: 12, animation: 'pulse-dot 1s ease infinite' }}>⌖</div>
              <div style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}>Hisseler taranıyor...</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{market} · {stocks.length} hisse analiz ediliyor</div>
            </div>
          ) : (
            <BreakoutTable stocks={filtered} onSelect={s => setSelected(s.symbol === selectedSymbol ? null : s.symbol)} />
          )}
        </div>
        {selectedStock && (
          <div style={{ overflow: 'hidden' }}>
            <StockDetailPanel stock={selectedStock} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  );
}
