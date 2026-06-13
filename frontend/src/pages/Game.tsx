import { useEffect, useRef, useState, Fragment } from "react";
import { createPortal, flushSync } from "react-dom";
import { useParams, Link } from "react-router-dom";
import { Board } from "../components/Board/Board";
import { MulliganPhase } from "../components/MulliganPhase/MulliganPhase";
import { StackOverlay } from "../components/StackOverlay/StackOverlay";
import { useGameStore } from "../store/gameStore";
import { getGameState, sendAction, advanceAiStep } from "../services/api";
import type { GameState } from "../types/game";

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

function stepDelay(): number {
  return 3000 + Math.random() * 2000; // 3 – 5 s
}

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms));
}

// ── Flying card animation ────────────────────────────────────────────────────

interface CardRect { left: number; top: number; width: number; height: number; }
interface FlyingCard { key: string; cardId: string; imageUri: string; fromRect: CardRect; toRect: CardRect; }

function collectAnimIntents(
  prevState: GameState | null,
  newState: GameState,
  knownCmdIds: Set<string>,
): Array<{ cardId: string; imageUri: string; fromRect: CardRect }> {
  if (!prevState) return [];

  const prevBfIds = new Set<string>();
  for (const p of prevState.players) {
    for (const c of [...(p.permanents ?? []), ...(p.lands ?? [])]) prevBfIds.add(c.id);
  }

  const intents: Array<{ cardId: string; imageUri: string; fromRect: CardRect }> = [];

  for (const player of newState.players) {
    for (const card of [...(player.permanents ?? []), ...(player.lands ?? [])]) {
      if (prevBfIds.has(card.id) || !card.image_uri) continue;

      const isCommander = knownCmdIds.has(card.id);
      const sourceEl = document.querySelector(
        isCommander ? `[data-cmdzone="${player.id}"]` : `[data-hand="${player.id}"]`
      );
      if (!sourceEl) continue;

      const r = sourceEl.getBoundingClientRect();
      const h = Math.min(Math.max(r.height * 0.7, 44), 88);
      const w = h * (63 / 88);
      intents.push({
        cardId: card.id,
        imageUri: card.image_uri,
        fromRect: {
          left: r.left + r.width / 2 - w / 2,
          top: r.top + (r.height - h) / 2,
          width: w,
          height: h,
        },
      });
    }
  }

  return intents;
}

const ANIM_DURATION_MS = 550;

function FlyingCardEl({ imageUri, fromRect, toRect, onDone }: {
  imageUri: string;
  fromRect: CardRect;
  toRect: CardRect;
  onDone: () => void;
}) {
  const [flying, setFlying] = useState(false);
  const firedRef = useRef(false);

  function fire() {
    if (!firedRef.current) {
      firedRef.current = true;
      onDone();
    }
  }

  useEffect(() => {
    let r2: number;
    let safetyTimer: ReturnType<typeof setTimeout>;
    const r1 = requestAnimationFrame(() => {
      r2 = requestAnimationFrame(() => {
        setFlying(true);
        // Safety: reveal the card even if onTransitionEnd never fires
        safetyTimer = setTimeout(fire, ANIM_DURATION_MS + 100);
      });
    });
    return () => {
      cancelAnimationFrame(r1);
      cancelAnimationFrame(r2!);
      clearTimeout(safetyTimer!);
    };
  }, []);

  const r = flying ? toRect : fromRect;
  return createPortal(
    <img
      src={imageUri}
      alt=""
      style={{
        position: "fixed",
        left: r.left,
        top: r.top,
        width: r.width,
        height: r.height,
        borderRadius: "6px",
        objectFit: "cover",
        zIndex: 8500,
        pointerEvents: "none",
        boxShadow: "0 8px 32px rgba(0,0,0,0.8), 0 0 0 2px rgba(255,215,0,0.45)",
        transition: flying
          ? `left ${ANIM_DURATION_MS}ms cubic-bezier(0.25,0.46,0.45,0.94), top ${ANIM_DURATION_MS}ms cubic-bezier(0.25,0.46,0.45,0.94), width ${ANIM_DURATION_MS}ms ease, height ${ANIM_DURATION_MS}ms ease`
          : "none",
      }}
      onTransitionEnd={(e) => {
        if (e.propertyName === "left") fire();
      }}
    />,
    document.body
  );
}

