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


async def fetch_collection_images(names: list[str]) -> dict[str, str]:
    """Batch-fetch image URIs for up to N card names via POST /cards/collection.
    Returns {canonical_name: image_uri}. Already-cached names are skipped."""
    result: dict[str, str] = {}
    to_fetch = [n for n in names if n not in _cache]

    async with httpx.AsyncClient() as client:
        for i in range(0, len(to_fetch), 75):
            chunk = to_fetch[i : i + 75]
            # DFC names ("Front // Back") confuse the collection API — use only the front face
            lookup = {n: n.split(" // ")[0].strip() if " // " in n else n for n in chunk}
            resp = await client.post(
                f"{SCRYFALL_BASE}/cards/collection",
                json={"identifiers": [{"name": lookup[n]} for n in chunk]},
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            for card in resp.json().get("data", []):
                _cache[card["name"]] = card
                # also index by original searched name if Scryfall normalised it
                for orig, front in lookup.items():
                    if front.lower() in card["name"].lower() or card["name"].lower() in front.lower():
                        _cache[orig] = card

    for name in names:
        card_data = _cache.get(name)
        if not card_data:
            continue
        if "image_uris" in card_data:
            uri = card_data["image_uris"].get("normal")
        elif "card_faces" in card_data:
            uri = card_data["card_faces"][0].get("image_uris", {}).get("normal")
        else:
            uri = None
        if uri:
            result[name] = uri
    return result


def apply_cached_data(cards: list) -> None:
    """Populate type_line, mana_cost, cmc, etc. on Card objects from the in-memory cache.
    Call after fetch_collection_images so the cache is already warm."""
    for card in cards:
        data = _cache.get(card.name)
        if not data:
            continue
        card.type_line = data.get("type_line") or card.type_line
        card.mana_cost = data.get("mana_cost") or (
            data.get("card_faces", [{}])[0].get("mana_cost") or card.mana_cost
        )
        card.cmc = data.get("cmc", card.cmc)
        card.oracle_text = data.get("oracle_text") or (
            data.get("card_faces", [{}])[0].get("oracle_text") or card.oracle_text
        )
        card.colors = data.get("colors", card.colors)
        card.color_identity = data.get("color_identity", card.color_identity)
        card.keywords = data.get("keywords", card.keywords)
        card.power = data.get("power", card.power)
        card.toughness = data.get("toughness", card.toughness)


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
