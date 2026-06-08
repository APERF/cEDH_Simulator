from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.models.schemas import CardType, Zone


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

    # runtime state
    zone: Zone = Zone.LIBRARY
    tapped: bool = False
    counters: dict[str, int] = field(default_factory=dict)
    owner_id: str = ""
    controller_id: str = ""

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
