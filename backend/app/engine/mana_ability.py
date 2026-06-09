from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

_BASIC_LAND_TYPES = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
_FETCH_TYPE_RE = re.compile(r"search your library for a(?:n)?\s+(.*?)\s+card", re.IGNORECASE)

_BASIC_TYPE_TO_COLOR: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}

_ADD_MANA_RE = re.compile(r"\{T\}\s*:\s*Add\s+([^.]+)", re.IGNORECASE)
_COLOR_SYMBOL_RE = re.compile(r"\{([WUBRG])\}")
_COLORLESS_SYMBOL_RE = re.compile(r"\{C\}")
_ANY_COLOR_RE = re.compile(r"one mana of any color", re.IGNORECASE)
_FETCH_RE = re.compile(r"search your library for a.*?land card", re.IGNORECASE | re.DOTALL)
_ETBT_RE = re.compile(r"enters the battlefield tapped", re.IGNORECASE)
_SHOCK_RE = re.compile(r"you may pay 2 life", re.IGNORECASE)
_CONDITIONAL_ETBT_RE = re.compile(r"enters the battlefield tapped unless", re.IGNORECASE)


@dataclass
class ManaAbility:
    """Describes what mana a land produces and any special entry conditions."""
    type: str  # "basic" | "dual" | "tri" | "any_color" | "colorless" | "fetch" | "utility"
    produces: list[str] = field(default_factory=list)  # subset of W U B R G C
    etbt: bool = False        # always enters tapped (no player choice bypasses it)
    condition: Optional[str] = None  # "pay_life:2" (shock) | "check" (conditional etbt) | None


def classify_land(type_line: str, oracle_text: str) -> ManaAbility:
    """
    Derive a ManaAbility from a land's type line and oracle text.
    Called once per card after Scryfall data is populated.
    """
    tl = type_line or ""
    oracle = oracle_text or ""

    # Fetch lands — sacrifice to search, produce no mana directly
    if _FETCH_RE.search(oracle):
        return ManaAbility(type="fetch", produces=[])

    # Entry conditions
    etbt = False
    condition = None

    if _SHOCK_RE.search(oracle):
        # Shock lands: enter tapped by default, player may pay 2 life to avoid it
        etbt = True
        condition = "pay_life:2"
    elif _CONDITIONAL_ETBT_RE.search(oracle):
        # Check/fast lands: ETBT only if a condition isn't met — not always tapped
        condition = "check"
    elif _ETBT_RE.search(oracle):
        # Unconditional ETBT: triomes, bounce lands, etc.
        etbt = True

    # Any-color producers: Command Tower, City of Brass, Mana Confluence, etc.
    if _ANY_COLOR_RE.search(oracle):
        return ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], etbt=etbt, condition=condition)

    # Extract colors from the {T}: Add ... line
    produces: list[str] = []
    add_match = _ADD_MANA_RE.search(oracle)
    if add_match:
        add_text = add_match.group(1)
        if _ANY_COLOR_RE.search(add_text):
            return ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], etbt=etbt, condition=condition)
        colors = list(dict.fromkeys(_COLOR_SYMBOL_RE.findall(add_text)))
        if colors:
            produces = colors
        elif _COLORLESS_SYMBOL_RE.search(add_text):
            return ManaAbility(type="colorless", produces=["C"], etbt=etbt, condition=condition)

    # Fall back to basic land subtypes in the type line (covers snow-covered basics, etc.)
    if not produces:
        produces = [color for name, color in _BASIC_TYPE_TO_COLOR.items() if name in tl]

    # No mana production found — utility land (Wasteland, Maze of Ith, etc.)
    if not produces:
        return ManaAbility(type="utility", produces=[], etbt=etbt, condition=None)

    if len(produces) == 1:
        mtype = "basic"
    elif len(produces) == 2:
        mtype = "dual"
    else:
        mtype = "tri"

    return ManaAbility(type=mtype, produces=produces, etbt=etbt, condition=condition)


def parse_fetch_targets(oracle_text: str) -> list[str]:
    """Return which basic land subtypes a fetch land can retrieve.

    An empty list means "any land" (shouldn't happen in practice but handled gracefully).
    Matching is by subtype, so shock lands and ABU duals with those subtypes qualify too.
    """
    oracle = oracle_text or ""

    # "basic land card" → any basic
    if re.search(r"\bbasic land card\b", oracle, re.IGNORECASE):
        return _BASIC_LAND_TYPES[:]

    m = _FETCH_TYPE_RE.search(oracle)
    if not m:
        return []

    type_clause = m.group(1)
    return [t for t in _BASIC_LAND_TYPES if t in type_clause]
