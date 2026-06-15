from __future__ import annotations
import uuid
from typing import Optional
from app.engine.card import Card
from app.engine.player import Player
from app.engine.stack import Stack
from app.models.schemas import Phase, Step, Zone
from app.engine.win_conditions import check_win_conditions
from app.engine.effects import (
    GameEvent, PendingEffect,
    EVENT_ETB, EVENT_LTB, EVENT_DRAW, EVENT_DAMAGE_DEALT,
    EVENT_UPKEEP_BEGIN, EVENT_TURN_BEGIN, EVENT_ATTACKED,
    EVENT_SPELL_CAST, EVENT_LAND_PLAYED,
)

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
        self.ai_decision_log: list[dict] = []
        # Mulligan state
        self.mulligan_phase: str = "mulliganing"
        self.mulligan_active: list[str] = [p.id for p in players]
        self.mulligan_counts: dict[str, int] = {p.id: 0 for p in players}
        self.ai_land_pause: bool = False

        # Combat state
        self.combat_attackers: dict[str, str] = {}       # card_id → defending_player_id
        self.combat_blockers: dict[str, list[str]] = {}  # attacker_id → [blocker_ids]
        self.combat_awaiting_human_action: Optional[str] = None  # "declare_attackers" | "declare_blockers" | None

        # Effect / rules engine
        self.effect_queue: list[PendingEffect] = []      # triggered effects waiting to resolve
        self.pending_choices: list[PendingEffect] = []   # optional effects awaiting human decision
        self.static_flags: dict[str, bool] = {}          # refreshed each step by apply_static_effects
        self.pending_etb_replacement: dict | None = None  # ETB replacement awaiting human choice

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
        if not self.stack.is_empty:
            return
        if self.ai_land_pause:
            self.ai_land_pause = False
            return
        if self.combat_awaiting_human_action:
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
        self.refresh_statics()

        if self.step == Step.UNTAP:
            player.land_played_this_turn = False
            player.mana_pool.empty()
            for p in self.players:
                p.battlefield.untap_all(player.id)
            count = len(player.battlefield)
            if count:
                self.log(f"{player.name} untaps {count} permanent(s)")
            self.fire_event(GameEvent(
                type=EVENT_TURN_BEGIN,
                controller_id=player.id,
            ))
            self.flush_effect_queue()

        elif self.step == Step.UPKEEP:
            self.fire_event(GameEvent(
                type=EVENT_UPKEEP_BEGIN,
                controller_id=player.id,
            ))
            self.flush_effect_queue()

        elif self.step == Step.DRAW:
            drawn = player.draw(1)
            if drawn:
                self.log(f"{player.name} draws a card")
                self.fire_event(GameEvent(
                    type=EVENT_DRAW,
                    controller_id=player.id,
                    data={"amount": 1},
                ))
                self.flush_effect_queue()

        elif self.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN):
            if not player.is_human and player.ai is not None:
                player.ai.main_phase_action(self)

        elif self.step == Step.BEGIN_COMBAT:
            pass  # priority window only

        elif self.step == Step.DECLARE_ATTACKERS:
            if player.is_human:
                self.combat_awaiting_human_action = "declare_attackers"
            elif player.ai is not None:
                attackers = player.ai.declare_attackers(self)
                if attackers:
                    self._process_attacker_declarations(attackers, player)
                else:
                    self.log(f"{player.name} chooses not to attack")

        elif self.step == Step.DECLARE_BLOCKERS:
            human = next((p for p in self.players if p.is_human), None)
            human_is_target = human and any(v == human.id for v in self.combat_attackers.values())
            if human_is_target:
                self.combat_awaiting_human_action = "declare_blockers"
            else:
                self._ai_declare_blockers_for_all()

        elif self.step == Step.COMBAT_DAMAGE:
            if self.combat_attackers:
                self._resolve_combat_damage()

        elif self.step == Step.END_OF_COMBAT:
            self._clear_combat_state()

        elif self.step == Step.CLEANUP:
            player.mana_pool.empty()
            while len(player.hand) > 7:
                card = player.hand._cards.pop()
                card.zone = Zone.GRAVEYARD
                player.graveyard.add(card)
                self.log(f"{player.name} discards {card.name}")

    # ── Combat helpers ────────────────────────────────────────────────────────

    def _find_card_and_owner(self, card_id: str) -> tuple[Optional[Card], Optional[Player]]:
        for p in self.players:
            card = p.battlefield.get(card_id)
            if card:
                return card, p
        return None, None

    def _card_name(self, card_id: str) -> str:
        card, _ = self._find_card_and_owner(card_id)
        return card.name if card else card_id

    def _process_attacker_declarations(self, attackers: dict[str, str], attacker_player: Player) -> None:
        for card_id, target_player_id in attackers.items():
            card = attacker_player.battlefield.get(card_id)
            if not card or not card.is_creature:
                continue
            if not card.has_keyword("Vigilance"):
                card.tapped = True
            card.is_attacking = True
            card.attacking_target = target_player_id
            self.combat_attackers[card_id] = target_player_id
            target = self.get_player(target_player_id)
            self.log(f"{attacker_player.name}: {card.name} attacks {target.name if target else '?'}")

    def _ai_declare_blockers_for_all(self) -> None:
        attackers_by_target: dict[str, list[Card]] = {}
        for card_id, target_id in self.combat_attackers.items():
            card, _ = self._find_card_and_owner(card_id)
            if card:
                attackers_by_target.setdefault(target_id, []).append(card)

        for defender in self.players:
            my_attackers = attackers_by_target.get(defender.id, [])
            if not my_attackers:
                continue
            if not defender.is_human and defender.ai:
                blocks = defender.ai.declare_blockers(my_attackers, self)
                for blocker_id, attacker_id in blocks.items():
                    blocker = defender.battlefield.get(blocker_id)
                    attacker, _ = self._find_card_and_owner(attacker_id)
                    if blocker and attacker:
                        blocker.is_blocking = True
                        blocker.blocking = attacker_id
                        self.combat_blockers.setdefault(attacker_id, []).append(blocker_id)
                        self.log(f"{defender.name}: {blocker.name} blocks {attacker.name}")

    def _resolve_combat_damage(self) -> None:
        from app.engine.effects.keywords import (
            has_deathtouch, has_lifelink, has_trample, has_flying,
            has_first_strike, has_double_strike, has_indestructible,
        )

        for attacker_id, defender_id in self.combat_attackers.items():
            attacker, attacker_owner = self._find_card_and_owner(attacker_id)
            if not attacker or not attacker.is_attacking:
                continue
            defender = self.get_player(defender_id)
            blocker_ids = self.combat_blockers.get(attacker_id, [])

            if not blocker_ids:
                dmg = attacker.parsed_power()
                if dmg > 0 and defender:
                    if attacker.is_commander and attacker_owner:
                        defender.take_damage(dmg, attacker_owner.id)
                        self.log(f"{attacker.name} deals {dmg} commander damage to {defender.name}")
                    else:
                        defender.take_damage(dmg)
                        self.log(f"{attacker.name} deals {dmg} damage to {defender.name}")
                    # Lifelink
                    if has_lifelink(attacker) and attacker_owner and dmg > 0:
                        attacker_owner.life_total += dmg
                        self.log(f"{attacker.name} lifelink: {attacker_owner.name} gains {dmg} life")
            else:
                blocker_cards: list[Card] = []
                for bid in blocker_ids:
                    bc, _ = self._find_card_and_owner(bid)
                    if bc:
                        blocker_cards.append(bc)

                remaining = attacker.parsed_power()
                for bc in blocker_cards:
                    # Deathtouch: any damage = lethal (assign 1 per blocker)
                    assign = 1 if has_deathtouch(attacker) else min(remaining, bc.parsed_toughness())
                    if assign > 0:
                        bc.damage_taken += assign
                        self.log(f"{attacker.name} deals {assign} damage to {bc.name}")
                        remaining -= assign
                    if remaining <= 0:
                        break

                # Trample: excess damage to player
                if has_trample(attacker) and remaining > 0 and defender:
                    defender.take_damage(remaining)
                    self.log(f"{attacker.name} tramples for {remaining} to {defender.name}")
                    if has_lifelink(attacker) and attacker_owner:
                        attacker_owner.life_total += remaining

                for bc in blocker_cards:
                    bp = bc.parsed_power()
                    if bp > 0:
                        attacker.damage_taken += bp
                        self.log(f"{bc.name} deals {bp} damage to {attacker.name}")
                    # Blocker deathtouch: any damage to attacker is lethal
                    if has_deathtouch(bc) and bp > 0:
                        attacker.damage_taken = max(attacker.damage_taken, attacker.parsed_toughness())

        # Destroy creatures with lethal damage (respects Indestructible)
        to_destroy: list[tuple[Player, Card]] = []
        for p in self.players:
            for card in p.battlefield.permanents:
                if (
                    card.is_creature
                    and card.damage_taken > 0
                    and card.damage_taken >= card.parsed_toughness()
                    and not has_indestructible(card)
                ):
                    to_destroy.append((p, card))
        for p, card in to_destroy:
            p.battlefield.remove(card.id)
            card.zone = Zone.GRAVEYARD
            p.graveyard.add(card)
            self.log(f"{card.name} is destroyed")
            self.fire_event(GameEvent(
                type=EVENT_LTB,
                source_card_id=card.id,
                source_name=card.name,
                controller_id=p.id,
                data={"to_zone": "graveyard"},
            ))
        if to_destroy:
            self.flush_effect_queue()

    def _clear_combat_state(self) -> None:
        for p in self.players:
            for card in p.battlefield.permanents:
                card.is_attacking = False
                card.attacking_target = None
                card.is_blocking = False
                card.blocking = None
                card.damage_taken = 0
        self.combat_attackers.clear()
        self.combat_blockers.clear()
        self.combat_awaiting_human_action = None

    def complete_combat_after_attackers(self) -> None:
        """Chain through DECLARE_BLOCKERS → COMBAT_DAMAGE → END_OF_COMBAT after attackers declared."""
        self.combat_awaiting_human_action = None
        for step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE, Step.END_OF_COMBAT):
            self.step = step
            self.phase = _STEP_TO_PHASE[step]
            self._process_current_step()
            self.check_state_based_actions()
            if self.combat_awaiting_human_action:
                return
            if not self.stack.is_empty:
                return
        self.step = Step.POSTCOMBAT_MAIN
        self.phase = Phase.POSTCOMBAT_MAIN

    def complete_combat_after_blockers(self) -> None:
        """Chain through COMBAT_DAMAGE → END_OF_COMBAT after blockers declared, then advance."""
        self.combat_awaiting_human_action = None
        for step in (Step.COMBAT_DAMAGE, Step.END_OF_COMBAT):
            self.step = step
            self.phase = _STEP_TO_PHASE[step]
            self._process_current_step()
            self.check_state_based_actions()
            if not self.stack.is_empty:
                return
        idx = _STEP_SEQUENCE.index(Step.END_OF_COMBAT)
        self.step = _STEP_SEQUENCE[idx + 1]
        self.phase = _STEP_TO_PHASE[self.step]

    # ── Turn / loop helpers ───────────────────────────────────────────────────

    def advance_ai_turns_until_human(self, human_player_id: str, max_steps: int = 200) -> None:
        steps = 0
        while (
            self.active_player.id != human_player_id
            and not self.winner
            and self.stack.is_empty
            and not self.combat_awaiting_human_action
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

    # ── Effect engine ─────────────────────────────────────────────────────────

    def fire_event(self, event: GameEvent) -> None:
        """Collect triggered effects from all battlefield permanents and queue them."""
        from app.engine.effects.resolver import collect_triggers
        new_effects = collect_triggers(event, self)
        self.effect_queue.extend(new_effects)

    def flush_effect_queue(self) -> None:
        """Resolve all queued effects (AI-controlled or mandatory) until queue is empty."""
        from app.engine.effects.resolver import resolve_next
        max_iter = 200
        i = 0
        while self.effect_queue and i < max_iter:
            resolve_next(self)
            i += 1

    def refresh_statics(self) -> None:
        from app.engine.effects.resolver import apply_static_effects
        apply_static_effects(self)

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
        return max(0, self.human_mulligan_count - 1)

    def mulligan_do_mulligan(self, player: Player) -> None:
        if player.id in self.mulligan_active:
            self.mulligan_active.remove(player.id)
            self.mulligan_active.append(player.id)
        self.mulligan_counts[player.id] = self.mulligan_counts.get(player.id, 0) + 1
        player.return_hand_to_library()
        player.draw(7)

    def mulligan_do_keep(self, player_id: str) -> None:
        if player_id in self.mulligan_active:
            self.mulligan_active.remove(player_id)
        self.mulligan_phase = "playing" if not self.mulligan_active else "mulliganing"

    def to_dict(self, include_ai_hands: bool = False) -> dict:
        return {
            "game_id": self.game_id,
            "pending_choices": [e.to_dict() for e in self.pending_choices],
            "effect_queue_size": len(self.effect_queue),
            "pending_etb_replacement": self.pending_etb_replacement,
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
                for obj in reversed(self.stack.objects)
            ],
            "winner": self.winner,
            "combat_awaiting_human_action": self.combat_awaiting_human_action,
            "combat_attackers": dict(self.combat_attackers),
            "combat_blockers": {k: list(v) for k, v in self.combat_blockers.items()},
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
                            "power": c.power,
                            "toughness": c.toughness,
                            "is_attacking": c.is_attacking,
                            "attacking_target": c.attacking_target,
                            "is_blocking": c.is_blocking,
                            "entered_turn": c.entered_turn,
                            "equipped_to": getattr(c, "equipped_to", None),
                            "oracle_text": c.oracle_text,
                            "mana_ability": (
                                {
                                    "type": c.mana_ability.type,
                                    "produces": c.mana_ability.produces,
                                    "count": c.mana_ability.count,
                                }
                                if c.mana_ability else None
                            ),
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
                    ] if p.is_human or include_ai_hands else [],
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
            "ai_decision_log": self.ai_decision_log[-50:] if include_ai_hands else [],
        }
