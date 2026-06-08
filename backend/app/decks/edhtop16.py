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

_cache: dict = {}
_cache_ttl = 3600  # 1 hour


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
