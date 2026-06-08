from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState


def check_thassas_oracle(game_state: GameState, player_id: str) -> bool:
    """Win if Thassa's Oracle ETB resolves with empty or near-empty library."""
    player = game_state.get_player(player_id)
    if player is None:
        return False
    return len(player.library) == 0


def check_laboratory_maniac(game_state: GameState, player_id: str) -> bool:
    player = game_state.get_player(player_id)
    if player is None:
        return False
    lab_man_on_field = any(
        c.name == "Laboratory Maniac"
        for c in player.battlefield.permanents
    )
    return lab_man_on_field and len(player.library) == 0


def check_thoracle_combo(player) -> bool:
    """Demonic Consultation / Tainted Pact + Thassa's Oracle."""
    return len(player.library) == 0


def check_life_total(game_state: GameState) -> list[str]:
    return [p.id for p in game_state.players if p.is_eliminated]


def check_win_conditions(game_state: GameState) -> str | None:
    """Return the winning player's ID, or None if game continues."""
    alive = [p for p in game_state.players if not p.is_eliminated]
    if len(alive) == 1:
        return alive[0].id
    return None
