from __future__ import annotations
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.player import ManaPool

_GENERIC_RE = re.compile(r"\{(\d+)\}")
_COLOR_RE = re.compile(r"\{([WUBRG])\}")
_COLORLESS_RE = re.compile(r"\{C\}")
_HYBRID_RE = re.compile(r"\{([WUBRG])/([WUBRG])\}")
_PHYREXIAN_RE = re.compile(r"\{[WUBRG]/P\}")

_ALL_COLORS = ("W", "U", "B", "R", "G", "C")


def parse_cost(mana_cost: str) -> dict:
    """Parse a Scryfall mana cost string into component requirements.

    Returns:
        {W, U, B, R, G, C: int, generic: int, hybrid: list[tuple[str, str]]}
    """
    cost: dict = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0, "generic": 0, "hybrid": []}
    if not mana_cost:
        return cost

    for m in _GENERIC_RE.finditer(mana_cost):
        cost["generic"] += int(m.group(1))

    for m in _HYBRID_RE.finditer(mana_cost):
        cost["hybrid"].append((m.group(1), m.group(2)))

    # Strip hybrid and phyrexian before counting single-color symbols
    stripped = _HYBRID_RE.sub("", mana_cost)
    stripped = _PHYREXIAN_RE.sub("", stripped)

    for m in _COLOR_RE.finditer(stripped):
        cost[m.group(1)] += 1

    cost["C"] += len(_COLORLESS_RE.findall(stripped))
    return cost


def can_pay(pool: "ManaPool", cost: dict, extra_generic: int = 0) -> bool:
    """Return True if pool can satisfy the cost (plus any extra generic, e.g. commander tax)."""
    avail = {c: getattr(pool, c, 0) for c in _ALL_COLORS}

    # Exact colored requirements
    for color in ("W", "U", "B", "R", "G"):
        needed = cost.get(color, 0)
        if avail[color] < needed:
            return False
        avail[color] -= needed

    # True colorless
    needed_c = cost.get("C", 0)
    if avail["C"] < needed_c:
        return False
    avail["C"] -= needed_c

    # Hybrid — greedy: prefer richer of the two options
    for c1, c2 in cost.get("hybrid", []):
        if avail.get(c1, 0) >= avail.get(c2, 0) and avail.get(c1, 0) > 0:
            avail[c1] -= 1
        elif avail.get(c2, 0) > 0:
            avail[c2] -= 1
        else:
            if sum(avail.values()) <= 0:
                return False
            best = max(avail, key=lambda k: avail[k])
            avail[best] -= 1

    # Generic (any color)
    total_left = sum(avail.values())
    return total_left >= cost.get("generic", 0) + extra_generic


def pay(pool: "ManaPool", cost: dict, extra_generic: int = 0) -> bool:
    """Deduct cost from pool. Returns False without touching pool if insufficient."""
    if not can_pay(pool, cost, extra_generic):
        return False

    for color in ("W", "U", "B", "R", "G"):
        pool.spend(color, cost.get(color, 0))

    pool.spend("C", cost.get("C", 0))

    for c1, c2 in cost.get("hybrid", []):
        if getattr(pool, c1, 0) >= getattr(pool, c2, 0) and getattr(pool, c1, 0) > 0:
            pool.spend(c1)
        elif getattr(pool, c2, 0) > 0:
            pool.spend(c2)
        else:
            for c in _ALL_COLORS:
                if getattr(pool, c, 0) > 0:
                    pool.spend(c)
                    break

    # Pay generic by draining the richest color first
    for _ in range(cost.get("generic", 0) + extra_generic):
        best = max(_ALL_COLORS, key=lambda c: getattr(pool, c, 0))
        pool.spend(best)

    return True
