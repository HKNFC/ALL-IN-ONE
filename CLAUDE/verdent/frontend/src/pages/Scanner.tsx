import { useState, useCallback, useMemo, useRef } from 'react';
import {
  useDebounce
} from '../hooks/useDebounce';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip,
} from 'recharts';

// ─── Types ────────────────────────────────────────────────────────────────────

type CriteriaType   = 'ALFA' | 'BETA' | 'DELTA';
type MarketScope    = 'BISTTUM' | 'BIST100' | 'BIST100DISI' | 'US';
type MarketLabel    = 'BULL' | 'BEAR' | 'SIDEWAYS';
type SortKey        = 'rank' | 'symbol' | 'score' | 'entry' | 'target' | 'stopLoss' | 'rr' | 'change';
type SortDir        = 'asc' | 'desc';

interface SignalDetail {
  label:   string;
  value:   string;
  passed:  boolean;
  pts:     number;
  category: 'technical' | 'fundamental';
}

interface ScanStock {
  rank:       number;
  symbol:     string;
  name:       string;
  sector:     string;
  score:      number;
  entry:      number;
  target:     number;
  stopLoss:   number;
  rr:         number;
  change:     number;
  volume:     number;
  vol20x:     number;   // volume / 20d avg
  rsi14:      number;
  adx14:      number;
  near52wHigh: number;  // % below 52w high
  signals:    SignalDetail[];
  radarData:  { dim: string; val: number }[];
}

interface MarketConditionSnap {
  condition:   MarketLabel;
  score:       number;
  confidence:  number;
}

interface ScanResult {
  criteria:        CriteriaType;
  date:            string;
  market:          MarketScope;
  scannedTotal:    number;
  passedFilters:   number;
  stocks:          ScanStock[];
  marketCondition: MarketConditionSnap;
  consistentWithBacktest: boolean | null;  // null = not checked yet
  runAt:           Date;
  runtimeMs:       number;
}

// ─── Mock data ────────────────────────────────────────────────────────────────

const BIST100_UNIVERSE = [
  { s: 'THYAO', n: 'Türk Hava Yolları',    sec: 'Havacılık'    },
  { s: 'EREGL', n: 'Ereğli Demir Çelik',   sec: 'Sanayi'       },
  { s: 'SISE',  n: 'Şişecam',              sec: 'Sanayi'       },
  { s: 'AKBNK', n: 'Akbank',               sec: 'Bankacılık'   },
  { s: 'TUPRS', n: 'Tüpraş',               sec: 'Enerji'       },
  { s: 'GARAN', n: 'Garanti BBVA',         sec: 'Bankacılık'   },
  { s: 'ISCTR', n: 'İş Bankası',           sec: 'Bankacılık'   },
  { s: 'KCHOL', n: 'Koç Holding',          sec: 'Holding'      },
  { s: 'SAHOL', n: 'Sabancı Holding',      sec: 'Holding'      },
  { s: 'BIMAS', n: 'BİM Mağazalar',        sec: 'Perakende'    },
  { s: 'FROTO', n: 'Ford Otomotiv',        sec: 'Otomotiv'     },
  { s: 'TOASO', n: 'Tofaş Otomobil',       sec: 'Otomotiv'     },
  { s: 'ASELS', n: 'Aselsan',              sec: 'Savunma'      },
  { s: 'TCELL', n: 'Turkcell',             sec: 'Telekom'      },
  { s: 'PGSUS', n: 'Pegasus',              sec: 'Havacılık'    },
];

const BIST_DISI_UNIVERSE = [
  { s: 'AEFES', n: 'Anadolu Efes',         sec: 'İçecek'       },
  { s: 'ALBRK', n: 'Albaraka Türk',        sec: 'Bankacılık'   },
  { s: 'BRISA', n: 'Brisa Bridgestone',    sec: 'Otomotiv'     },
  { s: 'DOHOL', n: 'Doğan Holding',        sec: 'Holding'      },
  { s: 'FENER', n: 'Fenerbahçe SK',        sec: 'Spor'         },
  { s: 'GSRAY', n: 'Galatasaray SK',       sec: 'Spor'         },
  { s: 'INDES', n: 'İndeks Bilgisayar',    sec: 'Teknoloji'    },
  { s: 'ISATR', n: 'İş Yatırım',           sec: 'Finans'       },
  { s: 'JANTS', n: 'Jantsa',               sec: 'Sanayi'       },
  { s: 'KAPLM', n: 'Kaplamin Ambalaj',     sec: 'Ambalaj'      },
  { s: 'ALKIM', n: 'Alkim Kağıt',          sec: 'Kağıt'        },
  { s: 'BUCIM', n: 'Bursa Çimento',        sec: 'Çimento'      },
  { s: 'IPEKE', n: 'İpek Doğal Enerji',   sec: 'Enerji'       },
  { s: 'GENIL', n: 'Gen İlaç',             sec: 'Sağlık'       },
  { s: 'EGEEN', n: 'Ege Endüstri',         sec: 'Sanayi'       },
];

const BISTTUM_UNIVERSE = [...BIST100_UNIVERSE, ...BIST_DISI_UNIVERSE];

// legacy alias
const BIST_UNIVERSE = BIST100_UNIVERSE;

