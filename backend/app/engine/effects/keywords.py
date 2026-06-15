"""
Layer 1: Keyword auto-inference.

Converts the `card.keywords` list (populated from Scryfall) into CardEffect
objects so that standard keyword abilities are enforced automatically.

Static keywords (Flying, Deathtouch, etc.) don't produce Effects — they are
checked inline by combat/targeting helpers that call `card_has_keyword()`.
Triggered keywords (Annihilator, Ward) produce CardEffects.
"""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
from app.engine.effects import CardEffect, GameEvent, EVENT_ATTACKED, EVENT_ETB

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState


# ── Helpers used by combat / targeting (called inline, no Effect needed) ──────

def has_flying(card: "Card") -> bool:
    return card.has_keyword("Flying")

def has_reach(card: "Card") -> bool:
    return card.has_keyword("Reach")

def has_deathtouch(card: "Card") -> bool:
    return card.has_keyword("Deathtouch")

def has_lifelink(card: "Card") -> bool:
    return card.has_keyword("Lifelink")

def has_trample(card: "Card") -> bool:
    return card.has_keyword("Trample")

def has_first_strike(card: "Card") -> bool:
    return card.has_keyword("First Strike")

def has_double_strike(card: "Card") -> bool:
    return card.has_keyword("Double Strike")

def has_menace(card: "Card") -> bool:
    return card.has_keyword("Menace")

def has_indestructible(card: "Card") -> bool:
    return card.has_keyword("Indestructible")

def has_hexproof(card: "Card") -> bool:
    return card.has_keyword("Hexproof")

def has_shroud(card: "Card") -> bool:
    return card.has_keyword("Shroud")

def can_block_flyer(card: "Card") -> bool:
    return has_flying(card) or has_reach(card)


# ── Triggered keyword effects ─────────────────────────────────────────────────

def _make_annihilator_effect(n: int) -> CardEffect:
    """Annihilator N: when this attacks, defending player sacrifices N permanents."""
    def resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
        if card is None:
            return
        defender = gs.get_player(event.data.get("defender_id", ""))
        if defender is None:
            return
        sacrificed = 0
        for perm in list(defender.battlefield.permanents):
            if sacrificed >= n:
                break
            defender.battlefield.remove(perm.id)
            from app.models.schemas import Zone
            perm.zone = Zone.GRAVEYARD
            defender.graveyard.add(perm)
            gs.log(f"Annihilator: {defender.name} sacrifices {perm.name}")
            sacrificed += 1

    return CardEffect(
        trigger=EVENT_ATTACKED,
        resolve=resolve,
        condition=lambda ev, gs, card: card is not None and ev.source_card_id == card.id,
        description=f"Annihilator {n} — defending player sacrifices {n} permanent(s)",
    )


def _make_ward_effect(cost: int) -> CardEffect:
    """Ward N: when this becomes the target of a spell/ability, counter it unless opponent pays N."""
    def resolve(event: GameEvent, gs: "GameState", card: "Card") -> None:
        if card is None:
            return
        gs.log(f"Ward {cost}: {card.name} is protected (Ward {cost} not yet fully interactive)")

    return CardEffect(
        trigger="targeted",
        resolve=resolve,
        condition=lambda ev, gs, card: card is not None and ev.target_id == card.id,
        description=f"Ward {cost}",
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def get_keyword_effects(card: "Card") -> list[CardEffect]:
    """Return triggered CardEffect objects derived from card.keywords."""
    effects: list[CardEffect] = []
    for kw in (card.keywords or []):
        kw_lower = kw.lower()

        # Annihilator N
        m = re.match(r"annihilator\s+(\d+)", kw_lower)
        if m:
            effects.append(_make_annihilator_effect(int(m.group(1))))
            continue

        # Ward N (numeric only; "Ward—pay N life" handled in registry)
        m = re.match(r"ward\s+(\d+)", kw_lower)
        if m:
            effects.append(_make_ward_effect(int(m.group(1))))
            continue

    return effects
