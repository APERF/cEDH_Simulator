from __future__ import annotations
from app.ai.base_ai import BaseAI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState

AD_NAU_PACKAGE = {"Ad Nauseam", "Peer into the Abyss"}
FAST_WIN = {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact"}
INTERACTION = {"Force of Will", "Mana Drain", "Counterspell", "Swan Song",
               "Flusterstorm", "Mindbreak Trap", "Spell Pierce"}


class KraumTymnaAI(BaseAI):
    @property
    def archetype_name(self) -> str:
        return "Kraum / Tymna"

    def take_turn(self, game_state: GameState) -> list[str]:
        logs: list[str] = []
        player = self.player

        player.battlefield.untap_all(player.id)
        drawn = player.draw(1)
        if drawn:
            logs.extend(self._log(f"Drew {drawn[0].name}."))

        # Deploy fast mana
        for card in list(player.hand.cards):
            if card.name in {"Sol Ring", "Mana Crypt", "Jeweled Lotus",
                             "Dark Ritual", "Cabal Ritual"}:
                player.battlefield.add(card)
                player.hand.remove(card.id)
                logs.extend(self._log(f"Played {card.name}."))

        # Cast Ad Nauseam / win if possible
        hand_names = {c.name for c in player.hand.cards}
        if AD_NAU_PACKAGE & hand_names:
            logs.extend(self._log("Attempting Ad Nauseam line..."))
        elif FAST_WIN & hand_names:
            logs.extend(self._log("Attempting Thassa's Oracle win..."))

        # Tymna draw trigger: attack if able
        logs.extend(self._log("Attacking with Tymna to draw cards."))

        game_state.log(f"{player.name} ends turn.")
        return logs

    def should_counter(self, game_state: GameState, spell_name: str, caster_id: str) -> bool:
        hand_counters = {c.name for c in self.player.hand.cards} & INTERACTION
        high_threats = {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
                        "Rhystic Study", "Smothering Tithe"}
        return bool(hand_counters) and spell_name in high_threats
