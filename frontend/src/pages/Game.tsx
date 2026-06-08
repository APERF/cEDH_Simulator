import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { Board } from "../components/Board/Board";
import { useGameStore } from "../store/gameStore";
import { getGameState, sendAction, advanceAiTurn } from "../services/api";

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const { gameState, setGameState, appendLog, setLoading } = useGameStore();

  useEffect(() => {
    if (!gameId) return;
    getGameState(gameId).then(setGameState).catch(() => {});
  }, [gameId]);

  async function handlePassPriority() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "pass_priority" });
      appendLog(result.log);
      const state = await getGameState(gameId);
      setGameState(state);
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
      const state = await getGameState(gameId);
      setGameState(state);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="game-page">
      <Board />
      <div className="controls">
        <button onClick={handlePassPriority}>Pass Priority</button>
        <button onClick={handleAiTurn}>Advance AI Turn</button>
      </div>
    </div>
  );
}
