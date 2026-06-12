import json
import time
from curl_cffi import requests as cffi_requests

_GRAPHQL_URL = "https://edhtop16.com/api/graphql"
_QUERY = """
{
  commanders(first: 100, sortBy: TOP_CUTS, timePeriod: SIX_MONTHS, minEntries: 20, minTournamentSize: 50) {
    edges {
      node {
        name
        colorId
        stats(filters: { timePeriod: SIX_MONTHS, minSize: 50 }) {
          topCuts
          conversionRate
        }
      }
    }
  }
}
"""

_ENTRIES_QUERY = """
query GetTopEntries($name: String!) {
  commander(name: $name) {
    entries(first: 20, filters: { timePeriod: SIX_MONTHS, minEventSize: 50, maxStanding: 16 }) {
      edges {
        node {
          decklist
          standing
          player { name }
          tournament { name tournamentDate }
        }
      }
    }
  }
}
"""

_cache: dict = {}
_cache_ttl = 3600  # 1 hour

_deck_cache: dict = {}
_deck_cache_ttl = 3600  # 1 hour


def _fetch_live() -> dict[str, dict]:
    resp = cffi_requests.post(
        _GRAPHQL_URL,
        json={"query": _QUERY},
        impersonate="chrome124",
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(data["errors"])

    result = {}
    for edge in data["data"]["commanders"]["edges"]:
        node = edge["node"]
        stats = node["stats"]
        result[node["name"]] = {
            "top_cuts": stats["topCuts"],
            "conversion_rate": round(stats["conversionRate"] * 100, 2),
            "colors": list(node["colorId"]),
        }
    return result


def get_live_stats() -> dict[str, dict]:
    now = time.time()
    if _cache.get("data") and now - _cache.get("fetched_at", 0) < _cache_ttl:
        return _cache["data"]
    try:
        stats = _fetch_live()
        _cache["data"] = stats
        _cache["fetched_at"] = now
        return stats
    except Exception:
        return _cache.get("data", {})


def get_top_entries(commander_name: str) -> list[dict]:
    resp = cffi_requests.post(
        _GRAPHQL_URL,
        json={"query": _ENTRIES_QUERY, "variables": {"name": commander_name}},
        impersonate="chrome124",
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(data["errors"])

    commander_data = data["data"].get("commander")
    if not commander_data:
        return []

    entries = []
    for edge in commander_data["entries"]["edges"]:
        node = edge["node"]
        if node.get("decklist"):
            entries.append({
                "url": node["decklist"],
                "standing": node["standing"],
                "player": node["player"]["name"],
                "tournament": node["tournament"]["name"],
                "date": node["tournament"]["tournamentDate"],
            })
    return entries


def get_top_decklist(commander_name: str) -> str | None:
    """Return the first public top-cut decklist for a commander, with 1-hour caching."""
    now = time.time()
    cached = _deck_cache.get(commander_name)
    if cached and now - cached.get("fetched_at", 0) < _deck_cache_ttl:
        return cached["decklist"]
    try:
        for entry in get_top_entries(commander_name):
            decklist = fetch_topdeck_decklist(entry["url"])
            if decklist:
                _deck_cache[commander_name] = {"decklist": decklist, "fetched_at": now}
                return decklist
    except Exception:
        pass
    return None


def fetch_topdeck_decklist(url: str) -> str | None:
    resp = cffi_requests.get(url, impersonate="chrome124", timeout=15)
    if resp.status_code != 200:
        return None

    pos = resp.text.find("const deckData = ")
    if pos == -1:
        return None
    start = resp.text.find("{", pos)
    if start == -1:
        return None

    try:
        deck_data, _ = json.JSONDecoder().raw_decode(resp.text[start:])
    except json.JSONDecodeError:
        return None

    commanders = deck_data.get("Commanders", [])
    mainboard = deck_data.get("Mainboard", [])
    if not mainboard:
        return None

    lines: list[str] = []
    if commanders:
        lines.append("Commander")
        for card in commanders:
            lines.append(f"{card['count']} {card['name']}")
        lines.append("")
    lines.append("Deck")
    for card in mainboard:
        lines.append(f"{card['count']} {card['name']}")

    return "\n".join(lines)
