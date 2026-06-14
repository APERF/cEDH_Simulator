from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.models.schemas import CardType, Zone
from app.engine.mana_ability import ManaAbility


@dataclass
class Card:
    id: str
    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: list[str]
    color_identity: list[str]
    keywords: list[str]
    power: Optional[str] = None
    toughness: Optional[str] = None
    scryfall_id: Optional[str] = None
    image_uri: Optional[str] = None

    is_commander: bool = False
    mana_ability: Optional[ManaAbility] = None  # set after Scryfall enrichment for lands

    # runtime state
    zone: Zone = Zone.LIBRARY
    tapped: bool = False
    tapped_for: Optional[str] = None  # color added to pool when tapped
    counters: dict[str, int] = field(default_factory=dict)
    owner_id: str = ""
    controller_id: str = ""

    # combat state
    is_attacking: bool = False
    attacking_target: Optional[str] = None   # defending player_id
    is_blocking: bool = False
    blocking: Optional[str] = None           # attacker card_id
    damage_taken: int = 0
    entered_turn: int = -1                   # game turn this card entered the battlefield

    @property
    def is_land(self) -> bool:
        return "Land" in self.type_line

    @property
    def is_creature(self) -> bool:
        return "Creature" in self.type_line

    @property
    def is_instant(self) -> bool:
        return "Instant" in self.type_line

    @property
    def is_sorcery(self) -> bool:
        return "Sorcery" in self.type_line

    @property
    def is_artifact(self) -> bool:
        return "Artifact" in self.type_line

    @property
    def is_enchantment(self) -> bool:
        return "Enchantment" in self.type_line

    @property
    def can_be_cast_at_instant_speed(self) -> bool:
        return self.is_instant or "Flash" in self.keywords

    def parsed_power(self) -> int:
        try:
            return max(0, int(self.power or "0"))
        except (ValueError, TypeError):
            return 0

    def parsed_toughness(self) -> int:
        try:
            return max(1, int(self.toughness or "1"))
        except (ValueError, TypeError):
            return 1

    def has_keyword(self, kw: str) -> bool:
        return any(k.lower() == kw.lower() for k in (self.keywords or []))

    def has_summoning_sickness(self, current_turn: int) -> bool:
        return (
            self.is_creature
            and self.entered_turn == current_turn
            and not self.has_keyword("Haste")
        )
