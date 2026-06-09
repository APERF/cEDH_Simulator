import { useState } from "react";
import { createPortal } from "react-dom";
import type { Player, HandCard, CommanderCard } from "../../types/game";

interface Props {
  player: Player;
  isActive: boolean;
  onCastCommander: (cardId: string) => void;
}

function CardPreviewPortal({ card, anchor }: { card: HandCard | CommanderCard; anchor: DOMRect }) {
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

export function PlayerPanel({ player, isActive, onCastCommander }: Props) {
  const [hovered, setHovered] = useState<{ card: HandCard | CommanderCard; rect: DOMRect } | null>(null);
  const cmdDamage = Object.entries(player.commander_damage).filter(([, dmg]) => dmg > 0);
  const commandZoneCommanders = (player.commanders ?? []).filter((c) => c.in_command_zone);

  return (
    <div className={`player-panel ${isActive ? "active" : ""} ${player.is_human ? "human" : "ai"}`}>
      <div className="pp-header">
        <div className="pp-name">{player.name}</div>
        <span className="pp-tag">{player.is_human ? "You" : "AI"}</span>
      </div>

      <div>
        <div className="pp-life">{player.life_total}</div>
        <div className="pp-life-label">Life Total</div>
      </div>

      <div className="pp-zones">
        <div className="pp-zone">
          <span className="zone-val">{player.hand_size}</span>
          <span className="zone-lbl">Hand</span>
        </div>
        <div className="pp-zone">
          <span className="zone-val">{player.battlefield_count}</span>
          <span className="zone-lbl">Board</span>
        </div>
      </div>

      {/* Command Zone */}
      {commandZoneCommanders.length > 0 && (
        <div className="pp-command-zone">
          <div className="pp-cz-label">Command Zone</div>
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
        </div>
      )}

      {/* Hand (human only) */}
      {player.is_human && (player.hand ?? []).length > 0 && (
        <div className="pp-hand">
          <div className="pp-hand-label">Hand ({player.hand.length})</div>
          <div className="pp-hand-cards">
            {(player.hand ?? []).map((card) =>
              card.image_uri ? (
                <img
                  key={card.id}
                  src={card.image_uri}
                  alt={card.name}
                  className="hand-card-img"
                  onMouseEnter={(e) =>
                    setHovered({ card, rect: e.currentTarget.getBoundingClientRect() })
                  }
                  onMouseLeave={() => setHovered(null)}
                />
              ) : (
                <div key={card.id} className="hand-card">{card.name}</div>
              )
            )}
          </div>
        </div>
      )}

      {hovered && hovered.card.image_uri && (
        <CardPreviewPortal card={hovered.card} anchor={hovered.rect} />
      )}

      {cmdDamage.length > 0 && (
        <div className="pp-cmd-damage">
          {cmdDamage.map(([src, dmg]) => (
            <div key={src} className="cmd-entry">
              <span>{src}</span>
              <span>{dmg} cmd</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
