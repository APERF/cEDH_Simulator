import { useState } from "react";
import { useGameStore } from "../../store/gameStore";
import { PlayerPanel } from "./PlayerPanel";
import { FetchModal } from "./FetchModal";
import { sendAction, getGameState } from "../../services/api";
import type { FetchOption, GameState, HandCard } from "../../types/game";

interface Props {
  onStateChange: (gs: GameState) => void;
  aiHandsMap?: Record<string, HandCard[]>;
}

export function Board({ onStateChange, aiHandsMap }: Props) {
  const { gameState, gameId, setLoading, appendLog } = useGameStore();
  const [fetchModal, setFetchModal] = useState<FetchOption[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Combat UI state
  // selectedAttackers: card_id → target_player_id (fully assigned)
  const [selectedAttackers, setSelectedAttackers] = useState<Map<string, string>>(new Map());
  // pendingAttacker: creature selected but waiting for the player to click a target
  const [pendingAttacker, setPendingAttacker] = useState<string | null>(null);
  const [pendingBlocks, setPendingBlocks] = useState<Record<string, string>>({});
  const [pendingBlocker, setPendingBlocker] = useState<string | null>(null);

  if (!gameState) {
    return <div className="board-empty">No active game.</div>;
  }

  const isHumanTurn = !!gameState.players.find(
    (p) => p.is_human && p.id === gameState.active_player_id
  );
  const humanPlayer = gameState.players.find(p => p.is_human);
  const combatAwaiting = gameState.combat_awaiting_human_action ?? null;
  const isSelectingAttackers = combatAwaiting === "declare_attackers";
  const isSelectingBlockers = combatAwaiting === "declare_blockers";

  function showError(e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? (e as { message?: string })?.message
      ?? "Action failed";
    setActionError(msg);
    setTimeout(() => setActionError(null), 4000);
  }

  async function handleCastCommander(cardId: string) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "cast_commander", card_id: cardId });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }

  async function handlePlayCard(
    cardId: string,
    actionType: "play_land" | "cast_spell",
    opts?: { payLife?: boolean }
  ) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: actionType,
        card_id: cardId,
        ...(opts?.payLife !== undefined ? { pay_life: opts.payLife } : {}),
      });
      appendLog(result.log);
      if (result.status === "fetch" && result.fetch_options) {
        setFetchModal(result.fetch_options);
      } else {
        onStateChange(await getGameState(gameId));
      }
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleCompleteFetch(cardId: string) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "complete_fetch", card_id: cardId });
      appendLog(result.log);
      setFetchModal(null);
      onStateChange(await getGameState(gameId));
    } finally {
      setLoading(false);
    }
  }

  async function handleTapLand(cardId: string, color?: string, untap = false) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: untap ? "untap_land" : "tap_land",
        card_id: cardId,
        ...(color ? { color } : {}),
      });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleTapArtifact(cardId: string, color?: string, untap = false) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: untap ? "untap_artifact" : "tap_artifact",
        card_id: cardId,
        ...(color ? { color } : {}),
      });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleEquip(equipmentId: string, creatureId: string) {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, {
        type: "equip",
        equipment_id: equipmentId,
        creature_id: creatureId,
      });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
    }
  }

  // ── Combat handlers ──────────────────────────────────────────────────────

  function handleToggleAttacker(cardId: string) {
    if (pendingAttacker === cardId) {
      // Clicking the pending creature again cancels it
      setPendingAttacker(null);
      return;
    }
    if (selectedAttackers.has(cardId)) {
      // Clicking an already-assigned attacker removes it
      setSelectedAttackers(prev => { const m = new Map(prev); m.delete(cardId); return m; });
      return;
    }
    // Select this creature as the pending attacker; player must now click an opponent
    setPendingAttacker(cardId);
  }

  function handleSelectAttackTarget(targetPlayerId: string) {
    if (!pendingAttacker) return;
    setSelectedAttackers(prev => new Map(prev).set(pendingAttacker, targetPlayerId));
    setPendingAttacker(null);
  }

  function handleToggleBlocker(blockerId: string) {
    if (pendingBlocker === blockerId) {
      setPendingBlocker(null);
    } else {
      setPendingBlocker(blockerId);
    }
  }

  function handleAssignBlockTarget(attackerId: string) {
    if (!pendingBlocker) return;
    // Don't double-assign the same blocker
    setPendingBlocks(prev => ({ ...prev, [pendingBlocker]: attackerId }));
    setPendingBlocker(null);
  }

  function handleUnassignBlock(blockerId: string) {
    setPendingBlocks(prev => {
      const next = { ...prev };
      delete next[blockerId];
      return next;
    });
  }

  async function handleConfirmAttackers() {
    if (!gameId) return;
    const attackersPayload: Record<string, string> = Object.fromEntries(selectedAttackers);
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "declare_attackers", attackers: attackersPayload });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
      setSelectedAttackers(new Map());
      setPendingAttacker(null);
    }
  }

  async function handleSkipAttack() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "declare_attackers", attackers: {} });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
      setSelectedAttackers(new Map());
      setPendingAttacker(null);
    }
  }

  async function handleConfirmBlocks() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "declare_blockers", blocks: pendingBlocks });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
      setPendingBlocks({});
      setPendingBlocker(null);
    }
  }

  async function handleSkipBlocks() {
    if (!gameId) return;
    setLoading(true);
    try {
      const result = await sendAction(gameId, { type: "declare_blockers", blocks: {} });
      appendLog(result.log);
      onStateChange(await getGameState(gameId));
    } catch (e) {
      showError(e);
    } finally {
      setLoading(false);
      setPendingBlocks({});
      setPendingBlocker(null);
    }
  }

  // Players arrive in turn order. Clockwise from top-left in a 2×2 grid: TL→TR→BR→BL.
  // CSS grid row-major order is TL→TR→BL→BR, so swap indices 2 and 3.
  const [p0, p1, p2, p3] = gameState.players;
  const seats = [p0 ?? null, p1 ?? null, p3 ?? null, p2 ?? null];

  return (
    <>
      {fetchModal && (
        <FetchModal
          options={fetchModal}
          onSelect={handleCompleteFetch}
          onClose={() => setFetchModal(null)}
        />
      )}

      {/* Action error toast */}
      {actionError && (
        <div className="action-error-toast">{actionError}</div>
      )}

      {/* Combat action bar */}
      {(isSelectingAttackers || isSelectingBlockers) && (
        <div className="combat-action-bar">
          {isSelectingAttackers && (
            <>
              <span className="combat-label">
                {pendingAttacker
                  ? "Click an opponent to attack with this creature"
                  : selectedAttackers.size > 0
                  ? `${selectedAttackers.size} attacker${selectedAttackers.size !== 1 ? "s" : ""} assigned — select more or confirm`
                  : "Click one of your creatures, then click an opponent to attack"}
              </span>
              {selectedAttackers.size > 0 && !pendingAttacker && (
                <button className="primary combat-confirm-btn" onClick={handleConfirmAttackers}>
                  ⚔ Confirm Attack
                </button>
              )}
              <button className="combat-skip-btn" onClick={handleSkipAttack}>
                Skip Attack
              </button>
            </>
          )}
          {isSelectingBlockers && (
            <>
              <span className="combat-label">
                {pendingBlocker
                  ? "Click an attacking creature to block it"
                  : Object.keys(pendingBlocks).length > 0
                  ? `${Object.keys(pendingBlocks).length} blocker${Object.keys(pendingBlocks).length !== 1 ? "s" : ""} assigned`
                  : "Select one of your creatures to block with"}
              </span>
              <button className="primary combat-confirm-btn" onClick={handleConfirmBlocks}>
                🛡 Confirm Blocks
              </button>
              <button className="combat-skip-btn" onClick={handleSkipBlocks}>
                Take All Damage
              </button>
            </>
          )}
        </div>
      )}

      <div className="commander-table">
        {seats.map((p, i) =>
          p ? (
            <PlayerPanel
              key={p.id}
              player={p}
              isActive={p.id === gameState.active_player_id}
              isHumanTurn={isHumanTurn}
              currentStep={gameState.step}
              currentTurn={gameState.turn}
              onCastCommander={handleCastCommander}
              onPlayCard={handlePlayCard}
              onTapLand={handleTapLand}
              onTapArtifact={handleTapArtifact}
              onEquip={handleEquip}
              aiHandCards={aiHandsMap?.[p.id]}
              allPlayers={gameState.players}
              // combat
              combatMode={
                isSelectingAttackers ? "select_attackers"
                : isSelectingBlockers ? "select_blockers"
                : null
              }
              selectedAttackers={selectedAttackers}
              pendingAttacker={pendingAttacker}
              pendingBlocks={pendingBlocks}
              pendingBlocker={pendingBlocker}
              humanPlayerId={humanPlayer?.id ?? ""}
              onToggleAttacker={handleToggleAttacker}
              onSelectAttackTarget={handleSelectAttackTarget}
              onToggleBlocker={handleToggleBlocker}
              onAssignBlockTarget={handleAssignBlockTarget}
              onUnassignBlock={handleUnassignBlock}
            />
          ) : (
            <div key={i} className="seat-empty" />
          )
        )}
      </div>
    </>
  );
}
