from __future__ import annotations
import uuid
from typing import Optional
from app.engine.player import Player
from app.engine.stack import Stack
from app.models.schemas import Phase, Step
from app.engine.win_conditions import check_win_conditions


class GameState:
    def __init__(self, players: list[Player]) -> None:
        self.game_id = str(uuid.uuid4())
        self.players = players
        self.turn = 1
        self.turn_order_index = 0
        self.phase = Phase.BEGINNING
        self.step = Step.UNTAP
        self.stack = Stack()
        self.winner: Optional[str] = None
        self.game_log: list[str] = []

    @property
    def active_player(self) -> Player:
        return self.players[self.turn_order_index % len(self.players)]

    def get_player(self, player_id: str) -> Optional[Player]:
        return next((p for p in self.players if p.id == player_id), None)

    def get_opponents(self, player_id: str) -> list[Player]:
        return [p for p in self.players if p.id != player_id]

    def advance_turn(self) -> None:
        self.active_player.mana_pool.empty()
        self.active_player.land_played_this_turn = False
        self.turn_order_index += 1
        self.turn += 1
        self.phase = Phase.BEGINNING
        self.step = Step.UNTAP
        self.log(f"--- Turn {self.turn}: {self.active_player.name} ---")

    def check_state_based_actions(self) -> None:
        for player in self.players:
            if player.is_eliminated and self.winner is None:
                self.log(f"{player.name} has been eliminated.")
        self.winner = check_win_conditions(self)

    def log(self, message: str) -> None:
        self.game_log.append(message)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "turn": self.turn,
            "active_player_id": self.active_player.id,
            "phase": self.phase.value,
            "step": self.step.value,
            "stack_size": len(self.stack),
            "winner": self.winner,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "is_human": p.is_human,
                    "life_total": p.life_total,
                    "commander_damage": p.commander_damage,
                    "hand_size": len(p.hand),
                    "battlefield_count": len(p.battlefield),
                }
                for p in self.players
            ],
        }
