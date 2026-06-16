from __future__ import annotations
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState
    from app.engine.player import Player
    from app.engine.card import Card


# ── Public trigger-specific checkers ─────────────────────────────────────────

def check_draw_replacement_win(game_state: GameState, player_id: str) -> bool:
    """
    Call before a draw when the library is empty.
    Returns True (and sets game_state.winner) if a draw_replacement win condition is met.
    """
    player = game_state.get_player(player_id)
    if player is None or len(player.library) != 0:
        return False

    for card in player.battlefield.permanents:
        spec = getattr(card, "effects_json", None)
        if not spec or spec.get("skip"):
            continue
        wc = spec.get("win_condition")
        if wc and wc.get("trigger") == "draw_replacement":
            if _evaluate_win_condition(wc, card, player, game_state):
                game_state.log(f"{player.name} wins the game! ({card.name} — drawing from an empty library)")
                game_state.winner = player_id
                return True

    # Legacy fallback: hardcoded names in case effects_json hasn't been generated yet
    legacy_names = {"Laboratory Maniac", "Jace, Wielder of Mysteries"}
    if any(c.name in legacy_names for c in player.battlefield.permanents):
        card_name = next(c.name for c in player.battlefield.permanents if c.name in legacy_names)
        game_state.log(f"{player.name} wins the game! ({card_name} — drawing from an empty library)")
        game_state.winner = player_id
        return True

    return False


def check_upkeep_win_conditions(game_state: GameState, player_id: str) -> str | None:
    """
    Call at the beginning of upkeep for the active player.
    Returns winning player_id or None.
    """
    player = game_state.get_player(player_id)
    if player is None:
        return None

    for card in player.battlefield.permanents:
        spec = getattr(card, "effects_json", None)
        if not spec or spec.get("skip"):
            continue
        wc = spec.get("win_condition")
        if wc and wc.get("trigger") == "upkeep_begin":
            if _evaluate_win_condition(wc, card, player, game_state):
                game_state.log(f"{player.name} wins the game! ({card.name})")
                return player_id

    return None


def check_etb_win_conditions(game_state: GameState, card: Card, player_id: str) -> bool:
    """
    Call when a permanent enters the battlefield.
    Returns True (and sets game_state.winner) if an ETB win condition fires.
    """
    player = game_state.get_player(player_id)
    if player is None:
        return False

    spec = getattr(card, "effects_json", None)
    if not spec or spec.get("skip"):
        return False

    wc = spec.get("win_condition")
    if wc and wc.get("trigger") == "etb":
        if _evaluate_win_condition(wc, card, player, game_state):
            game_state.log(f"{player.name} wins the game! ({card.name})")
            game_state.winner = player_id
            return True

    return False


def check_spell_resolve_win_conditions(game_state: GameState, card: Card, player_id: str) -> bool:
    """
    Call when a spell resolves off the stack.
    Returns True (and sets game_state.winner) if a spell_resolve win condition fires.
    """
    player = game_state.get_player(player_id)
    if player is None:
        return False

    spec = getattr(card, "effects_json", None)
    if not spec or spec.get("skip"):
        return False

    wc = spec.get("win_condition")
    if wc and wc.get("trigger") == "spell_resolve":
        if _evaluate_win_condition(wc, card, player, game_state):
            game_state.log(f"{player.name} wins the game! ({card.name})")
            game_state.winner = player_id
            return True

    return False


def check_win_conditions(game_state: GameState) -> str | None:
    """
    State-based win condition check. Called after every step.
    Checks elimination, state_based card wins, and ETB-trigger wins (continuously).
    Returns winning player_id or None.
    """
    alive = [p for p in game_state.players if not p.is_eliminated]
    if len(alive) == 1:
        return alive[0].id

    for player in alive:
        for card in player.battlefield.permanents:
            spec = getattr(card, "effects_json", None)
            if spec and not spec.get("skip"):
                wc = spec.get("win_condition")
                if wc and wc.get("trigger") in ("state_based", "etb"):
                    if _evaluate_win_condition(wc, card, player, game_state):
                        game_state.log(f"{player.name} wins the game! ({card.name})")
                        return player.id
            elif spec is None:
                # Legacy fallback: Thassa's Oracle before effects_json is generated
                if card.name == "Thassa's Oracle" and len(player.library) == 0:
                    game_state.log(f"{player.name} wins the game! (Thassa's Oracle)")
                    return player.id

    return None


# ── Condition evaluators ──────────────────────────────────────────────────────

def _evaluate_win_condition(wc: dict, card: Card, player: Player, game_state: GameState) -> bool:
    condition_type = wc.get("condition_type")

    if condition_type == "library_empty":
        return len(player.library) == 0

    elif condition_type == "life_threshold_gte":
        return player.life_total >= wc.get("threshold", 40)

    elif condition_type == "permanent_count_gte":
        ptype = wc.get("permanent_type", "").lower()
        count = sum(1 for c in player.battlefield.permanents if ptype in (c.type_line or "").lower())
        return count >= wc.get("threshold", 0)

    elif condition_type == "token_name_count_gte":
        token_name = wc.get("token_name", "").lower()
        count = sum(
            1 for c in player.battlefield.permanents
            if token_name in c.name.lower() and "token" in (c.type_line or "").lower()
        )
        return count >= wc.get("threshold", 0)

    elif condition_type == "creature_count_gte":
        count = sum(1 for c in player.battlefield.permanents if "Creature" in (c.type_line or ""))
        return count >= wc.get("threshold", 0)

    elif condition_type == "devotion_gte_library":
        color = wc.get("devotion_color", "U")
        devotion = sum(
            (c.mana_cost or "").count(color)
            for c in player.battlefield.permanents
            if c.id != card.id
        )
        return devotion >= len(player.library)

    elif condition_type == "llm_eval":
        return _llm_evaluate_win_condition(wc, player, game_state)

    return False


def _llm_evaluate_win_condition(wc: dict, player: Player, game_state: GameState) -> bool:
    """Use Claude Haiku to evaluate a complex win condition against the current game state."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return False

    try:
        import anthropic

        permanents = [c.name for c in player.battlefield.permanents]
        colors_present = sorted({
            color
            for c in player.battlefield.permanents
            for color in (c.colors or [])
        })
        land_subtypes = sorted({
            bt
            for c in player.battlefield.permanents
            if c.is_land
            for bt in ("Plains", "Island", "Swamp", "Mountain", "Forest")
            if bt in (c.type_line or "")
        })

        state_lines = "\n".join([
            f"Life total: {player.life_total}",
            f"Library size: {len(player.library)}",
            f"Permanents on battlefield: {permanents}",
            f"Colors represented: {colors_present}",
            f"Basic land types present: {land_subtypes}",
        ])

        prompt = (
            f'Win condition text: "{wc.get("llm_condition_text", "")}"\n\n'
            f"Player game state:\n{state_lines}\n\n"
            f"Is this win condition currently met? Reply YES or NO only."
        )

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip().upper().startswith("YES")
    except Exception:
        return False
