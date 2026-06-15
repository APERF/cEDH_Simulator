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
  "effects": [ <triggered/spell effect objects> ]
}

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
- "upkeep" — beginning of controller's upkeep
- "draw" — controller draws a card
- "spell_cast" — any player casts a spell

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
Untap:     {"type": "untap_all", "filter": "nonland_permanents"}
Discard:   {"type": "discard", "who": "controller", "amount": 1}
Library:   {"type": "scry", "amount": 2}
           {"type": "mill", "who": "controller", "amount": 3}
           {"type": "search_library", "filter": "any", "destination": "hand"}
           {"type": "search_library", "filter": "land", "destination": "battlefield"}
Counter:   {"type": "counter_spell"}

## skip=true Rules

Set skip=true (and skip_reason) for:
- Lands
- Cards whose ONLY effect is a tap mana ability "{T}: Add ..." with NO other triggered/spell effects — mark as skip_reason="tap_mana_only" (mana is handled automatically via oracle text parsing)
- However: equipment cards with mana grants must use is_equipment=true with grants_to_equipped, NOT skip=true
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
→ {"name":"Dockside Extortionist","skip":false,"is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[{"trigger":"etb","optional":false,"needs_target":false,"needs_choice":false,"actions":[{"type":"create_token","token_name":"Treasure","token_type":"Artifact — Token","count":3,"oracle_text":"{T}, Sacrifice this artifact: Add one mana of any color."}]}]}

"Llanowar Elves" Creature "{T}: Add {G}."
→ {"name":"Llanowar Elves","skip":true,"skip_reason":"tap_mana_only","is_equipment":false,"equip_cost":null,"grants_to_equipped":[],"etb_replacement":null,"effects":[]}

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


def parse_batch(cards: list[dict], api_key: str, max_retries: int = 3) -> list[dict] | None:
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
                max_tokens=4096,
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
