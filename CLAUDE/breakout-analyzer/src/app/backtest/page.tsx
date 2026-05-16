export default function BacktestPage() {
  return (
    <div style={{ padding: '20px 24px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>↺ Backtest</h1>
      <p style={{ marginTop: 4, fontSize: 11, color: 'var(--text-2)' }}>Python FastAPI backend bağlantısı ile aktif olacak</p>
      <div className="card fade-in" style={{ marginTop: 16, padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>
        Backtest motoru Python backend&apos;a bağlandığında burada görünecek
      </div>
    </div>
  );
}
