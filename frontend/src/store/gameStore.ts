import { create } from "zustand";
import type { GameState, MetaDeck } from "../types/game";

interface GameStore {
  gameId: string | null;
  gameState: GameState | null;
  metaDecks: MetaDeck[];
  actionLog: string[];
  isLoading: boolean;
  error: string | null;

  setGameId: (id: string) => void;
  setGameState: (state: GameState) => void;
  setMetaDecks: (decks: MetaDeck[]) => void;
  appendLog: (entries: string[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  gameId: null,
  gameState: null,
  metaDecks: [],
  actionLog: [],
  isLoading: false,
  error: null,

  setGameId: (id) => set({ gameId: id }),
  setGameState: (state) => set({ gameState: state }),
  setMetaDecks: (decks) => set({ metaDecks: decks }),
  appendLog: (entries) =>
    set((s) => ({ actionLog: [...s.actionLog, ...entries] })),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  reset: () =>
    set({
      gameId: null,
      gameState: null,
      actionLog: [],
      isLoading: false,
      error: null,
    }),
}));
