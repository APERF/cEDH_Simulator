import { useState } from "react";
import { createPortal } from "react-dom";
import type { Player, HandCard, CommanderCard, LandCard, BattlefieldCard, GraveyardCard, ManaPool, Step } from "../../types/game";
import { canAfford } from "../../utils/mana";

interface Props {
  player: Player;
  isActive: boolean;
  isHumanTurn: boolean;
  currentStep: Step;
  currentTurn: number;
  onCastCommander: (cardId: string) => void;
  onPlayCard: (cardId: string, actionType: "play_land" | "cast_spell", opts?: { payLife?: boolean }) => void;
  onTapLand: (cardId: string, color?: string, untap?: boolean) => void;
  onTapArtifact?: (cardId: string, color?: string, untap?: boolean) => void;
  onEquip?: (equipmentId: string, creatureId: string) => void;
  aiHandCards?: HandCard[];
  allPlayers?: Player[];   // for name lookup in combat badges
  // combat
  combatMode?: "select_attackers" | "select_blockers" | null;
  selectedAttackers?: Map<string, string>;  // card_id → target_player_id
  pendingAttacker?: string | null;          // creature selected, awaiting target click
  pendingBlocks?: Record<string, string>;
  pendingBlocker?: string | null;
  humanPlayerId?: string;
  onToggleAttacker?: (cardId: string) => void;
  onSelectAttackTarget?: (playerId: string) => void;
  onToggleBlocker?: (cardId: string) => void;
  onAssignBlockTarget?: (attackerId: string) => void;
  onUnassignBlock?: (blockerId: string) => void;
}

const MANA_COLORS = ["W", "U", "B", "R", "G", "C"] as const;

function ManaPoolDisplay({ pool }: { pool: ManaPool }) {
  const pips: string[] = [];
  for (const color of MANA_COLORS) {
    for (let i = 0; i < pool[color]; i++) pips.push(color);
  }
  return (
    <div className="pp-mana-pool">
      <span className="mp-label">Pool</span>
      {pips.length === 0 ? (
        <span className="mp-empty">—</span>
      ) : (
        <div className="mp-pips">
          {pips.map((c, i) => <span key={i} className={`pip pip-${c}`} />)}
        </div>
      )}
    </div>
  );
}

function ColorPickerPortal({ produces, anchor, onSelect, onClose }: {
  produces: string[];
  anchor: DOMRect;
  onSelect: (color: string) => void;
  onClose: () => void;
}) {
  return createPortal(
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 9997 }} onClick={onClose} />
      <div
        className="mana-picker"
        style={{
          position: "fixed",
          left: anchor.left + anchor.width / 2,
          top: anchor.bottom + 8,
          transform: "translateX(-50%)",
          zIndex: 9998,
        }}
      >
        <div className="mp-picker-label">Tap for:</div>
        <div className="mp-picker-colors">
          {produces.map(color => (
            <button
              key={color}
              className={`mp-color-btn pip-${color}`}
              onClick={(e) => { e.stopPropagation(); onSelect(color); }}
              title={color}
            >
              {color}
            </button>
          ))}
        </div>
      </div>
    </>,
    document.body
  );
}

function CardPreviewPortal({ card, anchor }: { card: HandCard | CommanderCard | LandCard | BattlefieldCard; anchor: DOMRect }) {
  const previewWidth = 220;
  const previewHeight = 308; // ~1.4 card ratio
  const margin = 10;

  // Clamp horizontally so preview never leaves the viewport
  let left = anchor.left + anchor.width / 2 - previewWidth / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - previewWidth - margin));

  // Prefer above; fall back to below if not enough room
  const top =
    anchor.top >= previewHeight + margin
      ? anchor.top - previewHeight - margin
      : anchor.bottom + margin;

  const style: React.CSSProperties = {
    position: "fixed",
    left,
    top,
    width: `${previewWidth}px`,
    borderRadius: "12px",
    zIndex: 9999,
    pointerEvents: "none",
    boxShadow: "0 12px 40px rgba(0,0,0,0.85)",
  };
  return createPortal(
    <img src={card.image_uri!} alt={card.name} style={style} />,
    document.body
  );
}

