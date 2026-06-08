from __future__ import annotations
from app.ai.base_ai import BaseAI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.game_state import GameState

# Key cards for Kinnan lines
MANA_DORKS = {"Birds of Paradise", "Llanowar Elves", "Elvish Mystic", "Arbor Elf"}
COMBO_PIECES = {"Basalt Monolith", "Freed from the Real", "Pemmin's Aura"}
WIN_CONDITIONS = {"Thassa's Oracle", "Blue Sun's Zenith", "Stroke of Genius"}


class KinnanAI(BaseAI):
    @property
    def archetype_name(self) -> str:
        return "Kinnan, Bonder Prodigy"

    def take_turn(self, game_state: GameState) -> list[str]:
        logs: list[str] = []
        player = self.player

        # 1. Untap
        player.battlefield.untap_all(player.id)
        logs.extend(self._log("Untap step."))

        # 2. Draw
        drawn = player.draw(1)
        if drawn:
            logs.extend(self._log(f"Drew {drawn[0].name}."))

        # 3. Play fast mana if available
        for card in player.hand.cards:
            if card.name in {"Sol Ring", "Mana Crypt", "Jeweled Lotus", "Mox Diamond"}:
                player.battlefield.add(card)
                player.hand.remove(card.id)
                logs.extend(self._log(f"Played {card.name}."))

        # 4. Play Kinnan if in hand
        for card in player.hand.cards:
            if card.name == "Kinnan, Bonder Prodigy":
                player.battlefield.add(card)
                player.hand.remove(card.id)
                logs.extend(self._log("Played Kinnan, Bonder Prodigy."))
                break

        # 5. Look for combo
        hand_names = {c.name for c in player.hand.cards}
        if COMBO_PIECES & hand_names:
            logs.extend(self._log("Assembling untap combo..."))

        game_state.log(f"{player.name} ends turn.")
        return logs

    def should_counter(self, game_state: GameState, spell_name: str, caster_id: str) -> bool:
        high_priority_threats = {"Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
                                  "Drannith Magistrate", "Rule of Law", "Arcane Laboratory"}
        counterspells = {"Force of Will", "Mana Drain", "Swan Song", "Counterspell"}
        has_counter = any(c.name in counterspells for c in self.player.hand.cards)
        return has_counter and spell_name in high_priority_threats
