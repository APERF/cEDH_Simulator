from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING
import random

if TYPE_CHECKING:
    from app.engine.card import Card


class Library:
    def __init__(self, cards: list[Card]) -> None:
        self._cards: deque[Card] = deque(cards)

    def shuffle(self) -> None:
        cards = list(self._cards)
        random.shuffle(cards)
        self._cards = deque(cards)

    def draw(self) -> Card | None:
        return self._cards.popleft() if self._cards else None

    def __len__(self) -> int:
        return len(self._cards)


class Hand:
    def __init__(self) -> None:
        self._cards: list[Card] = []

    def add(self, card: Card) -> None:
        self._cards.append(card)

    def remove(self, card_id: str) -> Card | None:
        for i, c in enumerate(self._cards):
            if c.id == card_id:
                return self._cards.pop(i)
        return None

    @property
    def cards(self) -> list[Card]:
        return list(self._cards)

    def __len__(self) -> int:
        return len(self._cards)


class Battlefield:
    def __init__(self) -> None:
        self._permanents: list[Card] = []

    def add(self, card: Card) -> None:
        self._permanents.append(card)

    def remove(self, card_id: str) -> Card | None:
        for i, c in enumerate(self._permanents):
            if c.id == card_id:
                return self._permanents.pop(i)
        return None

    def get(self, card_id: str) -> Card | None:
        return next((c for c in self._permanents if c.id == card_id), None)

    def untap_all(self, controller_id: str) -> None:
        for card in self._permanents:
            if card.controller_id == controller_id:
                card.tapped = False

    @property
    def permanents(self) -> list[Card]:
        return list(self._permanents)

    def __len__(self) -> int:
        return len(self._permanents)


class Graveyard:
    def __init__(self) -> None:
        self._cards: list[Card] = []

    def add(self, card: Card) -> None:
        self._cards.append(card)

    @property
    def cards(self) -> list[Card]:
        return list(self._cards)


class ExileZone:
    def __init__(self) -> None:
        self._cards: list[Card] = []

    def add(self, card: Card) -> None:
        self._cards.append(card)

    @property
    def cards(self) -> list[Card]:
        return list(self._cards)


class CommandZone:
    def __init__(self) -> None:
        self._commanders: list[Card] = []
        self._cast_count: dict[str, int] = {}

    def add(self, commander: Card) -> None:
        self._commanders.append(commander)
        self._cast_count[commander.id] = 0

    def cast_count(self, card_id: str) -> int:
        return self._cast_count.get(card_id, 0)

    def increment_cast(self, card_id: str) -> None:
        self._cast_count[card_id] = self._cast_count.get(card_id, 0) + 1

    def commander_tax(self, card_id: str) -> int:
        return self._cast_count.get(card_id, 0) * 2

    @property
    def commanders(self) -> list[Card]:
        return list(self._commanders)
