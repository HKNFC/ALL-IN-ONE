interface ScoreRingProps { score: number; size?: number; }

export function ScoreRing({ score, size = 48 }: ScoreRingProps) {
  const r = (size / 2) - 4;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color = score >= 80 ? 'var(--bull)' : score >= 60 ? 'var(--sideways)' : 'var(--bear)';
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--border)" strokeWidth={3} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color}
          strokeWidth={3} strokeLinecap="round"
          strokeDasharray={`${filled} ${circ - filled}`}
          style={{ transition: 'stroke-dasharray 0.5s ease', filter: `drop-shadow(0 0 4px ${color})` }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        fontSize: size < 48 ? 10 : 12, fontWeight: 700,
        color, fontFamily: 'var(--font-mono)',
      }}>{score}</div>
    </div>
  );
}
