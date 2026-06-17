"""
Reset effects_json for cards that need regeneration under the new schema.

Clears effects_json for:
  1. Equipment cards  (type_line contains 'Equipment') — new is_equipment schema
  2. ETB-replacement cards  (oracle text matches "If X would enter the battlefield")
  3. Any card currently marked skip=true  — may now be representable

Options:
  --card "Card Name"   Reset only that specific card by exact name
  --all-skipped        Reset only cards with skip=true (default subset)

Run with:
  cd backend && python -m app.scripts.reset_effects_json
  cd backend && python -m app.scripts.reset_effects_json --card "Thassa's Oracle"
"""
import os, sys

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cedh_simulator")

from app.db.database import SessionLocal
from app.db.models import CardData
from sqlalchemy import select, update

def main():
    args = sys.argv[1:]
    card_name: str | None = None
    if "--card" in args:
        idx = args.index("--card")
        if idx + 1 < len(args):
            card_name = args[idx + 1]
        else:
            print("Error: --card requires a card name argument")
            sys.exit(1)

    total = 0
    with SessionLocal() as session:
        if card_name:
            # Reset a single specific card
            result = session.execute(
                update(CardData)
                .where(CardData.name == card_name)
                .values(effects_json=None)
            )
            session.commit()
            total = result.rowcount
            if total:
                print(f"  reset: {card_name}")
            else:
                print(f"  not found in database: {card_name}")
        else:
            rows = session.execute(select(CardData)).scalars().all()
            to_reset = []
            for row in rows:
                tl = (row.type_line or "").lower()
                oracle = (row.oracle_text or "").lower()
                spec = row.effects_json or {}

                is_equipment = "equipment" in tl
                has_etb_replacement = "would enter the battlefield" in oracle
                is_skipped = spec.get("skip") is True

                if is_equipment or has_etb_replacement or is_skipped:
                    to_reset.append(row.name)

            if to_reset:
                session.execute(
                    update(CardData)
                    .where(CardData.name.in_(to_reset))
                    .values(effects_json=None)
                )
                session.commit()
                total = len(to_reset)
                for name in sorted(to_reset):
                    print(f"  reset: {name}")

    print(f"\nReset {total} card(s). They will regenerate lazily on next game start.")

if __name__ == "__main__":
    main()
