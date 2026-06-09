import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";

export function Board() {
  const { gameState } = useGameStore();

  if (!gameState) {
    return <div className="board-empty">No active game.</div>;
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
          <PlayerPanel key={p.id} player={p} isActive={p.id === gameState.active_player_id} />
        ) : (
          <div key={i} className="seat-empty" />
        )
      )}
    </div>
  );
}
