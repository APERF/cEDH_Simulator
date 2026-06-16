"""
Fetch and process all 'you win the game' cards from Scryfall.

Searches Scryfall for cards with oracle text containing "you win the game",
saves any missing cards to the local DB, then (re)generates their effects_json
via LLM so win_condition metadata is populated for runtime detection.

Usage (from backend/ directory):
    python -m app.scripts.fetch_win_condition_cards

Requires ANTHROPIC_API_KEY in environment or .env file.
Estimated cost: ~$0.01 (there are ~80 such cards).
"""

import asyncio
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY is not set.")
    print("Add it to backend/.env:  ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

from sqlalchemy import select, update
from app.db.database import SessionLocal
from app.db.models import CardData
from app.engine.effects.llm import parse_batch


SCRYFALL_QUERY = 'o:"you win the game" game:paper -t:token -t:emblem'
BATCH_SIZE = 10  # smaller batches — win condition cards have complex oracle text


async def fetch_win_condition_cards() -> list[dict]:
    from app.cards.scryfall import search_cards
    print(f'Searching Scryfall: {SCRYFALL_QUERY}')
    cards = await search_cards(SCRYFALL_QUERY)
    print(f"Found {len(cards)} cards")
    return cards


def upsert_cards(cards: list[dict]) -> int:
    """Save any missing cards to the DB. Returns count of new inserts."""
    inserted = 0
    with SessionLocal() as session:
        for card in cards:
            name = card.get("name", "")
            if not name:
                continue
            existing = session.execute(
                select(CardData).where(CardData.name == name)
            ).scalar_one_or_none()
            if existing is None:
                image_uri = None
                if "image_uris" in card:
                    image_uri = card["image_uris"].get("normal")
                elif "card_faces" in card:
                    image_uri = card["card_faces"][0].get("image_uris", {}).get("normal")
                oracle = card.get("oracle_text") or (
                    card.get("card_faces", [{}])[0].get("oracle_text", "")
                )
                row = CardData(
                    scryfall_id=card.get("id", ""),
                    name=name,
                    mana_cost=card.get("mana_cost"),
                    cmc=card.get("cmc"),
                    type_line=card.get("type_line", ""),
                    oracle_text=oracle,
                    keywords=card.get("keywords", []),
                    colors=card.get("colors", []),
                    color_identity=card.get("color_identity", []),
                    power=card.get("power"),
                    toughness=card.get("toughness"),
                    image_uri=image_uri,
                    layout=card.get("layout"),
                )
                session.add(row)
                inserted += 1
        session.commit()
    return inserted


def reprocess_win_condition_effects(cards: list[dict]) -> None:
    """Run LLM batch parser on all fetched cards, forcing regeneration of effects_json."""
    names = [c["name"] for c in cards if c.get("name")]
    cards_data = [
        {
            "name": c["name"],
            "type_line": c.get("type_line", ""),
            "oracle_text": c.get("oracle_text") or (
                c.get("card_faces", [{}])[0].get("oracle_text", "")
            ),
        }
        for c in cards if c.get("name")
    ]

    print(f"\nProcessing {len(cards_data)} cards through LLM in batches of {BATCH_SIZE}...")
    total_win_conditions = 0

    with SessionLocal() as session:
        for i in range(0, len(cards_data), BATCH_SIZE):
            batch = cards_data[i : i + BATCH_SIZE]
            print(f"  Batch {i // BATCH_SIZE + 1}: {[c['name'] for c in batch]}")

            results = parse_batch(batch, ANTHROPIC_API_KEY, max_tokens=8192)
            if results is None:
                print("  WARNING: LLM batch failed, skipping")
                time.sleep(2)
                continue

            result_map = {r["name"]: r for r in results if r.get("name")}
            for card_data in batch:
                spec = result_map.get(card_data["name"])
                if spec:
                    wc = spec.get("win_condition")
                    if wc:
                        total_win_conditions += 1
                        print(f"    [WIN] {card_data['name']}: {wc.get('trigger')} / {wc.get('condition_type')}")
                    else:
                        print(f"    [ - ] {card_data['name']}: no win_condition extracted")
                    session.execute(
                        update(CardData)
                        .where(CardData.name == card_data["name"])
                        .values(effects_json=spec)
                    )
            session.commit()
            time.sleep(0.3)

    print(f"\nwin_condition metadata extracted for {total_win_conditions}/{len(cards_data)} cards")


def main() -> None:
    print("cEDH Simulator — Win Condition Card Fetcher")
    print("=" * 50)

    cards = asyncio.run(fetch_win_condition_cards())
    if not cards:
        print("No cards found. Check Scryfall connectivity.")
        sys.exit(1)

    new_count = upsert_cards(cards)
    print(f"Inserted {new_count} new card(s) into local DB")

    reprocess_win_condition_effects(cards)

    print("\nDone. Win condition cards are ready for runtime detection.")


if __name__ == "__main__":
    main()
