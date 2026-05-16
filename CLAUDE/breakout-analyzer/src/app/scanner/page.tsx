'use client';
import { useState } from 'react';

export default function ScannerPage() {
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<Array<{ symbol: string; score: number; reason: string }>>([]);

  const runScan = () => {
    setScanning(true);
    setTimeout(() => {
      setResults([
        { symbol: 'THYAO', score: 87, reason: 'RSI > 60, Hacim 3.2x, EMA200 üstü' },
        { symbol: 'EREGL', score: 82, reason: 'Kupa Sapı pattern, ADX 32' },
        { symbol: 'ASELS', score: 79, reason: 'Pivot kırılımı, Hacim artışı' },
      ]);
      setScanning(false);
    }, 1500);
  };

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="fade-in">
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>⌖ Hisse Tarayıcı</h1>
        <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>Özel kriter ile BIST taraması</p>
      </div>
      <div className="card fade-in-d1" style={{ padding: '20px', textAlign: 'center', color: 'var(--text-2)', fontSize: 13 }}>
        <p>Scanner sayfası — Python FastAPI backend bağlantısı ile aktif olacak</p>
        <button className="btn-accent" style={{ marginTop: 16 }} onClick={runScan} disabled={scanning}>
          {scanning ? '⟳ Taranıyor...' : '⌖ Demo Tara'}
        </button>
        {results.length > 0 && (
          <div style={{ marginTop: 16, textAlign: 'left' }}>
            {results.map(r => (
              <div key={r.symbol} style={{ padding: '10px 14px', marginBottom: 8, background: 'var(--bg-elevated)', borderRadius: 6, border: '1px solid var(--border)' }}>
                <span style={{ fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{r.symbol}</span>
                <span style={{ marginLeft: 12, color: 'var(--text-3)', fontSize: 11 }}>Skor: {r.score} · {r.reason}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
