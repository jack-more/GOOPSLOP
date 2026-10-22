"""Kalshi public market data (no auth needed for reads)."""

import math
import time

from .http import get_json
from .quotes import Quote, clean_ask, clean_bid

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Every open GTA VI event as of Oct 22, 2026. Run `goopslop discover` to find new ones.
GTA_EVENTS = [
    "KXGTA6ONTIME-26NOV19",
    "KXMC-GTA6",
    "KXGTASALESRECORD-27JAN31",
    "KXCOMPANYACTIONTTWO-27",
    "KXGTAONLINE-GTA6ONLINE",
    "KXGTAPCRELEASE-GTA6PC",
    "KXGTA6SONGS-30",
    "KXROLEINPRODUCTION-GTA27NOV19",
    "KXFEATURE-26GTA6",
    "KXALBUMDEBUT-26DEC05-GTA",
    "KXPUREALBUMS-GTA626NOV26",
    "KXALBUMSTREAMS-GTA626NOV26",
    "KXALBUMEQUIV-GTA626NOV26",
]
KEYWORDS = ("gta", "grand theft", "rockstar games", "take-two")


def _quote(event, market):
    return Quote(
        venue="kalshi",
        event=event["event_ticker"],
        event_title=event["title"],
        outcome=market.get("yes_sub_title") or market.get("subtitle") or market["ticker"],
        bid=clean_bid(market.get("yes_bid_dollars")),
        ask=clean_ask(market.get("yes_ask_dollars")),
        volume=float(market.get("volume_fp") or 0),
        close=market.get("close_time", ""),
        market_id=market["ticker"],
    )


def fetch_event(ticker):
    data = get_json(f"{BASE}/events/{ticker}", {"with_nested_markets": "true"})
    event = data["event"]
    markets = event.get("markets") or data.get("markets") or []
    return [_quote(event, m) for m in markets if m.get("status") in ("active", "open", None)]


def fetch_gta(tickers=GTA_EVENTS):
    quotes = []
    for ticker in tickers:
        quotes.extend(fetch_event(ticker))
        time.sleep(0.3)  # the public API rate-limits bursts
    return quotes


def discover(keywords=KEYWORDS):
    """Full scan of open events; slow (~15k events), so only run it occasionally."""
    found, cursor = [], None
    while True:
        params = {"limit": "200", "status": "open"}
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{BASE}/events", params)
        for event in data.get("events", []):
            text = f"{event.get('title', '')} {event.get('event_ticker', '')}".lower()
            if any(k in text for k in keywords):
                found.append((event["event_ticker"], event["title"]))
        cursor = data.get("cursor")
        if not cursor:
            return found
        time.sleep(0.7)


def fee_per_contract(price):
    """Kalshi's standard taker fee is 7% of p*(1-p) per contract."""
    return 0.07 * price * (1 - price)


def order_fee(price, contracts):
    """The fee Kalshi actually charges on an order, rounded up to the cent."""
    # round first so float noise (175.00000000000003 cents) doesn't bump the fee a cent
    return math.ceil(round(fee_per_contract(price) * contracts * 100, 6)) / 100
