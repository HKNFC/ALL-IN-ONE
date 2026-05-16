/**
 * PortfolioRisk — position sizing calculator + max loss + correlation heat.
 */
import { useMemo } from 'react';
import { AlertTriangle, Shield, TrendingDown } from 'lucide-react';

export interface Position {
  symbol:    string;
  entryPrice: number;
  stopLoss:  number;
  shares:    number;
  currentPrice?: number;
}

interface Props {
  positions:     Position[];
  totalCapital:  number;
}

function correlationColor(v: number): string {
  // -1 → blue, 0 → gray, +1 → red
  if (v > 0.6)  return 'rgba(255,71,87,0.75)';
  if (v > 0.3)  return 'rgba(255,165,2,0.55)';
  if (v < -0.3) return 'rgba(64,156,255,0.55)';
  return 'rgba(130,138,165,0.30)';
}

/** Simplified mock correlation based on symbol hash */
function mockCorr(a: string, b: string): number {
  if (a === b) return 1;
  const h = (s: string) => s.split('').reduce((n, c) => n + c.charCodeAt(0), 0);
  const v = ((h(a) * 17 + h(b) * 31) % 200 - 100) / 100;
  return Math.round(v * 100) / 100;
}

export function PortfolioRisk({ positions, totalCapital }: Props) {
  const metrics = useMemo(() => {
    if (positions.length === 0) return null;

    let maxLoss = 0;
    const sized = positions.map(p => {
      const risk    = p.entryPrice - p.stopLoss;          // risk per share
      const posVal  = p.shares * p.entryPrice;
      const lossVal = p.shares * risk;
      const pctCap  = posVal / totalCapital * 100;
      maxLoss += lossVal;
      return { ...p, risk, posVal, lossVal, pctCap };
    });

    return {
      sized,
      maxLoss,
      maxLossPct: maxLoss / totalCapital * 100,
      avgPositionPct: sized.reduce((s, p) => s + p.pctCap, 0) / positions.length,
    };
  }, [positions, totalCapital]);

  if (!metrics) return (
    <div style={{ color: 'var(--text-3)', fontSize: 12, padding: 16 }}>Pozisyon yok</div>
  );

  const riskLevel = metrics.maxLossPct > 20 ? 'HIGH' : metrics.maxLossPct > 10 ? 'MEDIUM' : 'LOW';
  const riskColor = riskLevel === 'HIGH' ? '#FF4757' : riskLevel === 'MEDIUM' ? '#FFA502' : '#00D084';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Summary row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
        <div className="metric-tile">
          <span className="label">Maks. Zarar</span>
          <span className="value" style={{ color: '#FF4757', fontSize: 16 }}>
            -{metrics.maxLossPct.toFixed(1)}%
          </span>
          <span className="delta" style={{ color: 'var(--text-3)' }}>
            {metrics.maxLoss.toLocaleString('tr-TR',{maximumFractionDigits:0})} ₺
          </span>
        </div>
        <div className="metric-tile">
          <span className="label">Risk Seviyesi</span>
          <span className="value" style={{ color: riskColor, fontSize: 14, display:'flex', alignItems:'center', gap:4 }}>
            {riskLevel === 'LOW'  && <Shield size={14} />}
            {riskLevel !== 'LOW'  && <AlertTriangle size={14} />}
            {riskLevel}
          </span>
          <span className="delta" style={{ color: 'var(--text-3)' }}>
            {riskLevel === 'HIGH' ? 'Stop seviyelerini kontrol et' : riskLevel === 'MEDIUM' ? 'Kabul edilebilir' : 'İyi yönetilen'}
          </span>
        </div>
        <div className="metric-tile">
          <span className="label">Ort. Pozisyon</span>
          <span className="value" style={{ fontSize: 16 }}>
            {metrics.avgPositionPct.toFixed(1)}%
          </span>
          <span className="delta" style={{ color: 'var(--text-3)' }}>portföy başına</span>
        </div>
      </div>

      {/* Per-position breakdown */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '80px 1fr 80px 80px 80px',
          padding: '8px 14px', borderBottom: '1px solid var(--border)',
          fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.07em',
        }}>
          {['SEMBOL','POS. DEĞERİ','STOP ZARAR','% KAYIP','% PORTFÖY'].map(h => <span key={h}>{h}</span>)}
        </div>
        {metrics.sized.map((p, i) => (
          <div key={p.symbol} className={i % 2 === 0 ? 'table-row-even' : 'table-row-odd'} style={{
            display: 'grid', gridTemplateColumns: '80px 1fr 80px 80px 80px',
            padding: '9px 14px', fontSize: 12, alignItems: 'center',
          }}>
            <span style={{ fontWeight: 700 }}>{p.symbol}</span>
            <div>
              <div style={{ color: 'var(--text)', fontFamily:'monospace' }}>
                {p.posVal.toLocaleString('tr-TR',{maximumFractionDigits:0})} ₺
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                {p.shares} lot @ {p.entryPrice.toFixed(2)}
              </div>
            </div>
            <span style={{ color: '#FF4757', fontFamily:'monospace' }}>
              {p.stopLoss.toFixed(2)}
            </span>
            <span style={{ color: '#FF4757', fontFamily:'monospace' }}>
              -{(p.risk / p.entryPrice * 100).toFixed(1)}%
            </span>
            <div>
              <div style={{ fontFamily:'monospace' }}>{p.pctCap.toFixed(1)}%</div>
              <div style={{
                height: 3, background: 'var(--border)', borderRadius: 99, marginTop: 4,
                overflow: 'hidden', width: 48,
              }}>
                <div style={{
                  height: '100%', borderRadius: 99,
                  width: `${Math.min(100, p.pctCap / 30 * 100)}%`,
                  background: p.pctCap > 25 ? '#FF4757' : '#00D084',
                }} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Correlation matrix */}
      {positions.length > 1 && (
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8 }}>
            KORElASYON MATRİSİ (tahmini)
          </div>
          <div style={{ display: 'inline-grid', gap: 3, gridTemplateColumns: `28px repeat(${positions.length}, 48px)` }}>
            {/* Header row */}
            <span />
            {positions.map(p => (
              <span key={p.symbol} style={{ fontSize: 9, color: 'var(--text-3)', textAlign:'center', overflow:'hidden', textOverflow:'ellipsis' }}>
                {p.symbol}
              </span>
            ))}
            {/* Data rows */}
            {positions.map(row => (
              <>
                <span key={`lbl-${row.symbol}`} style={{ fontSize: 9, color: 'var(--text-3)', display:'flex', alignItems:'center' }}>
                  {row.symbol}
                </span>
                {positions.map(col => {
                  const v = mockCorr(row.symbol, col.symbol);
                  return (
                    <div key={`${row.symbol}-${col.symbol}`} style={{
                      height: 28, borderRadius: 4,
                      background: correlationColor(v),
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 9, fontFamily: 'monospace',
                      color: row.symbol === col.symbol ? '#000' : 'var(--text)',
                    }}>
                      {v.toFixed(2)}
                    </div>
                  );
                })}
              </>
            ))}
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 6 }}>
            <span style={{ color: 'rgba(255,71,87,0.9)' }}>■</span> Yüksek pozitif &nbsp;
            <span style={{ color: 'rgba(64,156,255,0.9)' }}>■</span> Negatif korelasyon
          </div>
        </div>
      )}
    </div>
  );
}
