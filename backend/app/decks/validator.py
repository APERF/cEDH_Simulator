from __future__ import annotations
from app.cards.banned_list import is_banned


def validate_singleton(entries: list[tuple[int, str]]) -> list[str]:
    """Return list of cards violating singleton rule (>1 copy, non-basic)."""
    basics = {"Plains", "Island", "Swamp", "Mountain", "Forest",
              "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
              "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest"}
    violations = []
    for count, name in entries:
        if count > 1 and name not in basics:
            violations.append(f"{name} ({count} copies)")
    return violations


def validate_banned(entries: list[tuple[int, str]]) -> list[str]:
    """Return list of banned cards found in the deck."""
    return [name for _, name in entries if is_banned(name)]


def validate_color_identity(
    entries: list[tuple[int, str]],
    commander_identity: list[str],
    card_identities: dict[str, list[str]],
) -> list[str]:
    """Return cards outside the commander's color identity."""
    violations = []
    allowed = set(commander_identity)
    for _, name in entries:
        identity = set(card_identities.get(name, []))
        if not identity.issubset(allowed):
            violations.append(name)
    return violations
