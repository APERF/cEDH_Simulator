from __future__ import annotations
from app.ai.base_ai import BaseAI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState

THRASIOS_SINKS = {"Thrasios, Triton Hero"}
COMBO_LINES = {"Isochron Scepter", "Dramatic Reversal", "Freed from the Real"}


class RograkhThrasiosAI(BaseAI):
    @property
    def archetype_name(self) -> str:
        return "Rograkh / Thrasios"

    def take_turn(self, game_state: GameState) -> list[str]:
        logs: list[str] = []
        player = self.player

        player.battlefield.untap_all(player.id)
        drawn = player.draw(1)
        if drawn:
            logs.extend(self._log(f"Drew {drawn[0].name}."))

        for card in list(player.hand.cards):
            if card.name in {"Sol Ring", "Mana Crypt", "Jeweled Lotus", "Chrome Mox",
                             "Mox Diamond", "Lotus Petal"}:
                player.battlefield.add(card)
                player.hand.remove(card.id)
                logs.extend(self._log(f"Played {card.name}."))

        hand_names = {c.name for c in player.hand.cards}
        if COMBO_LINES & hand_names:
            logs.extend(self._log("Assembling Isochron Scepter + Dramatic Reversal..."))

        # Thrasios sink: if infinite mana achieved
        field_names = {c.name for c in player.battlefield.permanents}
        if "Thrasios, Triton Hero" in field_names:
            logs.extend(self._log("Activating Thrasios to dig for combo."))

        game_state.log(f"{player.name} ends turn.")
        return logs

    def should_counter(self, game_state: GameState, spell_name: str, caster_id: str) -> bool:
        counterspells = {"Force of Will", "Mana Drain", "Swan Song", "Mental Misstep"}
        has_counter = any(c.name in counterspells for c in self.player.hand.cards)
        threats = {"Thassa's Oracle", "Demonic Consultation", "Rule of Law"}
        return has_counter and spell_name in threats
