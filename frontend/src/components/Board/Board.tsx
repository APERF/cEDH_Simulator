import { useState } from "react";
import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";
import { FetchModal } from "./FetchModal";
import { sendAction, getGameState } from "../../services/api";
import type { FetchOption } from "../../types/game";

export function Board() {
  const { gameState, gameId, setGameState, setLoading, appendLog } = useGameStore();
  const [fetchModal, setFetchModal] = useState<FetchOption[] | null>(null);

  if (!gameState) {
    return <div className="board-empty">No active game.</div>;
  }

  const isHumanTurn = !!gameState.players.find(
    (p) => p.is_human && p.id === gameState.active_player_id
  );

  async function handleCastCommander(cardId: string) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "cast_commander", card_id: cardId });
      appendLog(result.log);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  async function handlePlayCard(
    cardId: string,
    actionType: "play_land" | "cast_spell",
    opts?: { payLife?: boolean }
  ) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: actionType,
        card_id: cardId,
        ...(opts?.payLife !== undefined ? { pay_life: opts.payLife } : {}),
      });
      appendLog(result.log);
      if (result.status === "fetch" && result.fetch_options) {
        setFetchModal(result.fetch_options);
      } else {
        setGameState(await getGameState(gameId));
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleCompleteFetch(cardId: string) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "complete_fetch", card_id: cardId });
      appendLog(result.log);
      setFetchModal(null);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  async function handleTapLand(cardId: string, color?: string, untap = false) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: untap ? "untap_land" : "tap_land",
        card_id: cardId,
        ...(color ? { color } : {}),
      });
      appendLog(result.log);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  // Players arrive in turn order (index 0 = first seat).
  // Clockwise from top-left in a 2×2 grid: TL→TR→BR→BL.
  // CSS grid row-major order is TL→TR→BL→BR, so swap indices 2 and 3.
  const [p0, p1, p2, p3] = gameState.players;
  const seats = [p0 ?? null, p1 ?? null, p3 ?? null, p2 ?? null];

  return (
    <>
    {fetchModal && (
      <FetchModal
        options={fetchModal}
        onSelect={handleCompleteFetch}
        onClose={() => setFetchModal(null)}
      />
    )}
    <div className="commander-table">
      {seats.map((p, i) =>
        p ? (
          <PlayerPanel
            key={p.id}
            player={p}
            isActive={p.id === gameState.active_player_id}
            isHumanTurn={isHumanTurn}
            currentStep={gameState.step}
            onCastCommander={handleCastCommander}
            onPlayCard={handlePlayCard}
            onTapLand={handleTapLand}
          />
        ) : (
          <div key={i} className="seat-empty" />
        )
      )}
    </div>
    </>
  );
}
