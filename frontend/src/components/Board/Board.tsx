import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";
import { sendAction, getGameState } from "../../services/api";

export function Board() {
  const { gameState, gameId, setGameState, setLoading, appendLog } = useGameStore();

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

  async function handlePlayCard(cardId: string, actionType: "play_land" | "cast_spell") {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: actionType, card_id: cardId });
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
          />
        ) : (
          <div key={i} className="seat-empty" />
        )
      )}
    </div>
  );
}