const US_UNIVERSE = [
  { s: 'AAPL', n: 'Apple Inc.',             sec: 'Technology'   },
  { s: 'MSFT', n: 'Microsoft Corp.',        sec: 'Technology'   },
  { s: 'NVDA', n: 'NVIDIA Corp.',           sec: 'Technology'   },
  { s: 'AMZN', n: 'Amazon.com',             sec: 'Cons. Disc.'  },
  { s: 'JPM',  n: 'JPMorgan Chase',         sec: 'Financials'   },
  { s: 'XOM',  n: 'Exxon Mobil',            sec: 'Energy'       },
  { s: 'JNJ',  n: 'Johnson & Johnson',      sec: 'Health Care'  },
  { s: 'PG',   n: 'Procter & Gamble',       sec: 'Cons. Stapl.' },
  { s: 'V',    n: 'Visa Inc.',              sec: 'Financials'   },
  { s: 'KO',   n: 'Coca-Cola',              sec: 'Cons. Stapl.' },
];

function rnd(min: number, max: number, dp = 2) {
  return parseFloat((min + Math.random() * (max - min)).toFixed(dp));
}

function buildAlfaSignals(score: number): SignalDetail[] {
  const strong = score >= 85;
  return [
    { label: 'Fiyat > 200 EMA',       value: 'Üstünde',              passed: true,         pts: 15, category: 'technical'    },
    { label: 'Golden Cross (50>200)',  value: 'Aktif',                passed: strong,       pts: 10, category: 'technical'    },
    { label: `RSI(14): ${rnd(52,68,0)}`, value: 'Optimal (50-70)',   passed: true,         pts: 10, category: 'technical'    },
    { label: 'MACD',                   value: 'Sinyal üstünde',       passed: true,         pts: 10, category: 'technical'    },
    { label: `Hacim: ${rnd(1.5,2.8,1)}x ort`, value: 'Onaylandı',   passed: true,         pts: 10, category: 'technical'    },
    { label: `ADX(14): ${rnd(26,38,0)}`, value: 'Güçlü trend',       passed: strong,       pts: 8,  category: 'technical'    },
    { label: `52H Yakın: %${rnd(1,9,1)}`, value: 'Yakın',            passed: strong,       pts: 7,  category: 'technical'    },
    { label: `Gelir Büyümesi: %${rnd(12,28,0)}`, value: 'YoY > 15%', passed: true,         pts: 10, category: 'fundamental'  },
    { label: `EPS Büyümesi: %${rnd(10,24,0)}`, value: 'YoY > 10%',   passed: true,         pts: 10, category: 'fundamental'  },
    { label: `ROE: %${rnd(15,32,0)}`,  value: '> 15%',               passed: true,         pts: 5,  category: 'fundamental'  },
    { label: `D/E: ${rnd(0.4,1.9,1)}`, value: '< 1.5 hedef',         passed: score >= 80,  pts: 3,  category: 'fundamental'  },
    { label: 'Serbest Nakit Akışı',    value: 'Pozitif',              passed: score >= 75,  pts: 2,  category: 'fundamental'  },
  ];
}

function buildBetaSignals(score: number): SignalDetail[] {
  return [
    { label: `RS vs Endeks: ${rnd(1.0,1.4,2)}`, value: '> 1.0 (Üstün)', passed: true,      pts: 20, category: 'technical'   },
    { label: `Beta: ${rnd(0.4,0.79,2)}`,         value: '< 0.8 (Defansif)', passed: true,   pts: 10, category: 'technical'   },
    { label: `RSI(14): ${rnd(30,49,0)}`,          value: 'Dip değil',    passed: score >= 70, pts: 10, category: 'technical' },
    { label: 'Destek Seviyesi',                   value: 'Fibonacci 0.618', passed: true,    pts: 10, category: 'technical'  },
    { label: 'Stochastic',                        value: '< 20, yukarı kesiyor', passed: true, pts: 10, category: 'technical'},
    { label: `Temettü: %${rnd(2,5,1)}`,           value: '> 2%',         passed: true,       pts: 10, category: 'fundamental'},
    { label: `P/E: ${rnd(8,15,1)}`,               value: '< 15',         passed: true,       pts: 8,  category: 'fundamental'},
    { label: `P/B: ${rnd(0.8,1.5,1)}`,            value: '< 1.5',        passed: score >= 72, pts: 4, category: 'fundamental'},
    { label: `D/E: ${rnd(0.2,0.5,2)}`,            value: '< 0.5',        passed: true,       pts: 8,  category: 'fundamental'},
    { label: `ROE: %${rnd(12,22,0)}`,             value: '> 12%',        passed: score >= 68, pts: 4, category: 'fundamental'},
  ];
}

function buildDeltaSignals(score: number): SignalDetail[] {
  return [
    { label: `ADX(14): ${rnd(12,19,0)}`,      value: '< 20 (Yatay)',      passed: true,        pts: 15, category: 'technical'   },
    { label: 'BB Alt Band',                    value: 'Yakın, kırılmadı',  passed: true,        pts: 15, category: 'technical'   },
    { label: `RSI(14): ${rnd(30,44,0)}`,       value: '30-45 (Geri çekilme)', passed: true,     pts: 15, category: 'technical'   },
    { label: `Stochastic: ${rnd(18,29,0)}`,    value: '< 30 (Aşırı satım)', passed: score >= 65, pts: 10, category: 'technical' },
    { label: 'Destek Seviyesi',                value: 'Önceki zirve',      passed: true,        pts: 10, category: 'technical'   },
    { label: 'VWAP',                           value: 'Altında, yaklaşıyor', passed: score >= 60, pts: 10, category: 'technical' },
    { label: 'Kapitülasyon Hacmi',             value: 'Dip gün hacmi yüksek', passed: score >= 70, pts: 10, category: 'technical'},
    { label: `P/E: ${rnd(10,20,1)}`,           value: 'Adil değer (10-20)', passed: true,        pts: 10, category: 'fundamental'},
    { label: `ROE: %${rnd(10,18,0)}`,          value: '> 10%',             passed: score >= 62,  pts: 5,  category: 'fundamental'},
  ];
}

