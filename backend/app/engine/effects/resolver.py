"""
Effect resolver: ties the three layers together.

get_card_effects(card) -> list[CardEffect]
    Returns the effects for a card (registry → keywords → patterns, cached).

collect_triggers(event, game_state) -> list[PendingEffect]
    Checks all battlefield permanents for effects matching the event type.

resolve_next(game_state)
    Pops and executes the top PendingEffect from game_state.effect_queue.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from app.engine.effects import CardEffect, GameEvent, PendingEffect
from app.engine.effects.keywords import get_keyword_effects
from app.engine.effects.patterns import get_pattern_effects
from app.engine.effects.registry import get_registry_effects

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState

_effect_cache: dict[str, list[CardEffect]] = {}


def get_card_effects(card: "Card") -> list[CardEffect]:
    """
    Return all CardEffect objects for a card.
    Resolution priority: explicit registry > keyword inference > oracle text patterns.
    Cached by card name for the lifetime of the server process.
    """
    cached = _effect_cache.get(card.name)
    if cached is not None:
        return cached

    registry = get_registry_effects(card)
    if registry is not None:
        # Registry explicitly handles this card (may be [] = intentionally no effects)
        _effect_cache[card.name] = registry
        return registry

    effects: list[CardEffect] = []
    effects.extend(get_keyword_effects(card))

    # Layer 4: LLM-generated effects from effects_json (non-spell_resolve triggers only;
    # spell_resolve is executed directly in stack.py via interpreter.execute_spell)
    spec = getattr(card, "effects_json", None)
    if spec and not spec.get("skip"):
        from app.engine.effects.interpreter import json_to_card_effects
        lm_effects = json_to_card_effects(spec)
        if lm_effects:
            effects.extend(lm_effects)
            _effect_cache[card.name] = effects
            return effects

    # Layer 2: regex pattern fallback when no LLM spec is available
    effects.extend(get_pattern_effects(card))
    _effect_cache[card.name] = effects
    return effects


def collect_triggers(event: GameEvent, game_state: "GameState") -> list[PendingEffect]:
    """
    Scan all battlefield permanents and collect effects that match event.type.
    Returns in APNAP order (active player first, then clockwise).
    """
    pending: list[PendingEffect] = []

    # Build APNAP player order
    active_idx = game_state.turn_order_index % len(game_state.players)
    ordered_players = (
        game_state.players[active_idx:] + game_state.players[:active_idx]
    )

    for player in ordered_players:
        for card in player.battlefield.permanents:
            for effect in get_card_effects(card):
                if effect.trigger != event.type:
                    continue
                if effect.condition and not effect.condition(event, game_state, card):
                    continue
                pending.append(PendingEffect(
                    effect=effect,
                    event=event,
                    source_card_id=card.id,
                    controller_id=player.id,
                    description=f"{card.name}: {effect.description}",
                ))

    return pending


def resolve_next(game_state: "GameState") -> PendingEffect | None:
    """
    Pop and execute the next PendingEffect from game_state.effect_queue.
    Optional effects controlled by AI are auto-resolved (yes = beneficial).
    Optional effects controlled by a human are moved to pending_choices and NOT executed yet.
    Returns the effect that was processed (or None if queue is empty).
    """
    if not game_state.effect_queue:
        return None

    pending = game_state.effect_queue.pop(0)
    human = next((p for p in game_state.players if p.is_human), None)

    needs_prompt = pending.effect.optional or pending.effect.needs_choice
    if needs_prompt and human and pending.controller_id == human.id:
        # Human needs to decide — put it back in pending_choices for the API
        game_state.pending_choices.append(pending)
        return pending

    pending.execute(game_state)
    return pending


def apply_static_effects(game_state: "GameState") -> None:
    """
    Apply static effects (Narset, Drannith Magistrate, Kinnan, etc.).
    Called at the start of each step to refresh static state.
    Currently sets flags on game_state for downstream checks.
    """
    game_state.static_flags: dict[str, bool] = {}

    for player in game_state.players:
        for card in player.battlefield.permanents:
            name = card.name

            # Narset, Parter of Veils — opponents can't draw extra cards
            if name == "Narset, Parter of Veils":
                for opp in game_state.get_opponents(player.id):
                    game_state.static_flags[f"no_extra_draw:{opp.id}"] = True

            # Drannith Magistrate — opponents can't cast commanders from command zone
            if name == "Drannith Magistrate":
                for opp in game_state.get_opponents(player.id):
                    game_state.static_flags[f"no_commander_cast:{opp.id}"] = True

            # Kinnan, Bonder Prodigy — nonhuman mana abilities produce +1
            if name == "Kinnan, Bonder Prodigy":
                game_state.static_flags[f"kinnan:{player.id}"] = True
