"""
Shared LLM utilities for generating effects_json from MTG oracle text.

Used by:
  - app/cards/scryfall.py  (lazy per-game generation)
  - app/scripts/generate_effects.py  (optional bulk pre-warming)
"""
from __future__ import annotations
import json
import os
import time

SYSTEM_PROMPT = """You are an MTG (Magic: The Gathering) card oracle text parser.
Given a numbered list of cards (name, type, oracle text), output a JSON array with one object per card.

## Output Schema

Each object MUST include ALL of these top-level fields:
{
  "name": "<exact card name>",
  "skip": <true|false>,
  "skip_reason": "<string if skip=true, else null>",
  "is_equipment": <true if card has Equip keyword, else false>,
  "equip_cost": "<mana string like '{2}' if is_equipment, else null>",
  "grants_to_equipped": [ <ability objects granted to equipped creature, see below> ],
  "etb_replacement": <object or null — for 'If X would enter' replacement effects>,
  "win_condition": <null or win condition object — see below>,
  "activated_abilities": [ <activated ability objects — see below> ],
  "effects": [ <triggered/spell effect objects> ]
}

## win_condition

Set win_condition to a non-null object ONLY when the card's oracle text contains the phrase "you win the game".
Set win_condition to null for all other cards.

Win condition object format:
{
  "trigger": "<when this win condition is checked — see trigger values below>",
  "condition_type": "<how to evaluate the condition — see types below>",
  "threshold": <integer, for count/life threshold types>,
  "permanent_type": "<creature|artifact|enchantment — for permanent_count_gte>",
  "token_name": "<token name — for token_name_count_gte>",
  "devotion_color": "<W|U|B|R|G — for devotion_gte_library>",
  "llm_condition_text": "<oracle text of just the condition, for llm_eval type>",
  "description": "<one-line human-readable summary>"
}

Win condition trigger values:
- "etb" — fires when this permanent enters the battlefield (e.g. Thassa's Oracle)
- "upkeep_begin" — fires at the beginning of the controller's upkeep (e.g. Felidar Sovereign)
- "draw_replacement" — replaces a draw when controller's library is empty (e.g. Laboratory Maniac)
- "spell_resolve" — fires when the spell resolves (e.g. Approach of the Second Sun)
- "state_based" — checked continuously as a state-based action

Win condition condition_type values:
- "library_empty" — win if the controller's library has 0 cards
- "life_threshold_gte" — win if controller's life total >= threshold
- "permanent_count_gte" — win if controller controls >= threshold permanents matching permanent_type
- "token_name_count_gte" — win if controller controls >= threshold tokens named token_name
- "creature_count_gte" — win if controller controls >= threshold creatures
- "devotion_gte_library" — win if devotion to devotion_color >= controller's library size
- "card_cast_before_this_game" — win if the controller has previously cast this same card (Approach second-cast)
- "llm_eval" — condition is complex; include llm_condition_text so a later LLM call can evaluate it

Win condition examples:
- "Thassa's Oracle" Creature "When Thassa's Oracle enters the battlefield, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top and the rest on the bottom. If X is greater than or equal to the number of cards in your library, you win the game."
  → "win_condition": {"trigger":"etb","condition_type":"devotion_gte_library","devotion_color":"U","description":"Win if devotion to blue >= library size on ETB"}
  → "effects": [{"trigger":"etb","optional":false,"needs_target":false,"needs_choice":true,"description":"Look at top X cards where X is devotion to blue, put up to 1 on top","actions":[{"type":"look_arrange","compute_amount":"devotion:U","keep_top":1,"rest":"bottom_any_order"}]}]

- "Laboratory Maniac" Creature "If you would draw a card while your library has no cards in it, you win the game instead."
  → "win_condition": {"trigger":"draw_replacement","condition_type":"library_empty","description":"Win instead of drawing from an empty library"}

- "Felidar Sovereign" Creature "At the beginning of your upkeep, if you have 40 or more life, you win the game."
  → "win_condition": {"trigger":"upkeep_begin","condition_type":"life_threshold_gte","threshold":40,"description":"Win at upkeep if you have 40+ life"}

- "Revel in Riches" Enchantment "At the beginning of your upkeep, if you control ten or more Treasure tokens, you win the game."
  → "win_condition": {"trigger":"upkeep_begin","condition_type":"token_name_count_gte","token_name":"Treasure","threshold":10,"description":"Win at upkeep if you control 10+ Treasure tokens"}

- "Epic Struggle" Enchantment "At the beginning of your upkeep, if you control twenty or more creatures, you win the game."
  → "win_condition": {"trigger":"upkeep_begin","condition_type":"creature_count_gte","threshold":20,"description":"Win at upkeep if you control 20+ creatures"}

- "Coalition Victory" Sorcery "You win the game if you control a land of each basic land type and a creature of each color."
  → "win_condition": {"trigger":"spell_resolve","condition_type":"llm_eval","llm_condition_text":"you control a land of each basic land type and a creature of each color","description":"Win if you control all basic land types and creatures of all 5 colors"}

- "Approach of the Second Sun" Sorcery "If Approach of the Second Sun was cast from your hand and you've previously cast it this game, you win the game. Otherwise, put Approach of the Second Sun into its owner's library seventh from the top and you gain 7 life."
  → "win_condition": {"trigger":"spell_resolve","condition_type":"card_cast_before_this_game","description":"Win if you've previously cast Approach of the Second Sun"}
  → "effects": [{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":false,"description":"Put Approach 7th from top and gain 7 life (first cast)","actions":[{"type":"gain_life","who":"controller","amount":7},{"type":"put_on_top","amount":7}]}]

## is_equipment + grants_to_equipped

Use when oracle text contains "Equip" keyword. The tap mana ability belongs to the EQUIPPED CREATURE, not the equipment itself.

Ability object for grants_to_equipped:
  {"type": "mana_ability", "any_color": true, "count": 1}
  {"type": "mana_ability", "colors": ["G"], "count": 1}
  {"type": "mana_ability", "colors": ["W", "U"], "count": 1}

Example — Paradise Mantle "Equipped creature has '{T}: Add one mana of any color.' Equip {0}":
→ {"name":"Paradise Mantle","skip":false,"is_equipment":true,"equip_cost":"{0}","grants_to_equipped":[{"type":"mana_ability","any_color":true,"count":1}],"etb_replacement":null,"effects":[]}

Example — Sword of Feast and Famine (equipment with protection, not mana):
→ {"name":"Sword of Feast and Famine","skip":true,"skip_reason":"complex_combat_equipment","is_equipment":true,"equip_cost":"{2}","grants_to_equipped":[],"etb_replacement":null,"effects":[]}

## etb_replacement

Use when oracle text says "If [card name] would enter the battlefield, you may [cost]. If you do, put [card name] onto the battlefield. If you don't, put it into its owner's graveyard."

Format:
{
  "optional": true,
  "cost": {"type": "discard", "filter": "land", "count": 1},
  "on_pay": "enter_battlefield",
  "on_skip": "graveyard",
  "prompt": "Human-readable choice prompt"
}

Supported cost types: "discard" (filter: "land"|"any"|"creature"), "sacrifice" (filter: "creature"), "pay_life" (amount: N)

Example — Mox Diamond:
→ {"name":"Mox Diamond","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":{"optional":true,"cost":{"type":"discard","filter":"land","count":1},"on_pay":"enter_battlefield","on_skip":"graveyard","prompt":"Discard a land to put Mox Diamond onto the battlefield?"},"effects":[]}

## effects — Trigger Values
- "spell_resolve" — instant or sorcery resolves
- "etb" — permanent enters the battlefield
- "ltb" — permanent leaves the battlefield
- "upkeep_begin" — beginning of controller's upkeep (NOT "upkeep" — use "upkeep_begin")
- "turn_begin" — beginning of controller's turn (before untap)
- "draw" — controller draws a card
- "spell_cast" — any player casts a spell
- "attacked" — this creature was declared as an attacker

## compute_amount — Dynamic X Values

Some cards say "where X is your devotion to [color]" or "where X is the number of [things]".
Add "compute_amount" to the action instead of a hardcoded "amount". Supported values:
- "devotion:U" / "devotion:W" / "devotion:B" / "devotion:R" / "devotion:G" — count that color's pips in mana costs of permanents the controller controls (excluding the source card itself)
- "opponent_count" — number of opponents
- "hand_count" — cards in controller's hand
- "library_count" — cards in controller's library
- "creatures_count" — creatures controller controls
- "artifacts_opponents" — artifacts and enchantments opponents control (for Dockside-like effects)
- "spells_cast_this_turn" — number of spells the controller has cast this turn (Aetherflux Reservoir)

When compute_amount is present, omit "amount" (or set it to 0 as a fallback).

## condition — Conditional Triggers

Some triggered abilities only fire when a game-state condition is met ("if you have 40 or more life").
Add an optional "condition" object to an effects[] entry to gate when the trigger fires.
If the condition is false at trigger collection time the trigger is silently skipped.

Supported condition types:
- {"type": "controller_life_gte", "threshold": 40}   — controller has >= N life at trigger time
- {"type": "spells_cast_this_turn_gte", "threshold": 3} — controller has cast >= N spells this turn
- {"type": "card_cast_before_this_game"}              — controller previously cast this same card

Examples:
- Aetherflux Reservoir "Whenever you cast a spell, you gain 1 life for each spell you've cast this turn."
  → {"trigger":"spell_cast","optional":false,"needs_target":false,"needs_choice":false,
     "description":"Gain 1 life per spell cast this turn",
     "actions":[{"type":"gain_life","who":"controller","compute_amount":"spells_cast_this_turn"}]}
  (No condition needed — the trigger fires on every spell cast and gain=0 is harmless on turn 1)

- Approach of the Second Sun (second cast wins):
  Use win_condition with condition_type "card_cast_before_this_game" (see win_condition section)

## Action Types (inside effects[].actions)

Add mana:  {"type": "add_mana", "mana": {"B": 3}}
Draw:      {"type": "draw", "who": "controller", "amount": 1}
           {"type": "draw", "who": "each_opponent", "amount": 1}
Life:      {"type": "gain_life", "who": "controller", "amount": 3}
           {"type": "lose_life", "who": "each_opponent", "amount": 2}
Damage:    {"type": "deal_damage", "to": "each_opponent", "amount": 3}
           {"type": "deal_damage", "to": "target", "amount": 3}
Destroy:   {"type": "destroy_all", "filter": "creature"}
           {"type": "destroy", "target_type": "creature"}
Exile:     {"type": "exile_all", "filter": "artifact"}
           {"type": "exile", "target_type": "permanent"}
Bounce:    {"type": "bounce", "target_type": "creature"}
Tokens:    {"type": "create_token", "token_name": "Treasure", "token_type": "Artifact — Token", "count": 1, "oracle_text": "{T}, Sacrifice this artifact: Add one mana of any color."}
           {"type": "create_token", ..., "compute_count": "artifacts_opponents"}
Untap:     {"type": "untap_all", "filter": "nonland_permanents"}
Discard:   {"type": "discard", "who": "controller", "amount": 1}
Library:   {"type": "scry", "amount": 2}
           {"type": "mill", "who": "controller", "amount": 3}
           {"type": "search_library", "filter": "any", "destination": "hand"}
           {"type": "search_library", "filter": "any", "destination": "top_of_library"}
           {"type": "search_library", "filter": "land", "destination": "battlefield"}
           {"type": "put_on_top", "amount": 2}
           {"type": "exile_library_until_named", "exile_top_first": 6, "put_named_in_hand": true}
           {"type": "look_arrange", "compute_amount": "devotion:U", "keep_top": 1, "rest": "bottom_any_order"}
           — look at top X cards (X from compute_amount or amount), put up to keep_top on top, rest to bottom
Sacrifice: {"type": "sacrifice", "target_type": "creature", "who": "controller"}
           {"type": "sacrifice", "target_type": "permanent", "who": "each_opponent"}
Graveyard: {"type": "return_from_graveyard", "filter": "creature", "destination": "hand", "who": "controller"}
           — destination: "hand" | "battlefield" | "top_of_library"
Counters:  {"type": "add_counters", "counter_type": "+1/+1", "amount": 1, "target_filter": "self"}
           {"type": "add_counters", "counter_type": "+1/+1", "amount": 1, "target_filter": "controller_permanents", "filter": "creature", "who": "controller"}
Tap:       {"type": "tap_target", "target_type": "creature", "who": "each_opponent"}
           {"type": "tap_all", "target_type": "creature", "who": "each_opponent"}
Counter:   {"type": "counter_spell"}

## activated_abilities

Capture non-mana activated abilities in the top-level "activated_abilities" array.
Do NOT add simple "{T}: Add [mana]" here — those are handled by the mana system automatically.
DO capture: draw a card, create tokens, destroy targets, untap permanents, gain life, etc.
Cards with activated abilities must have skip=false even if they also have tap-mana.

Activated ability object format:
{
  "id": "<kebab-case unique id, e.g. 'kenrith-draw' or 'selvala-reveal'>",
  "description": "<short human-readable description>",
  "cost": {
    "tap": <true if {T} is part of the cost, else false>,
    "mana": "<mana string e.g. '{2}{U}', or null>",
    "pay_life": <integer, 0 if none>,
    "discard": <integer cards to discard, 0 if none>,
    "sacrifice_self": <true if this card sacrifices itself, else false>,
    "sacrifice_type": "<creature|artifact|permanent|null — type of OTHER permanent to sacrifice>"
  },
  "sorcery_speed": <true only if the ability explicitly says 'activate only as a sorcery'>,
  "needs_target": <true if ability requires choosing a target>,
  "actions": [ <same action objects as effects[].actions> ]
}

Examples:
- Kenrith "Pay {2}{U}: Target player draws a card."
  → {"id":"kenrith-draw","description":"Target player draws a card","cost":{"tap":false,"mana":"{2}{U}","pay_life":0,"discard":0,"sacrifice_self":false,"sacrifice_type":null},"sorcery_speed":false,"needs_target":true,"actions":[{"type":"draw","who":"target","amount":1}]}
- Walking Ballista "Remove a +1/+1 counter from Walking Ballista: It deals 1 damage to any target."
  → {"id":"ballista-shoot","description":"Deal 1 damage to target","cost":{"tap":false,"mana":null,"pay_life":0,"discard":0,"sacrifice_self":false,"sacrifice_type":null},"sorcery_speed":false,"needs_target":true,"actions":[{"type":"deal_damage","to":"target","amount":1}]}

## skip=true Rules

Set skip=true (and skip_reason) for:
- Lands
- Cards whose ONLY effect is a tap mana ability "{T}: Add ..." (including "{T}, Sacrifice [card]: Add ..." one-shot variants like Lotus Petal) with NO other triggered/spell/activated effects — mark as skip_reason="tap_mana_only" (mana system auto-detects sacrifice_on_tap and discard_hand_on_tap from oracle text)
- EXCEPTION: if a card has "{T}: Add ..." AND other activated abilities, set skip=false and capture the non-mana activated abilities in activated_abilities[]
- Equipment cards with mana grants must use is_equipment=true with grants_to_equipped, NOT skip=true
- ETB replacement cards (Mox Diamond) must use etb_replacement field, NOT skip=true
- Replacement effects other than ETB-entry ("if you would draw ... instead")
- Temporary stat boosts only (+N/+N until end of turn)
- Planeswalker loyalty abilities
- X spells where X varies (Blue Sun's Zenith, etc.)
- Modal spells with 3+ distinct modes
- Storm, cascade, or copy effects
- Cards too complex to express in this schema

## Rules for optional / needs_target / needs_choice

optional=true if oracle text says "you may"
needs_target=true for "target creature/player/permanent" (single chosen target)
needs_target=false for "each opponent", "all creatures", "each player"
needs_choice=true if player must make a non-targeting decision (choose a color, choose which card to keep)

## Examples

"Dark Ritual" Sorcery "Add {B}{B}{B}."
→ {"name":"Dark Ritual","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"add_mana","mana":{"B":3}}]}]}

"Sol Ring" Artifact "{T}: Add {C}{C}."
→ {"name":"Sol Ring","skip":true,"skip_reason":"tap_mana_only","is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[]}

"Paradise Mantle" Artifact "Equipped creature has '{T}: Add one mana of any color.' Equip {0}"
→ {"name":"Paradise Mantle","skip":false,"is_equipment":true,"equip_cost":"{0}","grants_to_equipped":[{"type":"mana_ability","any_color":true,"count":1}],"etb_replacement":null,"effects":[]}

"Mox Diamond" Artifact "If Mox Diamond would enter the battlefield, you may discard a land card instead. If you do, put Mox Diamond onto the battlefield. If you don't, put it into its owner's graveyard. {T}: Add one mana of any color."
→ {"name":"Mox Diamond","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":{"optional":true,"cost":{"type":"discard","filter":"land","count":1},"on_pay":"enter_battlefield","on_skip":"graveyard","prompt":"Discard a land to put Mox Diamond onto the battlefield?"},"effects":[]}

"Dockside Extortionist" Creature "When Dockside Extortionist enters the battlefield, create X Treasure tokens, where X is the number of artifacts and enchantments your opponents control."
→ {"name":"Dockside Extortionist","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"win_condition":null,"activated_abilities":[],"effects":[{"trigger":"etb","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"create_token","token_name":"Treasure","token_type":"Artifact — Token","count":0,"compute_count":"artifacts_opponents","oracle_text":"{T}, Sacrifice this artifact: Add one mana of any color."}]}]}

"Counterspell" Instant "Counter target spell."
→ {"name":"Counterspell","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":true,"needs_choice":false,"actions":[{"type":"counter_spell"}]}]}

"Ponder" Sorcery "Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card."
→ {"name":"Ponder","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"scry","amount":3},{"type":"draw","who":"controller","amount":1}]}]}

"Brainstorm" Instant "Draw three cards, then put two cards from your hand on top of your library in any order."
→ {"name":"Brainstorm","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"draw","who":"controller","amount":3},{"type":"put_on_top","amount":2}]}]}

"Vampiric Tutor" Instant "Search your library for a card and put that card on top of your library, then shuffle. You lose 2 life."
→ {"name":"Vampiric Tutor","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"search_library","filter":"any","destination":"top_of_library"},{"type":"lose_life","who":"controller","amount":2}]}]}

"Demonic Consultation" Instant "Name a card. Exile the top six cards of your library face down. Then reveal cards from the top of your library until you reveal the named card. Exile all other cards revealed this way, then put the named card into your hand."
→ {"name":"Demonic Consultation","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":true,"actions":[{"type":"exile_library_until_named","exile_top_first":6,"put_named_in_hand":true}]}]}

"Tainted Pact" Instant "Exile the top card of your library. You may put that card into your hand unless it has the same name as another card exiled this way. Repeat this process until you put a card into your hand or you exile two cards with the same name."
→ {"name":"Tainted Pact","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"spell_resolve","optional":false,"needs_target":false,"needs_choice":true,"actions":[{"type":"exile_library_until_named","exile_top_first":0,"put_named_in_hand":true}]}]}

"Llanowar Elves" Creature "{T}: Add {G}."
→ {"name":"Llanowar Elves","skip":true,"skip_reason":"tap_mana_only","is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"win_condition":null,"activated_abilities":[],"effects":[]}

"Thassa's Oracle" Creature "When Thassa's Oracle enters the battlefield, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top of your library and the rest on the bottom of your library in any order. If X is greater than or equal to the number of cards in your library, you win the game."
→ {"name":"Thassa's Oracle","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"win_condition":{"trigger":"etb","condition_type":"devotion_gte_library","devotion_color":"U","description":"Win if devotion to blue >= library size on ETB"},"activated_abilities":[],"effects":[{"trigger":"etb","optional":false,"needs_target":false,"needs_choice":true,"description":"Look at top X cards where X is devotion to blue, put up to 1 on top","actions":[{"type":"look_arrange","compute_amount":"devotion:U","keep_top":1,"rest":"bottom_any_order"}]}]}

Output ONLY the raw JSON array. No markdown, no explanation, no code fences."""


def build_prompt(cards: list[dict]) -> str:
    """Build the user prompt for a batch of cards."""
    lines = []
    for i, c in enumerate(cards, 1):
        lines.append(f"{i}. Name: {c['name']}")
        lines.append(f"   Type: {c['type_line']}")
        oracle = (c.get("oracle_text") or "").replace("\n", " ").strip()
        lines.append(f"   Oracle: {oracle}")
        lines.append("")
    return "\n".join(lines)


def parse_batch(cards: list[dict], api_key: str, max_retries: int = 3, max_tokens: int = 4096) -> list[dict] | None:
    """
    Call Claude Haiku with a batch of cards and return parsed effects_json list.
    Each card dict must have: name, type_line, oracle_text.
    Returns None if all retries fail.
    """
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(cards)

    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError as e:
            if attempt == max_retries - 1:
                return None
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)
    return None
