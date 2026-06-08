import type { Player } from "../../types/game";

interface Props {
  player: Player;
  isActive: boolean;
}

export function PlayerPanel({ player, isActive }: Props) {
  const cmdDamage = Object.entries(player.commander_damage).filter(([, dmg]) => dmg > 0);

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

      {player.is_human && (player.hand ?? []).length > 0 && (
        <div className="pp-hand">
          <div className="pp-hand-label">Hand</div>
          <div className="pp-hand-cards">
            {(player.hand ?? []).map((card) => (
              <div key={card.id} className="hand-card">{card.name}</div>
            ))}
          </div>
        </div>
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
