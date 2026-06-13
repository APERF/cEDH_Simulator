import axios from "axios";
import type { GameState, MetaDeck, GameAction } from "../types/game";

const api = axios.create({ baseURL: "http://localhost:8000/api" });

export async function createGame(
  playerName: string,
  decklist: string,
  opponentCommanders: string[],
  seatPreference?: number
): Promise<{ game_id: string }> {
  const { data } = await api.post("/game/new", {
    player_decklist: { name: playerName, decklist },
    opponent_commanders: opponentCommanders,
    seat_preference: seatPreference ?? null,
  });
  return data;
}

export async function getGameState(gameId: string): Promise<GameState> {
  const { data } = await api.get(`/game/${gameId}`);
  return data;
}

export async function mulliganAction(
  gameId: string,
  action: "mulligan" | "keep" | "bottom",
  cardIds?: string[]
): Promise<GameState> {
  const { data } = await api.post(`/game/${gameId}/mulligan`, {
    action,
    card_ids: cardIds ?? [],
  });
  return data;
}

export async function mulliganAiTurn(gameId: string): Promise<GameState> {
  const { data } = await api.post(`/game/${gameId}/mulligan/ai_turn`);
  return data;
}

export async function sendAction(
  gameId: string,
  action: GameAction
): Promise<{ status: string; log: string[]; fetch_options?: import("../types/game").FetchOption[] }> {
  const { data } = await api.post(`/game/${gameId}/action`, action);
  return data;
}

export async function advanceAiTurn(
  gameId: string
): Promise<{ status: string; log: string[] }> {
  const { data } = await api.post(`/game/${gameId}/ai-turn`);
  return data;
}

export async function advanceAiStep(
  gameId: string
): Promise<{ status: string; log: string[]; is_human_turn: boolean }> {
  const { data } = await api.post(`/game/${gameId}/ai-step`);
  return data;
}

export async function listMetaDecks(): Promise<MetaDeck[]> {
  const { data } = await api.get("/decks/meta");
  return data.decks;
}

export async function validateDecklist(
  name: string,
  decklist: string
): Promise<{ valid: boolean; card_count: number; size_error: string | null; banned_cards: string[] }> {
  const { data } = await api.post("/decks/validate", { name, decklist });
  return data;
}

export async function fetchMoxfieldDeck(
  url: string
): Promise<{ name: string; decklist: string }> {
  const { data } = await api.get("/decks/from-moxfield", { params: { url } });
  return data;
}

export async function fetchEdhtop16Deck(
  commander: string
): Promise<{ name: string; decklist: string; standing: number; player: string; tournament: string }> {
  const { data } = await api.get("/decks/from-edhtop16", { params: { commander } });
  return data;
}

export async function searchCard(name: string) {
  const { data } = await api.get("/cards/search", { params: { name } });
  return data;
}
