import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Board } from "../components/Board/Board";
import { MulliganPhase } from "../components/MulliganPhase/MulliganPhase";
import { useGameStore } from "../store/gameStore";
import { getGameState, sendAction, advanceAiTurn } from "../services/api";

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const { gameState, actionLog, appendLog, setGameState, setLoading, isLoading } = useGameStore();
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    if (!gameId) return;
    setFetchError(null);
    getGameState(gameId)
      .then(setGameState)
      .catch((e) => setFetchError(e?.response?.data?.detail ?? e?.message ?? "Failed to load game"));
  }, [gameId]);

  async function handlePassPriority() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "pass_priority" });
      appendLog(result.log);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  async function handleAiTurn() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await advanceAiTurn(gameId);
      appendLog(result.log);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="game-layout">
      {gameState && (
        <div className="phase-bar">
          <div className="pb-item">
            <span className="pb-label">Turn</span>
            <span className="pb-value">{gameState.turn}</span>
          </div>
          <div className="pb-item">
            <span className="pb-label">Active</span>
            <span className="pb-value">
              {gameState.players.find(p => p.id === gameState.active_player_id)?.name ?? "—"}
            </span>
          </div>
          <div className="pb-item">
            <span className="pb-label">Phase</span>
            <span className="pb-value">{gameState.phase.replace(/_/g, " ")}</span>
          </div>
          <div className="pb-item">
            <span className="pb-label">Step</span>
            <span className="pb-value">{gameState.step.replace(/_/g, " ")}</span>
          </div>
          <div className="pb-item">
            <span className="pb-label">Stack</span>
            <span className="pb-value">{gameState.stack_size}</span>
          </div>
          {gameState.winner && (
            <span className="pb-winner">&#x1F3C6; {gameState.winner} wins</span>
          )}
        </div>
      )}

      <div className="game-main">
        <div className="board-area">
          {fetchError && (
            <div style={{ color: "var(--red)", padding: "12px", fontSize: "13px" }}>
              Error loading game: {fetchError}
            </div>
          )}
          {gameState && gameState.mulligan_phase !== "playing" ? (
            <MulliganPhase gameState={gameState} onStateChange={setGameState} />
          ) : (
            <Board />
          )}
        </div>

        <div className="game-sidebar">
          <div className="sidebar-controls">
            <button onClick={handlePassPriority} disabled={isLoading}>
              Pass Priority
            </button>
            <button onClick={handleAiTurn} disabled={isLoading}>
              {isLoading ? "Thinking..." : "Advance AI Turn"}
            </button>
            <Link to="/" style={{ width: "100%" }}>
              <button style={{ width: "100%" }}>&#x2190; New Game</button>
            </Link>
          </div>

          <div className="game-log">
            <h3>Game Log</h3>
            <div className="log-entries">
              {actionLog.length === 0 ? (
                <span className="log-empty">No actions yet.</span>
              ) : (
                [...actionLog].reverse().map((entry, i) => (
                  <div key={i} className="log-entry">{entry}</div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
