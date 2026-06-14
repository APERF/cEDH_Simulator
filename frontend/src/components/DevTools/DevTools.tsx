import { useState } from "react";
import type { DebugGameState, AIDecision } from "../../types/game";

const MANA_COLORS = ["W", "U", "B", "R", "G", "C"] as const;
const COLOR_LABEL: Record<string, string> = { W: "W", U: "U", B: "B", R: "R", G: "G", C: "C" };

function ManaPips({ mana }: { mana: AIDecision["mana"] }) {
  const pips: string[] = [];
  for (const c of MANA_COLORS) {
    for (let i = 0; i < mana[c]; i++) pips.push(c);
  }
  if (pips.length === 0) return <span className="dt-mana-empty">∅</span>;
  return (
    <span className="dt-mana-pips">
      {pips.map((c, i) => (
        <span key={i} className={`pip pip-${c}`} title={COLOR_LABEL[c]} />
      ))}
    </span>
  );
}

function actionBadgeClass(action: string) {
  if (action === "cast_spell") return "dt-badge dt-badge-cast";
  if (action === "cast_commander") return "dt-badge dt-badge-cmd";
  if (action === "play_land") return "dt-badge dt-badge-land";
  return "dt-badge dt-badge-pass";
}

function actionLabel(action: string) {
  if (action === "cast_spell") return "cast";
  if (action === "cast_commander") return "cmd";
  if (action === "play_land") return "land";
  return "pass";
}

interface Props {
  debugState: DebugGameState | null;
  loading: boolean;
  onRefresh: () => void;
  speedMode: boolean;
  onSpeedModeToggle: () => void;
}

export function DevTools({ debugState, loading, onRefresh, speedMode, onSpeedModeToggle }: Props) {
  const [expandedPlayers, setExpandedPlayers] = useState<Set<string>>(new Set());
  const [expandedDecisions, setExpandedDecisions] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState(false);

  function togglePlayer(id: string) {
    setExpandedPlayers(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleDecision(idx: number) {
    setExpandedDecisions(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  function copyState() {
    if (!debugState) return;
    navigator.clipboard.writeText(JSON.stringify(debugState, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const aiPlayers = debugState?.players.filter(p => !p.is_human) ?? [];
  const decisions = [...(debugState?.ai_decision_log ?? [])].reverse();

  return (
    <div className="dev-tools">
      <div className="dt-toolbar">
        <button
          className={`dt-speed-btn${speedMode ? " active" : ""}`}
          onClick={onSpeedModeToggle}
          title="Reduce AI step delay to ~300ms"
        >
          {speedMode ? "⚡ Speed ON" : "⚡ Speed OFF"}
        </button>
        <button className="dt-refresh-btn" onClick={onRefresh} disabled={loading}>
          {loading ? "…" : "↻"}
        </button>
      </div>

      <div className="dt-section">
        <div className="dt-section-title">AI HANDS</div>
        {aiPlayers.length === 0 && (
          <div className="dt-empty">No AI players</div>
        )}
        {aiPlayers.map(p => {
          const open = expandedPlayers.has(p.id);
          const landCount = (p.lands ?? []).length;
          return (
            <div key={p.id} className="dt-player">
              <button className="dt-player-header" onClick={() => togglePlayer(p.id)}>
                <span className="dt-chevron">{open ? "▼" : "▶"}</span>
                <span className="dt-player-name">{p.name}</span>
                <span className="dt-player-meta">
                  {p.hand_size} in hand · {landCount} land{landCount !== 1 ? "s" : ""}
                </span>
              </button>
              {open && (
                <div className="dt-hand">
                  {p.hand.length === 0 && (
                    <div className="dt-empty">Empty hand</div>
                  )}
                  {p.hand.map(card => (
                    <div key={card.id} className="dt-hand-card">
                      <span className="dt-card-name">{card.name}</span>
                      {card.mana_cost && (
                        <span className="dt-card-cost">{card.mana_cost}</span>
                      )}
                      {card.type_line && (
                        <span className="dt-card-type">{card.type_line.split(" — ")[0]}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="dt-section">
        <div className="dt-section-title">
          <span>AI DECISIONS</span>
          <button className="dt-copy-btn" onClick={copyState} title="Copy full state as JSON">
            {copied ? "✓ copied" : "copy JSON"}
          </button>
        </div>
        <div className="dt-decisions">
          {decisions.length === 0 && (
            <div className="dt-empty">No decisions yet</div>
          )}
          {decisions.slice(0, 40).map((d, idx) => {
            const open = expandedDecisions.has(idx);
            return (
              <div key={idx} className="dt-decision">
                <button className="dt-decision-header" onClick={() => toggleDecision(idx)}>
                  <span className="dt-chevron-sm">{open ? "▾" : "▸"}</span>
                  <span className="dt-dec-turn">T{d.turn}</span>
                  <span className="dt-dec-step">{d.step.replace("_main", "M").replace("precombat", "pre").replace("postcombat", "post")}</span>
                  <span className={actionBadgeClass(d.action)}>{actionLabel(d.action)}</span>
                  <span className="dt-dec-player">{d.player.split(",")[0]}</span>
                  {d.card && <span className="dt-dec-card">{d.card}</span>}
                  {d.action === "pass" && !d.card && (
                    <span className="dt-dec-pass">no playable spells</span>
                  )}
                </button>
                {open && (
                  <div className="dt-decision-body">
                    <div className="dt-dec-row">
                      <span className="dt-dec-label">Mana</span>
                      <ManaPips mana={d.mana} />
                      <span className="dt-dec-mana-total">({d.mana.total})</span>
                    </div>
                    {d.card_cost && (
                      <div className="dt-dec-row">
                        <span className="dt-dec-label">Cost</span>
                        <span className="dt-dec-card-cost">{d.card_cost}</span>
                      </div>
                    )}
                    {d.reason && (
                      <div className="dt-dec-row">
                        <span className="dt-dec-label">Reason</span>
                        <span className="dt-dec-reason">{d.reason}</span>
                      </div>
                    )}
                    <div className="dt-dec-hand-label">Hand at decision:</div>
                    <div className="dt-dec-hand">
                      {d.hand.length === 0 && <span className="dt-empty">empty</span>}
                      {d.hand.map((c, ci) => (
                        <span
                          key={ci}
                          className={`dt-dec-hand-card${c.affordable ? " affordable" : ""}${c.is_land ? " is-land" : ""}`}
                          title={c.cost || (c.is_land ? "land" : "")}
                        >
                          {c.name}
                          {c.cost && <span className="dt-hc-cost">{c.cost}</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
