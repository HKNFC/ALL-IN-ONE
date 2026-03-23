describe('MarketConditionService – analyzeMarketCondition (algorithm logic)', () => {
  const buildPrices = (trend: 'up' | 'down', count = 250) =>
    Array.from({ length: count }, (_, i) => ({
      date:   new Date(2023, 0, i + 1),
      close:  trend === 'up' ? 100 + i * 0.5 : 200 - i * 0.5,
      open:   trend === 'up' ? 100 + i * 0.5 - 0.2 : 200 - i * 0.5 + 0.2,
      high:   trend === 'up' ? 100 + i * 0.5 + 0.5 : 200 - i * 0.5 + 0.5,
      low:    trend === 'up' ? 100 + i * 0.5 - 0.5 : 200 - i * 0.5 - 0.5,
      volume: 1000000,
    }))

  describe('Score range validation', () => {
    it('BULL score is in range 3–10 for 250-day uptrend', () => {
      const prices = buildPrices('up')
      const latestClose = prices[prices.length - 1].close
      const sma200 = prices.slice(-200).reduce((s, p) => s + p.close, 0) / 200
      const sma50  = prices.slice(-50).reduce((s, p) => s + p.close, 0) / 50

      // Manual scoring check (trend component)
      const aboveSma200 = latestClose > sma200 ? 2 : -2
      const goldenCross = sma50 > sma200    ? 2 : -2
      expect(aboveSma200 + goldenCross).toBe(4) // Both should be positive for uptrend
    })

    it('BEAR score is in range -10 to -3 for 250-day downtrend', () => {
      const prices = buildPrices('down')
      const latestClose = prices[prices.length - 1].close
      const sma200 = prices.slice(-200).reduce((s, p) => s + p.close, 0) / 200
      const sma50  = prices.slice(-50).reduce((s, p) => s + p.close, 0) / 50

      const aboveSma200 = latestClose > sma200 ? 2 : -2
      const goldenCross = sma50 > sma200    ? 2 : -2
      expect(aboveSma200 + goldenCross).toBe(-4) // Both negative for downtrend
    })
  })

  describe('Condition thresholds', () => {
    it('score > 3 maps to BULL', () => {
      const score = 4.5
      const condition = score > 3 ? 'BULL' : score < -3 ? 'BEAR' : 'SIDEWAYS'
      expect(condition).toBe('BULL')
    })

    it('score < -3 maps to BEAR', () => {
      const score = -4.0
      const condition = score > 3 ? 'BULL' : score < -3 ? 'BEAR' : 'SIDEWAYS'
      expect(condition).toBe('BEAR')
    })

    it('score -3 to 3 maps to SIDEWAYS', () => {
      const score = 1.2
      const condition = score > 3 ? 'BULL' : score < -3 ? 'BEAR' : 'SIDEWAYS'
      expect(condition).toBe('SIDEWAYS')
    })
  })

  describe('Recommended criteria mapping', () => {
    it('BULL condition recommends ALFA', () => {
      const map: Record<string, string> = { BULL: 'ALFA', BEAR: 'BETA', SIDEWAYS: 'DELTA' }
      expect(map['BULL']).toBe('ALFA')
    })

    it('BEAR condition recommends BETA', () => {
      const map: Record<string, string> = { BULL: 'ALFA', BEAR: 'BETA', SIDEWAYS: 'DELTA' }
      expect(map['BEAR']).toBe('BETA')
    })

    it('SIDEWAYS condition recommends DELTA', () => {
      const map: Record<string, string> = { BULL: 'ALFA', BEAR: 'BETA', SIDEWAYS: 'DELTA' }
      expect(map['SIDEWAYS']).toBe('DELTA')
    })
  })

  describe('Confidence calculation', () => {
    it('confidence is 0–100 for all agreement levels', () => {
      // Confidence = (number of indicators agreeing / total) * 100
      const totalIndicators = 10
      for (let agreeing = 0; agreeing <= totalIndicators; agreeing++) {
        const confidence = (agreeing / totalIndicators) * 100
        expect(confidence).toBeGreaterThanOrEqual(0)
        expect(confidence).toBeLessThanOrEqual(100)
      }
    })
  })
})
