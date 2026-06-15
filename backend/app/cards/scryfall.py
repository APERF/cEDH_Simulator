from __future__ import annotations
import os
import httpx
from app.engine.mana_ability import classify_land, classify_artifact_mana, classify_nonland_mana

SCRYFALL_BASE = "https://api.scryfall.com"
_cache: dict[str, dict] = {}


def _load_from_db(names: list[str]) -> dict[str, dict]:
    """Query the local cards table for the given names. Returns {name: card_dict}."""
    try:
        from app.db.database import SessionLocal
        from app.db.models import CardData
        from sqlalchemy import select
        with SessionLocal() as session:
            rows = session.execute(
                select(CardData).where(CardData.name.in_(names))
            ).scalars().all()
        result: dict[str, dict] = {}
        for row in rows:
            result[row.name] = {
                "name": row.name,
                "mana_cost": row.mana_cost,
                "cmc": row.cmc,
                "type_line": row.type_line,
                "oracle_text": row.oracle_text,
                "keywords": row.keywords or [],
                "colors": row.colors or [],
                "color_identity": row.color_identity or [],
                "power": row.power,
                "toughness": row.toughness,
                "image_uris": {"normal": row.image_uri} if row.image_uri else None,
                "id": row.scryfall_id,
                "effects_json": row.effects_json,
            }
        return result
    except Exception:
        return {}


def _lazy_generate_effects(cards: list) -> None:
    """
    Generate effects_json for cards missing it, save to DB, and update in-place.
    Silently no-ops if ANTHROPIC_API_KEY is not configured.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return
    try:
        from app.engine.effects.llm import parse_batch
        from app.db.database import SessionLocal
        from app.db.models import CardData
        from sqlalchemy import update
    except ImportError:
        return

    BATCH_SIZE = 25
    card_lookup = {c.name: c for c in cards}

    for i in range(0, len(cards), BATCH_SIZE):
        batch = cards[i : i + BATCH_SIZE]
        cards_data = [
            {"name": c.name, "type_line": c.type_line, "oracle_text": c.oracle_text or ""}
            for c in batch
        ]
        results = parse_batch(cards_data, api_key)
        if results is None:
            # Mark as error so we don't retry every game
            for c in batch:
                c.effects_json = {"skip": True, "skip_reason": "llm_error", "effects": []}
                _cache_set_effects(c.name, c.effects_json)
            continue

        result_map = {r["name"]: r for r in results if r.get("name")}
        for c in batch:
            spec = result_map.get(c.name) or {"skip": True, "skip_reason": "llm_missed", "effects": []}
            c.effects_json = spec
            _cache_set_effects(c.name, spec)

        # Persist to DB
        try:
            with SessionLocal() as session:
                for name, spec in result_map.items():
                    session.execute(
                        update(CardData).where(CardData.name == name).values(effects_json=spec)
                    )
                # Also persist error/missed cards
                for c in batch:
                    if c.name not in result_map:
                        session.execute(
                            update(CardData).where(CardData.name == c.name).values(effects_json=c.effects_json)
                        )
                session.commit()
        except Exception:
            pass  # DB save failure is non-fatal; in-memory spec is still usable


def _cache_set_effects(name: str, spec: dict) -> None:
    """Push effects_json into the in-memory cache entry for a card."""
    if name in _cache and isinstance(_cache[name], dict):
        _cache[name]["effects_json"] = spec


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
    """Batch-fetch image URIs for up to N card names.
    Checks local PostgreSQL DB first, then falls back to Scryfall API.
    Returns {canonical_name: image_uri}. Already-cached names are skipped."""
    result: dict[str, str] = {}

    # Seed cache from local DB for any names not already cached
    uncached = [n for n in names if n not in _cache]
    if uncached:
        db_data = _load_from_db(uncached)
        _cache.update(db_data)

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
        card.effects_json = data.get("effects_json") or card.effects_json
        if card.is_land:
            card.mana_ability = classify_land(card.type_line, card.oracle_text)
        else:
            card.mana_ability = classify_nonland_mana(card.oracle_text or "")

    # Lazy-generate effects_json for any cards that don't have it yet
    missing = [
        c for c in cards
        if c.effects_json is None and not c.is_land and (c.oracle_text or "").strip()
    ]
    if missing:
        _lazy_generate_effects(missing)


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
