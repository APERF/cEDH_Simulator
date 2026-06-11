import { useEffect, useRef, useState, Fragment } from "react";
import { useParams, Link } from "react-router-dom";
import { Board } from "../components/Board/Board";
import { MulliganPhase } from "../components/MulliganPhase/MulliganPhase";
import { StackOverlay } from "../components/StackOverlay/StackOverlay";
import { useGameStore } from "../store/gameStore";
import { getGameState, sendAction, advanceAiTurn } from "../services/api";

const STEP_ORDER = [
  "untap", "upkeep", "draw", "precombat_main",
  "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_of_combat",
  "postcombat_main",
  "end", "cleanup",
];

const STEP_LABELS: Record<string, string> = {
  untap: "UT",
  upkeep: "UP",
  draw: "DR",
  precombat_main: "M1",
  begin_combat: "BC",
  declare_attackers: "AT",
  declare_blockers: "BL",
  combat_damage: "DM",
  end_of_combat: "EC",
  postcombat_main: "M2",
  end: "EN",
  cleanup: "CL",
};

const PHASE_GROUPS = [
  { label: "Beginning", steps: ["untap", "upkeep", "draw"] },
  { label: "Pre-Main", steps: ["precombat_main"] },
  { label: "Combat", steps: ["begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_of_combat"] },
  { label: "Post-Main", steps: ["postcombat_main"] },
  { label: "Ending", steps: ["end", "cleanup"] },
];

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const { gameState, actionLog, appendLog, setGameState, setLoading, isLoading } = useGameStore();
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [holdingPriority, setHoldingPriority] = useState(false);
  const autoAdvancingRef = useRef(false);
  const prevStackTopIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!gameId) return;
    setFetchError(null);
    getGameState(gameId)
      .then(setGameState)
      .catch((e) => setFetchError(e?.response?.data?.detail ?? e?.message ?? "Failed to load game"));
  }, [gameId]);

  // Auto-advance through AI turns, but stop when the stack needs human priority
  useEffect(() => {
    if (!gameId || !gameState) return;
    if (gameState.mulligan_phase !== "playing") return;
    if (gameState.winner) return;
    const humanPlayer = gameState.players.find(p => p.is_human);
    if (!humanPlayer || gameState.active_player_id === humanPlayer.id) return;
    // Stack has items — human has priority regardless of whose turn it is
    if ((gameState.stack ?? []).length > 0) return;
    if (autoAdvancingRef.current) return;

    autoAdvancingRef.current = true;
    setLoading(true);
    advanceAiTurn(gameId)
      .then(result => {
        appendLog(result.log);
        return getGameState(gameId);
      })
      .then(setGameState)
      .catch(console.error)
      .finally(() => {
        autoAdvancingRef.current = false;
        setLoading(false);
      });
  // stack_size in deps so auto-advance resumes when human clears the stack
  }, [gameState?.active_player_id, gameState?.mulligan_phase, gameState?.stack_size]);

  // When a new spell appears on top of the stack (player just cast while holding priority),
  // drop hold-priority so the overlay shows for the new spell automatically.
  useEffect(() => {
    const topId = (gameState?.stack ?? [])[0]?.id ?? null;
    if (topId && topId !== prevStackTopIdRef.current) {
      prevStackTopIdRef.current = topId;
      setHoldingPriority(false);
    }
  }, [gameState?.stack?.[0]?.id]);

  const humanPlayer = gameState?.players.find(p => p.is_human);
  const isHumanTurn = !!humanPlayer && gameState?.active_player_id === humanPlayer.id;

  async function handlePassPriority() {
    if (!gameId || !isHumanTurn) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "pass_priority" });
      appendLog(result.log);
      setGameState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  const currentStepIdx = gameState ? STEP_ORDER.indexOf(gameState.step) : -1;
  const activeName = gameState?.players.find(p => p.id === gameState.active_player_id)?.name ?? "—";

  return (
    <div className="game-layout">
      {gameState && (
        <div className="phase-bar">
          <div className="pb-left">
            <div className="pb-item">
              <span className="pb-label">Turn</span>
              <span className="pb-value">{gameState.turn}</span>
            </div>
            <button
              className="primary pb-btn"
              onClick={handlePassPriority}
              disabled={isLoading || !isHumanTurn}
            >
              {isLoading && !isHumanTurn ? "AI thinking..." : "Move Phases"}
            </button>
            <Link to="/"><button className="pb-btn">&#x2190; New Game</button></Link>
          </div>

          <div className="pb-steps">
            {PHASE_GROUPS.map((group, gi) => (
              <Fragment key={group.label}>
                {gi > 0 && <div className="pb-phase-sep" />}
                {group.steps.map(step => {
                  const idx = STEP_ORDER.indexOf(step);
                  const isActive = step === gameState.step;
                  const isPast = idx < currentStepIdx;
                  return (
                    <div
                      key={step}
                      className={`pb-step${isActive ? " active" : ""}${isPast ? " past" : ""}`}
                      title={step.replace(/_/g, " ")}
                    >
                      {STEP_LABELS[step]}
                    </div>
                  );
                })}
              </Fragment>
            ))}
          </div>

          <div className="pb-right">
            <div className="pb-item">
              <span className="pb-label">Stack</span>
              <span className="pb-value">{gameState.stack_size}</span>
            </div>
            {gameState.winner && (
              <span className="pb-winner">&#x1F3C6; {gameState.winner} wins</span>
            )}
          </div>
        </div>
      )}

      <div className="game-main">
        <div className="board-area" style={{ position: "relative" }}>
          {fetchError && (
            <div style={{ color: "var(--red)", padding: "12px", fontSize: "13px" }}>
              Error loading game: {fetchError}
            </div>
          )}
          {gameState && gameState.mulligan_phase !== "playing" ? (
            <MulliganPhase gameState={gameState} onStateChange={setGameState} />
          ) : (
            <>
              <Board />
              {gameState && (gameState.stack ?? []).length > 0 && holdingPriority && (
                <div className="hold-priority-banner">
                  <span className="hold-priority-info">
                    Holding priority — {gameState.stack.length} spell{gameState.stack.length !== 1 ? "s" : ""} on stack
                    <span className="hold-priority-top"> · Next to resolve: <strong>{gameState.stack[0]?.name}</strong></span>
                  </span>
                  <button className="primary hold-priority-return" onClick={() => setHoldingPriority(false)}>
                    Return to Stack
                  </button>
                </div>
              )}
              {gameState && (gameState.stack ?? []).length > 0 && !holdingPriority && (
                <StackOverlay
                  gameState={gameState}
                  onStateChange={setGameState}
                  onHoldPriority={() => setHoldingPriority(true)}
                />
              )}
            </>
          )}
        </div>

        <div className={`game-sidebar${sidebarCollapsed ? " collapsed" : ""}`}>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(c => !c)}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? "«" : "»"}
          </button>

          {!sidebarCollapsed && (
            <>
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
