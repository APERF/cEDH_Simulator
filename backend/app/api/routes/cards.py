from fastapi import APIRouter, HTTPException
from app.cards.scryfall import fetch_card_by_name, scryfall_to_card_schema
from app.cards.banned_list import ensure_loaded, is_banned

router = APIRouter()


@router.get("/search")
async def search_card(name: str):
    data = await fetch_card_by_name(name)
    if not data:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")
    card = scryfall_to_card_schema(data)
    card["banned"] = is_banned(card["name"])
    return card


@router.get("/banned")
async def get_banned_list():
    await ensure_loaded()
    from app.cards.banned_list import _banned
    return {"banned_cards": sorted(_banned)}
