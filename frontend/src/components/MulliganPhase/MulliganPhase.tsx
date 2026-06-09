import { useState } from "react";
import type { GameState } from "../../types/game";
import { mulliganAction } from "../../services/api";

interface Props {
  gameState: GameState;
  onStateChange: (gs: GameState) => void;
}

export function MulliganPhase({ gameState, onStateChange }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const human = gameState.players.find((p) => p.is_human)!;
  const hand = human.hand ?? [];
  const isSelectingBottom = gameState.mulligan_phase === "selecting_bottom";
  const mulliganCount = gameState.mulligan_count ?? 0;
  const needed = gameState.cards_to_bottom ?? Math.max(0, mulliganCount - 1);

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

  return (
    <div className="mulligan-overlay">
      <div className="mulligan-panel">
        <div className="mulligan-header">
          <h2>Opening Hand</h2>
          {!isSelectingBottom && (
            <p className="mulligan-sub">
              {mulliganCount === 0
                ? `Keep or take your free mulligan? Your seat position is: ${["1st","2nd","3rd","4th"][human.seat - 1]} Seat`
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
              <button
                className="primary"
                onClick={() => act("keep")}
                disabled={busy}
              >
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
      </div>

    </div>
  );
}
