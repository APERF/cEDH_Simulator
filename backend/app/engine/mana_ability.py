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
_ARTIFACT_MANA_RE = re.compile(r"\{T\}[^:]*:\s*Add\s+([^.]+)", re.IGNORECASE)
_COLOR_SYMBOL_RE = re.compile(r"\{([WUBRG])\}")
_COLORLESS_SYMBOL_RE = re.compile(r"\{C\}")
_ANY_COLOR_RE = re.compile(r"one mana of any color", re.IGNORECASE)

# ── Patterns that mean the {T}: Add belongs to ANOTHER permanent ──────────────
# Equipment/aura grant patterns — the mana ability is on the equipped creature
_GRANT_RE = re.compile(
    r"(equipped creature|enchanted creature|enchanted permanent|"
    r"creatures you control|target creature|each creature) has",
    re.IGNORECASE,
)
# Equipment keyword — Equip {cost} in oracle text
_EQUIP_RE = re.compile(r"\bEquip\b", re.IGNORECASE)
# Keyword-gated abilities (Metalcraft, Threshold, etc.) — registry handles these
_KEYWORD_GATE_RE = re.compile(
    r"(metalcraft|threshold|delirium|morbid|formidable|grandeur|chroma|devotion)\s*[—\-]",
    re.IGNORECASE,
)
# Abilities whose mana production depends on an exiled/imprinted card
_EXILED_CARD_MANA_RE = re.compile(
    r"(color identity contains|that (exiled|imprinted) card)",
    re.IGNORECASE,
)
_FETCH_RE = re.compile(r"search your library for a.*?land card", re.IGNORECASE | re.DOTALL)
_ETBT_RE = re.compile(r"enters the battlefield tapped", re.IGNORECASE)
_SHOCK_RE = re.compile(r"you may pay 2 life", re.IGNORECASE)
_CONDITIONAL_ETBT_RE = re.compile(r"enters the battlefield tapped unless", re.IGNORECASE)


@dataclass
class ManaAbility:
    """Describes what mana a permanent produces from its tap ability."""
    type: str  # "basic" | "dual" | "tri" | "any_color" | "colorless" | "fetch" | "utility"
    produces: list[str] = field(default_factory=list)  # subset of W U B R G C
    count: int = 1            # mana added per activation (e.g. 2 for Sol Ring, 3 for Grim Monolith)
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


def classify_artifact_mana(oracle_text: str) -> "ManaAbility | None":
    """Return ManaAbility for an artifact's tap mana ability, or None if it has none."""
    oracle = oracle_text or ""
    add_match = _ARTIFACT_MANA_RE.search(oracle)
    if not add_match:
        return None
    add_text = add_match.group(1)

    if _ANY_COLOR_RE.search(add_text):
        return ManaAbility(type="any_color", produces=["W", "U", "B", "R", "G"], count=1)

    colors = list(dict.fromkeys(_COLOR_SYMBOL_RE.findall(add_text)))
    if colors:
        mtype = "basic" if len(colors) == 1 else ("dual" if len(colors) == 2 else "tri")
        return ManaAbility(type=mtype, produces=colors, count=1)

    colorless = _COLORLESS_SYMBOL_RE.findall(add_text)
    if colorless:
        return ManaAbility(type="colorless", produces=["C"], count=len(colorless))

    return None


def classify_nonland_mana(oracle_text: str) -> "ManaAbility | None":
    """
    Return ManaAbility for any non-land card's tap mana ability, or None.

    Filters out false positives that classify_artifact_mana would emit:
    - Equipment / auras that *grant* a tap ability to another permanent
    - Keyword-gated abilities (Metalcraft, Threshold) handled by registry ETB
    - Abilities that depend on an exiled / imprinted card's colors
    """
    oracle = oracle_text or ""
    if _GRANT_RE.search(oracle):
        return None
    if _EQUIP_RE.search(oracle):
        return None
    if _KEYWORD_GATE_RE.search(oracle):
        return None
    if _EXILED_CARD_MANA_RE.search(oracle):
        return None
    return classify_artifact_mana(oracle)


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
