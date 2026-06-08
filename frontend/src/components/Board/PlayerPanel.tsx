import type { Player } from "../../types/game";

interface Props {
  player: Player;
  isActive: boolean;
}

export function PlayerPanel({ player, isActive }: Props) {
  return (
    <div className={`player-panel ${isActive ? "active" : ""} ${player.is_human ? "human" : "ai"}`}>
      <div className="player-name">{player.name}</div>
      <div className="life">{player.life_total} life</div>
      <div className="stats">
        <span>Hand: {player.hand_size}</span>
        <span>Board: {player.battlefield_count}</span>
      </div>
      {Object.entries(player.commander_damage).map(([source, dmg]) => (
        <div key={source} className="cmd-damage">
          {dmg} cmd dmg from {source}
        </div>
      ))}
    </div>
  );
}
