"""
Layer 2: Oracle text pattern matching.

Parses `card.oracle_text` at card-load time and returns CardEffect objects
for common spell/ability templates. Results are cached by card name so each
card is parsed only once per server process.

Handles instants/sorceries (on-resolve) and permanents with simple ETB or
activated mana abilities.
"""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
from app.engine.effects import (
    CardEffect, GameEvent,
    EVENT_ETB, EVENT_SPELL_CAST,
)

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState

_pattern_cache: dict[str, list[CardEffect]] = {}


# ── Effect action helpers ─────────────────────────────────────────────────────

def _draw_cards(gs: "GameState", player_id: str, n: int) -> None:
    p = gs.get_player(player_id)
    if p:
        drawn = p.draw(n)
        gs.log(f"{p.name} draws {n} card(s)")
        from app.engine.effects import GameEvent, EVENT_DRAW
        for _ in range(len(drawn)):
            gs.fire_event(GameEvent(
                type=EVENT_DRAW,
                controller_id=player_id,
                data={"amount": 1},
            ))


def _add_mana(gs: "GameState", player_id: str, mana_str: str) -> None:
    """Parse a Scryfall mana string like '{G}{G}' or '{2}{U}' and add to pool."""
    p = gs.get_player(player_id)
    if not p:
        return
    for token in re.findall(r"\{([^}]+)\}", mana_str.upper()):
        if token in ("W", "U", "B", "R", "G", "C"):
            setattr(p.mana_pool, token, getattr(p.mana_pool, token) + 1)
        elif token.isdigit():
            p.mana_pool.C += int(token)
    gs.log(f"{p.name} adds mana from effect")


def _life_gain(gs: "GameState", player_id: str, n: int) -> None:
    p = gs.get_player(player_id)
    if p:
        p.life_total += n
        gs.log(f"{p.name} gains {n} life")


def _life_loss(gs: "GameState", player_id: str, n: int) -> None:
    p = gs.get_player(player_id)
    if p:
        p.life_total -= n
        gs.log(f"{p.name} loses {n} life")


def _destroy_all_of_type(gs: "GameState", controller_id: str, type_filter: str) -> None:
    from app.models.schemas import Zone
    to_destroy = []
    for p in gs.get_opponents(controller_id):
        for perm in list(p.battlefield.permanents):
            if type_filter in perm.type_line.lower():
                to_destroy.append((p, perm))
    for p, card in to_destroy:
        if not card.has_keyword("Indestructible"):
            p.battlefield.remove(card.id)
            card.zone = Zone.GRAVEYARD
            p.graveyard.add(card)
            gs.log(f"{card.name} is destroyed")


# ── Pattern definitions ───────────────────────────────────────────────────────

_DRAW_N = re.compile(r"draw (\w+) cards?", re.I)
_DRAW_A = re.compile(r"draw a card", re.I)
_GAIN_LIFE = re.compile(r"you gain (\d+) life", re.I)
_OPP_LOSE_LIFE = re.compile(r"each opponent loses (\d+) life", re.I)
_TARGET_OPP_LOSE = re.compile(r"target opponent loses (\d+) life", re.I)
_ADD_MANA_SIMPLE = re.compile(r"\{T\}:.*?add ((?:\{[WUBRGC0-9X]\})+)", re.I)
_COUNTER_SPELL = re.compile(r"counter target spell", re.I)
_DESTROY_ALL_CREATURES = re.compile(r"destroy all creatures", re.I)
_EACH_OPP_DISCARD = re.compile(r"each opponent discards (\w+) cards?", re.I)
_TUTOR_HAND = re.compile(
    r"search your library for (?:a |an )?(\w[\w\s,]*?)card.*?put it into your hand",
    re.I | re.S,
)
_WORD_TO_NUM = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7,
}


def _word_num(s: str) -> int:
    return _WORD_TO_NUM.get(s.lower().strip(), 1)


def _make_draw_effect(n: int, trigger: str, desc: str) -> CardEffect:
    def resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
        if card is None:
            return
        _draw_cards(gs, card.controller_id, n)
    return CardEffect(trigger=trigger, resolve=resolve, description=desc)


def _make_life_gain_effect(n: int, trigger: str) -> CardEffect:
    def resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
        if card is None:
            return
        _life_gain(gs, card.controller_id, n)
    return CardEffect(trigger=trigger, resolve=resolve, description=f"You gain {n} life")