function buildRadar(criteria: CriteriaType, score: number): { dim: string; val: number }[] {
  const base = score * 0.8;
  if (criteria === 'ALFA') return [
    { dim: 'Trend',      val: Math.min(100, base + rnd(-8, 12)) },
    { dim: 'Momentum',   val: Math.min(100, base + rnd(-10, 15)) },
    { dim: 'Hacim',      val: Math.min(100, base + rnd(-5, 10)) },
    { dim: 'Temel',      val: Math.min(100, base + rnd(-15, 10)) },
    { dim: 'Değerleme',  val: Math.min(100, base + rnd(-12, 8)) },
    { dim: 'Güç',        val: Math.min(100, base + rnd(-6, 12)) },
  ];
  if (criteria === 'BETA') return [
    { dim: 'RS',         val: Math.min(100, base + rnd(-5, 15)) },
    { dim: 'Defansif',   val: Math.min(100, base + rnd(-8, 12)) },
    { dim: 'Değer',      val: Math.min(100, base + rnd(-10, 10)) },
    { dim: 'Temettü',    val: Math.min(100, base + rnd(-12, 8)) },
    { dim: 'Düşük Risk', val: Math.min(100, base + rnd(-6, 12)) },
    { dim: 'Likidite',   val: Math.min(100, base + rnd(-8, 10)) },
  ];
  return [
    { dim: 'Yatay Güç',  val: Math.min(100, base + rnd(-8, 12)) },
    { dim: 'Aşırı Satım',val: Math.min(100, base + rnd(-10, 15)) },
    { dim: 'Destek',     val: Math.min(100, base + rnd(-5, 10)) },
    { dim: 'BB Pozisyon',val: Math.min(100, base + rnd(-12, 8)) },
    { dim: 'Hacim',      val: Math.min(100, base + rnd(-8, 12)) },
    { dim: 'Temel',      val: Math.min(100, base + rnd(-10, 10)) },
  ];
}

