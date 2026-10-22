"""Match the same question across Kalshi and Polymarket and price the locked-in two-leg trade."""

import re
from dataclasses import dataclass

from . import kalshi


@dataclass(frozen=True)
class PairSpec:
    name: str
    kalshi_event: str
    pm_event: str
    match: str  # "single", "name", "metacritic" or "outcome:<polymarket outcome label>"
    inverted: bool = False  # True when Polymarket YES means Kalshi NO


PAIRS = [
    # Both settle on a US release by Nov 19, 11:59 PM ET; Polymarket asks the inverse question.
    PairSpec("On-time release", "KXGTA6ONTIME-26NOV19", "gta-6-launch-postponed-again", "single", inverted=True),
    # Both settle on the default-platform Metascore 7 days after release at 10 AM ET.
    PairSpec("Metacritic", "KXMC-GTA6", "gta-vi-metacritic-score", "metacritic"),
    PairSpec("Radio songs at launch", "KXGTA6SONGS-30", "songs-on-gta-vi-radio-at-launch", "name"),
    # Polymarket's album market voids to NO if the album slips past Nov 26; Kalshi's runs to Dec 31.
    PairSpec("Album features", "KXFEATURE-26GTA6", "who-will-be-featured-on-gta-vi-the-album", "name"),
    PairSpec("PC release by end of 2027", "KXGTAPCRELEASE-GTA6PC", "rockstar-releases-pc-version-of-gta-vi-by", "outcome:December 31, 2027"),
]


@dataclass(frozen=True)
class PairQuote:
    spec: PairSpec
    label: str
    k: object  # Kalshi Quote
    p: object  # Polymarket Quote

    def legs(self):
        """Both ways to hold YES on one venue and NO on the other, as (description, kalshi price, pm price)."""
        k, p = self.k, self.p
        if self.spec.inverted:
            return [("Kalshi YES + Poly YES", k.ask, p.ask), ("Kalshi NO + Poly NO", k.no_ask, p.no_ask)]
        return [("Kalshi YES + Poly NO", k.ask, p.no_ask), ("Kalshi NO + Poly YES", k.no_ask, p.ask)]

    def best(self):
        """Cheapest locked-in combo after Kalshi's taker fee, or None when a book is empty."""
        priced = [
            (desc, kp + pp + kalshi.fee_per_contract(kp), kp, pp)
            for desc, kp, pp in self.legs()
            if kp is not None and pp is not None
        ]
        return min(priced, key=lambda row: row[1]) if priced else None


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'")).strip()


def _metacritic_key(venue, outcome):
    """Kalshi 'Above 95' and Polymarket '96+' are the same bet because Metascores are integers."""
    number = int(re.search(r"\d+", outcome).group())
    return number + 1 if venue == "kalshi" else number


def match(spec, kalshi_quotes, pm_quotes):
    ks = [q for q in kalshi_quotes if q.event == spec.kalshi_event]
    ps = [q for q in pm_quotes if q.event == spec.pm_event]
    if spec.match == "single":
        return [PairQuote(spec, spec.name, ks[0], ps[0])] if ks and ps else []
    if spec.match.startswith("outcome:"):
        wanted = spec.match.split(":", 1)[1]
        ps = [q for q in ps if q.outcome == wanted]
        return [PairQuote(spec, spec.name, ks[0], ps[0])] if ks and ps else []
    key = (lambda q: _metacritic_key(q.venue, q.outcome)) if spec.match == "metacritic" else (lambda q: _norm(q.outcome))
    by_key = {key(q): q for q in ps}
    pairs = []
    for kq in ks:
        pq = by_key.get(key(kq))
        if pq:
            label = f"{pq.outcome}" if spec.match == "metacritic" else kq.outcome
            pairs.append(PairQuote(spec, label, kq, pq))
    return pairs


def match_all(kalshi_quotes, pm_quotes, specs=PAIRS):
    return [pair for spec in specs for pair in match(spec, kalshi_quotes, pm_quotes)]
