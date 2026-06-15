"""
Core dataclasses for the card rules / effect system.

Events are fired by game_state.py at key moments. Effects registered on
battlefield permanents listen for matching events and are collected into
the effect_queue for resolution.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState


# ── Event types fired during gameplay ────────────────────────────────────────

EVENT_SPELL_CAST = "spell_cast"
EVENT_ETB = "etb"                  # card enters the battlefield
EVENT_LTB = "ltb"                  # card leaves the battlefield (dies, exiled, bounced)
EVENT_DRAW = "draw"                # a player draws one card
EVENT_DAMAGE_DEALT = "damage_dealt"
EVENT_UPKEEP_BEGIN = "upkeep_begin"
EVENT_TURN_BEGIN = "turn_begin"
EVENT_ATTACKED = "attacked"        # creature declared as attacker
EVENT_LAND_PLAYED = "land_played"
EVENT_LIFE_LOSS = "life_loss"


@dataclass
class GameEvent:
    type: str
    source_card_id: Optional[str] = None   # card that caused the event
    source_name: Optional[str] = None
    controller_id: Optional[str] = None    # player who controls the source
    target_id: Optional[str] = None        # card or player targeted
    data: dict = field(default_factory=dict)
    # e.g. data={"amount": 3}, data={"to_zone": "graveyard"}, data={"damage_type": "combat"}


# ── Effect definition ─────────────────────────────────────────────────────────

@dataclass
class CardEffect:
    """
    Represents one rule on a card (triggered, static keyword, or activated).

    trigger:      the EVENT_* constant this effect listens for (None = static/activated)
    condition:    optional callable — must return True for the effect to fire
    resolve:      callable that mutates game_state when the effect executes
    optional:     True = "you may" — human player gets a Yes/No prompt; No skips the effect
    needs_choice: True = mandatory but requires human acknowledgement before auto-executing
                  (e.g. Mox Diamond — must discard or sacrifice; No = sacrifice path)
    description:  human-readable label shown in the UI effect queue
    """
    trigger: Optional[str]
    resolve: Callable[[GameEvent, "GameState", "Card"], None]
    condition: Optional[Callable[[GameEvent, "GameState", "Card"], bool]] = None
    optional: bool = False
    needs_choice: bool = False
    description: str = ""


# ── Pending effect in the queue ───────────────────────────────────────────────

@dataclass
class PendingEffect:
    effect: CardEffect
    event: GameEvent
    source_card_id: str
    controller_id: str
    description: str = ""

    def execute(self, game_state: "GameState") -> None:
        source = _find_card(game_state, self.source_card_id)
        self.effect.resolve(self.event, game_state, source)

    def to_dict(self) -> dict:
        return {
            "source_card_id": self.source_card_id,
            "controller_id": self.controller_id,
            "description": self.description,
            "optional": self.effect.optional,
            "needs_choice": self.effect.needs_choice,
        }


def _find_card(game_state, card_id: str):
    """Find a Card anywhere in any player's zones."""
    if not card_id:
        return None
    for p in game_state.players:
        for zone_cards in [
            p.battlefield.permanents,
            p.hand.cards,
            p.graveyard.cards,
            p.exile.cards,
            p.command_zone.commanders,
        ]:
            for c in zone_cards:
                if c.id == card_id:
                    return c
    return None
