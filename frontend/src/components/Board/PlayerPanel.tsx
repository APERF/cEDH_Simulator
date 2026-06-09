import { useState } from "react";
import { createPortal } from "react-dom";
import type { Player, HandCard, CommanderCard, LandCard, Step } from "../../types/game";

interface Props {
  player: Player;
  isActive: boolean;
  isHumanTurn: boolean;
  currentStep: Step;
  onCastCommander: (cardId: string) => void;
  onPlayCard: (cardId: string, actionType: "play_land" | "cast_spell") => void;
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

export function PlayerPanel({ player, isActive, isHumanTurn, currentStep, onCastCommander, onPlayCard }: Props) {
  const [hovered, setHovered] = useState<{ card: HandCard | CommanderCard | LandCard; rect: DOMRect } | null>(null);
  const isMainPhase = currentStep === "precombat_main" || currentStep === "postcombat_main";
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
                  {player.is_human && (
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
                  {(player.lands ?? []).map((land: LandCard) => (
                    <div key={land.id} className={`bf-land-card${land.tapped ? " tapped" : ""}`}>
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
                  ))}
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
              const canAct = isHumanTurn && isMainPhase && (isLand ? !player.land_played_this_turn : true);
              return (
                <div
                  key={card.id}
                  className={`hand-card-wrap${canAct ? " playable" : ""}`}
                  onClick={() => canAct && onPlayCard(card.id, isLand ? "play_land" : "cast_spell")}
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
    </div>
  );
}
