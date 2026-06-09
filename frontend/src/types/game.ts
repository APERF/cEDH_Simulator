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
  type_line: string;
  mana_cost: string | null;
  entry_condition: string | null;  // "pay_life:2" | "check" | null
  land_type: string | null;        // "fetch" | "basic" | "dual" | etc.
}

export interface FetchOption {
  id: string;
  name: string;
  image_uri: string | null;
  type_line: string;
}

export interface CommanderCard {
  id: string;
  name: string;
  image_uri: string | null;
  mana_cost: string | null;
  cast_count: number;
  commander_tax: number;
  in_command_zone: boolean;
}

export interface LandManaAbility {
  type: string;
  produces: string[];
  etbt: boolean;
  condition: string | null;
}

export interface LandCard {
  id: string;
  name: string;
  image_uri: string | null;
  tapped: boolean;
  tapped_for: string | null;
  mana_ability: LandManaAbility | null;
}

export interface ManaPool {
  W: number;
  U: number;
  B: number;
  R: number;
  G: number;
  C: number;
}

export interface Player {
  id: string;
  name: string;
  is_human: boolean;
  seat: number;
  life_total: number;
  commander_damage: Record<string, number>;
  hand_size: number;
  battlefield_count: number;
  land_count: number;
  library_count: number;
  graveyard_count: number;
  exile_count: number;
  poison_counters: number;
  land_played_this_turn: boolean;
  mana_pool: ManaPool | undefined;
  hand: HandCard[];
  commanders: CommanderCard[];
  lands: LandCard[];
}

export interface GameState {
  game_id: string;
  mulligan_phase: "mulliganing" | "selecting_bottom" | "playing";
  mulligan_count: number;
  cards_to_bottom: number;
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
  | "play_land"
  | "cast_commander"
  | "tap_land"
  | "untap_land"
  | "complete_fetch";

export interface GameAction {
  type: ActionType;
  card_id?: string;
  targets?: string[];
  color?: string;
  pay_life?: boolean;
}
