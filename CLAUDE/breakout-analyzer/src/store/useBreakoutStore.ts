import { create } from 'zustand';
import type { BreakoutStock } from '@/lib/mockData';

interface BreakoutStore {
  stocks: BreakoutStock[];
  selectedSymbol: string | null;
  minScore: number;
  sortBy: 'score' | 'volume' | 'change';
  searchQuery: string;
  viewMode: 'grid' | 'table';
  setStocks: (stocks: BreakoutStock[]) => void;
  setSelected: (symbol: string | null) => void;
  setMinScore: (v: number) => void;
  setSortBy: (v: BreakoutStore['sortBy']) => void;
  setSearch: (v: string) => void;
  setViewMode: (v: BreakoutStore['viewMode']) => void;
}

export const useBreakoutStore = create<BreakoutStore>(set => ({
  stocks: [],
  selectedSymbol: null,
  minScore: 60,
  sortBy: 'score',
  searchQuery: '',
  viewMode: 'table',
  setStocks: stocks => set({ stocks }),
  setSelected: selectedSymbol => set({ selectedSymbol }),
  setMinScore: minScore => set({ minScore }),
  setSortBy: sortBy => set({ sortBy }),
  setSearch: searchQuery => set({ searchQuery }),
  setViewMode: viewMode => set({ viewMode }),
}));
