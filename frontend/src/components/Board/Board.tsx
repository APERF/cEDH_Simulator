import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";

export function Board() {
  const { gameState } = useGameStore();

  if (!gameState) {
    return <div className="board-empty">No active game.</div>;
  }

  const aiPlayers = gameState.players.filter((p) => !p.is_human);
  const humanPlayer = gameState.players.find((p) => p.is_human);

  return (
    <>
      <div className="opponents-row">
        {aiPlayers.map((p) => (
          <PlayerPanel key={p.id} player={p} isActive={p.id === gameState.active_player_id} />
        ))}
      </div>

      {humanPlayer && (
        <div className="human-row">
          <PlayerPanel player={humanPlayer} isActive={humanPlayer.id === gameState.active_player_id} />
        </div>
      )}
    </>
  );
}
