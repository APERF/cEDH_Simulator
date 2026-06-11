import { useState, useEffect, useRef } from "react";
import type { GameState, StackItem } from "../../types/game";
import { sendAction, getGameState } from "../../services/api";

interface Props {
  gameState: GameState;
  onStateChange: (gs: GameState) => void;
  onHoldPriority: () => void;
}

type OverlayPhase = "human_priority" | "ai_thinking";
type AIDecision = "thinking" | "pass" | "counter";

interface AIState {
  playerId: string;
  name: string;
  decision: AIDecision;
  counterSpell?: string;
}

const ORDINAL = ["Resolves Next", "Resolves 2nd", "Resolves 3rd", "Resolves 4th", "Resolves 5th"];
function ordinal(n: number): string {
  return ORDINAL[n] ?? `Resolves ${n + 1}th`;
}

const THINKING_DOTS = ["", ".", "..", "..."];

export function StackOverlay({ gameState, onStateChange, onHoldPriority }: Props) {
  const [phase, setPhase] = useState<OverlayPhase>("human_priority");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiStates, setAiStates] = useState<AIState[]>([]);
  const [aiDone, setAiDone] = useState(false);
  const [dotIdx, setDotIdx] = useState(0);

  // Track top-of-stack id so we reset to human_priority when a new spell lands
  const topIdRef = useRef<string | null>(null);

  const stack = gameState.stack ?? [];
  const human = gameState.players.find((p) => p.is_human);
  const opponents = gameState.players.filter((p) => !p.is_human);

  // Who cast the top spell?
  const topCasterId = stack[0]?.controller_id ?? null;
  const topCasterName = stack[0]?.controller_name ?? "";
  const humanCastTop = !!human && topCasterId === human.id;

  // Non-caster opponents are the ones who still need to pass priority
  const thinkingOpponents = opponents.filter((p) => p.id !== topCasterId);

  // Animated dots for thinking state
  useEffect(() => {
    const id = setInterval(() => setDotIdx((i) => (i + 1) % THINKING_DOTS.length), 380);
    return () => clearInterval(id);
  }, []);

  // When a new spell appears on top, go back to human_priority so they act first
  useEffect(() => {
    const topId = stack[0]?.id ?? null;
    if (topId && topId !== topIdRef.current) {
      topIdRef.current = topId;
      // Only reset if we're not mid-animation (ai_thinking drives the resolve flow itself)
      if (phase !== "ai_thinking") {
        setPhase("human_priority");
        setAiStates([]);
        setAiDone(false);
        setError(null);
      }
    }
  }, [stack[0]?.id]);

  // Run the AI thinking animation for non-caster opponents, then call the backend
  async function runAiThenResolve() {
    setError(null);

    if (thinkingOpponents.length > 0) {
      setPhase("ai_thinking");
      setAiDone(false);

      const initialStates: AIState[] = thinkingOpponents.map((p) => ({
        playerId: p.id,
        name: p.name,
        decision: "thinking",
      }));
      setAiStates(initialStates);

      // Stagger each opponent's decision reveal
      let delay = 0;
      await Promise.all(
        thinkingOpponents.map(
          (opp) =>
            new Promise<void>((resolve) => {
              delay += 900 + Math.random() * 1100;
              setTimeout(() => {
                setAiStates((prev) =>
                  prev.map((s) =>
                    s.playerId === opp.id ? { ...s, decision: "pass" } : s
                  )
                );
                resolve();
              }, delay);
            })
        )
      );

      setAiDone(true);
      // Brief pause so the player sees all ✓ Pass badges before resolving
      await new Promise<void>((r) => setTimeout(r, 500));
    }

    // Resolve via backend
    setBusy(true);
    try {
      await sendAction(gameState.game_id, { type: "pass_priority" });
      const next = await getGameState(gameState.game_id);
      topIdRef.current = null;
      setPhase("human_priority");
      setAiStates([]);
      setAiDone(false);
      onStateChange(next);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Request failed");
      setPhase("human_priority");
    } finally {
      setBusy(false);
    }
  }

  const inAiPhase = phase === "ai_thinking";

  return (
    <div className="stack-overlay">
      <div className="stack-panel">

        {/* ── Header ── */}
        <div className="stack-header">
          <h2>The Stack</h2>
          <p className="stack-sub">
            {humanCastTop
              ? "You cast a spell — you have priority first."
              : `${topCasterName} cast a spell — you have priority to respond.`}
          </p>
        </div>

        {/* ── Stack items ── */}
        <div className="stack-resolution-hint">
          <span className="stack-arrow-label">Resolves first</span>
          <span className="stack-arrow">&#8592;</span>
          <span className="stack-arrow-label">Cast first</span>
        </div>

        <div className="stack-items">
          {stack.map((item: StackItem, i: number) => (
            <div key={item.id} className={`stack-card${i === 0 ? " stack-card--top" : ""}`}>
              <div className="stack-order-badge">{ordinal(i)}</div>
              {item.image_uri ? (
                <img src={item.image_uri} alt={item.name} className="stack-card-img" />
              ) : (
                <div className="stack-card-text">{item.name}</div>
              )}
              <div className="stack-controller-badge">{item.controller_name}</div>
              {item.mana_cost && <div className="stack-mana-cost">{item.mana_cost}</div>}
            </div>
          ))}
        </div>

        {/* ── Human priority (acts FIRST) ── */}
        {!inAiPhase && (
          <div className="stack-human-priority">
            <div className="stack-priority-label">
              {humanCastTop ? "Your priority — respond or pass:" : `Your priority — respond to ${topCasterName} or pass:`}
            </div>
            <div className="stack-actions">
              <button
                className="primary"
                onClick={runAiThenResolve}
                disabled={busy}
                title={`Pass priority — opponents respond, then "${stack[0]?.name ?? "top"}" resolves`}
              >
                Pass Priority
              </button>
              <button
                onClick={onHoldPriority}
                disabled={busy}
                title="Return to the battlefield to cast another spell before passing"
              >
                Hold Priority
              </button>
            </div>
            <p className="stack-respond-hint">
              Hold Priority to cast an <strong>instant</strong> (or flash spell) first — or Pass Priority to let opponents respond.
            </p>
          </div>
        )}

        {/* ── AI priority round (runs AFTER human passes) ── */}
        {inAiPhase && (
          <div className="stack-priority-round">
            <div className="stack-priority-label">
              {aiDone
                ? "All opponents passed — resolving…"
                : "Opponents considering response…"}
            </div>
            <div className="stack-ai-row">
              {aiStates.map((ai) => (
                <div
                  key={ai.playerId}
                  className={`stack-ai-badge ${ai.decision}`}
                >
                  <span className="stack-ai-name">{ai.name}</span>
                  <span className="stack-ai-decision">
                    {ai.decision === "thinking" && (
                      <span className="stack-ai-thinking">
                        Thinking{THINKING_DOTS[dotIdx]}
                      </span>
                    )}
                    {ai.decision === "pass" && (
                      <span className="stack-ai-pass">&#10003; Pass</span>
                    )}
                    {ai.decision === "counter" && (
                      <span className="stack-ai-counter">
                        Casts {ai.counterSpell ?? "response"}
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <p className="stack-error">{error}</p>}

        <p className="stack-rule-note">
          Lands and mana abilities bypass the stack. Triggered abilities (When/Whenever/At)
          and non-mana activated abilities do use it.
        </p>
      </div>
    </div>
  );
}
