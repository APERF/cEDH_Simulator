import { useState } from "react";
import { createPortal } from "react-dom";
import type { Player, HandCard, CommanderCard, LandCard, ManaPool, Step } from "../../types/game";
import { canAfford } from "../../utils/mana";

interface Props {
  player: Player;
  isActive: boolean;
  isHumanTurn: boolean;
  currentStep: Step;
  onCastCommander: (cardId: string) => void;
  onPlayCard: (cardId: string, actionType: "play_land" | "cast_spell", opts?: { payLife?: boolean }) => void;
  onTapLand: (cardId: string, color?: string, untap?: boolean) => void;
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

function CardPreviewPortal({ card, anchor }: { card: HandCard | CommanderCard | LandCard; anchor: DOMRect }) {
  const style: React.CSSProperties = {
    position: "fixed",
    left: anchor.left + anchor.width / 2,
    bottom: window.innerHeight - anchor.top + 10,
    transform: "translateX(-50%)",
    width: "220px",
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

export function PlayerPanel({ player, isActive, isHumanTurn, currentStep, onCastCommander, onPlayCard, onTapLand }: Props) {
  const [hovered, setHovered] = useState<{ card: HandCard | CommanderCard | LandCard; rect: DOMRect } | null>(null);
  const [colorPicker, setColorPicker] = useState<{ landId: string; produces: string[]; anchor: DOMRect } | null>(null);
  const [shockPrompt, setShockPrompt] = useState<{ cardId: string; name: string } | null>(null);
  const isMainPhase = currentStep === "precombat_main" || currentStep === "postcombat_main";

  function handleLandClick(land: LandCard, e: React.MouseEvent<HTMLDivElement>) {
    if (!player.is_human || !isHumanTurn) return;
    if (land.tapped) {
      onTapLand(land.id, undefined, true);
      return;
    }
    const ma = land.mana_ability;
    if (ma && ma.produces.length > 1) {
      setColorPicker({ landId: land.id, produces: ma.produces, anchor: e.currentTarget.getBoundingClientRect() });
    } else {
      onTapLand(land.id, ma?.produces[0]);
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

      {/* Main zone layout: Command Zone | Battlefield | Library/GY/Exile */}
      <div className="pp-body">
        <div className="pp-command-zone">
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
                  {player.is_human && (() => {
                    const cmdAffordable = canAfford(cmd.mana_cost, player.mana_pool, cmd.commander_tax);
                    return (
                      <button
                        className={`cz-cast-btn${cmdAffordable ? "" : " disabled"}`}
                        onClick={() => cmdAffordable && onCastCommander(cmd.id)}
                        title={
                          cmdAffordable
                            ? `Cast ${cmd.name}${cmd.commander_tax > 0 ? ` (+${cmd.commander_tax} tax)` : ""}`
                            : `Need ${cmd.mana_cost ?? ""}${cmd.commander_tax > 0 ? ` +${cmd.commander_tax}` : ""} generic`
                        }
                      >
                        Cast
                      </button>
                    );
                  })()}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="pp-battlefield">
          <div className="bf-permanents">
            <div className="zone-label">Battlefield</div>
            <div className="bf-area">
              {player.battlefield_count - (player.land_count ?? 0) > 0 ? (
                <div className="bf-count-badge">
                  {player.battlefield_count - (player.land_count ?? 0)} permanent{player.battlefield_count - (player.land_count ?? 0) !== 1 ? "s" : ""}
                </div>
              ) : (
                <div className="bf-empty">Empty</div>
              )}
            </div>
          </div>
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
          <div className="zone-pile">
            <div className="pile-count">{player.graveyard_count ?? 0}</div>
            <div className="pile-icon">☽</div>
            <div className="pile-label">GY</div>
          </div>
          <div className="zone-pile">
            <div className="pile-count">{player.exile_count ?? 0}</div>
            <div className="pile-icon">⊘</div>
            <div className="pile-label">Exile</div>
          </div>
        </div>
      </div>

      {/* Human player hand: card images */}
      {player.is_human && (player.hand ?? []).length > 0 && (
        <div className="pp-hand">
          <div className="zone-label">Hand ({player.hand.length})</div>
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

      {/* AI hand: face-down card backs */}
      {!player.is_human && player.hand_size > 0 && (
        <div className="pp-ai-hand">
          <div className="zone-label">Hand ({player.hand_size})</div>
          <div className="ai-hand-cards">
            {Array.from({ length: Math.min(player.hand_size, 12) }).map((_, i) => (
              <div key={i} className="ai-card-back" />
            ))}
            {player.hand_size > 12 && (
              <span className="ai-hand-more">+{player.hand_size - 12}</span>
            )}
          </div>
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
            onTapLand(colorPicker.landId, color);
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
    </div>
  );
}
