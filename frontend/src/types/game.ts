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

export interface ArtifactManaAbility {
  type: string;
  produces: string[];
  count: number;
}

export interface BattlefieldCard {
  id: string;
  name: string;
  image_uri: string | null;
  tapped: boolean;
  type_line: string;
  oracle_text: string | null;
  power: string | null;
  toughness: string | null;
  is_attacking: boolean;
  attacking_target: string | null;
  is_blocking: boolean;
  entered_turn: number;
  equipped_to: string | null;
  mana_ability: ArtifactManaAbility | null;
}

export interface GraveyardCard {
  id: string;
  name: string;
  image_uri: string | null;
  type_line: string;
}

export interface ExileCard {
  id: string;
  name: string;
  image_uri: string | null;
  type_line: string;
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
  graveyard: GraveyardCard[];
  exile_count: number;
  exile: ExileCard[];
  poison_counters: number;
  land_played_this_turn: boolean;
  mana_pool: ManaPool | undefined;
  hand: HandCard[];
  commanders: CommanderCard[];
  lands: LandCard[];
  permanents: BattlefieldCard[];
}

export interface StackItem {
  id: string;
  name: string;
  image_uri: string | null;
  type_line: string;
  mana_cost: string | null;
  controller_id: string;
  controller_name: string;
}

export interface PendingEffectChoice {
  source_card_id: string;
  controller_id: string;
  description: string;
  optional: boolean;
  needs_choice: boolean;
}

export interface ETBReplacementCost {
  type: "discard" | "sacrifice" | "pay_life";
  filter?: "land" | "any" | "creature";
  count?: number;
  amount?: number;
}

export interface ETBReplacement {
  optional: boolean;
  cost: ETBReplacementCost;
  on_pay: string;
  on_skip: string;
  prompt: string;
}

export interface PendingETBReplacement {
  stack_obj_id: string;
  card_id: string;
  card_name: string;
  etb_replacement: ETBReplacement;
}

export interface GameState {
  game_id: string;
  mulligan_phase: "mulliganing" | "selecting_bottom" | "playing";
  mulligan_count: number;
  cards_to_bottom: number;
  mulligan_current_player_id: string | null;
  mulligan_active_player_ids: string[];
  mulligan_counts: Record<string, number>;
  turn: number;
  active_player_id: string;
  phase: Phase;
  step: Step;
  players: Player[];
  stack_size: number;
  stack: StackItem[];
  winner: string | null;
  combat_awaiting_human_action: "declare_attackers" | "declare_blockers" | null;
  combat_attackers: Record<string, string>;
  combat_blockers: Record<string, string[]>;
  pending_choices: PendingEffectChoice[];
  effect_queue_size: number;
  pending_etb_replacement: PendingETBReplacement | null;
}

export interface AIDecisionHandCard {
  name: string;
  cost: string;
  is_land: boolean;
  affordable: boolean;
}

export interface AIDecision {
  turn: number;
  step: string;
  player: string;
  player_id: string;
  action: "play_land" | "cast_spell" | "cast_commander" | "pass";
  card?: string;
  card_cost?: string;
  reason?: string;
  mana: { W: number; U: number; B: number; R: number; G: number; C: number; total: number };
  hand: AIDecisionHandCard[];
}

export interface DebugGameState extends GameState {
  ai_decision_log: AIDecision[];
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
  | "declare_attackers"
  | "declare_blockers"
  | "play_land"
  | "cast_commander"
  | "tap_land"
  | "untap_land"
  | "tap_artifact"
  | "untap_artifact"
  | "complete_fetch"
  | "etb_replacement_choice"
  | "equip";

export interface GameAction {
  type: ActionType;
  card_id?: string;
  targets?: string[];
  color?: string;
  pay_life?: boolean;
  attackers?: Record<string, string>;
  blocks?: Record<string, string>;
  choice?: "pay" | "skip";
  land_id?: string;
  equipment_id?: string;
  creature_id?: string;
}
