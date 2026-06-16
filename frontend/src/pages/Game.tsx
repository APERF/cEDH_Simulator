import { useEffect, useRef, useState, useMemo, Fragment } from "react";
import { createPortal, flushSync } from "react-dom";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Board } from "../components/Board/Board";
import { MulliganPhase } from "../components/MulliganPhase/MulliganPhase";
import { StackOverlay } from "../components/StackOverlay/StackOverlay";
import { EffectQueueOverlay } from "../components/EffectQueueOverlay/EffectQueueOverlay";
import { DevTools } from "../components/DevTools/DevTools";
import { useGameStore } from "../store/gameStore";
import { getGameState, getDebugState, sendAction, advanceAiStep } from "../services/api";
import type { GameState, DebugGameState, HandCard } from "../types/game";

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

const SPEED_DELAY_MS = 400;

function stepDelay(speedMode: boolean): number {
  return speedMode ? SPEED_DELAY_MS : 3000 + Math.random() * 2000; // 3 – 5 s normal, ~400ms speed mode
}

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms));
}

// ── ETB Replacement — land discard picker ────────────────────────────────────

function ETBLandPicker({ lands, cardName, gameId, onStateChange, onSkip }: {
  lands: HandCard[];
  cardName: string;
  gameId: string;
  onStateChange: (s: GameState) => void;
  onSkip: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <div>
      <div style={{ fontSize: 13, color: "#aaa", marginBottom: 10 }}>
        Choose a land to discard:
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {lands.map(land => (
          <button
            key={land.id}
            onClick={() => setSelectedId(land.id)}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: `2px solid ${selectedId === land.id ? "#f0c040" : "#444"}`,
              background: selectedId === land.id ? "#3a3010" : "#222",
              color: "#e8e8e8",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {land.name}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <button
          disabled={!selectedId}
          style={{
            flex: 1, padding: "10px 0", background: selectedId ? "#2a5a2a" : "#333",
            border: "none", borderRadius: 8, color: "#fff",
            cursor: selectedId ? "pointer" : "not-allowed", fontSize: 14,
          }}
          onClick={async () => {
            if (!selectedId) return;
            await sendAction(gameId, { type: "etb_replacement_choice", choice: "pay", land_id: selectedId });
            onStateChange(await getGameState(gameId));
          }}
        >
          Discard &amp; Enter Battlefield
        </button>
        <button
          style={{ flex: 1, padding: "10px 0", background: "#3a1a1a", border: "none", borderRadius: 8, color: "#fff", cursor: "pointer", fontSize: 14 }}
          onClick={onSkip}
        >
          Let {cardName} go to graveyard
        </button>
      </div>
    </div>
  );
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

// ── Demonic Consultation name modal ──────────────────────────────────────────

function DCNameModal({ spellName, gameId, onStateChange }: {
  spellName: string;
  gameId: string;
  onStateChange: (s: any) => void;
}) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { appendLog } = useGameStore();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const r = await sendAction(gameId, { type: "dc_name_choice", named_card: name.trim() });
      appendLog(r.log);
      onStateChange(await getGameState(gameId));
    } catch {
      setError("Failed to submit. Try again.");
      setLoading(false);
    }
  }

  return (
    <div className="fetch-overlay" style={{ zIndex: 9990 }}>
      <div className="fetch-modal" style={{ maxWidth: 420 }}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: "var(--gold-light)" }}>
          {spellName}
        </div>
        <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 20 }}>
          Name a card. Your library will be searched — if found, it goes to your hand and everything before it is exiled. If not found, your entire library is exiled.
        </div>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Card name…"
            style={{
              background: "var(--surface)", border: "1px solid var(--border-hi)",
              borderRadius: 8, padding: "10px 14px", color: "var(--text-h)",
              fontSize: 14, outline: "none",
            }}
          />
          {error && <div style={{ color: "var(--red)", fontSize: 13 }}>{error}</div>}
          <button
            type="submit"
            className="primary"
            disabled={!name.trim() || loading}
            style={{ padding: "10px 0" }}
          >
            {loading ? "Resolving…" : "Confirm"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Chrome Mox imprint modal ──────────────────────────────────────────────────

function ImprintModal({ candidates, gameId, onStateChange }: {
  candidates: { id: string; name: string }[];
  gameId: string;
  onStateChange: (s: any) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { appendLog } = useGameStore();

  async function handleChoose(cardId: string) {
    setLoading(true);
    setError(null);
    try {
      const r = await sendAction(gameId, { type: "imprint_choice", card_id: cardId });
      appendLog(r.log);
      onStateChange(await getGameState(gameId));
    } catch {
      setError("Failed to submit. Try again.");
      setLoading(false);
    }
  }

  return (
    <div className="fetch-overlay" style={{ zIndex: 9990 }}>
      <div className="fetch-modal" style={{ maxWidth: 420 }}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: "var(--gold-light)" }}>
          Chrome Mox — Imprint
        </div>
        <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 16 }}>
          Choose a nonartifact, nonland card from your hand to exile (imprint).
        </div>
        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {candidates.map(c => (
            <button
              key={c.id}
              className="primary"
              disabled={loading}
              onClick={() => handleChoose(c.id)}
              style={{ padding: "10px 14px", textAlign: "left" }}
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Game component ───────────────────────────────────────────────────────────

export function Game() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const { gameState, actionLog, appendLog, setGameState, setGameId, setLoading, isLoading } = useGameStore();
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [holdingPriority, setHoldingPriority] = useState(false);
  const [aiThinking, setAiThinking] = useState(false);
  const [aiThinkingName, setAiThinkingName] = useState("");
  const [flyingCards, setFlyingCards] = useState<FlyingCard[]>([]);
  const [devPanelOpen, setDevPanelOpen] = useState(false);
  const [speedMode, setSpeedMode] = useState(false);
  const [debugState, setDebugState] = useState<DebugGameState | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const speedModeRef = useRef(false);
  const debugIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isDevUser = localStorage.getItem("role") === "dev";
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
    setGameId(gameId);
    getGameState(gameId)
      .then(state => { prevStateRef.current = state; setGameState(state); })
      .catch((e) => setFetchError(e?.response?.data?.detail ?? e?.message ?? "Failed to load game"));
  }, [gameId]);

  // Keep prevStateRef in sync with store updates that bypass applyNewState (e.g. human plays via Board)
  useEffect(() => {
    if (gameState) prevStateRef.current = gameState;
  }, [gameState]);

  // Keep speedModeRef in sync so runAiStepLoop reads the latest value
  useEffect(() => { speedModeRef.current = speedMode; }, [speedMode]);

  // Poll debug state (AI hands + decision log) while the dev panel is open
  useEffect(() => {
    if (!devPanelOpen || !gameId) {
      if (debugIntervalRef.current) { clearInterval(debugIntervalRef.current); debugIntervalRef.current = null; }
      if (!devPanelOpen) setDebugState(null);
      return;
    }
    async function fetchDebug() {
      if (!gameId) return;
      setDebugLoading(true);
      try { setDebugState(await getDebugState(gameId)); } catch { /* ignore */ }
      finally { setDebugLoading(false); }
    }
    fetchDebug();
    debugIntervalRef.current = setInterval(fetchDebug, 3000);
    return () => { if (debugIntervalRef.current) { clearInterval(debugIntervalRef.current); debugIntervalRef.current = null; } };
  }, [devPanelOpen, gameId]);

  // Build playerId→hand map from debug state so Board can reveal AI hands
  const aiHandsMap = useMemo<Record<string, HandCard[]> | undefined>(() => {
    if (!devPanelOpen || !debugState) return undefined;
    const map: Record<string, HandCard[]> = {};
    for (const p of debugState.players) {
      if (!p.is_human && p.hand.length > 0) map[p.id] = p.hand;
    }
    return Object.keys(map).length > 0 ? map : undefined;
  }, [devPanelOpen, debugState]);

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
  }, [gameState?.active_player_id, gameState?.mulligan_phase, gameState?.stack_size, gameState?.combat_awaiting_human_action]);

  async function runAiStepLoop(id: string, aiName: string) {
    aiLoopActiveRef.current = true;
    setAiThinkingName(aiName);
    setAiThinking(true);

    try {
      while (aiLoopActiveRef.current) {
        await sleep(stepDelay(speedModeRef.current));
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
          !newState.winner &&
          !newState.combat_awaiting_human_action;

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
            {isDevUser && (
              <button
                className={`pb-btn pb-dev-btn${devPanelOpen ? " active" : ""}`}
                onClick={() => setDevPanelOpen(o => !o)}
                title="Toggle dev tools"
              >
                {speedMode ? "⚡ DEV" : "DEV"}
              </button>
            )}
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

      {gameState?.winner && (() => {
        const winningPlayer = gameState.players.find(p => p.id === gameState.winner);
        const winnerName = winningPlayer?.name ?? "A player";
        return (
          <div className="win-overlay">
            <div className="win-modal">
              <div className="win-trophy">🏆</div>
              <h2 className="win-title">{winnerName} has won the game!</h2>
              <button className="primary win-new-game-btn" onClick={() => navigate("/")}>
                New Game
              </button>
            </div>
          </div>
        );
      })()}

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
            <div style={gameState?.winner ? { pointerEvents: "none", userSelect: "none" } : undefined}>
              <Board onStateChange={applyNewState} aiHandsMap={aiHandsMap} />

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
              {gameState && (gameState.pending_choices ?? []).length > 0 && (gameState.stack ?? []).length === 0 && (
                <EffectQueueOverlay
                  gameState={gameState}
                  onStateChange={applyNewState}
                />
              )}
              {gameState?.pending_dc_name && (
                <DCNameModal
                  spellName={gameState.pending_dc_name.spell_name}
                  gameId={gameId!}
                  onStateChange={applyNewState}
                />
              )}
              {gameState?.pending_imprint_choice && (
                <ImprintModal
                  candidates={gameState.pending_imprint_choice.candidates}
                  gameId={gameId!}
                  onStateChange={applyNewState}
                />
              )}
              {gameState?.pending_etb_replacement && (() => {
                const etbPending = gameState.pending_etb_replacement!;
                const human = gameState.players.find(p => p.is_human);
                const etbRep = etbPending.etb_replacement;
                const needsLand = etbRep.cost?.type === "discard" && etbRep.cost?.filter === "land";
                const landCards = needsLand
                  ? (human?.hand ?? []).filter(c =>
                      c.land_type !== null || c.type_line?.toLowerCase().includes("land")
                    )
                  : [];
                return (
                  <div style={{ position: "fixed", inset: 0, zIndex: 9990, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ background: "#1a1a2e", border: "1px solid #444", borderRadius: 12, padding: 28, maxWidth: 440, width: "90%", color: "#e8e8e8" }}>
                      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: "#f0c040" }}>
                        {etbPending.card_name}
                      </div>
                      <div style={{ fontSize: 14, marginBottom: 20, color: "#aaa" }}>
                        {etbRep.prompt || "Choose an option:"}
                      </div>
                      {needsLand ? (
                        <ETBLandPicker
                          lands={landCards}
                          cardName={etbPending.card_name}
                          gameId={gameId!}
                          onStateChange={applyNewState}
                          onSkip={async () => {
                            const r = await sendAction(gameId!, { type: "etb_replacement_choice", choice: "skip" });
                            appendLog(r.log);
                            applyNewState(await getGameState(gameId!));
                          }}
                        />
                      ) : (
                        <div style={{ display: "flex", gap: 12 }}>
                          <button
                            style={{ flex: 1, padding: "10px 0", background: "#2a5a2a", border: "none", borderRadius: 8, color: "#fff", cursor: "pointer", fontSize: 14 }}
                            onClick={async () => {
                              const r = await sendAction(gameId!, { type: "etb_replacement_choice", choice: "pay" });
                              appendLog(r.log);
                              applyNewState(await getGameState(gameId!));
                            }}
                          >
                            Pay Cost
                          </button>
                          <button
                            style={{ flex: 1, padding: "10px 0", background: "#3a1a1a", border: "none", borderRadius: 8, color: "#fff", cursor: "pointer", fontSize: 14 }}
                            onClick={async () => {
                              const r = await sendAction(gameId!, { type: "etb_replacement_choice", choice: "skip" });
                              appendLog(r.log);
                              applyNewState(await getGameState(gameId!));
                            }}
                          >
                            Let it go to graveyard
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
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
              {devPanelOpen && (
                <DevTools
                  debugState={debugState}
                  loading={debugLoading}
                  onRefresh={async () => {
                    if (!gameId) return;
                    setDebugLoading(true);
                    try { setDebugState(await getDebugState(gameId)); } catch { /* ignore */ }
                    finally { setDebugLoading(false); }
                  }}
                  speedMode={speedMode}
                  onSpeedModeToggle={() => setSpeedMode(m => !m)}
                />
              )}
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
