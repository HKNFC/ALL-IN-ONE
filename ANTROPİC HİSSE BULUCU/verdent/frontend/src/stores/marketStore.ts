import { create } from 'zustand'

interface MarketStore {
  marketStatus: 'open' | 'closed'
  setMarketStatus: (status: 'open' | 'closed') => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  marketStatus: 'closed',
  setMarketStatus: (status) => set({ marketStatus: status }),
}))
