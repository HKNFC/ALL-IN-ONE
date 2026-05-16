import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useAppStore } from '../../stores/appStore';
import { formatNumber } from '../../utils';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:4000';

interface IndexQuote {
  index:     string;
  value:     number;
  change:    number;
  changePct: number;
}

export default function TopBar() {
  const { stocks } = useAppStore();
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [loadedAt, setLoadedAt] = useState('');

  const gainers = stocks.filter(s => s.changePct > 0).length;
  const losers  = stocks.filter(s => s.changePct < 0).length;

  // İlk yükleme + her 60 saniyede yenile
  useEffect(() => {
    const load = async () => {
      try {
        const res  = await fetch(`${API_BASE}/api/market/indices`);
        const json = await res.json() as { data: IndexQuote[] };
        if (json.data?.length) {
          setIndices(json.data);
          setLoadedAt(new Date().toLocaleTimeString('tr-TR', { hour12: false }));
        }
      } catch {
        // sessiz başarısız — önceki değerler kalır
      }
    };

    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const display = indices.length > 0 ? indices : [];

  return (
    <header
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', height: 44, flexShrink: 0 }}
      className="flex items-center overflow-hidden"
    >
      {/* Ticker tape */}
      <div className="flex-1 overflow-hidden">
        {display.length > 0 ? (
          <div
            className="ticker-scroll flex items-center gap-0"
            style={{ whiteSpace: 'nowrap', display: 'inline-flex' }}
          >
            {[...display, ...display].map((m, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-5"
                style={{ borderRight: '1px solid var(--border)', height: 44 }}
              >
                <span style={{ color: 'var(--text-3)', fontSize: 10, fontWeight: 600 }}>{m.index}</span>
                <span style={{ color: 'var(--text)', fontSize: 12, fontWeight: 600 }}>
                  {formatNumber(m.value)}
                </span>
                <span
                  className="flex items-center gap-1"
                  style={{ color: m.changePct >= 0 ? 'var(--accent)' : 'var(--red)', fontSize: 10 }}
                >
                  {m.changePct >= 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                  {m.changePct >= 0 ? '+' : ''}{m.changePct.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 px-5" style={{ color: 'var(--text-3)', fontSize: 11 }}>
            Piyasa verileri yükleniyor…
          </div>
        )}
      </div>

      {/* Sağ taraf: breadth + saat */}
      <div
        className="flex items-center gap-4 px-5"
        style={{ borderLeft: '1px solid var(--border)', height: '100%', flexShrink: 0 }}
      >
        <div className="flex items-center gap-1">
          <TrendingUp size={11} style={{ color: 'var(--accent)' }} />
          <span style={{ color: 'var(--accent)', fontSize: 11, fontWeight: 600 }}>{gainers}</span>
          <span style={{ color: 'var(--text-3)', fontSize: 10 }}>UP</span>
        </div>
        <div className="flex items-center gap-1">
          <TrendingDown size={11} style={{ color: 'var(--red)' }} />
          <span style={{ color: 'var(--red)', fontSize: 11, fontWeight: 600 }}>{losers}</span>
          <span style={{ color: 'var(--text-3)', fontSize: 10 }}>DN</span>
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
          {loadedAt || new Date().toLocaleTimeString('tr-TR', { hour12: false })}
        </div>
      </div>
    </header>
  );
}
