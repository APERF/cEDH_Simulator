import uuid as uuid_lib
import json
import os
import random
from fastapi import APIRouter, HTTPException
from app.models.schemas import NewGameRequest, Zone
from app.engine.card import Card
from app.engine.player import Player
from app.engine.game_state import GameState
from app.decks.parser import parse_decklist, extract_commanders
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


def _build_human_deck(raw: str, owner_id: str) -> tuple[list[Card], list[Card]]:
    """Parse a decklist and return (library_cards, commander_cards) separately."""
    commander_names = set(extract_commanders(raw))
    entries = parse_decklist(raw)
    library: list[Card] = []
    commanders: list[Card] = []
    for count, name in entries:
        for _ in range(count):
            card = _make_card(name, owner_id)
            if name in commander_names:
                card.is_commander = True
                card.zone = Zone.COMMAND
                commanders.append(card)
            else:
                library.append(card)
    return library, commanders


def _deck_for_ai(commander_name: str, owner_id: str) -> list[Card]:
    """Build a 99-card AI library from the meta deck JSON if available."""
    for fname in os.listdir(_META_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(_META_DIR, fname)) as f:
            data = json.load(f)
        if data.get("commander") == commander_name:
            key_cards: list[str] = data.get("key_cards", [])
            cards = [_make_card(c, owner_id) for c in key_cards]
            while len(cards) < 99:
                cards.append(_make_card("(Unknown Card)", owner_id))
            return cards
    return [_make_card("(Unknown Card)", owner_id) for _ in range(99)]


@router.post("/new", response_model=dict)
async def new_game(request: NewGameRequest):
    human_id = "player_human"

    # Separate human commanders from library
    human_library, human_commanders = _build_human_deck(
        request.player_decklist.decklist, human_id
    )
    human = Player(
        player_id=human_id,
        name=request.player_decklist.name or "You",
        is_human=True,
        deck=human_library,
    )
    for cmd in human_commanders:
        human.command_zone.add(cmd)
    human.library.shuffle()
    human.draw(7)

    # Batch-fetch Scryfall images for all human cards + commanders
    all_human_cards = list(human.hand.cards) + list(human.library._cards) + human_commanders
    unique_names = list({c.name for c in all_human_cards})
    images = await fetch_collection_images(unique_names)
    for card in all_human_cards:
        card.image_uri = images.get(card.name)

    players: list[Player] = [human]
    ai_commanders: list[Card] = []

    for i, commander_name in enumerate(request.opponent_commanders[:3]):
        ai_id = f"player_ai_{i}"
        ai_deck = _deck_for_ai(commander_name, ai_id)
        ai = Player(player_id=ai_id, name=commander_name, is_human=False, deck=ai_deck)

        # Support partner commanders stored as "Name1 / Name2"
        partner_names = [n.strip() for n in commander_name.split(" / ")]
        for pname in partner_names:
            ai_cmd = _make_card(pname, ai_id)
            ai_cmd.is_commander = True
            ai_cmd.zone = Zone.COMMAND
            ai.command_zone.add(ai_cmd)
            ai_commanders.append(ai_cmd)

        ai.library.shuffle()
        ai.draw(7)
        players.append(ai)

    # Fetch images for all AI commanders in one batch
    if ai_commanders:
        ai_images = await fetch_collection_images([c.name for c in ai_commanders])
        for cmd in ai_commanders:
            cmd.image_uri = ai_images.get(cmd.name)

    random.shuffle(players)

    if request.seat_preference is not None:
        seat_idx = max(0, min(3, request.seat_preference - 1))
        human_pos = next(i for i, p in enumerate(players) if p.is_human)
        players.insert(seat_idx, players.pop(human_pos))

    gs = GameState(players)
    _sessions[gs.game_id] = gs
    return {"game_id": gs.game_id}


@router.get("/{game_id}", response_model=dict)
async def get_game_state(game_id: str):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    return _sessions[game_id].to_dict()


@router.post("/{game_id}/mulligan", response_model=dict)
async def mulligan_action(game_id: str, body: dict):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    gs = _sessions[game_id]
    if gs.mulligan_phase not in ("mulliganing", "selecting_bottom"):
        raise HTTPException(status_code=400, detail="Not in mulligan phase")

    human = next(p for p in gs.players if p.is_human)
    action = body.get("action")

    if action == "mulligan":
        if gs.mulligan_phase != "mulliganing":
            raise HTTPException(status_code=400, detail="Cannot mulligan now")
        human.return_hand_to_library()
        human.draw(7)
        new_names = [c.name for c in human.hand.cards if not c.image_uri]
        if new_names:
            images = await fetch_collection_images(new_names)
            for card in human.hand.cards:
                if not card.image_uri:
                    card.image_uri = images.get(card.name)
        gs.human_mulligan_count += 1

    elif action == "keep":
        if gs.mulligan_phase != "mulliganing":
            raise HTTPException(status_code=400, detail="Cannot keep now")
        if gs.cards_to_bottom == 0:
            gs.mulligan_phase = "playing"
        else:
            gs.mulligan_phase = "selecting_bottom"

    elif action == "bottom":
        if gs.mulligan_phase != "selecting_bottom":
            raise HTTPException(status_code=400, detail="Not selecting bottom cards")
        card_ids: list[str] = body.get("card_ids", [])
        if len(card_ids) != gs.cards_to_bottom:
            raise HTTPException(
                status_code=400,
                detail=f"Must select exactly {gs.cards_to_bottom} card(s) to put on bottom",
            )
        human.put_on_bottom(card_ids)
        gs.mulligan_phase = "playing"

    else:
        raise HTTPException(status_code=400, detail="action must be 'mulligan', 'keep', or 'bottom'")

    return gs.to_dict()


@router.post("/{game_id}/action", response_model=dict)
async def player_action(game_id: str, action: dict):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    gs = _sessions[game_id]

    action_type = action.get("type")

    if action_type == "pass_priority":
        if not gs.active_player.is_human:
            return {"status": "ok", "log": []}
        log_before = len(gs.game_log)
        gs.advance_step()
        return {"status": "ok", "log": gs.game_log[log_before:]}

    if action_type == "cast_commander":
        card_id = action.get("card_id")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")

        commander = next(
            (c for c in human.command_zone.commanders if c.id == card_id),
            None,
        )
        if not commander:
            raise HTTPException(status_code=400, detail="Commander not found")
        if commander.zone != Zone.COMMAND:
            raise HTTPException(status_code=400, detail="Commander is not in command zone")

        tax = human.command_zone.commander_tax(card_id)
        commander.zone = Zone.BATTLEFIELD
        human.battlefield.add(commander)
        human.command_zone.increment_cast(card_id)

        tax_str = f" (+{tax} tax)" if tax > 0 else ""
        msg = f"{human.name} casts {commander.name}{tax_str}"
        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    return {"status": "ok", "log": []}


@router.post("/{game_id}/ai-turn", response_model=dict)
async def ai_turn(game_id: str):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    gs = _sessions[game_id]
    human = next((p for p in gs.players if p.is_human), None)
    if not human:
        return {"status": "ok", "log": []}
    log_before = len(gs.game_log)
    gs.advance_ai_turns_until_human(human.id)
    return {"status": "ok", "log": gs.game_log[log_before:]}
