from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState
    from app.engine.player import Player


class BaseAI(ABC):
    """Base class for all cEDH AI archetypes."""

    def __init__(self, player: Player) -> None:
        self.player = player

    @property
    @abstractmethod
    def archetype_name(self) -> str:
        """Human-readable archetype name."""

    @abstractmethod
    def take_turn(self, game_state: GameState) -> list[str]:
        """Execute a full turn and return a list of action log strings."""

    def should_counter(self, game_state: GameState, spell_name: str, caster_id: str) -> bool:
        """Decide whether to counter a spell on the stack. Override per archetype."""
        return False

    def priority_pass(self, game_state: GameState) -> bool:
        """Return True to pass priority, False to take an action."""
        return True

    def _log(self, message: str) -> list[str]:
        return [f"[{self.archetype_name}] {message}"]
