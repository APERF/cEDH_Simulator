from __future__ import annotations
import httpx
from functools import lru_cache

SCRYFALL_BASE = "https://api.scryfall.com"
_cache: dict[str, dict] = {}


async def fetch_card_by_name(name: str) -> dict | None:
    if name in _cache:
        return _cache[name]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SCRYFALL_BASE}/cards/named",
            params={"fuzzy": name},
            timeout=10,
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    _cache[name] = data
    return data


async def fetch_card_by_id(scryfall_id: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SCRYFALL_BASE}/cards/{scryfall_id}", timeout=10)
    if resp.status_code != 200:
        return None
    return resp.json()


async def search_cards(query: str) -> list[dict]:
    results = []
    url = f"{SCRYFALL_BASE}/cards/search"
    params: dict = {"q": query}
    async with httpx.AsyncClient() as client:
        while url:
            resp = await client.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                break
            data = resp.json()
            results.extend(data.get("data", []))
            url = data.get("next_page")
            params = {}
    return results


def scryfall_to_card_schema(data: dict) -> dict:
    image_uri = None
    if "image_uris" in data:
        image_uri = data["image_uris"].get("normal")
    elif "card_faces" in data:
        face = data["card_faces"][0]
        image_uri = face.get("image_uris", {}).get("normal")

    return {
        "id": data.get("id", ""),
        "name": data.get("name", ""),
        "mana_cost": data.get("mana_cost") or (
            data.get("card_faces", [{}])[0].get("mana_cost")
        ),
        "cmc": data.get("cmc", 0),
        "type_line": data.get("type_line", ""),
        "oracle_text": data.get("oracle_text") or (
            data.get("card_faces", [{}])[0].get("oracle_text", "")
        ),
        "power": data.get("power"),
        "toughness": data.get("toughness"),
        "colors": data.get("colors", []),
        "color_identity": data.get("color_identity", []),
        "keywords": data.get("keywords", []),
        "scryfall_id": data.get("id"),
        "image_uri": image_uri,
    }