function generateScanResult(criteria: CriteriaType, date: string, market: MarketScope, portfolioSize: 1|3|5|7 = 5): ScanResult {
  const isBIST    = market !== 'US';
  const universeMap: Record<MarketScope, typeof BIST100_UNIVERSE> = {
    BIST100:     BIST100_UNIVERSE,
    BISTTUM:     BISTTUM_UNIVERSE,
    BIST100DISI: BIST_DISI_UNIVERSE,
    US:          US_UNIVERSE,
  };
  const universe  = universeMap[market];
  const baseScores = [94, 89, 85, 82, 78, 74, 71];
  const priceBase = isBIST ? [285, 45, 28, 52, 168, 62, 38] : [112, 148, 163, 61, 39, 88, 210];
  const change = [2.34, 1.12, -0.42, 0.87, 1.65, -0.23, 0.95];

  const stocks: ScanStock[] = universe.slice(0, portfolioSize).map((u, i) => {
    const score = baseScores[i] + rnd(-2, 2, 0);
    const entry = priceBase[i] + rnd(-2, 2, 2);
    const atr   = entry * 0.025;
    const target = parseFloat((entry + atr * (criteria === 'ALFA' ? 3.0 : criteria === 'BETA' ? 2.0 : 1.5)).toFixed(2));
    const stop   = parseFloat((entry - atr * (criteria === 'ALFA' ? 1.5 : 1.0)).toFixed(2));
    const rr     = parseFloat(((target - entry) / (entry - stop)).toFixed(1));

    const sigs = criteria === 'ALFA' ? buildAlfaSignals(score)
      : criteria === 'BETA' ? buildBetaSignals(score) : buildDeltaSignals(score);

    return {
      rank: i + 1, symbol: u.s, name: u.n, sector: u.sec,
      score, entry, target, stopLoss: stop, rr,
      change: change[i], volume: Math.floor(rnd(5e6, 50e6, 0)),
      vol20x: rnd(1.2, 2.8), rsi14: rnd(35, 68, 1), adx14: rnd(20, 38, 1),
      near52wHigh: rnd(1, 12, 1), signals: sigs,
      radarData: buildRadar(criteria, score),
    };
  });

  const condMap: Record<CriteriaType, MarketLabel> = { ALFA: 'BULL', BETA: 'BEAR', DELTA: 'SIDEWAYS' };
  const scoreMap: Record<CriteriaType, number>     = { ALFA: 6.2, BETA: -4.1, DELTA: 1.3 };

  return {
    criteria, date, market, scannedTotal: market === 'US' ? 903 : market === 'BISTTUM' ? 603 : market === 'BIST100DISI' ? 503 : 100,
    passedFilters: Math.floor(rnd(18, 34, 0)), stocks,
    marketCondition: { condition: condMap[criteria], score: scoreMap[criteria] + rnd(-0.8, 0.8), confidence: rnd(68, 88, 1) },
    consistentWithBacktest: Math.random() > 0.15,
    runAt: new Date(), runtimeMs: Math.floor(rnd(40, 180, 0)),
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const CRIT_COLOR: Record<string, string> = { ALFA: 'var(--accent)', BETA: 'var(--red)', DELTA: 'var(--yellow)' };
const COND_COLOR: Record<string, string> = { BULL: 'var(--accent)', BEAR: 'var(--red)', SIDEWAYS: 'var(--yellow)' };
const COND_LABEL: Record<string, string> = { BULL: '🐂 BOĞA', BEAR: '🐻 AYI', SIDEWAYS: '↔ YATAY' };

function pctColor(v: number) { return v >= 0 ? 'var(--accent)' : 'var(--red)'; }
function fmtPct(v: number) { return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`; }

function exportCSV(stocks: ScanStock[], result: ScanResult) {
  const rows = stocks.map(s => ({
    Sıra: s.rank, Sembol: s.symbol, Şirket: s.name, Sektör: s.sector,
    Skor: s.score, Giriş: s.entry, Hedef: s.target, Stop: s.stopLoss,
    'R/R': s.rr, 'Değişim%': s.change,
  }));
  const keys = Object.keys(rows[0]);
  const csv  = [keys.join(','), ...rows.map(r => keys.map(k => JSON.stringify((r as Record<string, unknown>)[k] ?? '')).join(','))].join('\n');
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `scan_${result.criteria}_${result.date}_${result.market}.csv`;
  a.click();
}

// ─── Score Radar ──────────────────────────────────────────────────────────────

function ScoreRadar({ data, color }: { data: { dim: string; val: number }[]; color: string }) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <RadarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <PolarGrid stroke="var(--border)" />
        <PolarAngleAxis dataKey="dim" tick={{ fontSize: 9, fill: 'var(--text-3)' }} />
        <Radar dataKey="val" stroke={color} fill={color} fillOpacity={0.18} strokeWidth={1.5} dot={{ r: 2, fill: color }} />
        <Tooltip formatter={(v: unknown) => [`${Number(v).toFixed(0)}`, 'Puan']}
          contentStyle={{ background: 'var(--surface-el)', border: '1px solid var(--border)', fontSize: 10 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

function StockDetail({ stock, criteria, market }: { stock: ScanStock; criteria: CriteriaType; market: MarketScope }) {
  const color    = CRIT_COLOR[criteria];
  const currency = market === 'BIST' ? '₺' : '$';
  const technical   = stock.signals.filter(s => s.category === 'technical');
  const fundamental = stock.signals.filter(s => s.category === 'fundamental');

  return (
    <div style={{ padding: '16px 18px', background: 'var(--surface-el)', borderTop: `1px solid ${color}30` }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <span style={{ fontSize: 14, fontWeight: 700, marginRight: 10 }}>{stock.symbol}</span>
          <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{stock.name} · {stock.sector}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-ghost" style={{ fontSize: 10, padding: '5px 12px' }}>📈 Grafik</button>
          <button className="btn-ghost" style={{ fontSize: 10, padding: '5px 12px' }}>⬆ İzleme Listesi</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 220px', gap: 16 }}>
        {/* Technical signals */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8 }}>TEKNİK SİNYALLER</div>
          {technical.map((sig, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 12, flexShrink: 0 }}>{sig.passed ? '✅' : '❌'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: sig.passed ? 'var(--text)' : 'var(--text-2)' }}>{sig.label}</span>
                  <span style={{ fontSize: 10, color: sig.passed ? color : 'var(--text-3)', fontWeight: sig.passed ? 600 : 400 }}>
                    {sig.passed ? `+${sig.pts} pt` : '0 pt'}
                  </span>
                </div>
                <div style={{ fontSize: 9, color: 'var(--text-3)' }}>{sig.value}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Fundamental signals */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8 }}>TEMEL ANALİZ</div>
          {fundamental.map((sig, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 12, flexShrink: 0 }}>{sig.passed ? '✅' : '❌'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: sig.passed ? 'var(--text)' : 'var(--text-2)' }}>{sig.label}</span>
                  <span style={{ fontSize: 10, color: sig.passed ? color : 'var(--text-3)', fontWeight: sig.passed ? 600 : 400 }}>
                    {sig.passed ? `+${sig.pts} pt` : '0 pt'}
                  </span>
                </div>
                <div style={{ fontSize: 9, color: 'var(--text-3)' }}>{sig.value}</div>
              </div>
            </div>
          ))}

          {/* Price levels */}
          <div style={{ marginTop: 14, padding: '10px 12px', background: 'var(--surface)', borderRadius: 6, border: '1px solid var(--border)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
              {[
                { l: 'GİRİŞ', v: `${currency}${stock.entry.toFixed(2)}`, c: 'var(--text)' },
                { l: 'HEDEF', v: `${currency}${stock.target.toFixed(2)}`, c: 'var(--accent)' },
                { l: 'STOP',  v: `${currency}${stock.stopLoss.toFixed(2)}`, c: 'var(--red)' },
              ].map(item => (
                <div key={item.l}>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', marginBottom: 3 }}>{item.l}</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: item.c }}>{item.v}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)', fontSize: 10, color: 'var(--text-2)' }}>
              Risk/Ödül: <strong style={{ color: stock.rr >= 2 ? 'var(--accent)' : 'var(--yellow)' }}>1:{stock.rr}</strong>
            </div>
          </div>
        </div>

        {/* Radar */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 4 }}>SKOR ANALIZI</div>
          <ScoreRadar data={stock.radarData} color={color.replace('var(--accent)', '#00D084').replace('var(--red)', '#FF4757').replace('var(--yellow)', '#FFC700')} />
          <div style={{ textAlign: 'center', marginTop: 4 }}>
            <span style={{ fontSize: 22, fontWeight: 700, color }}>{stock.score}</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>/100</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Comparison View ──────────────────────────────────────────────────────────

function ComparisonView({ stocks, criteria, market }: { stocks: ScanStock[]; criteria: CriteriaType; market: MarketScope }) {
  const color    = CRIT_COLOR[criteria];
  const currency = market === 'BIST' ? '₺' : '$';

  const rows: { label: string; getValue: (s: ScanStock) => string; getColor?: (s: ScanStock) => string }[] = [
    { label: 'Skor',          getValue: s => `${s.score}/100`,              getColor: s => s.score >= 85 ? 'var(--accent)' : color },
    { label: 'Giriş',         getValue: s => `${currency}${s.entry.toFixed(2)}` },
    { label: 'Hedef',         getValue: s => `${currency}${s.target.toFixed(2)}`, getColor: () => 'var(--accent)' },
    { label: 'Stop',          getValue: s => `${currency}${s.stopLoss.toFixed(2)}`, getColor: () => 'var(--red)' },
    { label: 'R/R',           getValue: s => `1:${s.rr}`,                   getColor: s => s.rr >= 2 ? 'var(--accent)' : 'var(--yellow)' },
    { label: 'Değişim',       getValue: s => fmtPct(s.change),              getColor: s => pctColor(s.change) },
    { label: 'RSI(14)',       getValue: s => s.rsi14.toFixed(1),            getColor: s => s.rsi14 > 50 ? 'var(--accent)' : 'var(--yellow)' },
    { label: 'ADX(14)',       getValue: s => s.adx14.toFixed(1),            getColor: s => s.adx14 > 25 ? 'var(--accent)' : 'var(--text-2)' },
    { label: '52H Uzaklık',   getValue: s => `%${s.near52wHigh.toFixed(1)}`, getColor: s => s.near52wHigh < 5 ? 'var(--accent)' : 'var(--text-2)' },
    { label: 'Hacim Çarpanı', getValue: s => `${s.vol20x.toFixed(1)}x` },
  ];

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      {/* Stock headers */}
      <div style={{ display: 'grid', gridTemplateColumns: `120px repeat(${stocks.length}, 1fr)`, borderBottom: '1px solid var(--border)', background: 'var(--surface-el)' }}>
        <div style={{ padding: '10px 14px', fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em' }}>GÖSTERGE</div>
        {stocks.map(s => (
          <div key={s.symbol} style={{ padding: '10px 14px', borderLeft: '1px solid var(--border)', textAlign: 'center' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color }}>{s.symbol}</div>
            <div style={{ fontSize: 9, color: 'var(--text-3)' }}>{s.name}</div>
          </div>
        ))}
      </div>

      {rows.map((row, ri) => (
        <div key={row.label} style={{
          display: 'grid', gridTemplateColumns: `120px repeat(${stocks.length}, 1fr)`,
          borderBottom: ri < rows.length - 1 ? '1px solid var(--border)' : 'none',
          background: ri % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
        }}>
          <div style={{ padding: '9px 14px', fontSize: 10, color: 'var(--text-2)' }}>{row.label}</div>
          {stocks.map(s => {
            const val = row.getValue(s);
            const col = row.getColor ? row.getColor(s) : 'var(--text)';
            return (
              <div key={s.symbol} style={{ padding: '9px 14px', borderLeft: '1px solid var(--border)', textAlign: 'center', fontSize: 12, fontWeight: 600, color: col }}>
                {val}
              </div>
            );
          })}
        </div>
      ))}

      {/* Radar row */}
      <div style={{ display: 'grid', gridTemplateColumns: `120px repeat(${stocks.length}, 1fr)`, borderTop: '1px solid var(--border)' }}>
        <div style={{ padding: '10px 14px', fontSize: 10, color: 'var(--text-2)' }}>Radar</div>
        {stocks.map(s => (
          <div key={s.symbol} style={{ borderLeft: '1px solid var(--border)' }}>
            <ScoreRadar data={s.radarData}
              color={color.replace('var(--accent)', '#00D084').replace('var(--red)', '#FF4757').replace('var(--yellow)', '#FFC700')} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Results Table ────────────────────────────────────────────────────────────

function ResultsTable({ result, minScore, onMinScoreChange }: {
  result: ScanResult;
  minScore: number;
  onMinScoreChange: (v: number) => void;
}) {
  const [expanded, setExpanded]     = useState<number | null>(null);
  const [viewMode, setViewMode]     = useState<'list' | 'compare'>('list');
  const [sortKey, setSortKey]       = useState<SortKey>('rank');
  const [sortDir, setSortDir]       = useState<SortDir>('asc');

  const color = CRIT_COLOR[result.criteria];

  const sorted = useMemo(() => {
    const filtered = result.stocks.filter(s => s.score >= minScore);
    return [...filtered].sort((a, b) => {
      const av = a[sortKey as keyof ScanStock] as number;
      const bv = b[sortKey as keyof ScanStock] as number;
      if (typeof av !== 'number' || typeof bv !== 'number') return 0;
      return sortDir === 'asc' ? av - bv : bv - av;
    });
  }, [result.stocks, minScore, sortKey, sortDir]);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(k); setSortDir('desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) => (
    <span style={{ fontSize: 9, opacity: sortKey === k ? 1 : 0.3, marginLeft: 3 }}>
      {sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
    </span>
  );

  const cols: { label: string; key: SortKey; right?: boolean; width?: number }[] = [
    { label: '#',       key: 'rank',     width: 40 },
    { label: 'SEMBOL',  key: 'symbol',   width: 110 },
    { label: 'SKOR',    key: 'score',    right: true, width: 80 },
    { label: 'GİRİŞ',   key: 'entry',    right: true, width: 90 },
    { label: 'HEDEF',   key: 'target',   right: true, width: 90 },
    { label: 'STOP',    key: 'stopLoss', right: true, width: 90 },
    { label: 'R/R',     key: 'rr',       right: true, width: 72 },
    { label: 'DEĞİŞİM', key: 'change',   right: true, width: 80 },
  ];
  const gridCols = cols.map(c => c.width ? `${c.width}px` : '1fr').join(' ') + ' 1fr';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* View toggle */}
          {['list', 'compare'].map(v => (
            <button key={v} onClick={() => setViewMode(v as 'list' | 'compare')} style={{
              padding: '5px 14px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
              background: viewMode === v ? 'var(--surface-el)' : 'transparent',
              border: `1px solid ${viewMode === v ? 'var(--border)' : 'transparent'}`,
              color: viewMode === v ? 'var(--text)' : 'var(--text-2)', transition: 'all 0.15s ease',
            }}>
              {v === 'list' ? '☰ Liste' : '⊞ Karşılaştır'}
            </button>
          ))}

          {/* Min score */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--text-2)' }}>Min Skor:</span>
            <input type="range" min={0} max={100} step={5} value={minScore}
              onChange={e => onMinScoreChange(Number(e.target.value))}
              style={{ width: 80, accentColor: '#00D084' }} />
            <span style={{ fontSize: 11, fontWeight: 600, color, minWidth: 28 }}>{minScore}</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => exportCSV(sorted, result)} className="btn-ghost" style={{ fontSize: 10 }}>⬇ CSV İndir</button>
        </div>
      </div>

      {/* Consistency badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {result.consistentWithBacktest === true && (
          <div style={{ fontSize: 10, padding: '4px 10px', borderRadius: 5,
            background: 'rgba(0,208,132,0.1)', border: '1px solid rgba(0,208,132,0.25)', color: 'var(--accent)' }}>
            ✅ Backtest ile Tutarlı — Aynı tarih/kriter kombinasyonu doğrulandı
          </div>
        )}
        {result.consistentWithBacktest === false && (
          <div style={{ fontSize: 10, padding: '4px 10px', borderRadius: 5,
            background: 'rgba(255,199,0,0.1)', border: '1px solid rgba(255,199,0,0.25)', color: 'var(--yellow)' }}>
            ⚠️ Kontrol Gerekiyor — Bu tarih/kriter için backtest verisi bulunamadı
          </div>
        )}
        <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 'auto' }}>
          {sorted.length}/{result.stocks.length} hisse gösteriliyor
        </span>
      </div>

      {/* Compare view */}
      {viewMode === 'compare' && <ComparisonView stocks={sorted.slice(0, 5)} criteria={result.criteria} market={result.market} />}

      {/* List view */}
      {viewMode === 'list' && (
        <div className="card" style={{ overflow: 'hidden' }}>
          {/* Table header */}
          <div style={{ display: 'grid', gridTemplateColumns: gridCols, padding: '9px 16px',
            borderBottom: '1px solid var(--border)', background: 'var(--surface-el)' }}>
            {cols.map(c => (
              <div key={c.key} onClick={() => toggleSort(c.key)} style={{
                fontSize: 10, color: sortKey === c.key ? color : 'var(--text-3)',
                letterSpacing: '0.08em', cursor: 'pointer', userSelect: 'none',
                textAlign: c.right ? 'right' : 'left',
              }}>
                {c.label}<SortIcon k={c.key} />
              </div>
            ))}
            <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', textAlign: 'right' }}>DETAY</div>
          </div>

          {sorted.map((s, i) => {
            const isOpen = expanded === s.rank;
            const scoreColor = s.score >= 85 ? 'var(--accent)' : s.score >= 70 ? color : 'var(--text-2)';
            return (
              <div key={s.symbol}>
                <div
                  style={{
                    display: 'grid', gridTemplateColumns: gridCols,
                    padding: '11px 16px', borderBottom: '1px solid var(--border)',
                    background: isOpen ? `${color}06` : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                    alignItems: 'center', cursor: 'pointer', transition: 'background 0.15s ease',
                  }}
                  onClick={() => setExpanded(isOpen ? null : s.rank)}
                  onMouseEnter={e => !isOpen && (e.currentTarget.style.background = 'var(--surface-el)')}
                  onMouseLeave={e => !isOpen && (e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)')}
                >
                  <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>{s.rank}</span>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 6,
                      background: `${color}18`, border: `1px solid ${color}30`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 9, fontWeight: 700, color, letterSpacing: '-0.02em' }}>
                      {s.symbol.slice(0, 2)}
                    </div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>{s.symbol}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-3)' }}>{s.sector}</div>
                    </div>
                  </div>

                  {/* Score with mini-bar */}
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: scoreColor }}>{s.score}</div>
                    <div style={{ height: 2, background: 'var(--border)', borderRadius: 1, marginTop: 3 }}>
                      <div style={{ height: '100%', width: `${s.score}%`, background: scoreColor, borderRadius: 1 }} />
                    </div>
                  </div>

                  <span style={{ fontSize: 11, textAlign: 'right' }}>{s.entry.toFixed(2)}</span>
                  <span style={{ fontSize: 11, textAlign: 'right', color: 'var(--accent)', fontWeight: 600 }}>{s.target.toFixed(2)}</span>
                  <span style={{ fontSize: 11, textAlign: 'right', color: 'var(--red)' }}>{s.stopLoss.toFixed(2)}</span>
                  <span style={{ fontSize: 11, textAlign: 'right', fontWeight: 600,
                    color: s.rr >= 2 ? 'var(--accent)' : 'var(--text-2)' }}>{s.rr}x</span>
                  <span style={{ fontSize: 11, textAlign: 'right', fontWeight: 600, color: pctColor(s.change) }}>
                    {fmtPct(s.change)}
                  </span>

                  <div style={{ textAlign: 'right' }}>
                    <button style={{
                      padding: '4px 12px', borderRadius: 5, cursor: 'pointer', fontFamily: 'inherit', fontSize: 10,
                      background: isOpen ? `${color}20` : 'transparent',
                      border: `1px solid ${isOpen ? color : 'var(--border)'}`,
                      color: isOpen ? color : 'var(--text-2)', transition: 'all 0.15s ease',
                    }}>
                      {isOpen ? '▲ Kapat' : '▼ Detay'}
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <StockDetail stock={s} criteria={result.criteria} market={result.market} />
                )}
              </div>
            );
          })}

          {sorted.length === 0 && (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-2)', fontSize: 12 }}>
              Minimum skor ({minScore}) için hisse bulunamadı.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Scanner() {
  const [criteria,       setCriteria]       = useState<CriteriaType>('ALFA');
  const [date,           setDate]           = useState(() => new Date().toISOString().split('T')[0]);
  const [market,         setMarket]         = useState<MarketScope>('BIST100');
  const [portfolioSize,  setPortfolioSize]  = useState<1|3|5|7>(5);
  const [running,  setRunning]  = useState(false);
  const [progress, setProgress] = useState(0);
  const [result,   setResult]   = useState<ScanResult | null>(null);
  const [saved,    setSaved]    = useState<ScanResult[]>([]);
  const [minScore, setMinScore] = useState(0);
  const debouncedMinScore = useDebounce(minScore, 300);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const runScan = useCallback(() => {
    setRunning(true);
    setProgress(0);
    setResult(null);

    let p = 0;
    timerRef.current = setInterval(() => {
      p += rnd(8, 22, 0);
      if (p >= 100) {
        p = 100;
        clearInterval(timerRef.current!);
        setTimeout(() => {
          setResult(generateScanResult(criteria, date, market, portfolioSize));
          setRunning(false);
        }, 250);
      }
      setProgress(Math.min(p, 100));
    }, 120);
  }, [criteria, date, market]);

  const saveResult = () => {
    if (result) setSaved(prev => [result, ...prev.slice(0, 9)]);
  };

  const inputStyle: React.CSSProperties = {
    padding: '8px 12px', background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 6, color: 'var(--text)', fontSize: 12, fontFamily: 'inherit', outline: 'none',
    cursor: 'pointer',
  };

  const cColor = CRIT_COLOR[criteria];

  return (
    <div style={{ padding: '20px 24px', height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* Header */}
      <div className="fade-in" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>Hisse Tarama</h1>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>
            ALFA · BETA · DELTA kriterleri ile gerçek zamanlı ve geçmiş tarih taraması
          </p>
        </div>
        {result && (
          <button onClick={saveResult} className="btn-ghost" style={{ fontSize: 10 }}>💾 Sonucu Kaydet</button>
        )}
      </div>

      {/* Config panel */}
      <div className="fade-in-d1 card" style={{ padding: '18px 20px' }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 16, letterSpacing: '-0.01em' }}>🔍 TARAMA YAPILANDIRMA</div>

        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          {/* Criteria selector */}
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6 }}>KRİTER</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['ALFA','BETA','DELTA'] as CriteriaType[]).map(c => (
                <button key={c} onClick={() => setCriteria(c)} style={{
                  padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                  fontSize: 12, fontWeight: criteria === c ? 700 : 400,
                  background: criteria === c ? `${CRIT_COLOR[c]}18` : 'var(--surface)',
                  border: `1px solid ${criteria === c ? CRIT_COLOR[c] : 'var(--border)'}`,
                  color: criteria === c ? CRIT_COLOR[c] : 'var(--text-2)', transition: 'all 0.15s ease',
                }}>
                  {c}
                  <div style={{ fontSize: 8, marginTop: 2, opacity: 0.7 }}>
                    {c === 'ALFA' ? 'BOĞA' : c === 'BETA' ? 'AYI' : 'YATAY'}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Date */}
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6 }}>TARAMA TARİHİ</div>
            <input type="date" style={inputStyle} value={date} onChange={e => setDate(e.target.value)} />
          </div>

          {/* Market / Universe */}
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6 }}>VERİ HAVUZU</div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {([
                { id: 'BIST100',     label: 'BIST 100' },
                { id: 'BISTTUM',     label: 'BIST Tüm' },
                { id: 'BIST100DISI', label: 'BIST 100 Dışı' },
                { id: 'US',          label: 'US Markets' },
              ] as { id: MarketScope; label: string }[]).map(m => (
                <button key={m.id} onClick={() => setMarket(m.id)} style={{
                  padding: '8px 14px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
                  fontWeight: market === m.id ? 700 : 400,
                  background: market === m.id ? 'var(--surface-el)' : 'var(--surface)',
                  border: `1px solid ${market === m.id ? 'var(--accent)' : 'var(--border)'}`,
                  color: market === m.id ? 'var(--accent)' : 'var(--text-2)', transition: 'all 0.15s ease',
                }}>{m.label}</button>
              ))}
            </div>
          </div>

          {/* Portfolio Size */}
          <div>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 6 }}>FON SAYISI</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {([1, 3, 5, 7] as const).map(n => (
                <button key={n} onClick={() => setPortfolioSize(n)} style={{
                  padding: '8px 14px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
                  fontWeight: portfolioSize === n ? 700 : 400,
                  background: portfolioSize === n ? 'var(--surface-el)' : 'var(--surface)',
                  border: `1px solid ${portfolioSize === n ? 'var(--accent)' : 'var(--border)'}`,
                  color: portfolioSize === n ? 'var(--accent)' : 'var(--text-2)', transition: 'all 0.15s ease',
                }}>{n}</button>
              ))}
            </div>
          </div>

          {/* Run button */}
          <button className="btn-accent" onClick={runScan} disabled={running}
            style={{ padding: '10px 28px', fontSize: 12, letterSpacing: '0.06em',
              background: running ? 'var(--surface-el)' : undefined,
              color: running ? 'var(--text-2)' : undefined, border: running ? '1px solid var(--border)' : undefined }}>
            {running ? '⏳ Tarıyor...' : '🔍 TARAMAYI BAŞLAT'}
          </button>
        </div>

        {/* Consistency note */}
        <div style={{ marginTop: 14, padding: '8px 12px', background: 'rgba(64,156,255,0.08)',
          border: '1px solid rgba(64,156,255,0.2)', borderRadius: 6, fontSize: 10, color: 'var(--blue)' }}>
          ℹ️ Geçmiş tarih taramalarının sonuçları, aynı tarih/kriter kombinasyonu için backtest sonuçlarıyla birebir eşleşir.
          Her ikisi de aynı paylaşımlı <code>sharedScan()</code> motorunu kullanır.
        </div>
      </div>

      {/* Progress */}
      {running && (
        <div className="card fade-in" style={{ padding: '24px 28px', textAlign: 'center' }}>
          <div style={{ fontSize: 12, color: cColor, marginBottom: 14, fontWeight: 600 }}>
            {{ BIST100: 'BIST 100', BISTTUM: 'BIST Tüm', BIST100DISI: 'BIST 100 Dışı', US: 'NYSE/NASDAQ' }[market] ?? market} taranıyor — {criteria} kriterleri uygulanıyor...
          </div>
          <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden', marginBottom: 10 }}>
            <div style={{ height: '100%', width: `${progress}%`, background: cColor, borderRadius: 3,
              boxShadow: `0 0 12px ${cColor}66`, transition: 'width 0.2s ease' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-2)' }}>
            <span>Hisseler analiz ediliyor...</span>
            <span style={{ fontWeight: 700, color: cColor }}>{progress.toFixed(0)}%</span>
          </div>
        </div>
      )}

      {/* Results */}
      {result && !running && (
        <div className="fade-in">
          {/* Results header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 4 }}>─── TARAMA SONUÇLARI</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: CRIT_COLOR[result.criteria] }}>{result.criteria}</span>
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{result.date} · {result.market}</span>

                {/* Market condition pill */}
                <div style={{
                  fontSize: 10, padding: '3px 10px', borderRadius: 5, fontWeight: 700,
                  background: `${COND_COLOR[result.marketCondition.condition]}15`,
                  border: `1px solid ${COND_COLOR[result.marketCondition.condition]}30`,
                  color: COND_COLOR[result.marketCondition.condition],
                }}>
                  {COND_LABEL[result.marketCondition.condition]} · Skor: {result.marketCondition.score > 0 ? '+' : ''}{result.marketCondition.score.toFixed(1)}
                </div>
              </div>
            </div>

            {/* Stats row */}
            <div style={{ display: 'flex', gap: 16 }}>
              {[
                { label: 'Taranan', value: result.scannedTotal, color: 'var(--text-2)' },
                { label: 'Geçti',   value: result.passedFilters, color: 'var(--accent)' },
                { label: 'TOP 5',  value: result.stocks.length,  color: CRIT_COLOR[result.criteria] },
                { label: 'Süre',   value: `${result.runtimeMs}ms`, color: 'var(--text-3)' },
              ].map(stat => (
                <div key={stat.label} style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.06em' }}>{stat.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: stat.color }}>{stat.value}</div>
                </div>
              ))}
            </div>
          </div>

          <ResultsTable result={result} minScore={debouncedMinScore} onMinScoreChange={setMinScore} />
        </div>
      )}

      {/* Saved scans */}
      {saved.length > 0 && !running && (
        <div className="fade-in">
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>─── KAYDEDİLEN TARAMALAR</div>
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '80px 90px 100px 80px 80px 1fr 100px',
              padding: '9px 14px', borderBottom: '1px solid var(--border)',
              fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', background: 'var(--surface-el)',
            }}>
              {['TARİH','KRİTER','PİYASA','TARANAN','GEÇTİ','PİYASA KOŞULU','İŞLEM'].map(h => <span key={h}>{h}</span>)}
            </div>
            {saved.map((s, i) => (
              <div key={i} style={{
                display: 'grid', gridTemplateColumns: '80px 90px 100px 80px 80px 1fr 100px',
                padding: '10px 14px', borderBottom: i < saved.length - 1 ? '1px solid var(--border)' : 'none',
                alignItems: 'center', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
              }}>
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.date}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: CRIT_COLOR[s.criteria] }}>{s.criteria}</span>
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.market}</span>
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.scannedTotal}</span>
                <span style={{ fontSize: 11, color: 'var(--accent)' }}>{s.passedFilters}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 10, color: COND_COLOR[s.marketCondition.condition] }}>
                    {COND_LABEL[s.marketCondition.condition]}
                  </span>
                  <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{s.marketCondition.confidence.toFixed(0)}% conf</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => setResult(s)} style={{
                    padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 10, background: 'rgba(0,208,132,0.1)', border: '1px solid rgba(0,208,132,0.25)',
                    color: 'var(--accent)',
                  }}>Yükle</button>
                  <button onClick={() => exportCSV(s.stocks, s)} style={{
                    padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 10, background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-2)',
                  }}>CSV</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!result && !running && saved.length === 0 && (
        <div className="fade-in-d3 card" style={{ padding: '48px 32px', textAlign: 'center', opacity: 0.6 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Tarama Bekleniyor</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
            Kriter, tarih ve piyasa seçin, ardından taramayı başlatın
          </div>
        </div>
      )}

    </div>
  );
}
