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
            # Fire ETB event if the card is now on the battlefield
            from app.engine.effects import GameEvent, EVENT_ETB, EVENT_SPELL_CAST
            from app.models.schemas import Zone as _Zone
            if obj.card.zone == _Zone.BATTLEFIELD:
                event = GameEvent(
                    type=EVENT_ETB,
                    source_card_id=obj.card.id,
                    source_name=obj.card.name,
                    controller_id=obj.controller_id,
                )
                game_state.fire_event(event)
                game_state.flush_effect_queue()
            elif obj.card.zone == _Zone.GRAVEYARD:
                # Check explicit spell registry first
                from app.engine.effects.registry import SPELL_REGISTRY
                spell_fn = SPELL_REGISTRY.get(obj.card.name)
                if spell_fn:
                    spell_fn(game_state, obj.controller_id, obj.card)
                else:
                    # Execute the spell's own effects (Dark Ritual, board wipes, etc.)
                    from app.engine.effects.interpreter import execute_spell
                    execute_spell(obj.card, game_state, obj.controller_id)

                # Fire for permanents watching (Rhystic Study, Mystic Remora, etc.)
                event = GameEvent(
                    type=EVENT_SPELL_CAST,
                    source_card_id=obj.card.id,
                    source_name=obj.card.name,
                    controller_id=obj.controller_id,
                    data={"resolved": True},
                )
                game_state.fire_event(event)
                game_state.flush_effect_queue()
        return obj

    @property
    def is_empty(self) -> bool:
        return len(self._objects) == 0

    @property
    def objects(self) -> list[StackObject]:
        return list(self._objects)

    def __len__(self) -> int:
        return len(self._objects)
