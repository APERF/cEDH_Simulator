"""
One-time bulk import of all MTG card data from Scryfall into PostgreSQL.

Usage (from backend/):
    python -m app.scripts.import_cards

Downloads the Scryfall "oracle_cards" bulk file (~230 MB), filters out
tokens/art-cards/emblems, and upserts all unique cards into the `cards` table.
Subsequent runs update only changed records via ON CONFLICT DO UPDATE.
"""
from __future__ import annotations
import os
import sys
import json
import urllib.request
import tempfile
from datetime import datetime, timezone

# ensure app package is importable when run as __main__
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cedh_simulator")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"

EXCLUDE_LAYOUTS = {
    "token", "double_faced_token", "emblem", "art_series",
    "scheme", "phenomenon", "vanguard", "planar",
}


HEADERS = {
    "User-Agent": "cEDH-Simulator/1.0 (a.perf.beta@gmail.com)",
    "Accept": "application/json",
}


def _urlopen(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _get_bulk_download_url() -> str:
    print("Fetching Scryfall bulk-data index...")
    data = json.loads(_urlopen(BULK_DATA_URL))
    for entry in data.get("data", []):
        if entry.get("type") == "oracle_cards":
            return entry["download_uri"]
    raise RuntimeError("Could not find oracle_cards bulk-data entry")


def _download_to_temp(url: str) -> str:
    tmp = tempfile.mktemp(suffix=".json")
    print(f"Downloading to {tmp}")
    print("(This is ~230 MB and may take a minute...)")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        downloaded = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            print(f"  {downloaded // 1_000_000} MB downloaded...", end="\r")
    print(f"\nDownload complete ({downloaded // 1_000_000} MB).")
    return tmp


def _extract_image_uri(card: dict) -> str | None:
    if "image_uris" in card:
        return card["image_uris"].get("normal")
    faces = card.get("card_faces", [])
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get("normal")
    return None


def _extract_oracle_text(card: dict) -> str | None:
    if "oracle_text" in card:
        return card["oracle_text"]
    faces = card.get("card_faces", [])
    if faces:
        texts = [f.get("oracle_text", "") for f in faces if f.get("oracle_text")]
        return "\n//\n".join(texts) if texts else None
    return None


def _extract_mana_cost(card: dict) -> str | None:
    if "mana_cost" in card:
        return card["mana_cost"] or None
    faces = card.get("card_faces", [])
    if faces:
        return faces[0].get("mana_cost") or None
    return None


def run_import(path: str) -> None:
    engine = create_engine(DATABASE_URL)
    now = datetime.now(timezone.utc)

    print("Parsing card data...")
    with open(path, encoding="utf-8") as f:
        raw_cards: list[dict] = json.load(f)

    filtered = [
        c for c in raw_cards
        if c.get("lang") == "en"
        and c.get("layout") not in EXCLUDE_LAYOUTS
        and c.get("set_type") not in ("token", "memorabilia")
    ]
    print(f"Filtered to {len(filtered):,} unique cards (from {len(raw_cards):,} total).")

    upsert_sql = text("""
        INSERT INTO cards
            (scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
             keywords, colors, color_identity, power, toughness,
             image_uri, layout, last_synced)
        VALUES
            (:scryfall_id, :name, :mana_cost, :cmc, :type_line, :oracle_text,
             :keywords, :colors, :color_identity, :power, :toughness,
             :image_uri, :layout, :last_synced)
        ON CONFLICT (name) DO UPDATE SET
            scryfall_id   = EXCLUDED.scryfall_id,
            mana_cost     = EXCLUDED.mana_cost,
            cmc           = EXCLUDED.cmc,
            type_line     = EXCLUDED.type_line,
            oracle_text   = EXCLUDED.oracle_text,
            keywords      = EXCLUDED.keywords,
            colors        = EXCLUDED.colors,
            color_identity= EXCLUDED.color_identity,
            power         = EXCLUDED.power,
            toughness     = EXCLUDED.toughness,
            image_uri     = EXCLUDED.image_uri,
            layout        = EXCLUDED.layout,
            last_synced   = EXCLUDED.last_synced
    """)

    BATCH = 500
    total = 0
    with Session(engine) as session:
        batch: list[dict] = []
        for card in filtered:
            row = {
                "scryfall_id": card["id"],
                "name": card["name"],
                "mana_cost": _extract_mana_cost(card),
                "cmc": card.get("cmc"),
                "type_line": card.get("type_line", ""),
                "oracle_text": _extract_oracle_text(card),
                "keywords": card.get("keywords") or [],
                "colors": card.get("colors") or [],
                "color_identity": card.get("color_identity") or [],
                "power": card.get("power"),
                "toughness": card.get("toughness"),
                "image_uri": _extract_image_uri(card),
                "layout": card.get("layout"),
                "last_synced": now,
            }
            batch.append(row)
            if len(batch) >= BATCH:
                session.execute(upsert_sql, batch)
                session.commit()
                total += len(batch)
                print(f"  Inserted/updated {total:,} cards...", end="\r")
                batch = []

        if batch:
            session.execute(upsert_sql, batch)
            session.commit()
            total += len(batch)

    print(f"\nDone. {total:,} cards upserted into PostgreSQL.")


def main() -> None:
    download_url = _get_bulk_download_url()
    tmp_path = _download_to_temp(download_url)
    try:
        run_import(tmp_path)
    finally:
        os.unlink(tmp_path)
        print(f"Cleaned up temp file {tmp_path}")


if __name__ == "__main__":
    main()