function ShockModal({ landName, playerLife, onPayLife, onEnterTapped, onClose }: {
  landName: string;
  playerLife: number;
  onPayLife: () => void;
  onEnterTapped: () => void;
  onClose: () => void;
}) {
  return createPortal(
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 9997, background: "rgba(0,0,0,0.55)" }} onClick={onClose} />
      <div className="shock-modal" style={{ position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", zIndex: 9998 }}>
        <div className="shock-title">{landName}</div>
        <div className="shock-sub">As this enters, you may pay 2 life.</div>
        <div className="shock-life">{playerLife} → {playerLife - 2} life</div>
        <div className="shock-actions">
          <button className="primary" onClick={onPayLife}>Pay 2 Life — Enter Untapped</button>
          <button onClick={onEnterTapped}>Enter Tapped</button>
        </div>
      </div>
    </>,
    document.body
  );
}

function GraveyardModal({ cards, playerName, zoneName = "Graveyard", onClose }: {
  cards: GraveyardCard[];
  playerName: string;
  zoneName?: string;
  onClose: () => void;
}) {
  return createPortal(
    <>
      <div className="gy-overlay" onClick={onClose} />
      <div className="gy-modal">
        <div className="gy-header">
          <span className="gy-title">{playerName} — {zoneName} ({cards.length})</span>
          <button className="bf-fs-close" onClick={onClose}>✕</button>
        </div>
        <div className="gy-body">
          {cards.length === 0 ? (
            <div className="gy-empty">{zoneName} is empty.</div>
          ) : (
            <div className="gy-cards">
              {[...cards].reverse().map((card) => (
                <div key={card.id} className="gy-card">
                  {card.image_uri ? (
                    <img src={card.image_uri} alt={card.name} className="gy-card-img" />
                  ) : (
                    <div className="gy-card-fallback">
                      <span className="gy-card-name">{card.name}</span>
                      <span className="gy-card-type">{card.type_line}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>,
    document.body
  );
}

export function PlayerPanel({
  player, isActive, isHumanTurn, currentStep, currentTurn,
  onCastCommander, onPlayCard, onTapLand, onTapArtifact, onEquip, aiHandCards,
  combatMode, selectedAttackers, pendingAttacker, pendingBlocks, pendingBlocker,
  humanPlayerId, allPlayers, onToggleAttacker, onSelectAttackTarget, onToggleBlocker, onAssignBlockTarget, onUnassignBlock,
}: Props) {
  const [hovered, setHovered] = useState<{ card: HandCard | CommanderCard | LandCard | BattlefieldCard; rect: DOMRect } | null>(null);
  const [colorPicker, setColorPicker] = useState<{ produces: string[]; anchor: DOMRect; onSelect: (color: string) => void } | null>(null);
  const [shockPrompt, setShockPrompt] = useState<{ cardId: string; name: string } | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [showGY, setShowGY] = useState(false);
  const [showExile, setShowExile] = useState(false);
  const [equipMode, setEquipMode] = useState<string | null>(null); // equipment card id being equipped
  const isMainPhase = currentStep === "precombat_main" || currentStep === "postcombat_main";

  function handleLandClick(land: LandCard, e: React.MouseEvent<HTMLDivElement>) {
    if (!player.is_human || !isHumanTurn) return;
    if (land.tapped) {
      onTapLand(land.id, undefined, true);
      return;
    }
    const ma = land.mana_ability;
    if (ma && ma.produces.length > 1) {
      setColorPicker({
        produces: ma.produces,
        anchor: e.currentTarget.getBoundingClientRect(),
        onSelect: (color) => onTapLand(land.id, color),
      });
    } else {
      onTapLand(land.id, ma?.produces[0]);
    }
  }

  function handleArtifactClick(card: BattlefieldCard, e: React.MouseEvent<HTMLDivElement>) {
    if (!player.is_human || !isHumanTurn || !onTapArtifact) return;
    if (card.tapped) {
      onTapArtifact(card.id, undefined, true);
      return;
    }
    const ma = card.mana_ability;
    if (!ma || !ma.produces.length) return;
    if (ma.type === "any_color") {
      setColorPicker({
        produces: ["W", "U", "B", "R", "G"],
        anchor: e.currentTarget.getBoundingClientRect(),
        onSelect: (color) => onTapArtifact(card.id, color),
      });
    } else if (ma.produces.length > 1) {
      setColorPicker({
        produces: ma.produces,
        anchor: e.currentTarget.getBoundingClientRect(),
        onSelect: (color) => onTapArtifact(card.id, color),
      });
    } else {
      onTapArtifact(card.id, ma.produces[0]);
    }
  }
  const cmdDamage = Object.entries(player.commander_damage).filter(([, dmg]) => dmg > 0);
  const commandZoneCommanders = (player.commanders ?? []).filter((c) => c.in_command_zone);

  return (
    <div className={`player-panel ${isActive ? "active" : ""} ${player.is_human ? "human" : "ai"}`}>
      {/* Header: name + tag on left, life total on right */}
      <div className="pp-header">
        <div className="pp-header-left">
          <span className="pp-name">{player.name}</span>
          <span className="pp-tag">{player.is_human ? "You" : "AI"}</span>
        </div>
        <div className="pp-header-right">
          {combatMode === "select_attackers" && !player.is_human && pendingAttacker && (
            <button
              className="attack-target-btn"
              onClick={() => onSelectAttackTarget?.(player.id)}
              title={`Attack ${player.name} with selected creature`}
            >
              ⚔ Attack {player.name}
            </button>
          )}
          <span className="pp-life">{player.life_total}</span>
          {(player.poison_counters ?? 0) > 0 && (
            <span className="pp-poison">☠{player.poison_counters}</span>
          )}
        </div>
      </div>

      {cmdDamage.length > 0 && (
        <div className="pp-cmd-damage">
          {cmdDamage.map(([src, dmg]) => (
            <div key={src} className="cmd-entry">
              <span>{src}</span>
              <span>{dmg}⚔</span>
            </div>
          ))}
        </div>
      )}

      {player.is_human && player.mana_pool != null && (
        <ManaPoolDisplay pool={player.mana_pool} />
      )}
      {equipMode && (
        <div className="equip-mode-banner">
          Select a creature to equip, or{" "}
          <button className="equip-cancel-btn" onClick={() => setEquipMode(null)}>Cancel</button>
        </div>
      )}

      {/* Main zone layout: Command Zone | Battlefield | Library/GY/Exile */}
      <div className="pp-body">
        <div className="pp-command-zone" data-cmdzone={player.id}>
          <div className="zone-label">Cmd Zone</div>
          {commandZoneCommanders.length === 0 ? (
            <div className="cz-empty">—</div>
          ) : (
            <div className="pp-cz-commanders">
              {commandZoneCommanders.map((cmd) => (
                <div key={cmd.id} className="cz-commander">
                  {cmd.image_uri ? (
                    <img
                      src={cmd.image_uri}
                      alt={cmd.name}
                      className="cz-card-img"
                      onMouseEnter={(e) =>
                        setHovered({ card: cmd, rect: e.currentTarget.getBoundingClientRect() })
                      }
                      onMouseLeave={() => setHovered(null)}
                    />
                  ) : (
                    <div className="cz-card-placeholder">{cmd.name}</div>
                  )}
                  {cmd.commander_tax > 0 && (
                    <div className="cz-tax">+{cmd.commander_tax}</div>
                  )}
                  {player.is_human && canAfford(cmd.mana_cost, player.mana_pool, cmd.commander_tax) && (
                    <button
                      className="cz-cast-btn"
                      onClick={() => onCastCommander(cmd.id)}
                      title={`Cast ${cmd.name}${cmd.commander_tax > 0 ? ` (+${cmd.commander_tax} tax)` : ""}`}
                    >
                      Cast
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="pp-battlefield">
          <div className="bf-permanents">
            <div className="zone-label">Battlefield</div>
            <div className="bf-area">
              {(player.permanents ?? []).filter(c => !c.type_line?.toLowerCase().includes("artifact")).length > 0 ? (
                <div className="bf-lands-cards">
                  {(player.permanents ?? []).filter(c => !c.type_line?.toLowerCase().includes("artifact")).map((card: BattlefieldCard) => {
                    const isCreature = card.type_line?.toLowerCase().includes("creature");
                    const isHuman = player.id === humanPlayerId;

                    // Attacker selection mode (human's own creatures)
                    const hasSummoningSickness = isCreature && card.entered_turn === currentTurn;
                    const isValidAttacker = isCreature && !card.tapped && !hasSummoningSickness && combatMode === "select_attackers" && isHuman;
                    const isSelectedAttacker = selectedAttackers?.has(card.id) ?? false;

                    // Blocker selection mode
                    const isValidBlocker = isCreature && !card.tapped && combatMode === "select_blockers" && isHuman;
                    const isThisPendingBlocker = pendingBlocker === card.id;
                    const assignedAttackerId = pendingBlocks?.[card.id];
                    const isAssignedBlocker = !!assignedAttackerId;

                    // AI attacker display (card is attacking the human)
                    const isAttackingMe = card.is_attacking && !isHuman && combatMode === "select_blockers";
                    const isClickableAttackTarget = isAttackingMe && !!pendingBlocker;

                    let combatClass = "";
                    if (card.is_attacking) combatClass += " attacking";
                    if (card.is_blocking) combatClass += " blocking";
                    if (isSelectedAttacker) combatClass += " selected-attacker";
                    if (isValidAttacker && !isSelectedAttacker) combatClass += " attackable";
                    if (isThisPendingBlocker) combatClass += " pending-blocker";
                    if (isAssignedBlocker) combatClass += " assigned-blocker";
                    if (isValidBlocker && !isThisPendingBlocker && !isAssignedBlocker) combatClass += " blockable";
                    if (isClickableAttackTarget) combatClass += " attack-target";

                    const isManaProducer = isCreature && isHuman && isHumanTurn && !!card.mana_ability?.produces?.length;
                    const manaClass = isManaProducer && !combatMode && !equipMode
                      ? (card.tapped ? " untappable" : " tappable")
                      : "";

                    // Equip targeting: when equipMode is active and this is a creature on the human's side
                    const isEquipTarget = !!equipMode && isCreature && isHuman && !combatMode;
                    if (isEquipTarget) combatClass += " equip-target";

                    function handleCreatureClick(e: React.MouseEvent<HTMLDivElement>) {
                      // Equip target selection
                      if (equipMode && isCreature && isHuman) {
                        onEquip?.(equipMode, card.id);
                        setEquipMode(null);
                        return;
                      }
                      // Mana dork tap
                      if (!combatMode && !equipMode && isManaProducer && !card.tapped && onTapArtifact) {
                        const ma = card.mana_ability!;
                        if (ma.type === "any_color" || ma.produces.length > 1) {
                          setColorPicker({
                            produces: ma.type === "any_color" ? ["W", "U", "B", "R", "G"] : ma.produces,
                            anchor: e.currentTarget.getBoundingClientRect(),
                            onSelect: (color) => { setColorPicker(null); onTapArtifact(card.id, color); },
                          });
                        } else {
                          onTapArtifact(card.id, ma.produces[0]);
                        }
                        return;
                      }
                      // Mana dork untap
                      if (!combatMode && !equipMode && isManaProducer && card.tapped && onTapArtifact) {
                        onTapArtifact(card.id, undefined, true);
                        return;
                      }
                      // Combat
                      if (combatMode === "select_attackers" && isValidAttacker) {
                        onToggleAttacker?.(card.id);
                      } else if (combatMode === "select_blockers") {
                        if (isHuman && isValidBlocker) {
                          if (isAssignedBlocker) {
                            onUnassignBlock?.(card.id);
                          } else {
                            onToggleBlocker?.(card.id);
                          }
                        } else if (isClickableAttackTarget) {
                          onAssignBlockTarget?.(card.id);
                        }
                      }
                    }

                    return (
                      <div
                        key={card.id}
                        data-bf-card={card.id}
                        className={`bf-land-card${card.tapped ? " tapped" : ""}${combatClass}${manaClass}`}
                        onClick={handleCreatureClick}
                        style={{ cursor: (isEquipTarget) || (isManaProducer && !combatMode && !equipMode) || isValidAttacker || isValidBlocker || isClickableAttackTarget ? "pointer" : undefined }}
                      >
                        {card.image_uri ? (
                          <img
                            src={card.image_uri}
                            alt={card.name}
                            title={card.name}
                            onMouseEnter={(e) =>
                              setHovered({ card, rect: e.currentTarget.getBoundingClientRect() })
                            }
                            onMouseLeave={() => setHovered(null)}
                          />
                        ) : (
                          <div className="bf-land-card-fallback">{card.name}</div>
                        )}
                        {isCreature && card.power != null && card.toughness != null && (
                          <div className="creature-pt">{card.power}/{card.toughness}</div>
                        )}
                        {isSelectedAttacker && (
                          <div className="combat-badge attack-badge">
                            ⚔ {(() => {
                              const tid = selectedAttackers?.get(card.id);
                              const tname = allPlayers?.find(p => p.id === tid)?.name;
                              return tname ? `→${tname.split(" ")[0]}` : "";
                            })()}
                          </div>
                        )}
                        {isThisPendingBlocker && <div className="combat-badge block-badge">🛡</div>}
                        {isAssignedBlocker && <div className="combat-badge block-badge">🛡</div>}
                        {card.is_attacking && <div className="combat-badge attacking-badge">⚔</div>}
                        {card.is_blocking && <div className="combat-badge blocking-badge">🛡</div>}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="bf-empty">Empty</div>
              )}
            </div>
          </div>
          <div className="bf-lower-row">
            <div className="bf-lands">
              <div className="zone-label">Lands</div>
              <div className="bf-area">
                {(player.lands ?? []).length > 0 ? (
                  <div className="bf-lands-cards">
                    {(player.lands ?? []).map((land: LandCard) => {
                      const canInteract = player.is_human && isHumanTurn;
                      return (
                        <div
                          key={land.id}
                          data-bf-card={land.id}
                          className={`bf-land-card${land.tapped ? " tapped" : ""}${canInteract && !land.tapped ? " tappable" : ""}${canInteract && land.tapped ? " untappable" : ""}`}
                          onClick={(e) => handleLandClick(land, e)}
                        >
                          {land.image_uri ? (
                            <img
                              src={land.image_uri}
                              alt={land.name}
                              title={land.name}
                              onMouseEnter={(e) =>
                                setHovered({ card: land, rect: e.currentTarget.getBoundingClientRect() })
                              }
                              onMouseLeave={() => setHovered(null)}
                            />
                          ) : (
                            <div className="bf-land-card-fallback">{land.name}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="bf-empty">Empty</div>
                )}
              </div>
            </div>
            <div className="bf-mana-artifacts">
              <div className="zone-label">Mana Artifacts</div>
              <div className="bf-area">
                {(player.permanents ?? []).filter(c => c.type_line?.toLowerCase().includes("artifact")).length > 0 ? (
                  <div className="bf-lands-cards">
                    {(player.permanents ?? []).filter(c => c.type_line?.toLowerCase().includes("artifact")).map((card: BattlefieldCard) => {
                      const hasMana = !!card.mana_ability?.produces?.length;
                      const canInteract = player.is_human && isHumanTurn && hasMana && !!onTapArtifact;
                      const isEquipment = player.is_human && isHumanTurn && !!onEquip && (
                        card.type_line?.toLowerCase().includes("equipment") ||
                        (card.oracle_text || "").includes("Equip")
                      );
                      const isSelectedEquip = equipMode === card.id;
                      let artifactClass = `bf-land-card${card.tapped ? " tapped" : ""}`;
                      if (canInteract && !card.tapped) artifactClass += " tappable";
                      if (canInteract && card.tapped) artifactClass += " untappable";
                      if (isEquipment && !isSelectedEquip) artifactClass += " equippable";
                      if (isSelectedEquip) artifactClass += " selected-equip";

                      function handleArtifactCardClick(e: React.MouseEvent<HTMLDivElement>) {
                        if (isEquipment && !card.tapped) {
                          // Toggle equip mode for this equipment
                          setEquipMode(prev => prev === card.id ? null : card.id);
                          return;
                        }
                        if (canInteract) handleArtifactClick(card, e);
                      }

                      return (
                        <div
                          key={card.id}
                          data-bf-card={card.id}
                          className={artifactClass}
                          onClick={handleArtifactCardClick}
                          style={{ cursor: canInteract || isEquipment ? "pointer" : undefined }}
                        >
                          {card.image_uri ? (
                            <img
                              src={card.image_uri}
                              alt={card.name}
                              title={card.name}
                              onMouseEnter={(e) =>
                                setHovered({ card, rect: e.currentTarget.getBoundingClientRect() })
                              }
                              onMouseLeave={() => setHovered(null)}
                            />
                          ) : (
                            <div className="bf-land-card-fallback">{card.name}</div>
                          )}
                          {isSelectedEquip && (
                            <div className="equip-badge">Equipping…</div>
                          )}
                          {card.equipped_to && (
                            <div className="equip-attached-badge">⚙ Equipped</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="bf-empty">Empty</div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="pp-zone-piles">
          <div className="zone-pile lib-pile-zone">
            <div className="pile-count">{player.library_count ?? 0}</div>
            <div className="pile-stack">
              <div className="pile-card" />
              <div className="pile-card" />
              <div className="pile-card" />
            </div>
            <div className="pile-label">Lib</div>
          </div>
          <div
            className="zone-pile zone-pile-clickable"
            onClick={() => setShowGY(true)}
            title="View graveyard"
          >
            <div className="pile-count">{player.graveyard_count ?? 0}</div>
            <div className="pile-icon">☽</div>
            <div className="pile-label">GY</div>
          </div>
          <div
            className="zone-pile zone-pile-clickable"
            onClick={() => setShowExile(true)}
            title="View exile"
          >
            <div className="pile-count">{player.exile_count ?? 0}</div>
            <div className="pile-icon">⊘</div>
            <div className="pile-label">Exile</div>
          </div>
        </div>
      </div>

      {/* Human player hand: card images */}
      {player.is_human && (player.hand ?? []).length > 0 && (
        <div className="pp-hand" data-hand={player.id}>
          <div className="zone-label">Hand ({player.hand.length})</div>
          <button className="bf-fullscreen-btn" onClick={() => setFullscreen(true)} title="Fullscreen battlefield">⛶</button>
          <div className="pp-hand-cards">
            {(player.hand ?? []).map((card) => {
              const isLand = card.type_line?.toLowerCase().includes("land");
              const affordable = isLand || canAfford(card.mana_cost, player.mana_pool ?? undefined);
              const canAct = isHumanTurn && isMainPhase && (isLand ? !player.land_played_this_turn : affordable);
              return (
                <div
                  key={card.id}
                  className={`hand-card-wrap${canAct ? " playable" : ""}`}
                  onClick={() => {
                    if (!canAct) return;
                    if (isLand && card.entry_condition === "pay_life:2") {
                      setShockPrompt({ cardId: card.id, name: card.name });
                    } else {
                      onPlayCard(card.id, isLand ? "play_land" : "cast_spell");
                    }
                  }}
                  onMouseEnter={(e) => setHovered({ card, rect: e.currentTarget.getBoundingClientRect() })}
                  onMouseLeave={() => setHovered(null)}
                >
                  {card.image_uri ? (
                    <img src={card.image_uri} alt={card.name} className="hand-card-img" />
                  ) : (
                    <div className="hand-card">{card.name}</div>
                  )}
                  {canAct && <div className="hand-card-action-label">{isLand ? "Play" : "Cast"}</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI hand: revealed card images in dev mode, face-down card backs normally */}
      {!player.is_human && player.hand_size > 0 && (
        <div className="pp-ai-hand" data-hand={player.id}>
          <div className="zone-label">
            Hand ({player.hand_size})
            {aiHandCards && <span className="hand-revealed-tag">revealed</span>}
          </div>
          <button className="bf-fullscreen-btn" onClick={() => setFullscreen(true)} title="Fullscreen battlefield">⛶</button>
          {aiHandCards && aiHandCards.length > 0 ? (
            <div className="pp-hand-cards">
              {aiHandCards.map((card) => (
                <div
                  key={card.id}
                  className="hand-card-wrap dev-revealed"
                  onMouseEnter={(e) => setHovered({ card, rect: e.currentTarget.getBoundingClientRect() })}
                  onMouseLeave={() => setHovered(null)}
                >
                  {card.image_uri ? (
                    <img src={card.image_uri} alt={card.name} className="hand-card-img" />
                  ) : (
                    <div className="hand-card">{card.name}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="ai-hand-cards">
              {Array.from({ length: Math.min(player.hand_size, 12) }).map((_, i) => (
                <div key={i} className="ai-card-back" />
              ))}
              {player.hand_size > 12 && (
                <span className="ai-hand-more">+{player.hand_size - 12}</span>
              )}
            </div>
          )}
        </div>
      )}

      {hovered && hovered.card.image_uri && (
        <CardPreviewPortal card={hovered.card} anchor={hovered.rect} />
      )}

      {colorPicker && (
        <ColorPickerPortal
          produces={colorPicker.produces}
          anchor={colorPicker.anchor}
          onSelect={(color) => {
            colorPicker.onSelect(color);
            setColorPicker(null);
          }}
          onClose={() => setColorPicker(null)}
        />
      )}

      {shockPrompt && (
        <ShockModal
          landName={shockPrompt.name}
          playerLife={player.life_total}
          onPayLife={() => {
            onPlayCard(shockPrompt.cardId, "play_land", { payLife: true });
            setShockPrompt(null);
          }}
          onEnterTapped={() => {
            onPlayCard(shockPrompt.cardId, "play_land", { payLife: false });
            setShockPrompt(null);
          }}
          onClose={() => setShockPrompt(null)}
        />
      )}

      {showGY && (
        <GraveyardModal
          cards={player.graveyard ?? []}
          playerName={player.name}
          onClose={() => setShowGY(false)}
        />
      )}

      {showExile && (
        <GraveyardModal
          cards={player.exile ?? []}
          playerName={player.name}
          zoneName="Exile"
          onClose={() => setShowExile(false)}
        />
      )}

      {fullscreen && createPortal(
        <>
          <div className="bf-fs-overlay" onClick={() => setFullscreen(false)} />
          <div className="bf-fs-panel">
            <div className="bf-fs-header">
              <span className="bf-fs-title">{player.name} — Battlefield</span>
              <button className="bf-fs-close" onClick={() => setFullscreen(false)}>✕</button>
            </div>
            <div className="bf-fs-body">
              <div className="bf-fs-row">

                {/* Command Zone */}
                <div className="bf-fs-cz">
                  <div className="zone-label">Cmd Zone</div>
                  <div className="bf-fs-cz-cards">
                    {(player.commanders ?? []).filter(cmd => cmd.in_command_zone).map((cmd) => (
                      cmd.image_uri ? (
                        <img key={cmd.id} src={cmd.image_uri} alt={cmd.name} title={cmd.name} className="bf-fs-cz-img" />
                      ) : (
                        <div key={cmd.id} className="bf-land-card-fallback">{cmd.name}</div>
                      )
                    ))}
                  </div>
                </div>

                {/* Battlefield + Lands */}
                <div className="bf-fs-main">
                  <div className="bf-fs-zone">
                    <div className="zone-label">Battlefield</div>
                    <div className="bf-fs-cards">
                      {(player.permanents ?? []).length === 0
                        ? <div className="bf-empty">Empty</div>
                        : (player.permanents ?? []).map((card: BattlefieldCard) => (
                            <div key={card.id} className={`bf-land-card${card.tapped ? " tapped" : ""}`}>
                              {card.image_uri
                                ? <img src={card.image_uri} alt={card.name} title={card.name} />
                                : <div className="bf-land-card-fallback">{card.name}</div>}
                            </div>
                          ))}
                    </div>
                  </div>
                  <div className="bf-fs-zone lands">
                    <div className="zone-label">Lands</div>
                    <div className="bf-fs-cards">
                      {(player.lands ?? []).length === 0
                        ? <div className="bf-empty">Empty</div>
                        : (player.lands ?? []).map((land: LandCard) => (
                            <div key={land.id} className={`bf-land-card${land.tapped ? " tapped" : ""}`}>
                              {land.image_uri
                                ? <img src={land.image_uri} alt={land.name} title={land.name} />
                                : <div className="bf-land-card-fallback">{land.name}</div>}
                            </div>
                          ))}
                    </div>
                  </div>
                </div>

                {/* Piles */}
                <div className="bf-fs-piles">
                  {[
                    { label: "Library", count: player.library_count ?? 0, icon: null },
                    { label: "Graveyard", count: player.graveyard_count ?? 0, icon: "☽" },
                    { label: "Exile", count: player.exile_count ?? 0, icon: "⊘" },
                  ].map(({ label, count, icon }) => (
                    <div key={label} className="bf-fs-pile">
                      <div className="bf-fs-pile-count">{count}</div>
                      {icon && <div className="bf-fs-pile-icon">{icon}</div>}
                      <div className="bf-fs-pile-label">{label}</div>
                    </div>
                  ))}
                </div>

              </div>
            </div>
          </div>
        </>,
        document.body
      )}
    </div>
  );
}