def _make_opp_life_loss_effect(n: int, trigger: str) -> CardEffect:
    def resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
        if card is None:
            return
        for opp in gs.get_opponents(card.controller_id):
            _life_loss(gs, opp.id, n)
    return CardEffect(trigger=trigger, resolve=resolve, description=f"Each opponent loses {n} life")


def _spell_trigger(card: "Card") -> str:
    """Instants/sorceries fire on resolution; ETB for permanents."""
    if card.is_instant or card.is_sorcery:
        return EVENT_SPELL_CAST
    return EVENT_ETB


# ── Main entry point ──────────────────────────────────────────────────────────

def get_pattern_effects(card: "Card") -> list[CardEffect]:
    """
    Return CardEffect list for card based on oracle text patterns.
    Results are cached by card name.
    """
    cached = _pattern_cache.get(card.name)
    if cached is not None:
        return cached

    text = card.oracle_text or ""
    effects: list[CardEffect] = []
    trigger = _spell_trigger(card)

    # Draw N cards
    m = _DRAW_N.search(text)
    if m:
        n = _word_num(m.group(1)) if not m.group(1).isdigit() else int(m.group(1))
        effects.append(_make_draw_effect(n, trigger, f"Draw {n} card(s)"))
    elif _DRAW_A.search(text):
        effects.append(_make_draw_effect(1, trigger, "Draw a card"))

    # You gain N life
    m = _GAIN_LIFE.search(text)
    if m:
        effects.append(_make_life_gain_effect(int(m.group(1)), trigger))

    # Each opponent loses N life
    m = _OPP_LOSE_LIFE.search(text)
    if m:
        effects.append(_make_opp_life_loss_effect(int(m.group(1)), trigger))

    # Counter target spell (only for instants — basic stub, no priority windows yet)
    if _COUNTER_SPELL.search(text) and card.is_instant:
        def _counter(event: GameEvent, gs: "GameState", src: "Card") -> None:
            if gs.stack.is_empty:
                gs.log(f"{src.name if src else 'Counter'}: no target on stack")
                return
            top = gs.stack.pop()
            if top:
                controller = gs.get_player(top.controller_id)
                if controller:
                    from app.models.schemas import Zone
                    top.card.zone = Zone.GRAVEYARD
                    controller.graveyard.add(top.card)
                gs.log(f"{src.name if src else 'Counter'} counters {top.card.name}")
        effects.append(CardEffect(
            trigger=trigger,
            resolve=_counter,
            description="Counter target spell",
        ))

    # Destroy all creatures (board wipe)
    if _DESTROY_ALL_CREATURES.search(text):
        def _wipe(event: GameEvent, gs: "GameState", src: "Card") -> None:
            from app.models.schemas import Zone
            to_destroy = []
            for p in gs.players:
                for perm in list(p.battlefield.permanents):
                    if perm.is_creature and not perm.has_keyword("Indestructible"):
                        to_destroy.append((p, perm))
            for p, c in to_destroy:
                p.battlefield.remove(c.id)
                c.zone = Zone.GRAVEYARD
                p.graveyard.add(c)
                gs.log(f"{c.name} is destroyed (board wipe)")
        effects.append(CardEffect(trigger=trigger, resolve=_wipe, description="Destroy all creatures"))

    # Tutor — search library for card, put into hand
    m = _TUTOR_HAND.search(text)
    if m:
        type_hint = m.group(1).strip().lower()

        def _tutor(event: GameEvent, gs: "GameState", src: "Card") -> None:
            if src is None:
                return
            controller = gs.get_player(src.controller_id)
            if not controller:
                return
            # AI auto-picks first matching card; human gets first card (UI improvement deferred)
            candidates = [
                c for c in controller.library._cards
                if not type_hint or any(t in c.type_line.lower() for t in type_hint.split())
            ]
            if candidates:
                chosen = candidates[0]
                controller.library._cards.remove(chosen)
                from app.models.schemas import Zone
                chosen.zone = Zone.HAND
                controller.hand._cards.append(chosen)
                controller.library.shuffle()
                gs.log(f"{controller.name} tutors {chosen.name} to hand")

        effects.append(CardEffect(
            trigger=trigger,
            resolve=_tutor,
            description=f"Search library for {type_hint or 'any'} card → hand",
        ))

    _pattern_cache[card.name] = effects
    return effects
