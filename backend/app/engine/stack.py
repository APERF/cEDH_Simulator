from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState


@dataclass
class StackObject:
    id: str
    card: Card
    controller_id: str
    targets: list[str] = field(default_factory=list)
    resolve_fn: Optional[Callable[[GameState], None]] = field(default=None, repr=False)

    def to_dict(self, controller_name: str = "") -> dict:
        return {
            "id": self.id,
            "name": self.card.name,
            "image_uri": self.card.image_uri,
            "type_line": self.card.type_line,
            "mana_cost": self.card.mana_cost,
            "controller_id": self.controller_id,
            "controller_name": controller_name,
        }


class Stack:
    def __init__(self) -> None:
        self._objects: list[StackObject] = []

    def push(self, obj: StackObject) -> None:
        self._objects.append(obj)

    def pop(self) -> StackObject | None:
        return self._objects.pop() if self._objects else None

    def counter(self, obj_id: str) -> bool:
        for i, obj in enumerate(self._objects):
            if obj.id == obj_id:
                self._objects.pop(i)
                return True
        return False

    def resolve_top(self, game_state: GameState) -> StackObject | None:
        obj = self.pop()
        if obj and obj.resolve_fn:
            obj.resolve_fn(game_state)
        return obj

    @property
    def is_empty(self) -> bool:
        return len(self._objects) == 0

    @property
    def objects(self) -> list[StackObject]:
        return list(self._objects)

    def __len__(self) -> int:
        return len(self._objects)
