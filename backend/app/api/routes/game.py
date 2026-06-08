import uuid as uuid_lib
import json
import os
from fastapi import APIRouter, HTTPException
from app.models.schemas import NewGameRequest
from app.engine.card import Card
from app.engine.player import Player
from app.engine.game_state import GameState
from app.decks.parser import parse_decklist
from app.cards.scryfall import fetch_collection_images

router = APIRouter()

_sessions: dict[str, GameState] = {}  # noqa

_META_DIR = os.path.join(os.path.dirname(__file__), "../../decks/meta_decks")


def _make_card(name: str, owner_id: str) -> Card:
    return Card(
        id=str(uuid_lib.uuid4()),
        name=name,
        mana_cost="",
        cmc=0,
        type_line="Unknown",
        oracle_text="",
        colors=[],
        color_identity=[],
        keywords=[],
        owner_id=owner_id,
        controller_id=owner_id,
    )


def _deck_from_decklist(raw: str, owner_id: str) -> list[Card]:
    entries = parse_decklist(raw)
    cards: list[Card] = []
    for count, name in entries:
        for _ in range(count):
            cards.append(_make_card(name, owner_id))
    return cards


def _deck_for_ai(commander_name: str, owner_id: str) -> list[Card]:
    """Build a minimal AI library from the meta deck JSON if available."""
    for fname in os.listdir(_META_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(_META_DIR, fname)) as f:
            data = json.load(f)
        if data.get("commander") == commander_name:
            key_cards: list[str] = data.get("key_cards", [])
            cards = [_make_card(c, owner_id) for c in key_cards]
            # Pad to 99 with generic "Card" placeholders so the library is drawable
            while len(cards) < 99:
                cards.append(_make_card("(Unknown Card)", owner_id))
            return cards
    # Fallback: 99 placeholder cards
    return [_make_card("(Unknown Card)", owner_id) for _ in range(99)]


@router.post("/new", response_model=dict)
async def new_game(request: NewGameRequest):
    human_id = "player_human"
    human_deck = _deck_from_decklist(request.player_decklist.decklist, human_id)
    human = Player(
        player_id=human_id,
        name=request.player_decklist.name or "You",
        is_human=True,
        deck=human_deck,
    )
    human.library.shuffle()
    human.draw(7)

    # Enrich all human cards with Scryfall images (one batch call)
    all_human_cards = list(human.hand.cards) + list(human.library._cards)
    unique_names = list({c.name for c in all_human_cards})
    images = await fetch_collection_images(unique_names)
    for card in all_human_cards:
        card.image_uri = images.get(card.name)

    players: list[Player] = [human]
    for i, commander in enumerate(request.opponent_commanders[:3]):
        ai_id = f"player_ai_{i}"
        ai_deck = _deck_for_ai(commander, ai_id)
        ai = Player(player_id=ai_id, name=commander, is_human=False, deck=ai_deck)
        ai.library.shuffle()
        ai.draw(7)
        players.append(ai)

    gs = GameState(players)
    _sessions[gs.game_id] = gs
    return {"game_id": gs.game_id}


@router.get("/{game_id}", response_model=dict)
async def get_game_state(game_id: str):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    return _sessions[game_id].to_dict()


@router.post("/{game_id}/action", response_model=dict)
async def player_action(game_id: str, action: dict):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"status": "ok", "log": []}


@router.post("/{game_id}/ai-turn", response_model=dict)
async def ai_turn(game_id: str):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"status": "ok", "log": []}
