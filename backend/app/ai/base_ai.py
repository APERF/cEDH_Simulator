from __future__ import annotations
import uuid
from abc import ABC
from typing import TYPE_CHECKING

from app.engine.mana_cost import parse_cost, can_pay, pay
from app.engine.stack import StackObject
from app.models.schemas import Zone

if TYPE_CHECKING:
    from app.engine.game_state import GameState
    from app.engine.player import Player


class BaseAI(ABC):
    """Base class for all cEDH AI archetypes."""

    def __init__(self, player: Player) -> None:
        self.player = player

    @property
    def archetype_name(self) -> str:
        return "Generic AI"

    def take_turn(self, game_state: GameState) -> list[str]:
        """Override per archetype for custom full-turn logic."""
        return []

    def main_phase_action(self, game_state: GameState) -> None:
        """Default main phase logic: play a land, tap lands, cast spells by CMC."""
        player = self.player

        # Play one non-fetch land if available
        if not player.land_played_this_turn:
            lands = [c for c in player.hand.cards if c.is_land]
            playable = next(
                (c for c in lands if not (c.mana_ability and c.mana_ability.type == "fetch")),
                None,
            )
            if playable:
                player.hand.remove(playable.id)
                playable.zone = Zone.BATTLEFIELD
                if playable.mana_ability and playable.mana_ability.etbt:
                    playable.tapped = True
                player.battlefield.add(playable)
                player.land_played_this_turn = True
                game_state.log(f"{player.name} plays {playable.name}")

        # Tap all untapped lands for mana
        for land in player.battlefield.permanents:
            if land.is_land and not land.tapped and land.mana_ability and land.mana_ability.produces:
                color = land.mana_ability.produces[0]
                land.tapped = True
                land.tapped_for = color
                player.mana_pool.add(color)

        # Cast commanders from command zone if affordable (CMC 0 commanders are always free)
        for cmd in player.command_zone.commanders:
            if cmd.zone != Zone.COMMAND:
                continue
            tax = player.command_zone.commander_tax(cmd.id)
            cost = parse_cost(cmd.mana_cost or "")
            if can_pay(player.mana_pool, cost, extra_generic=tax):
                pay(player.mana_pool, cost, extra_generic=tax)
                player.command_zone.increment_cast(cmd.id)
                cmd.zone = Zone.STACK

                def _make_cmd_resolve(c, p):
                    def resolve_fn(gs):
                        c.zone = Zone.BATTLEFIELD
                        c.tapped = False
                        p.battlefield.add(c)
                    return resolve_fn

                game_state.stack.push(StackObject(
                    id=str(uuid.uuid4()),
                    card=cmd,
                    controller_id=player.id,
                    targets=[],
                    resolve_fn=_make_cmd_resolve(cmd, player),
                ))
                game_state.log(f"{player.name} casts {cmd.name} from command zone")

        # Cast affordable spells onto the stack, lowest CMC first
        while True:
            castable = sorted(
                [
                    c for c in player.hand.cards
                    if not c.is_land and c.mana_cost
                    and can_pay(player.mana_pool, parse_cost(c.mana_cost))
                ],
                key=lambda c: c.cmc,
            )
            if not castable:
                break
            card = castable[0]
            if not pay(player.mana_pool, parse_cost(card.mana_cost)):
                break
            player.hand.remove(card.id)
            card.zone = Zone.STACK
            is_permanent = (
                card.is_creature or card.is_artifact or card.is_enchantment
                or "Planeswalker" in (card.type_line or "")
            )

            def _make_resolve_fn(c, p, permanent):
                def resolve_fn(gs):
                    if permanent:
                        c.zone = Zone.BATTLEFIELD
                        c.tapped = False
                        p.battlefield.add(c)
                    else:
                        c.zone = Zone.GRAVEYARD
                        p.graveyard.add(c)
                return resolve_fn

            game_state.stack.push(StackObject(
                id=str(uuid.uuid4()),
                card=card,
                controller_id=player.id,
                targets=[],
                resolve_fn=_make_resolve_fn(card, player, is_permanent),
            ))
            game_state.log(f"{player.name} casts {card.name}")

    def should_counter(self, game_state: GameState, spell_name: str, caster_id: str) -> bool:
        return False

    def priority_pass(self, game_state: GameState) -> bool:
        return True

    def _log(self, message: str) -> list[str]:
        return [f"[{self.archetype_name}] {message}"]
