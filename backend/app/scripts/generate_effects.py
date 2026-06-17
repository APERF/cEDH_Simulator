"""
Optional bulk pre-warming script: generate effects_json for all cards in the DB.

The game engine generates effects lazily on first play (no cost until a card
is actually seen).  Run this script only if you want every card pre-processed
before any game starts.

Usage (from backend/ directory):
    python -m app.scripts.generate_effects

Requires ANTHROPIC_API_KEY in environment or .env file.
Estimated cost: ~$13-17 for all 34k cards (one-time).
"""

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

from sqlalchemy import select, update, func, and_
from app.db.database import SessionLocal
from app.db.models import CardData
from app.engine.effects.llm import parse_batch

BATCH_SIZE = 25
DELAY_BETWEEN_BATCHES = 0.3


def fetch_unprocessed(session, limit: int = 500) -> list[CardData]:
    return session.execute(
        select(CardData)
        .where(
            and_(
                CardData.effects_json.is_(None),
                CardData.oracle_text.isnot(None),
                CardData.oracle_text != "",
            )
        )
        .limit(limit)
    ).scalars().all()


def mark_lands(session) -> int:
    rows = session.execute(
        select(CardData).where(
            and_(
                CardData.effects_json.is_(None),
                CardData.type_line.ilike("%Land%"),
            )
        )
    ).scalars().all()
    for row in rows:
        row.effects_json = {"skip": True, "skip_reason": "land", "effects": []}
    session.commit()
    return len(rows)


def main() -> None:
    print("cEDH Simulator — Bulk Effect Pre-warmer")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    with SessionLocal() as session:
        land_count = mark_lands(session)
        print(f"Marked {land_count} lands as skipped")
        total = session.execute(
            select(func.count()).select_from(CardData).where(CardData.effects_json.is_(None))
        ).scalar_one()
        print(f"Cards remaining to process: {total}")
        print()

    processed = 0
    failed_batches = 0
    start = time.time()

    while True:
        with SessionLocal() as session:
            batch = fetch_unprocessed(session, limit=BATCH_SIZE)
            if not batch:
                break

            cards_data = [
                {"name": c.name, "type_line": c.type_line, "oracle_text": c.oracle_text or ""}
                for c in batch
            ]
            results = parse_batch(cards_data, ANTHROPIC_API_KEY, max_tokens=8192)

            if results is None:
                for c in batch:
                    c.effects_json = {"skip": True, "skip_reason": "llm_error", "effects": []}
                session.commit()
                failed_batches += 1
            else:
                result_map = {r["name"]: r for r in results if r.get("name")}
                for c in batch:
                    spec = result_map.get(c.name) or {
                        "name": c.name, "skip": True, "skip_reason": "llm_missed", "effects": []
                    }
                    session.execute(
                        update(CardData).where(CardData.name == c.name).values(effects_json=spec)
                    )
                session.commit()
                processed += len(batch)
                elapsed = time.time() - start
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  [{processed:>6} processed]  {rate:.1f} cards/s")

            time.sleep(DELAY_BETWEEN_BATCHES)

    elapsed = time.time() - start
    print()
    print(f"Done! {processed} cards in {elapsed:.1f}s")
    if failed_batches:
        print(f"WARNING: {failed_batches} batches failed")


if __name__ == "__main__":
    main()
