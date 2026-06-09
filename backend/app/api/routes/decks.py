from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import DecklistInput
from app.decks.parser import parse_decklist, validate_deck_size
from app.cards.banned_list import ensure_loaded, is_banned
from app.decks.edhtop16 import get_live_stats
from curl_cffi import requests as cffi_requests
import json
import os
import re

router = APIRouter()

_MOXFIELD_API = "https://api.moxfield.com/v2/decks/all/{}"


def _extract_moxfield_id(url: str) -> str | None:
    m = re.search(r"moxfield\.com/decks/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def _format_moxfield_decklist(data: dict) -> tuple[str, str]:
    name = data.get("name", "Imported Deck")
    lines: list[str] = []
    commanders = data.get("commanders", {})
    if commanders:
        lines.append("Commander")
        for entry in commanders.values():
            lines.append(f"{entry['quantity']} {entry['card']['name']}")
        lines.append("")
    lines.append("Deck")
    for entry in data.get("mainboard", {}).values():
        lines.append(f"{entry['quantity']} {entry['card']['name']}")
    return name, "\n".join(lines)

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


@router.get("/from-moxfield")
async def deck_from_moxfield(url: str = Query(...)):
    deck_id = _extract_moxfield_id(url)
    if not deck_id:
        raise HTTPException(status_code=400, detail="Invalid Moxfield URL")
    resp = cffi_requests.get(
        _MOXFIELD_API.format(deck_id),
        impersonate="chrome124",
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Moxfield returned {resp.status_code}")
    name, decklist = _format_moxfield_decklist(resp.json())
    return {"name": name, "decklist": decklist}


@router.get("/meta")
async def list_meta_decks():
    import asyncio
    live_stats = await asyncio.to_thread(get_live_stats)
    decks = []
    for fname in os.listdir(META_DECKS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(META_DECKS_DIR, fname)) as f:
                data = json.load(f)
            commander = data["commander"]
            live = live_stats.get(commander, {})
            decks.append({
                "id": data["id"],
                "commander": commander,
                "colors": live.get("colors", data["colors"]),
                "archetype": data["archetype"],
                "top_cuts": live.get("top_cuts", data.get("top_cuts")),
                "conversion_rate": live.get("conversion_rate", data.get("conversion_rate")),
            })
    return {"decks": decks}


@router.get("/meta/{deck_id}")
async def get_meta_deck(deck_id: str):
    path = os.path.join(META_DECKS_DIR, f"{deck_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Meta deck not found")
    with open(path) as f:
        return json.load(f)
