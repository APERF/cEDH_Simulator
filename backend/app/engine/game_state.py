from __future__ import annotations
import uuid
from typing import Optional
from app.engine.player import Player
from app.engine.stack import Stack
from app.models.schemas import Phase, Step, Zone
from app.engine.win_conditions import check_win_conditions

_STEP_SEQUENCE = [
    Step.UNTAP, Step.UPKEEP, Step.DRAW, Step.PRECOMBAT_MAIN,
    Step.BEGIN_COMBAT, Step.DECLARE_ATTACKERS, Step.DECLARE_BLOCKERS,
    Step.COMBAT_DAMAGE, Step.END_OF_COMBAT, Step.POSTCOMBAT_MAIN,
    Step.END, Step.CLEANUP,
]

_STEP_TO_PHASE = {
    Step.UNTAP: Phase.BEGINNING,
    Step.UPKEEP: Phase.BEGINNING,
    Step.DRAW: Phase.BEGINNING,
    Step.PRECOMBAT_MAIN: Phase.PRECOMBAT_MAIN,
    Step.BEGIN_COMBAT: Phase.COMBAT,
    Step.DECLARE_ATTACKERS: Phase.COMBAT,
    Step.DECLARE_BLOCKERS: Phase.COMBAT,
    Step.COMBAT_DAMAGE: Phase.COMBAT,
    Step.END_OF_COMBAT: Phase.COMBAT,
    Step.POSTCOMBAT_MAIN: Phase.POSTCOMBAT_MAIN,
    Step.END: Phase.ENDING,
    Step.CLEANUP: Phase.ENDING,
}


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
        # Mulligan state — seat-ordered queue; each player decides in turn, keepers leave the queue
        self.mulligan_phase: str = "mulliganing"  # "mulliganing" | "selecting_bottom" | "playing"
        self.mulligan_active: list[str] = [p.id for p in players]   # IDs in decision order
        self.mulligan_counts: dict[str, int] = {p.id: 0 for p in players}
        self.ai_land_pause: bool = False  # True after AI land drop; holds the step so casting gets a separate turn

    @property
    def active_player(self) -> Player:
        return self.players[self.turn_order_index % len(self.players)]

    def get_player(self, player_id: str) -> Optional[Player]:
        return next((p for p in self.players if p.id == player_id), None)

    def get_opponents(self, player_id: str) -> list[Player]:
        return [p for p in self.players if p.id != player_id]

    def advance_step(self) -> None:
        if self.winner:
            return
        self._process_current_step()
        self.check_state_based_actions()
        # If the step put spells on the stack, pause here so players get priority.
        if not self.stack.is_empty:
            return
        # AI played a land this step — hold here so the frontend thinking timer
        # fires before the next advance_step call that will do the casting.
        if self.ai_land_pause:
            self.ai_land_pause = False
            return
        idx = _STEP_SEQUENCE.index(self.step)
        if idx == len(_STEP_SEQUENCE) - 1:
            self.turn_order_index += 1
            if self.turn_order_index % len(self.players) == 0:
                self.turn += 1
            self.step = Step.UNTAP
            self.phase = Phase.BEGINNING
            self.log(f"--- Turn {self.turn}: {self.active_player.name} ---")
        else:
            self.step = _STEP_SEQUENCE[idx + 1]
            self.phase = _STEP_TO_PHASE[self.step]

    def _process_current_step(self) -> None:
        player = self.active_player
        if self.step == Step.UNTAP:
            player.land_played_this_turn = False
            player.mana_pool.empty()
            for p in self.players:
                p.battlefield.untap_all(player.id)
            count = len(player.battlefield)
            if count:
                self.log(f"{player.name} untaps {count} permanent(s)")
        elif self.step == Step.DRAW:
            drawn = player.draw(1)
            if drawn:
                self.log(f"{player.name} draws a card")
        elif self.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN):
            if not player.is_human and player.ai is not None:
                player.ai.main_phase_action(self)
        elif self.step == Step.CLEANUP:
            player.mana_pool.empty()
            while len(player.hand) > 7:
                card = player.hand._cards.pop()
                card.zone = Zone.GRAVEYARD
                player.graveyard.add(card)
                self.log(f"{player.name} discards {card.name}")

    def advance_ai_turns_until_human(self, human_player_id: str, max_steps: int = 200) -> None:
        steps = 0
        while (
            self.active_player.id != human_player_id
            and not self.winner
            and self.stack.is_empty
            and steps < max_steps
        ):
            self.advance_step()
            steps += 1

    def advance_turn(self) -> None:
        self.active_player.mana_pool.empty()
        self.active_player.land_played_this_turn = False
        self.turn_order_index += 1
        if self.turn_order_index % len(self.players) == 0:
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

    # ── Mulligan queue helpers ────────────────────────────────────────────────

    @property
    def mulligan_current_player_id(self) -> Optional[str]:
        return self.mulligan_active[0] if self.mulligan_active else None

    @property
    def human_mulligan_count(self) -> int:
        human = next((p for p in self.players if p.is_human), None)
        return self.mulligan_counts.get(human.id, 0) if human else 0

    @property
    def cards_to_bottom(self) -> int:
        """Cards the human must put on the bottom when keeping (first mulligan free)."""
        return max(0, self.human_mulligan_count - 1)

    def mulligan_do_mulligan(self, player: Player) -> None:
        """Rotate player to the back of the queue and redraw 7."""
        if player.id in self.mulligan_active:
            self.mulligan_active.remove(player.id)
            self.mulligan_active.append(player.id)
        self.mulligan_counts[player.id] = self.mulligan_counts.get(player.id, 0) + 1
        player.return_hand_to_library()
        player.draw(7)

    def mulligan_do_keep(self, player_id: str) -> None:
        """Remove player from the queue; set phase to 'playing' when queue is empty."""
        if player_id in self.mulligan_active:
            self.mulligan_active.remove(player_id)
        self.mulligan_phase = "playing" if not self.mulligan_active else "mulliganing"

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "mulligan_phase": self.mulligan_phase,
            "mulligan_count": self.human_mulligan_count,
            "cards_to_bottom": self.cards_to_bottom,
            "mulligan_current_player_id": self.mulligan_current_player_id,
            "mulligan_active_player_ids": list(self.mulligan_active),
            "mulligan_counts": dict(self.mulligan_counts),
            "turn": self.turn,
            "active_player_id": self.active_player.id,
            "phase": self.phase.value,
            "step": self.step.value,
            "stack_size": len(self.stack),
            "stack": [
                obj.to_dict(
                    controller_name=next((p.name for p in self.players if p.id == obj.controller_id), "")
                )
                for obj in reversed(self.stack.objects)  # top of stack first
            ],
            "winner": self.winner,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "is_human": p.is_human,
                    "seat": i + 1,
                    "life_total": p.life_total,
                    "commander_damage": p.commander_damage,
                    "hand_size": len(p.hand),
                    "battlefield_count": len(p.battlefield),
                    "land_count": sum(1 for c in p.battlefield.permanents if c.is_land),
                    "mana_pool": {
                        "W": p.mana_pool.W,
                        "U": p.mana_pool.U,
                        "B": p.mana_pool.B,
                        "R": p.mana_pool.R,
                        "G": p.mana_pool.G,
                        "C": p.mana_pool.C,
                    },
                    "lands": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "tapped": c.tapped,
                            "tapped_for": c.tapped_for,
                            "mana_ability": (
                                {
                                    "type": c.mana_ability.type,
                                    "produces": c.mana_ability.produces,
                                    "etbt": c.mana_ability.etbt,
                                    "condition": c.mana_ability.condition,
                                }
                                if c.mana_ability else None
                            ),
                        }
                        for c in p.battlefield.permanents if c.is_land
                    ],
                    "permanents": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "tapped": c.tapped,
                            "type_line": c.type_line,
                        }
                        for c in p.battlefield.permanents if not c.is_land
                    ],
                    "library_count": len(p.library),
                    "graveyard_count": len(p.graveyard.cards),
                    "graveyard": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "type_line": c.type_line,
                        }
                        for c in p.graveyard.cards
                    ],
                    "exile_count": len(p.exile.cards),
                    "exile": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "type_line": c.type_line,
                        }
                        for c in p.exile.cards
                    ],
                    "poison_counters": p.poison_counters,
                    "land_played_this_turn": p.land_played_this_turn if p.is_human else False,
                    "hand": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "type_line": c.type_line,
                            "mana_cost": c.mana_cost,
                            "entry_condition": (
                                c.mana_ability.condition if c.is_land and c.mana_ability else None
                            ),
                            "land_type": (
                                c.mana_ability.type if c.is_land and c.mana_ability else None
                            ),
                        }
                        for c in p.hand.cards
                    ] if p.is_human else [],
                    "commanders": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "image_uri": c.image_uri,
                            "mana_cost": c.mana_cost,
                            "cast_count": p.command_zone.cast_count(c.id),
                            "commander_tax": p.command_zone.commander_tax(c.id),
                            "in_command_zone": c.zone == Zone.COMMAND,
                        }
                        for c in p.command_zone.commanders
                    ],
                }
                for i, p in enumerate(self.players)
            ],
        }
