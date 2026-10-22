"""One normalized shape for a binary market quote across venues. Prices are dollars per $1 contract."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    venue: str  # "kalshi" or "polymarket"
    event: str  # Kalshi event ticker or Polymarket event slug
    event_title: str
    outcome: str  # what YES means inside the event, e.g. "Above 95" or "Pepas"
    bid: float | None  # best YES bid; None when the book is empty
    ask: float | None  # best YES ask; None when the book is empty
    volume: float
    close: str
    market_id: str

    @property
    def no_ask(self):
        """Cost of buying NO, which is the other side of the best YES bid."""
        return None if self.bid is None else round(1 - self.bid, 4)

    @property
    def mid(self):
        if self.bid is None or self.ask is None:
            return None
        return round((self.bid + self.ask) / 2, 4)


def clean_bid(value):
    price = float(value) if value not in (None, "") else 0.0
    return price if price > 0 else None


def clean_ask(value):
    price = float(value) if value not in (None, "") else 1.0
    return price if price < 1 else None
