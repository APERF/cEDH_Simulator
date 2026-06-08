import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";

export function Board() {
  const { gameState, actionLog } = useGameStore();

  if (!gameState) return <div className="board empty">No active game.</div>;

  return (
    <div className="board">
      <div className="turn-info">
        <span>Turn {gameState.turn}</span>
        <span>{gameState.phase} — {gameState.step}</span>
        <span>Stack: {gameState.stack_size}</span>
        {gameState.winner && (
          <span className="winner">Winner: {gameState.winner}</span>
        )}
      </div>

      <div className="players">
        {gameState.players.map((p) => (
          <PlayerPanel
            key={p.id}
            player={p}
            isActive={p.id === gameState.active_player_id}
          />
        ))}
      </div>

      <div className="action-log">
        <h3>Game Log</h3>
        <ul>
          {actionLog.map((entry, i) => (
            <li key={i}>{entry}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
