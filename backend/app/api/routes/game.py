import uuid as uuid_lib
import json
import os
import re
import random
from fastapi import APIRouter, HTTPException
from app.models.schemas import NewGameRequest, Zone, Step
from app.engine.card import Card
from app.engine.player import Player
from app.engine.game_state import GameState
from app.decks.parser import parse_decklist, extract_commanders
from app.cards.scryfall import fetch_collection_images, apply_cached_data
from app.engine.mana_cost import parse_cost, can_pay, pay
from app.engine.mana_ability import parse_fetch_targets
from app.ai.base_ai import BaseAI
from app.ai.archetypes.kinnan import KinnanAI

_ARCHETYPE_MAP: dict[str, type] = {
    "Kinnan, Bonder Prodigy": KinnanAI,
}


def _get_ai_class(commander_name: str) -> type:
    for key, cls in _ARCHETYPE_MAP.items():
        if key.lower() in commander_name.lower():
            return cls
    return BaseAI


router = APIRouter()


def _evaluate_check_land(oracle_text: str, player: Player) -> bool:
    """Return True if a check/fast land can enter the battlefield untapped."""
    oracle = (oracle_text or "").lower()

    # Fast lands: "unless you control two or fewer other lands"
    if "two or fewer" in oracle:
        land_count = sum(1 for c in player.battlefield.permanents if c.is_land)
        return land_count <= 2

    # Check lands: "unless you control a Forest or Plains"
    m = re.search(r"unless you control a (\w+) or (\w+)", oracle)
    if m:
        t1, t2 = m.group(1).capitalize(), m.group(2).capitalize()
        return any(
            c.is_land and (t1 in (c.type_line or "") or t2 in (c.type_line or ""))
            for c in player.battlefield.permanents
        )

    return False  # conservative: enter tapped

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

    # Batch-fetch Scryfall data for all human cards + commanders
    all_human_cards = list(human.hand.cards) + list(human.library._cards) + human_commanders
    unique_names = list({c.name for c in all_human_cards})
    images = await fetch_collection_images(unique_names)
    for card in all_human_cards:
        card.image_uri = images.get(card.name)
    apply_cached_data(all_human_cards)

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
        ai.ai = _get_ai_class(commander_name)(ai)

        # Populate Scryfall data for AI key cards so mana_cost/type_line/image_uri are set
        all_ai_cards = list(ai.hand.cards) + list(ai.library._cards)
        unique_ai_names = list({c.name for c in all_ai_cards if c.name != "(Unknown Card)"})
        if unique_ai_names:
            ai_key_images = await fetch_collection_images(unique_ai_names)
            for c in all_ai_cards:
                if c.image_uri is None:
                    c.image_uri = ai_key_images.get(c.name)
        apply_cached_data(all_ai_cards)

        players.append(ai)

    # Fetch images and card data for all AI commanders in one batch
    if ai_commanders:
        ai_images = await fetch_collection_images([c.name for c in ai_commanders])
        for cmd in ai_commanders:
            cmd.image_uri = ai_images.get(cmd.name)
        apply_cached_data(ai_commanders)

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
        cost = parse_cost(commander.mana_cost or "")
        if not can_pay(human.mana_pool, cost, extra_generic=tax):
            cost_str = commander.mana_cost or "free"
            tax_str = f" +{tax}" if tax else ""
            raise HTTPException(
                status_code=400,
                detail=f"Not enough mana (need {cost_str}{tax_str} generic)",
            )
        pay(human.mana_pool, cost, extra_generic=tax)
        commander.zone = Zone.BATTLEFIELD
        human.battlefield.add(commander)
        human.command_zone.increment_cast(card_id)

        tax_str = f" (+{tax} tax)" if tax > 0 else ""
        msg = f"{human.name} casts {commander.name}{tax_str}"
        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    if action_type == "play_land":
        card_id = action.get("card_id")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")
        if gs.active_player.id != human.id:
            raise HTTPException(status_code=400, detail="Not your turn")
        if gs.step not in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN):
            raise HTTPException(status_code=400, detail="Can only play a land during main phase")
        if human.land_played_this_turn:
            raise HTTPException(status_code=400, detail="Already played a land this turn")
        card = human.hand.remove(card_id)
        if not card:
            raise HTTPException(status_code=400, detail="Card not found in hand")
        if not card.is_land:
            human.hand.add(card)
            raise HTTPException(status_code=400, detail="Card is not a land")

        human.land_played_this_turn = True
        ma = card.mana_ability

        # ── Fetch land ──────────────────────────────────────────────────────────
        if ma and ma.type == "fetch":
            card.zone = Zone.GRAVEYARD
            human.graveyard.add(card)
            valid_types = parse_fetch_targets(card.oracle_text or "")
            fetch_options = [
                {
                    "id": c.id,
                    "name": c.name,
                    "image_uri": c.image_uri,
                    "type_line": c.type_line,
                }
                for c in human.library._cards
                if c.is_land and (
                    not valid_types
                    or any(t in (c.type_line or "") for t in valid_types)
                )
            ]
            msg = f"{human.name} cracks {card.name}"
            gs.log(msg)
            return {"status": "fetch", "log": [msg], "fetch_options": fetch_options}

        # ── Shock land ───────────────────────────────────────────────────────────
        if ma and ma.condition == "pay_life:2":
            pay_life = action.get("pay_life", False)
            if pay_life:
                human.take_damage(2)
                card.tapped = False
            else:
                card.tapped = True

        # ── Check / fast land ────────────────────────────────────────────────────
        elif ma and ma.condition == "check":
            card.tapped = not _evaluate_check_land(card.oracle_text or "", human)

        # ── Normal land ──────────────────────────────────────────────────────────
        else:
            card.tapped = False

        card.zone = Zone.BATTLEFIELD
        human.battlefield.add(card)
        msg = f"{human.name} plays {card.name}"
        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    if action_type == "complete_fetch":
        card_id = action.get("card_id")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")

        land = next((c for c in human.library._cards if c.id == card_id), None)
        if not land:
            raise HTTPException(status_code=400, detail="Land not found in library")
        if not land.is_land:
            raise HTTPException(status_code=400, detail="Not a land")

        human.library._cards.remove(land)
        land.zone = Zone.BATTLEFIELD
        land.tapped = True  # fetched lands always enter tapped
        human.battlefield.add(land)
        human.library.shuffle()

        msg = f"{human.name} fetches {land.name}"
        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    if action_type == "cast_spell":
        card_id = action.get("card_id")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")
        if gs.active_player.id != human.id:
            raise HTTPException(status_code=400, detail="Not your turn")
        card = human.hand.remove(card_id)
        if not card:
            raise HTTPException(status_code=400, detail="Card not found in hand")
        if card.is_land:
            human.hand.add(card)
            raise HTTPException(status_code=400, detail="Use play_land for lands")
        if not card.can_be_cast_at_instant_speed:
            if gs.step not in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN):
                human.hand.add(card)
                raise HTTPException(status_code=400, detail="Can only cast sorcery-speed spells during main phase")
        cost = parse_cost(card.mana_cost or "")
        if not can_pay(human.mana_pool, cost):
            human.hand.add(card)
            raise HTTPException(
                status_code=400,
                detail=f"Not enough mana (need {card.mana_cost or 'free'})",
            )
        pay(human.mana_pool, cost)
        is_permanent = card.is_creature or card.is_artifact or card.is_enchantment or "Planeswalker" in card.type_line
        if is_permanent:
            card.zone = Zone.BATTLEFIELD
            card.tapped = False
            human.battlefield.add(card)
        else:
            card.zone = Zone.GRAVEYARD
            human.graveyard.add(card)
        msg = f"{human.name} casts {card.name}"
        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    if action_type == "tap_land":
        card_id = action.get("card_id")
        color = action.get("color")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")
        if gs.active_player.id != human.id:
            raise HTTPException(status_code=400, detail="Not your turn")

        land = next((c for c in human.battlefield.permanents if c.id == card_id), None)
        if not land:
            raise HTTPException(status_code=400, detail="Land not found on battlefield")
        if land.tapped:
            raise HTTPException(status_code=400, detail="Land is already tapped")
        if not land.is_land:
            raise HTTPException(status_code=400, detail="Card is not a land")

        land.tapped = True
        land.tapped_for = None

        ma = land.mana_ability
        if ma and ma.type == "fetch":
            msg = f"{human.name} activates {land.name}"
        elif ma and ma.produces:
            if len(ma.produces) == 1:
                chosen = ma.produces[0]
                human.mana_pool.add(chosen)
                land.tapped_for = chosen
                msg = f"{human.name} taps {land.name} for {{{chosen}}}"
            else:
                if not color or color not in ma.produces:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Must specify color from {ma.produces}",
                    )
                human.mana_pool.add(color)
                land.tapped_for = color
                msg = f"{human.name} taps {land.name} for {{{color}}}"
        else:
            msg = f"{human.name} taps {land.name}"

        gs.log(msg)
        return {"status": "ok", "log": [msg]}

    if action_type == "untap_land":
        card_id = action.get("card_id")
        human = next((p for p in gs.players if p.is_human), None)
        if not human:
            raise HTTPException(status_code=400, detail="No human player found")
        if gs.active_player.id != human.id:
            raise HTTPException(status_code=400, detail="Not your turn")

        land = next((c for c in human.battlefield.permanents if c.id == card_id), None)
        if not land:
            raise HTTPException(status_code=400, detail="Land not found on battlefield")
        if not land.tapped:
            raise HTTPException(status_code=400, detail="Land is not tapped")

        land.tapped = False
        if land.tapped_for:
            human.mana_pool.spend(land.tapped_for)
            msg = f"{human.name} untaps {land.name}, removing {{{land.tapped_for}}} from pool"
        else:
            msg = f"{human.name} untaps {land.name}"
        land.tapped_for = None

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
