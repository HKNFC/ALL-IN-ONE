import { create } from 'zustand'

export interface Position {
  id: string
  symbol: string
  shares: number
  avgPrice: number
  currentPrice: number
  value: number
  pnl: number
  pnlPct: number
}

interface PortfolioStore {
  positions: Position[]
  totalValue: number
  totalPnl: number
  setPositions: (positions: Position[]) => void
}

export const usePortfolioStore = create<PortfolioStore>((set) => ({
  positions: [],
  totalValue: 0,
  totalPnl: 0,
  setPositions: (positions) => {
    const totalValue = positions.reduce((sum, p) => sum + p.value, 0)
    const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0)
    set({ positions, totalValue, totalPnl })
  },
}))
