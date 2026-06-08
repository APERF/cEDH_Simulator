from fastapi import APIRouter, HTTPException
from app.models.schemas import DecklistInput
from app.decks.parser import parse_decklist, validate_deck_size
from app.cards.banned_list import ensure_loaded, is_banned
import json
import os

router = APIRouter()

META_DECKS_DIR = os.path.join(os.path.dirname(__file__), "../../decks/meta_decks")


@router.post("/validate")
async def validate_decklist(payload: DecklistInput):
    await ensure_loaded()
    entries = parse_decklist(payload.decklist)
    valid, msg = validate_deck_size(entries)
    banned = [name for _, name in entries if is_banned(name)]
    return {
        "valid": valid and not banned,
        "card_count": sum(c for c, _ in entries),
        "size_error": None if valid else msg,
        "banned_cards": banned,
    }


@router.get("/meta")
async def list_meta_decks():
    """Return the list of available top-15 meta commander decklists."""
    decks = []
    for fname in os.listdir(META_DECKS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(META_DECKS_DIR, fname)) as f:
                data = json.load(f)
                decks.append({
                    "id": data["id"],
                    "commander": data["commander"],
                    "colors": data["colors"],
                    "archetype": data["archetype"],
                    "top_cuts": data.get("top_cuts"),
                    "conversion_rate": data.get("conversion_rate"),
                })
    return {"decks": decks}


@router.get("/meta/{deck_id}")
async def get_meta_deck(deck_id: str):
    path = os.path.join(META_DECKS_DIR, f"{deck_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Meta deck not found")
    with open(path) as f:
        return json.load(f)
