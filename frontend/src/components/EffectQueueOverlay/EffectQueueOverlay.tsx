import { useState } from "react";
import type { GameState, PendingEffectChoice } from "../../types/game";
import { sendAction, getGameState } from "../../services/api";

interface Props {
  gameState: GameState;
  onStateChange: (gs: GameState) => void;
}

export function EffectQueueOverlay({ gameState, onStateChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choices = gameState.pending_choices ?? [];
  if (choices.length === 0) return null;

  const top: PendingEffectChoice = choices[0];
  const isOptional = top.optional;
  const needsChoice = top.needs_choice;
  const showChoice = isOptional || needsChoice;

  async function resolve(choice: boolean) {
    setError(null);
    setBusy(true);
    try {
      await sendAction(gameState.game_id, { type: "resolve_effect" as any, choice } as any);
      const next = await getGameState(gameState.game_id);
      onStateChange(next);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="effect-overlay">
      <div className="effect-panel">
        <div className="effect-header">
          <h2>Triggered Ability</h2>
          {choices.length > 1 && (
            <span className="effect-queue-count">+{choices.length - 1} more</span>
          )}
        </div>

        <div className="effect-description">{top.description}</div>

        {choices.length > 1 && (
          <div className="effect-queue-list">
            {choices.slice(1).map((c, i) => (
              <div key={i} className="effect-queue-item">{c.description}</div>
            ))}
          </div>
        )}

        <div className="effect-actions">
          {showChoice ? (
            <>
              <button className="primary" onClick={() => resolve(true)} disabled={busy}>
                {needsChoice && !isOptional ? "Keep" : "Yes"}
              </button>
              <button onClick={() => resolve(false)} disabled={busy}>
                {needsChoice && !isOptional ? "Sacrifice" : "No"}
              </button>
            </>
          ) : (
            <button className="primary" onClick={() => resolve(true)} disabled={busy}>
              Resolve
            </button>
          )}
        </div>

        {error && <p className="effect-error">{error}</p>}
      </div>
    </div>
  );
}
