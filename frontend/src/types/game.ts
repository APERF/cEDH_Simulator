export type Phase =
  | "beginning"
  | "precombat_main"
  | "combat"
  | "postcombat_main"
  | "ending";

export type Step =
  | "untap"
  | "upkeep"
  | "draw"
  | "precombat_main"
  | "begin_combat"
  | "declare_attackers"
  | "declare_blockers"
  | "combat_damage"
  | "end_of_combat"
  | "postcombat_main"
  | "end"
  | "cleanup";

export interface Card {
  id: string;
  name: string;
  mana_cost: string | null;
  cmc: number;
  type_line: string;
  oracle_text: string | null;
  power: string | null;
  toughness: string | null;
  colors: string[];
  color_identity: string[];
  keywords: string[];
  image_uri: string | null;
  tapped?: boolean;
  zone?: string;
}

export interface HandCard {
  id: string;
  name: string;
  image_uri: string | null;
}

export interface Player {
  id: string;
  name: string;
  is_human: boolean;
  life_total: number;
  commander_damage: Record<string, number>;
  hand_size: number;
  battlefield_count: number;
  hand: HandCard[];
}

export interface GameState {
  game_id: string;
  turn: number;
  active_player_id: string;
  phase: Phase;
  step: Step;
  players: Player[];
  stack_size: number;
  winner: string | null;
}

export interface MetaDeck {
  id: string;
  commander: string;
  colors: string[];
  archetype: string;
  top_cuts: number;
  conversion_rate: number;
}

export type ActionType =
  | "cast_spell"
  | "activate_ability"
  | "pass_priority"
  | "declare_attacker"
  | "play_land";

export interface GameAction {
  type: ActionType;
  card_id?: string;
  targets?: string[];
}
