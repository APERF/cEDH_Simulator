from __future__ import annotations
import re

# Accepts MTGO / Moxfield / plain text format:
#   1 Sol Ring
#   1x Sol Ring
#   1 Sol Ring (CMR) 465
_LINE_RE = re.compile(r"^(\d+)x?\s+(.+?)(?:\s+\([A-Z0-9]+\))?(?:\s+\d+)?$")

_SECTION_HEADERS = {"commander", "commanders", "deck", "sideboard", "maybeboard", "companion"}


def parse_decklist(raw: str) -> list[tuple[int, str]]:
    """Return list of (count, card_name) tuples from raw decklist text."""
    entries: list[tuple[int, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.lower() in _SECTION_HEADERS:
            continue
        m = _LINE_RE.match(line)
        if m:
            count = int(m.group(1))
            name = m.group(2).strip()
            entries.append((count, name))
    return entries


def extract_commanders(raw: str) -> list[str]:
    """Return card names listed under the Commander section of a Moxfield/MTGO decklist."""
    commanders: list[str] = []
    in_commander_section = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.split()[0] in ("commander", "commanders"):
            in_commander_section = True
            continue
        if lower.split()[0] in ("deck", "sideboard", "maybeboard", "companion"):
            in_commander_section = False
            continue
        if stripped.startswith("//"):
            in_commander_section = "commander" in lower
            continue
        if in_commander_section:
            m = _LINE_RE.match(stripped)
            if m:
                commanders.append(m.group(2).strip())
    return commanders


def validate_deck_size(entries: list[tuple[int, str]]) -> tuple[bool, str]:
    total = sum(c for c, _ in entries)
    if total != 100:
        return False, f"Deck must contain exactly 100 cards (found {total})"
    return True, "ok"
