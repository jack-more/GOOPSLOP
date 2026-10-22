"""Polymarket public market data via the Gamma API (no auth needed for reads)."""

from .http import get_json
from .quotes import Quote, clean_ask, clean_bid

GAMMA = "https://gamma-api.polymarket.com"
QUERIES = ("GTA VI", "GTA 6", "Grand Theft Auto")


def _quote(event, market):
    return Quote(
        venue="polymarket",
        event=event["slug"],
        event_title=event["title"],
        outcome=market.get("groupItemTitle") or market.get("question", ""),
        bid=clean_bid(market.get("bestBid")),
        ask=clean_ask(market.get("bestAsk")),
        volume=float(market.get("volume") or 0),
        close=market.get("endDate", ""),
        market_id=market.get("slug", ""),
    )


def _open_quotes(event):
    if event.get("closed"):
        return []
    return [_quote(event, m) for m in event.get("markets") or [] if not m.get("closed")]


def fetch_event(slug):
    return _open_quotes(get_json(f"{GAMMA}/events/slug/{slug}"))


def fetch_gta(queries=QUERIES):
    seen, quotes = set(), []
    for query in queries:
        data = get_json(f"{GAMMA}/public-search", {"q": query, "limit_per_type": "50"})
        for event in data.get("events", []):
            title = event.get("title", "").lower()
            if event["id"] in seen or not any(k in title for k in ("gta", "grand theft")):
                continue
            seen.add(event["id"])
            quotes.extend(_open_quotes(event))
    return quotes
