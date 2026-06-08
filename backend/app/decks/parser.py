from __future__ import annotations
import re

# Accepts MTGO / Moxfield / plain text format:
#   1 Sol Ring
#   1x Sol Ring
#   1 Sol Ring (CMR) 465
_LINE_RE = re.compile(r"^(\d+)x?\s+(.+?)(?:\s+\([A-Z0-9]+\))?(?:\s+\d+)?$")


def parse_decklist(raw: str) -> list[tuple[int, str]]:
    """Return list of (count, card_name) tuples from raw decklist text."""
    entries: list[tuple[int, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.lower() in ("commander", "deck", "sideboard"):
            continue
        m = _LINE_RE.match(line)
        if m:
            count = int(m.group(1))
            name = m.group(2).strip()
            entries.append((count, name))
    return entries


def validate_deck_size(entries: list[tuple[int, str]]) -> tuple[bool, str]:
    total = sum(c for c, _ in entries)
    if total != 100:
        return False, f"Deck must contain exactly 100 cards (found {total})"
    return True, "ok"
