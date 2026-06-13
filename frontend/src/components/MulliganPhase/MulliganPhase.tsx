import { useState, useEffect } from "react";
import type { GameState } from "../../types/game";
import { mulliganAction, mulliganAiTurn } from "../../services/api";

interface Props {
  gameState: GameState;
  onStateChange: (gs: GameState) => void;
}

export function MulliganPhase({ gameState, onStateChange }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const human = gameState.players.find((p) => p.is_human)!;
  const currentPlayerId = gameState.mulligan_current_player_id;
  const isHumanTurn =
    currentPlayerId === human?.id || gameState.mulligan_phase === "selecting_bottom";
  const currentPlayer = gameState.players.find((p) => p.id === currentPlayerId);
  const isSelectingBottom = gameState.mulligan_phase === "selecting_bottom";
  const mulliganCount = gameState.mulligan_count ?? 0;
  const needed = gameState.cards_to_bottom ?? 0;
  const hand = human?.hand ?? [];

  // Key that changes every time it is a new AI player's turn to act
  const aiTriggerKey =
    !isHumanTurn && currentPlayerId && gameState.mulligan_phase === "mulliganing"
      ? `${currentPlayerId}-${(gameState.mulligan_counts ?? {})[currentPlayerId] ?? 0}`
      : null;

  useEffect(() => {
    if (!aiTriggerKey) return;
    setBusy(true);
    setError(null);
    const timer = setTimeout(async () => {
      try {
        const next = await mulliganAiTurn(gameState.game_id);
        onStateChange(next);
      } catch (e: any) {
        setError(e?.response?.data?.detail ?? "AI decision failed");
      } finally {
        setBusy(false);
      }
    }, 1400);
    return () => clearTimeout(timer);
  }, [aiTriggerKey]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleSelect(id: string) {
    if (!isSelectingBottom) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < needed) {
        next.add(id);
      }
      return next;
    });
  }

  async function act(action: "mulligan" | "keep" | "bottom") {
    setBusy(true);
    setError(null);
    try {
      const next = await mulliganAction(
        gameState.game_id,
        action,
        action === "bottom" ? Array.from(selected) : undefined
      );
      setSelected(new Set());
      onStateChange(next);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const freeMulliganNote =
    mulliganCount === 0
      ? "Your first mulligan is free — you'll draw 7 again."
      : mulliganCount === 1
      ? "Next mulligan costs 1 card on the bottom."
      : `Next mulligan costs ${mulliganCount} card${mulliganCount !== 1 ? "s" : ""} on the bottom.`;

  // ── Opponents status sidebar ─────────────────────────────────────────────
  const activeIds: string[] = gameState.mulligan_active_player_ids ?? [];
  const counts: Record<string, number> = gameState.mulligan_counts ?? {};

  const opponentsSection = (
    <div className="mulligan-opponents">
      <p className="mulligan-opponents-label">Table Status</p>
      <div className="mulligan-opponents-rows">
        {gameState.players.filter((p) => !p.is_human).map((ai) => {
          const hasKept = !activeIds.includes(ai.id);
          const isCurrent = ai.id === currentPlayerId && !isHumanTurn;
          const taken = counts[ai.id] ?? 0;

          let decision: string;
          if (hasKept) {
            const bottomCount = Math.max(0, 7 - ai.hand_size);
            decision =
              ai.hand_size === 7
                ? "Keeps 7"
                : `Keeps ${ai.hand_size} · ${bottomCount} on bottom`;
          } else if (isCurrent) {
            decision =
              taken === 0
                ? "Deciding..."
                : `Mulliganed ${taken}× · Deciding...`;
          } else {
            decision =
              taken === 0 ? "Waiting..." : `Mulliganed ${taken}× · Waiting`;
          }

          return (
            <div
              key={ai.id}
              className={`mulligan-opponent-row${isCurrent ? " mulligan-opponent-row--active" : ""}${hasKept ? " mulligan-opponent-row--kept" : ""}`}
            >
              <div className="mulligan-opponent-arts">
                {ai.commanders.length > 0
                  ? ai.commanders.map((cmd) =>
                      cmd?.image_uri ? (
                        <img key={cmd.id} src={cmd.image_uri} alt={cmd.name} className="mulligan-opponent-art" />
                      ) : (
                        <div key={cmd.id} className="mulligan-opponent-art mulligan-opponent-art--placeholder">
                          {cmd.name.charAt(0)}
                        </div>
                      )
                    )
                  : (
                    <div className="mulligan-opponent-art mulligan-opponent-art--placeholder">
                      {ai.name.charAt(0)}
                    </div>
                  )}
              </div>
              <div className="mulligan-opponent-info">
                <div className="mulligan-opponent-names">
                  {ai.commanders.length > 0
                    ? ai.commanders.map((cmd) => (
                        <span key={cmd.id} className="mulligan-opponent-name">{cmd.name}</span>
                      ))
                    : <span className="mulligan-opponent-name">{ai.name}</span>}
                </div>
                <span className="mulligan-opponent-decision">
                  {isCurrent && !hasKept && (
                    <span className="mulligan-dot-pulse" />
                  )}
                  {decision}
                </span>
              </div>
              <div className="mulligan-opponent-hand">
                {hasKept
                  ? Array.from({ length: ai.hand_size }).map((_, i) => (
                      <div key={i} className="mulligan-card-back" />
                    ))
                  : Array.from({ length: 7 }).map((_, i) => (
                      <div key={i} className="mulligan-card-back mulligan-card-back--unknown" />
                    ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  // ── AI is deciding ───────────────────────────────────────────────────────
  if (!isHumanTurn && gameState.mulligan_phase === "mulliganing") {
    const aiTaken = currentPlayerId ? (counts[currentPlayerId] ?? 0) : 0;
    return (
      <div className="mulligan-overlay">
        <div className="mulligan-panel">
          <div className="mulligan-header">
            <h2>Opening Hands</h2>
            <p className="mulligan-sub">
              Waiting for opponents to decide...
            </p>
          </div>

          <div className="mulligan-ai-deciding">
            <div className="mulligan-opponent-arts">
              {(currentPlayer?.commanders ?? []).map((cmd) =>
                cmd?.image_uri ? (
                  <img key={cmd.id} src={cmd.image_uri} alt={cmd.name} className="mulligan-ai-commander-art" />
                ) : (
                  <div key={cmd.id} className="mulligan-ai-commander-art mulligan-opponent-art--placeholder">
                    {cmd.name.charAt(0)}
                  </div>
                )
              )}
            </div>
            <div className="mulligan-ai-deciding-info">
              {(currentPlayer?.commanders ?? []).map((cmd) => (
                <p key={cmd.id} className="mulligan-ai-deciding-name">{cmd.name}</p>
              ))}
              <p className="mulligan-ai-deciding-sub">
                {aiTaken === 0
                  ? "Considering opening hand..."
                  : `Considering hand after ${aiTaken} mulligan${aiTaken !== 1 ? "s" : ""}...`}
              </p>
              <div className="mulligan-thinking-dots">
                <span /><span /><span />
              </div>
            </div>
          </div>

          {opponentsSection}
        </div>
      </div>
    );
  }

  // ── Human is deciding ────────────────────────────────────────────────────
  return (
    <div className="mulligan-overlay">
      <div className="mulligan-panel">
        <div className="mulligan-header">
          <h2>Opening Hand</h2>
          {!isSelectingBottom && (
            <p className="mulligan-sub">
              {mulliganCount === 0
                ? `Keep or take your free mulligan? Your seat position is: ${["1st", "2nd", "3rd", "4th"][human.seat - 1]} Seat`
                : mulliganCount === 1
                ? "Free mulligan taken — keep or mulligan again? Next costs 1 card on the bottom."
                : `${mulliganCount} mulligans taken — keep costs ${needed} card${needed !== 1 ? "s" : ""} on the bottom.`}
            </p>
          )}
          {isSelectingBottom && (
            <p className="mulligan-sub">
              Select {needed} card{needed !== 1 ? "s" : ""} to place on the bottom of your library.
              ({selected.size} / {needed} selected)
            </p>
          )}
        </div>

        <div className="mulligan-hand">
          {hand.map((card) =>
            card.image_uri ? (
              <div
                key={card.id}
                className={`mulligan-card ${isSelectingBottom && selected.has(card.id) ? "bottom-selected" : ""}`}
                onClick={() => toggleSelect(card.id)}
              >
                <img src={card.image_uri} alt={card.name} className="mulligan-card-img" />
                {isSelectingBottom && selected.has(card.id) && (
                  <div className="bottom-badge">Bottom</div>
                )}
              </div>
            ) : (
              <div key={card.id} className="mulligan-card-text">{card.name}</div>
            )
          )}
        </div>

        <div className="mulligan-actions">
          {!isSelectingBottom && (
            <>
              <button className="primary" onClick={() => act("keep")} disabled={busy}>
                Keep Hand
              </button>
              <button onClick={() => act("mulligan")} disabled={busy}>
                {busy ? "Drawing..." : `Mulligan${mulliganCount === 0 ? " (Free)" : ""}`}
              </button>
            </>
          )}
          {isSelectingBottom && (
            <button
              className="primary"
              onClick={() => act("bottom")}
              disabled={busy || selected.size !== needed}
            >
              {selected.size === needed
                ? `Confirm — Put ${needed} card${needed !== 1 ? "s" : ""} on Bottom`
                : `Select ${needed - selected.size} more card${needed - selected.size !== 1 ? "s" : ""}…`}
            </button>
          )}
        </div>

        {error && (
          <p style={{ color: "var(--red)", textAlign: "center", fontSize: "13px" }}>{error}</p>
        )}

        {!isSelectingBottom && mulliganCount === 0 && (
          <p className="mulligan-rule-note">
            Commander rule: first mulligan is free (redraw 7, no cost).
          </p>
        )}
        {!isSelectingBottom && mulliganCount > 0 && (
          <p className="mulligan-rule-note">{freeMulliganNote}</p>
        )}

        {opponentsSection}
      </div>
    </div>
  );
}
