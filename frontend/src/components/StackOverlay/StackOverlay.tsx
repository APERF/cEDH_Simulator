import { useState, useEffect, useRef } from "react";
import type { GameState, Player, StackItem } from "../../types/game";
import { sendAction, getGameState } from "../../services/api";

interface Props {
  gameState: GameState;
  onStateChange: (gs: GameState) => void;
  onHoldPriority: () => void;
}

type OverlayPhase = "pre_human_ai" | "human_priority" | "post_human_ai";
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

// Returns players in priority order after the caster auto-passes, following seat/turn order.
function priorityOrderAfterCast(players: Player[], casterId: string): Player[] {
  const n = players.length;
  const casterIdx = players.findIndex((p) => p.id === casterId);
  if (casterIdx === -1) return players.filter((p) => p.id !== casterId);
  const order: Player[] = [];
  for (let i = 1; i < n; i++) {
    order.push(players[(casterIdx + i) % n]);
  }
  return order;
}

export function StackOverlay({ gameState, onStateChange, onHoldPriority }: Props) {
  const [phase, setPhase] = useState<OverlayPhase>("human_priority");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiStates, setAiStates] = useState<AIState[]>([]);
  const [aiDone, setAiDone] = useState(false);
  const [dotIdx, setDotIdx] = useState(0);

  const topIdRef = useRef<string | null>(null);
  // Incremented on each new spell to cancel superseded animations.
  const animGenRef = useRef<number>(0);

  const stack = gameState.stack ?? [];
  const human = gameState.players.find((p) => p.is_human);

  const topCasterId = stack[0]?.controller_id ?? null;
  const topCasterName = stack[0]?.controller_name ?? "";
  const topIsAbility = stack[0]?.is_ability ?? false;
  const humanCastTop = !!human && topCasterId === human.id;

  // Priority order (excluding caster) in turn/seat order.
  const priorityOrder: Player[] = topCasterId
    ? priorityOrderAfterCast(gameState.players, topCasterId)
    : gameState.players.filter((p) => !p.is_human);

  const humanPriorityIdx = priorityOrder.findIndex((p) => p.is_human);

  // AIs who act before the human in this priority window.
  const preHumanAIs: Player[] =
    humanPriorityIdx > 0
      ? priorityOrder.slice(0, humanPriorityIdx).filter((p) => !p.is_human)
      : [];

  // AIs who act after the human (or all AIs when human is the caster).
  const postHumanAIs: Player[] =
    humanPriorityIdx === -1
      ? priorityOrder.filter((p) => !p.is_human)
      : priorityOrder.slice(humanPriorityIdx + 1).filter((p) => !p.is_human);

  // Animated dots for thinking state.
  useEffect(() => {
    const id = setInterval(() => setDotIdx((i) => (i + 1) % THINKING_DOTS.length), 380);
    return () => clearInterval(id);
  }, []);

  // When a new spell lands on top, run pre-human AI animation then give human priority.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const topId = stack[0]?.id ?? null;
    if (!topId || topId === topIdRef.current) return;
    topIdRef.current = topId;

    const gen = ++animGenRef.current;
    const cancelled = () => animGenRef.current !== gen;

    setAiStates([]);
    setAiDone(false);
    setError(null);
    setBusy(false);

    if (humanCastTop || preHumanAIs.length === 0) {
      setPhase("human_priority");
      return;
    }

    async function runPreHumanAIs() {
      setPhase("pre_human_ai");
      setAiStates(
        preHumanAIs.map((p) => ({ playerId: p.id, name: p.name, decision: "thinking" as AIDecision }))
      );

      for (const opp of preHumanAIs) {
        await new Promise<void>((resolve) =>
          setTimeout(resolve, 900 + Math.random() * 1100)
        );
        if (cancelled()) return;
        setAiStates((prev) =>
          prev.map((s) => (s.playerId === opp.id ? { ...s, decision: "pass" } : s))
        );
      }

      await new Promise<void>((resolve) => setTimeout(resolve, 500));
      if (cancelled()) return;

      setPhase("human_priority");
      setAiStates([]);
    }

    runPreHumanAIs();
  }, [stack[0]?.id]);

  // Run post-human AI animation then resolve via backend.
  async function runAiThenResolve() {
    setError(null);

    if (postHumanAIs.length > 0) {
      setPhase("post_human_ai");
      setAiDone(false);

      setAiStates(
        postHumanAIs.map((p) => ({ playerId: p.id, name: p.name, decision: "thinking" as AIDecision }))
      );

      let delay = 0;
      await Promise.all(
        postHumanAIs.map(
          (opp) =>
            new Promise<void>((resolve) => {
              delay += 900 + Math.random() * 1100;
              setTimeout(() => {
                setAiStates((prev) =>
                  prev.map((s) => (s.playerId === opp.id ? { ...s, decision: "pass" } : s))
                );
                resolve();
              }, delay);
            })
        )
      );

      setAiDone(true);
      await new Promise<void>((r) => setTimeout(r, 500));
    }

    setBusy(true);
    try {
      await sendAction(gameState.game_id, { type: "pass_priority" });
      const next = await getGameState(gameState.game_id);
      topIdRef.current = null;
      animGenRef.current++;
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

  const showAiPanel = phase === "pre_human_ai" || phase === "post_human_ai";

  return (
    <div className="stack-overlay">
      <div className="stack-panel">

        {/* ── Header ── */}
        <div className="stack-header">
          <h2>The Stack</h2>
          <p className="stack-sub">
            {topIsAbility
              ? humanCastTop
                ? "Your triggered ability — pass priority to let it resolve."
                : phase === "pre_human_ai"
                ? `${topCasterName}'s triggered ability — waiting for players before you…`
                : `${topCasterName}'s triggered ability — you may respond before it resolves.`
              : humanCastTop
              ? "You cast a spell — you have priority first."
              : phase === "pre_human_ai"
              ? `${topCasterName} cast a spell — waiting for players before you…`
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
              {!item.is_ability && item.mana_cost && <div className="stack-mana-cost">{item.mana_cost}</div>}
              {item.is_ability && <div className="stack-ability-badge">Triggered Ability</div>}
            </div>
          ))}
        </div>

        {/* ── Human priority window ── */}
        {phase === "human_priority" && (
          <div className="stack-human-priority">
            <div className="stack-priority-label">
              {humanCastTop
                ? "Your priority — respond or pass:"
                : `Your priority — respond to ${topCasterName} or pass:`}
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
              Hold Priority to cast an <strong>instant</strong> (or flash spell) first — or Pass
              Priority to let opponents respond.
            </p>
          </div>
        )}

        {/* ── AI priority panel (pre-human or post-human) ── */}
        {showAiPanel && (
          <div className="stack-priority-round">
            <div className="stack-priority-label">
              {phase === "pre_human_ai"
                ? "Players before you in priority order…"
                : aiDone
                ? "All opponents passed — resolving…"
                : "Opponents considering response…"}
            </div>
            <div className="stack-ai-row">
              {aiStates.map((ai) => (
                <div key={ai.playerId} className={`stack-ai-badge ${ai.decision}`}>
                  <span className="stack-ai-name">{ai.name}</span>
                  <span className="stack-ai-decision">
                    {ai.decision === "thinking" && (
                      <span className="stack-ai-thinking">Thinking{THINKING_DOTS[dotIdx]}</span>
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
          Lands and mana abilities bypass the stack. Triggered abilities (When/Whenever/At) and
          non-mana activated abilities do use it.
        </p>
      </div>
    </div>
  );
}
