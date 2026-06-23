"""
Layer 3: Explicit cEDH staple card effects.

Each entry is a list of CardEffect objects keyed by exact card name.
These override/supplement Layer 1 (keyword) and Layer 2 (pattern) effects
for cards that need precise, hand-written logic.

Resolution order: registry → keywords → patterns
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable
from app.engine.effects import (
    CardEffect, GameEvent,
    EVENT_ETB, EVENT_SPELL_CAST, EVENT_DRAW, EVENT_LTB,
    EVENT_UPKEEP_BEGIN, EVENT_TURN_BEGIN, EVENT_ATTACKED,
)

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState


# ── Shared helpers ────────────────────────────────────────────────────────────

def _draw(gs: "GameState", player_id: str, n: int = 1) -> None:
    p = gs.get_player(player_id)
    if not p:
        return
    p.draw(n)
    gs.log(f"{p.name} draws {n} card(s)")
    for _ in range(n):
        gs.fire_event(GameEvent(type=EVENT_DRAW, controller_id=player_id, data={"amount": 1}))


def _add_mana(gs: "GameState", player_id: str, **colors: int) -> None:
    p = gs.get_player(player_id)
    if not p:
        return
    for color, amount in colors.items():
        setattr(p.mana_pool, color, getattr(p.mana_pool, color) + amount)
    mana_str = " ".join(f"{{{c}}}×{a}" for c, a in colors.items() if a)
    gs.log(f"{p.name} adds {mana_str} to mana pool")


def _create_treasure(gs: "GameState", player_id: str, count: int) -> None:
    import uuid
    from app.engine.card import Card
    from app.models.schemas import Zone
    p = gs.get_player(player_id)
    if not p:
        return
    for _ in range(count):
        token = Card(
            id=str(uuid.uuid4()),
            name="Treasure",
            mana_cost="",
            cmc=0,
            type_line="Artifact — Token",
            oracle_text="{T}, Sacrifice this artifact: Add one mana of any color.",
            colors=[],
            color_identity=[],
            keywords=[],
            owner_id=player_id,
            controller_id=player_id,
            zone=Zone.BATTLEFIELD,
        )
        p.battlefield.add(token)
    gs.log(f"{p.name} creates {count} Treasure token(s)")


def _count_opp_artifacts_enchantments(gs: "GameState", player_id: str) -> int:
    total = 0
    for opp in gs.get_opponents(player_id):
        for perm in opp.battlefield.permanents:
            if perm.is_artifact or perm.is_enchantment:
                total += 1
    return total


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, list[CardEffect]] = {}

# Spell resolve registry: name → fn(gs, controller_id, card)
# Called when an instant/sorcery resolves off the stack, before the LLM interpreter.
SPELL_REGISTRY: dict[str, Callable] = {}

# ETB replacement effects — checked in game.py BEFORE resolve_fn fires.
# Structure per entry: {optional, cost: {type, filter, count}, on_pay, on_skip}
ETB_REPLACEMENTS: dict[str, dict] = {
    "Mox Diamond": {
        "optional": True,
        "cost": {"type": "discard", "filter": "land", "count": 1},
        "on_pay": "enter_battlefield",
        "on_skip": "graveyard",
        "prompt": "Discard a land to put Mox Diamond onto the battlefield?",
    },
}


def _reg(name: str, effects: list[CardEffect]) -> None:
    REGISTRY[name] = effects


def _spell(name: str, fn: Callable) -> None:
    """Register a spell resolve function AND suppress LLM fallthrough."""
    SPELL_REGISTRY[name] = fn
    _reg(name, [])


# ── Mana rocks ────────────────────────────────────────────────────────────────

def _simple_mana_etb(name: str, **colors: int) -> None:
    """Register a mana rock that does nothing on ETB (mana comes from tapping, handled by mana_ability)."""
    # These are artifacts; mana comes from tap activated ability in base_ai + mana_ability system.
    # We register them so the resolver knows they have rules covered.
    _reg(name, [])


_simple_mana_etb("Sol Ring")
_simple_mana_etb("Mana Crypt")
_simple_mana_etb("Mana Vault")
_simple_mana_etb("Arcane Signet")
_simple_mana_etb("Talisman of Dominance")
_simple_mana_etb("Talisman of Creativity")
_simple_mana_etb("Talisman of Progress")
_simple_mana_etb("Talisman of Conviction")
_simple_mana_etb("Talisman of Curiosity")
_simple_mana_etb("Talisman of Unity")
_simple_mana_etb("Talisman of Resilience")
_simple_mana_etb("Talisman of Hierarchy")
_simple_mana_etb("Talisman of Indulgence")
_simple_mana_etb("Mind Stone")
_simple_mana_etb("Thought Vessel")
_simple_mana_etb("Grim Monolith")
_simple_mana_etb("Basalt Monolith")


# Lotus Petal: activated ability ({T}, Sacrifice: Add one mana of any color).
# Handled entirely by the tap_artifact action in game.py — no ETB effect needed.


# ── Library-exile spells handled by interpreter ───────────────────────────────
# Demonic Consultation and Tainted Pact use the exile_library_until_named action
# in their effects_json. The interpreter (interpreter.py) handles it generically
# via _exile_library_for_name — no per-card Python needed here.




# ── Mox Diamond ───────────────────────────────────────────────────────────────

def _mox_diamond_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if not controller:
        return
    # Discard a land or sacrifice Mox Diamond
    land_in_hand = next((c for c in controller.hand.cards if c.is_land), None)
    if land_in_hand:
        controller.hand._cards.remove(land_in_hand)
        from app.models.schemas import Zone
        land_in_hand.zone = Zone.GRAVEYARD
        controller.graveyard.add(land_in_hand)
        gs.log(f"{card.name}: discard {land_in_hand.name} to stay in play")
    else:
        controller.battlefield.remove(card.id)
        from app.models.schemas import Zone
        card.zone = Zone.GRAVEYARD
        controller.graveyard.add(card)
        gs.log(f"{card.name}: no land to discard, sacrificed")

_reg("Mox Diamond", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_mox_diamond_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    needs_choice=True,
    description="Discard a land from hand to keep Mox Diamond, or sacrifice it",
)])


# ── Dockside Extortionist ─────────────────────────────────────────────────────

def _dockside_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    n = _count_opp_artifacts_enchantments(gs, card.controller_id)
    if n > 0:
        _create_treasure(gs, card.controller_id, n)
        gs.log(f"Dockside Extortionist: creates {n} Treasure(s)")

_reg("Dockside Extortionist", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_dockside_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    description="Create X Treasure tokens where X = opponent artifacts + enchantments",
)])


# ── Rhystic Study ─────────────────────────────────────────────────────────────

def _rhystic_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None:
        return False
    # Fires when any opponent casts a spell
    return event.controller_id != card.controller_id

def _rhystic_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    caster = gs.get_player(event.controller_id)
    if not controller or not caster:
        return
    # AI opponents auto-pay if they have {1} available; human always draws (simplified)
    if caster.is_human:
        caster_pool_total = sum([
            caster.mana_pool.W, caster.mana_pool.U, caster.mana_pool.B,
            caster.mana_pool.R, caster.mana_pool.G, caster.mana_pool.C,
        ])
        if caster_pool_total >= 1:
            caster.mana_pool.C = max(0, caster.mana_pool.C - 1)
            gs.log(f"{caster.name} pays {{1}} for Rhystic Study")
            return
    _draw(gs, card.controller_id)
    gs.log(f"Rhystic Study: {controller.name} draws a card")

_reg("Rhystic Study", [CardEffect(
    trigger=EVENT_SPELL_CAST,
    resolve=_rhystic_resolve,
    condition=_rhystic_trigger,
    optional=False,
    description="Opponent casts a spell → draw unless they pay {1}",
)])


# ── Mystic Remora ─────────────────────────────────────────────────────────────

def _remora_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None:
        return False
    if event.controller_id == card.controller_id:
        return False
    # Only noncreature spells
    from app.engine.effects import _find_card
    source = _find_card(gs, event.source_card_id)
    return source is not None and not source.is_creature

def _remora_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    caster = gs.get_player(event.controller_id)
    controller = gs.get_player(card.controller_id)
    if not caster or not controller:
        return
    pool_total = sum([
        caster.mana_pool.W, caster.mana_pool.U, caster.mana_pool.B,
        caster.mana_pool.R, caster.mana_pool.G, caster.mana_pool.C,
    ])
    if pool_total >= 4:
        # AI pays {4}
        paid = 0
        for attr in ["C", "G", "R", "B", "U", "W"]:
            while paid < 4 and getattr(caster.mana_pool, attr) > 0:
                setattr(caster.mana_pool, attr, getattr(caster.mana_pool, attr) - 1)
                paid += 1
        gs.log(f"{caster.name} pays {{4}} for Mystic Remora")
    else:
        _draw(gs, card.controller_id)
        gs.log(f"Mystic Remora: {controller.name} draws a card")

_reg("Mystic Remora", [CardEffect(
    trigger=EVENT_SPELL_CAST,
    resolve=_remora_resolve,
    condition=_remora_trigger,
    description="Opponent casts noncreature → draw unless they pay {4}",
)])


# ── Smothering Tithe ─────────────────────────────────────────────────────────

def _tithe_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None:
        return False
    return event.controller_id != card.controller_id

def _tithe_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    drawing_player = gs.get_player(event.controller_id)
    controller = gs.get_player(card.controller_id)
    if not drawing_player or not controller:
        return
    # Check if drawing player has {2} to pay
    pool_total = sum([
        drawing_player.mana_pool.W, drawing_player.mana_pool.U,
        drawing_player.mana_pool.B, drawing_player.mana_pool.R,
        drawing_player.mana_pool.G, drawing_player.mana_pool.C,
    ])
    if pool_total >= 2:
        paid = 0
        for attr in ["C", "G", "R", "B", "U", "W"]:
            while paid < 2 and getattr(drawing_player.mana_pool, attr) > 0:
                setattr(drawing_player.mana_pool, attr, getattr(drawing_player.mana_pool, attr) - 1)
                paid += 1
        gs.log(f"{drawing_player.name} pays {{2}} for Smothering Tithe")
    else:
        _create_treasure(gs, card.controller_id, 1)
        gs.log(f"Smothering Tithe: {controller.name} creates a Treasure")

_reg("Smothering Tithe", [CardEffect(
    trigger=EVENT_DRAW,
    resolve=_tithe_resolve,
    condition=_tithe_trigger,
    description="Opponent draws → create Treasure unless they pay {2}",
)])


# ── Thassa's Oracle ───────────────────────────────────────────────────────────

def _thassa_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if not controller:
        return
    # Count blue devotion (simplified: count {U} pips in mana costs on battlefield)
    devotion = 0
    for perm in controller.battlefield.permanents:
        mc = perm.mana_cost or ""
        devotion += mc.count("{U}") + mc.count("U/") + mc.count("/U")
    lib_count = len(controller.library)
    gs.log(f"Thassa's Oracle ETB: devotion={devotion}, library={lib_count}")
    if lib_count <= devotion:
        gs.winner = controller.id
        gs.log(f"{controller.name} wins via Thassa's Oracle!")
    else:
        # Look at top X (devotion), put rest on bottom — simplified: scry devotion
        scry_count = min(devotion, lib_count)
        if scry_count > 0:
            gs.log(f"Thassa's Oracle: {controller.name} looks at top {scry_count} card(s)")

_reg("Thassa's Oracle", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_thassa_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    description="ETB: win if library ≤ blue devotion",
)])


# ── Laboratory Maniac ─────────────────────────────────────────────────────────

def _labman_draw_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None:
        return False
    controller = gs.get_player(card.controller_id)
    return (
        controller is not None
        and event.controller_id == card.controller_id
        and len(controller.library) == 0
    )

def _labman_draw_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if controller:
        gs.winner = controller.id
        gs.log(f"{controller.name} wins via Laboratory Maniac!")

_reg("Laboratory Maniac", [CardEffect(
    trigger=EVENT_DRAW,
    resolve=_labman_draw_resolve,
    condition=_labman_draw_trigger,
    description="Win if you would draw from an empty library",
)])


# ── Jace, Wielder of Mysteries ────────────────────────────────────────────────

_reg("Jace, Wielder of Mysteries", [CardEffect(
    trigger=EVENT_DRAW,
    resolve=_labman_draw_resolve,
    condition=_labman_draw_trigger,
    description="Win if you would draw from an empty library",
)])


# Demonic Tutor and Vampiric Tutor handled by interpreter via effects_json.


# Dramatic Reversal handled by interpreter via effects_json (untap_all nonland_permanents).


# ── Narset, Parter of Veils (static — blocks extra draws) ────────────────────
# Implemented as a static check in the draw handler; register as empty to mark as handled.
_reg("Narset, Parter of Veils", [])


# ── Drannith Magistrate (static — blocks casting commanders) ─────────────────
_reg("Drannith Magistrate", [])


# ── Kinnan, Bonder Prodigy (static — adds 1 to nonhuman mana) ────────────────
_reg("Kinnan, Bonder Prodigy", [])


# ── Necropotence ─────────────────────────────────────────────────────────────
# Complex replacement effect (skip draw → exile → end of turn to hand)
# Stubbed: register as handled; full implementation requires end-step hooks.
_reg("Necropotence", [])


# ── Sylvan Library ────────────────────────────────────────────────────────────
# Complex upkeep trigger (draw 2 extra, pay 4 life per kept or put back)
# Stubbed — registered to suppress pattern-matching false positives.
_reg("Sylvan Library", [])


# ── Force of Will ─────────────────────────────────────────────────────────────
# Counterspell with alternate cost (exile blue card + pay 1 life).
# Priority windows not yet implemented; registered empty to suppress pattern.
_reg("Force of Will", [])
_reg("Pact of Negation", [])
_reg("Fierce Guardianship", [])
_reg("Mental Misstep", [])
_reg("Mana Drain", [])


# ── Mox Diamond — ETB replacement handled in game.py; suppress LLM ───────────
_reg("Mox Diamond", [])


# ── Chrome Mox — imprint ETB, then tap for imprinted card's colors ────────────

def _chrome_mox_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if not controller:
        return
    candidates = [
        c for c in controller.hand._cards
        if "Artifact" not in (c.type_line or "") and "Land" not in (c.type_line or "")
    ]
    if not candidates:
        gs.log("Chrome Mox: nothing to imprint")
        card.mana_ability = None
        return
    if controller.is_human:
        gs.pending_imprint_choice = {
            "player_id": controller.id,
            "mox_id": card.id,
            "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        }
        gs.log(f"Chrome Mox: waiting for {controller.name} to choose a card to imprint")
    else:
        from app.models.schemas import Zone
        from app.engine.mana_ability import ManaAbility
        imprint = max(candidates, key=lambda c: c.cmc or 0)
        controller.hand._cards.remove(imprint)
        imprint.zone = Zone.EXILE
        controller.exile.add(imprint)
        gs.log(f"Chrome Mox imprints {imprint.name}")
        colors = list(dict.fromkeys((imprint.color_identity or []) + (imprint.colors or [])))
        if colors:
            mtype = "basic" if len(colors) == 1 else ("dual" if len(colors) == 2 else "tri")
            card.mana_ability = ManaAbility(type=mtype, produces=colors, count=1)
        else:
            card.mana_ability = None

_reg("Chrome Mox", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_chrome_mox_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    optional=True,
    description="Imprint nonartifact nonland, tap for its color identity",
)])


# ── Creature mana dorks — mana comes from tap_artifact + classify_nonland_mana ─

for _dork in [
    "Birds of Paradise", "Noble Hierarch", "Llanowar Elves", "Elvish Mystic",
    "Arbor Elf", "Fyndhorn Elves", "Avacyn's Pilgrim", "Deathrite Shaman",
    "Elves of Deep Shadow", "Selvala, Heart of the Wilds", "Jegantha, the Wellspring",
]:
    _reg(_dork, [])


# Counterspell handled by interpreter via effects_json (counter_spell action).


# ── Spell Pierce ──────────────────────────────────────────────────────────────

def _spell_pierce_resolve(gs: "GameState", controller_id: str, card: "Card") -> None:
    for obj in reversed(gs.stack.objects):
        if obj.controller_id == controller_id:
            continue
        if obj.card.is_creature:
            continue
        opp = gs.get_player(obj.controller_id)
        if opp:
            pool_total = sum([opp.mana_pool.W, opp.mana_pool.U, opp.mana_pool.B,
                              opp.mana_pool.R, opp.mana_pool.G, opp.mana_pool.C])
            if pool_total >= 2:
                paid = 0
                for attr in ["C", "G", "R", "B", "U", "W"]:
                    while paid < 2 and getattr(opp.mana_pool, attr) > 0:
                        setattr(opp.mana_pool, attr, getattr(opp.mana_pool, attr) - 1)
                        paid += 1
                gs.log(f"Spell Pierce: {opp.name} pays {{2}}, spell survives")
                return
        gs.stack.counter(obj.id)
        from app.models.schemas import Zone
        ctrl = gs.get_player(obj.controller_id)
        if ctrl:
            obj.card.zone = Zone.GRAVEYARD
            ctrl.graveyard.add(obj.card)
        gs.log(f"Spell Pierce: counters {obj.card.name}")
        return
    gs.log("Spell Pierce: no valid target")

_spell("Spell Pierce", _spell_pierce_resolve)


# Ponder and Brainstorm handled by interpreter via effects_json.


# ── Pyroblast / Red Elemental Blast ──────────────────────────────────────────

def _pyroblast_resolve(gs: "GameState", controller_id: str, card: "Card") -> None:
    from app.models.schemas import Zone
    for obj in reversed(gs.stack.objects):
        if obj.controller_id == controller_id:
            continue
        if "U" in (obj.card.colors or []):
            gs.stack.counter(obj.id)
            ctrl = gs.get_player(obj.controller_id)
            if ctrl:
                obj.card.zone = Zone.GRAVEYARD
                ctrl.graveyard.add(obj.card)
            gs.log(f"{card.name}: counters {obj.card.name}")
            return
    for opp in gs.get_opponents(controller_id):
        for perm in list(opp.battlefield.permanents):
            if "U" in (perm.colors or []):
                opp.battlefield.remove(perm.id)
                perm.zone = Zone.GRAVEYARD
                opp.graveyard.add(perm)
                gs.log(f"{card.name}: destroys {perm.name}")
                return
    gs.log(f"{card.name}: no blue target")

_spell("Pyroblast", _pyroblast_resolve)
_spell("Red Elemental Blast", _pyroblast_resolve)


# ── Jeska's Will ─────────────────────────────────────────────────────────────

def _jeska_will_resolve(gs: "GameState", controller_id: str, card: "Card") -> None:
    controller = gs.get_player(controller_id)
    if not controller:
        return
    has_commander = any(c for c in controller.battlefield.permanents if c.is_commander)
    opponents = gs.get_opponents(controller_id)
    if opponents:
        target_opp = max(opponents, key=lambda p: len(p.hand.cards))
        hand_count = len(target_opp.hand.cards)
        if hand_count > 0:
            _add_mana(gs, controller_id, R=hand_count)
            gs.log(f"Jeska's Will: adds {hand_count}{{R}} (target opp has {hand_count} cards)")
    if has_commander or not opponents:
        from app.models.schemas import Zone
        exiled = []
        for _ in range(3):
            if controller.library._cards:
                c = controller.library._cards.popleft()
                c.zone = Zone.HAND
                controller.hand._cards.append(c)
                exiled.append(c.name)
        if exiled:
            gs.log(f"Jeska's Will: {controller.name} plays {', '.join(exiled)}")

_spell("Jeska's Will", _jeska_will_resolve)


# ── Lion's Eye Diamond ────────────────────────────────────────────────────────
# ETB assigns mana_ability; discard_hand_on_tap + sacrifice_on_tap drive tap_artifact logic.

def _led_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    from app.engine.mana_ability import ManaAbility
    card.mana_ability = ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], count=3,
                                    sacrifice_on_tap=True, discard_hand_on_tap=True)

_reg("Lion's Eye Diamond", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_led_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    description="LED: assign any_color mana_ability count=3 with sacrifice+discard-hand",
)])


# ── Jeweled Lotus ─────────────────────────────────────────────────────────────

def _jeweled_lotus_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    from app.engine.mana_ability import ManaAbility
    card.mana_ability = ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], count=3,
                                    sacrifice_on_tap=True)

_reg("Jeweled Lotus", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_jeweled_lotus_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    description="Jeweled Lotus: assign any_color x3 mana ability with sacrifice",
)])


# ── Mox Opal ─────────────────────────────────────────────────────────────────

def _mox_opal_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if not controller:
        return
    artifact_count = sum(1 for p in controller.battlefield.permanents if p.is_artifact)
    if artifact_count >= 3:
        from app.engine.mana_ability import ManaAbility
        card.mana_ability = ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], count=1)
        gs.log(f"Mox Opal: metalcraft active ({artifact_count} artifacts)")
    else:
        gs.log(f"Mox Opal: metalcraft inactive ({artifact_count} artifacts)")

_reg("Mox Opal", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_mox_opal_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    description="Metalcraft: add any color if 3+ artifacts",
)])


# ── Kraum, Ludevic's Opus ─────────────────────────────────────────────────────

_kraum_spell_count: dict[str, dict[str, int]] = {}

def _kraum_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None or event.controller_id == card.controller_id:
        return False
    turn_key = f"{gs.turn}_{event.controller_id}"
    count = _kraum_spell_count.get(gs.game_id, {}).get(turn_key, 0) + 1
    _kraum_spell_count.setdefault(gs.game_id, {})[turn_key] = count
    return count == 2

def _kraum_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    _draw(gs, card.controller_id)
    gs.log("Kraum, Ludevic's Opus: draws a card (opponent cast second spell)")

_reg("Kraum, Ludevic's Opus", [CardEffect(
    trigger=EVENT_SPELL_CAST,
    resolve=_kraum_resolve,
    condition=_kraum_trigger,
    description="Opponent casts second spell → draw a card",
)])


# ── Vial Smasher the Fierce ───────────────────────────────────────────────────

_vial_smasher_first_spell: dict[str, set] = {}

def _vial_smasher_trigger(event: GameEvent, gs: "GameState", card: "Card") -> bool:
    if card is None or event.controller_id != card.controller_id:
        return False
    key = (gs.turn, event.controller_id)
    seen = _vial_smasher_first_spell.setdefault(gs.game_id, set())
    if key in seen:
        return False
    seen.add(key)
    return True

def _vial_smasher_resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    from app.engine.effects import _find_card
    spell = _find_card(gs, event.source_card_id)
    if not spell:
        for obj in gs.stack.objects:
            if obj.card.id == event.source_card_id:
                spell = obj.card
                break
    cmc = int(spell.cmc) if spell and spell.cmc else 0
    opponents = gs.get_opponents(card.controller_id)
    if opponents and cmc > 0:
        import random
        target = random.choice(opponents)
        target.life_total -= cmc
        gs.log(f"Vial Smasher the Fierce: deals {cmc} damage to {target.name}")

_reg("Vial Smasher the Fierce", [CardEffect(
    trigger=EVENT_SPELL_CAST,
    resolve=_vial_smasher_resolve,
    condition=_vial_smasher_trigger,
    description="First spell each turn → deal damage = CMC to random opponent",
)])


# ── Isochron Scepter ─────────────────────────────────────────────────────────

def _isochron_etb(event: GameEvent, gs: "GameState", card: "Card") -> None:
    if card is None:
        return
    controller = gs.get_player(card.controller_id)
    if not controller:
        return
    candidates = [c for c in controller.hand.cards
                  if "Instant" in (c.type_line or "") and (c.cmc or 0) <= 2]
    if candidates:
        imprint = min(candidates, key=lambda c: c.cmc)
        controller.hand._cards.remove(imprint)
        from app.models.schemas import Zone
        imprint.zone = Zone.EXILE
        controller.exile.add(imprint)
        if not hasattr(card, "counters"):
            card.counters = {}
        card.counters["imprinted"] = imprint.name
        card.counters["imprinted_id"] = imprint.id
        gs.log(f"Isochron Scepter imprints {imprint.name}")

_reg("Isochron Scepter", [CardEffect(
    trigger=EVENT_ETB,
    resolve=_isochron_etb,
    condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
    optional=True,
    description="Imprint an instant with MV ≤ 2 from hand",
)])


# ── Storm (stub) ──────────────────────────────────────────────────────────────
for _storm in ["Brain Freeze", "Flusterstorm", "Grapeshot", "Tendrils of Agony"]:
    _reg(_storm, [])

# ── Static stax (stub) ────────────────────────────────────────────────────────
for _stax in ["Null Rod", "Cursed Totem", "Linvala, Keeper of Silence", "Rule of Law", "Opposition Agent"]:
    _reg(_stax, [])

# ── Complex spells/effects (stub) ─────────────────────────────────────────────
for _complex in [
    "Ad Nauseam", "Tainted Pact", "Underworld Breach", "Angel's Grace",
    "Deflecting Swat", "Berserk", "Savage Summoning",
    "Freed from the Real", "Pemmin's Aura", "Carpet of Flowers",
    "Blue Sun's Zenith", "Stroke of Genius", "Finale of Devastation",
]:
    if _complex not in REGISTRY:
        _reg(_complex, [])

# ── Commanders / complex triggered abilities (stub) ───────────────────────────
for _cmd in [
    "Rograkh, Son of Rohgahh", "Yoshimaru, Ever Faithful",
    "Silas Renn, Seeker Adept", "Thrasios, Triton Hero",
    "Tivit, Seller of Secrets", "Sisay, Weatherlight Captain",
    "Kenrith, the Returned King", "Dargo, the Shipwrecker",
    "Tymna the Weaver", "Magda, Brazen Outlaw",
]:
    if _cmd not in REGISTRY:
        _reg(_cmd, [])


# ── Public lookup ─────────────────────────────────────────────────────────────

def get_registry_effects(card: "Card") -> list[CardEffect] | None:
    """
    Return explicit effects for a card, or None if not in registry.
    None means "fall through to patterns/keywords"; [] means "handled, no effects".
    """
    return REGISTRY.get(card.name)
