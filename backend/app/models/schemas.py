from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Zone(str, Enum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    COMMAND = "command"
    STACK = "stack"


class Phase(str, Enum):
    BEGINNING = "beginning"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT = "combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    ENDING = "ending"


class Step(str, Enum):
    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    PRECOMBAT_MAIN = "precombat_main"
    BEGIN_COMBAT = "begin_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    END_OF_COMBAT = "end_of_combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    END = "end"
    CLEANUP = "cleanup"


class CardType(str, Enum):
    CREATURE = "creature"
    INSTANT = "instant"
    SORCERY = "sorcery"
    ARTIFACT = "artifact"
    ENCHANTMENT = "enchantment"
    PLANESWALKER = "planeswalker"
    LAND = "land"
    BATTLE = "battle"


class CardSchema(BaseModel):
    id: str
    name: str
    mana_cost: Optional[str] = None
    cmc: float = 0
    type_line: str
    oracle_text: Optional[str] = None
    power: Optional[str] = None
    toughness: Optional[str] = None
    colors: list[str] = []
    color_identity: list[str] = []
    keywords: list[str] = []
    scryfall_id: Optional[str] = None
    image_uri: Optional[str] = None


class DecklistInput(BaseModel):
    name: str
    decklist: str  # raw decklist text (MTGO/Moxfield format)


class PlayerSchema(BaseModel):
    id: str
    name: str
    is_human: bool
    life_total: int = 40
    commander_damage: dict[str, int] = {}
    hand_size: int = 0
    battlefield_count: int = 0


class GameStateSchema(BaseModel):
    game_id: str
    turn: int
    active_player_id: str
    phase: Phase
    step: Step
    players: list[PlayerSchema]
    stack_size: int
    winner: Optional[str] = None


class NewGameRequest(BaseModel):
    player_decklist: DecklistInput
    opponent_commanders: list[str]  # list of commander names from top 15
    seat_preference: Optional[int] = None  # 1-4; None = random
