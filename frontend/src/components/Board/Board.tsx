import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";

export function Board() {
  const { gameState } = useGameStore();

  if (!gameState) {
    return <div className="board-empty">No active game.</div>;
  }

  const aiPlayers = gameState.players.filter((p) => !p.is_human);
  const humanPlayer = gameState.players.find((p) => p.is_human);

  // 2×2 Commander table: AI fills top-left, top-right, bottom-left; human is bottom-right
  const seats = [
    aiPlayers[0] ?? null,
    aiPlayers[1] ?? null,
    aiPlayers[2] ?? null,
    humanPlayer ?? null,
  ];

  return (
    <div className="commander-table">
      {seats.map((p, i) =>
        p ? (
          <PlayerPanel key={p.id} player={p} isActive={p.id === gameState.active_player_id} />
        ) : (
          <div key={i} className="seat-empty" />
        )
      )}
    </div>
  );
}
