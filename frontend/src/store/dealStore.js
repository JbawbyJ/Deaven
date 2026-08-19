import { create } from 'zustand';

export const useDealStore = create((set) => ({
  deals: [],
  selectedDeal: null,
  activeTier: 'all',
  stats: {},

  setDeals: (deals) => set({ deals }),
  setSelectedDeal: (selectedDeal) => set({ selectedDeal }),
  setActiveTier: (activeTier) => set({ activeTier }),
  setStats: (stats) => set({ stats }),
}));
