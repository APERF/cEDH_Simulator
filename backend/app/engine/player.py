from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from app.engine.zones import Library, Hand, Battlefield, Graveyard, ExileZone, CommandZone

if TYPE_CHECKING:
    from app.engine.card import Card


@dataclass
class ManaPool:
    W: int = 0
    U: int = 0
    B: int = 0
    R: int = 0
    G: int = 0
    C: int = 0

    def add(self, color: str, amount: int = 1) -> None:
        if hasattr(self, color):
            setattr(self, color, getattr(self, color) + amount)

    def spend(self, color: str, amount: int = 1) -> bool:
        current = getattr(self, color, 0)
        if current < amount:
            return False
        setattr(self, color, current - amount)
        return True

    def total(self) -> int:
        return self.W + self.U + self.B + self.R + self.G + self.C

    def empty(self) -> None:
        self.W = self.U = self.B = self.R = self.G = self.C = 0


class Player:
    def __init__(self, player_id: str, name: str, is_human: bool, deck: list[Card]) -> None:
        self.id = player_id
        self.name = name
        self.is_human = is_human
        self.life_total = 40
        self.poison_counters = 0
        self.commander_damage: dict[str, int] = {}
        self.mana_pool = ManaPool()
        self.land_played_this_turn = False
        self.ai = None  # BaseAI instance assigned during game initialization

        self.library = Library(deck)
        self.hand = Hand()
        self.battlefield = Battlefield()
        self.graveyard = Graveyard()
        self.exile = ExileZone()
        self.command_zone = CommandZone()

    def draw(self, count: int = 1) -> list[Card]:
        drawn = []
        for _ in range(count):
            card = self.library.draw()
            if card is None:
                self.lose("decked")
                break
            card.zone = "hand"  # type: ignore[assignment]
            self.hand.add(card)
            drawn.append(card)
        return drawn

    def return_hand_to_library(self) -> None:
        """Shuffle hand back into library (for mulligan)."""
        for card in self.hand.cards:
            card.zone = "library"  # type: ignore[assignment]
            self.library._cards.append(card)
        self.hand._cards.clear()
        self.library.shuffle()

    def put_on_bottom(self, card_ids: list[str]) -> None:
        """Move specific hand cards to the bottom of library (post-mulligan)."""
        for card_id in card_ids:
            card = self.hand.remove(card_id)
            if card:
                card.zone = "library"  # type: ignore[assignment]
                self.library._cards.append(card)

    def take_damage(self, amount: int, source_player_id: str | None = None) -> None:
        self.life_total -= amount
        if source_player_id:
            self.commander_damage[source_player_id] = (
                self.commander_damage.get(source_player_id, 0) + amount
            )

    @property
    def is_eliminated(self) -> bool:
        if self.life_total <= 0:
            return True
        if self.poison_counters >= 10:
            return True
        if any(dmg >= 21 for dmg in self.commander_damage.values()):
            return True
        return False

    def lose(self, reason: str = "unknown") -> None:
        self.life_total = -9999  # marks as eliminated

    def __repr__(self) -> str:
        return f"Player({self.name}, {self.life_total} life)"