// ── Game component ───────────────────────────────────────────────────────────

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const { gameState, actionLog, appendLog, setGameState, setLoading, isLoading } = useGameStore();
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [holdingPriority, setHoldingPriority] = useState(false);
  const [aiThinking, setAiThinking] = useState(false);
  const [aiThinkingName, setAiThinkingName] = useState("");
  const [flyingCards, setFlyingCards] = useState<FlyingCard[]>([]);
  const aiLoopActiveRef = useRef(false);
  const prevStackTopIdRef = useRef<string | null>(null);
  const prevStateRef = useRef<GameState | null>(null);
  const knownCmdIdsRef = useRef<Set<string>>(new Set());

  // Used only for AI-driven state updates (runAiStepLoop + StackOverlay resolutions).
  // Diffs old→new to detect cards entering the battlefield and launches flying animations.
  // Wrapped in try-catch so animation bugs never crash the game UI.
  function applyNewState(newState: GameState) {
    try {
      for (const p of newState.players) {
        for (const c of (p.commanders ?? [])) knownCmdIdsRef.current.add(c.id);
      }
      const intents = collectAnimIntents(prevStateRef.current, newState, knownCmdIdsRef.current);
      prevStateRef.current = newState;
      // flushSync ensures React commits the new DOM elements (including lands) synchronously
      // before the requestAnimationFrame callbacks fire. Without this, React 18's concurrent
      // scheduler may defer the commit past rAF, so querySelector finds nothing.
      flushSync(() => setGameState(newState));

      if (intents.length === 0) return;

      // flushSync already committed the DOM, so a single rAF is enough to
      // let the browser finish layout before we read getBoundingClientRect.
      requestAnimationFrame(() => {
        try {
          const resolved: FlyingCard[] = [];
          for (const intent of intents) {
            const el = document.querySelector(`[data-bf-card="${intent.cardId}"]`) as HTMLElement | null;
            if (!el) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue; // element not yet laid out
            // Hide the real card while the flying animation plays
            el.style.opacity = "0";
            resolved.push({
              key: `${intent.cardId}-${Date.now()}`,
              cardId: intent.cardId,
              imageUri: intent.imageUri,
              fromRect: intent.fromRect,
              toRect: { left: r.left, top: r.top, width: r.width, height: r.height },
            });
          }
          if (resolved.length > 0) setFlyingCards(prev => [...prev, ...resolved]);
        } catch { /* animation frame error — ignore */ }
      });
    } catch (e) {
      console.error("applyNewState error:", e);
      // Fallback: still update the game state even if animation detection failed
      prevStateRef.current = newState;
      setGameState(newState);
    }
  }

  // Initial load — seed prevStateRef (no animation on first load)
  useEffect(() => {
    if (!gameId) return;
    setFetchError(null);
    getGameState(gameId)
      .then(state => { prevStateRef.current = state; setGameState(state); })
      .catch((e) => setFetchError(e?.response?.data?.detail ?? e?.message ?? "Failed to load game"));
  }, [gameId]);

  // Keep prevStateRef in sync with store updates that bypass applyNewState (e.g. human plays via Board)
  useEffect(() => {
    if (gameState) prevStateRef.current = gameState;
  }, [gameState]);

  // Stop the AI loop on unmount
  useEffect(() => {
    return () => { aiLoopActiveRef.current = false; };
  }, []);

  // Kick off the step-by-step AI loop whenever it becomes the AI's turn
  useEffect(() => {
    if (!gameId || !gameState) return;
    if (gameState.mulligan_phase !== "playing") return;
    if (gameState.winner) return;
    const humanPlayer = gameState.players.find(p => p.is_human);
    if (!humanPlayer || gameState.active_player_id === humanPlayer.id) return;
    if ((gameState.stack ?? []).length > 0) return;
    if (aiLoopActiveRef.current) return;

    const aiName = gameState.players.find(
      p => !p.is_human && p.id === gameState.active_player_id
    )?.name ?? "AI";

    runAiStepLoop(gameId, aiName);
  }, [gameState?.active_player_id, gameState?.mulligan_phase, gameState?.stack_size]);

  async function runAiStepLoop(id: string, aiName: string) {
    aiLoopActiveRef.current = true;
    setAiThinkingName(aiName);
    setAiThinking(true);

    try {
      while (aiLoopActiveRef.current) {
        await sleep(stepDelay());
        if (!aiLoopActiveRef.current) break;

        const result = await advanceAiStep(id);
        if (!aiLoopActiveRef.current) break;

        appendLog(result.log);
        const newState = await getGameState(id);
        if (!aiLoopActiveRef.current) break;

        applyNewState(newState);

        const currentAiName = newState.players.find(
          p => !p.is_human && p.id === newState.active_player_id
        )?.name;
        if (currentAiName) setAiThinkingName(currentAiName);

        const human = newState.players.find(p => p.is_human);
        const continueLoop =
          !!human &&
          newState.active_player_id !== human.id &&
          (newState.stack ?? []).length === 0 &&
          !newState.winner;

        if (!continueLoop) break;
      }
    } catch (e) {
      console.error(e);
    } finally {
      aiLoopActiveRef.current = false;
      setAiThinking(false);
      setAiThinkingName("");
    }
  }

  // When a new spell appears on top of the stack (player cast while holding priority),
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
      applyNewState(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  const currentStepIdx = gameState ? STEP_ORDER.indexOf(gameState.step) : -1;

  return (
    <div className="game-layout">
      {/* Flying card animations (portaled to document.body inside FlyingCardEl) */}
      {flyingCards.map(fc => (
        <FlyingCardEl
          key={fc.key}
          imageUri={fc.imageUri}
          fromRect={fc.fromRect}
          toRect={fc.toRect}
          onDone={() => {
            // Reveal the battlefield card now that the animation has landed
            const el = document.querySelector(`[data-bf-card="${fc.cardId}"]`) as HTMLElement | null;
            if (el) el.style.removeProperty("opacity");
            setFlyingCards(prev => prev.filter(c => c.key !== fc.key));
          }}
        />
      ))}

      {gameState && (
        <div className="phase-bar">
          {aiThinking && (
            <div className="ai-thinking-banner">
              <span className="ai-thinking-name">{aiThinkingName}</span>
              <span className="ai-thinking-label">is thinking</span>
              <span className="ai-thinking-dots">
                <span /><span /><span />
              </span>
            </div>
          )}
          <div className="pb-left">
            <div className="pb-item">
              <span className="pb-label">Turn</span>
              <span className="pb-value">{gameState.turn}</span>
            </div>
            <button
              className="primary pb-btn"
              onClick={handlePassPriority}
              disabled={isLoading || aiThinking || !isHumanTurn}
            >
              {isLoading ? "..." : "Move Phases"}
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
            <MulliganPhase gameState={gameState} onStateChange={applyNewState} />
          ) : (
            <>
              <Board onStateChange={applyNewState} />

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
                  onStateChange={applyNewState}
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
