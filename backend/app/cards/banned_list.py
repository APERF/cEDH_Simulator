from __future__ import annotations
import httpx
import re
from datetime import datetime, timedelta

_banned: set[str] = set()
_last_fetched: datetime | None = None
_CACHE_TTL = timedelta(hours=24)

BANNED_LIST_URL = "https://mtgcommander.net/index.php/banned-list/"


async def fetch_banned_list() -> set[str]:
    global _banned, _last_fetched
    if _last_fetched and datetime.utcnow() - _last_fetched < _CACHE_TTL:
        return _banned

    async with httpx.AsyncClient() as client:
        resp = await client.get(BANNED_LIST_URL, timeout=15)

    if resp.status_code != 200:
        return _banned

    # Parse card names from the HTML — the RC page lists them in <li> elements
    names = re.findall(r"<li[^>]*>([^<]+)</li>", resp.text)
    _banned = {n.strip() for n in names if n.strip()}
    _last_fetched = datetime.utcnow()
    return _banned


def is_banned(card_name: str) -> bool:
    return card_name in _banned


async def ensure_loaded() -> None:
    global _banned
    if not _banned:
        await fetch_banned_list()
