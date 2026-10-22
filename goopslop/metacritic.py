"""Live Metascore tracking and a calibrated forecast of the score both venues settle on.

Kalshi KXMC-GTA6 and Polymarket gta-vi-metacritic-score both resolve on the default-platform
Metascore shown 7 days after release at 10 AM ET. The edge is speed: when the review embargo
lifts, this reads the unrounded score (`normalizedScore`) and review count within seconds and
prices every threshold before people refreshing the page do.
"""

import math
import statistics
import time
from dataclasses import dataclass
from datetime import date, timedelta

from .http import get_json

BACKEND = "https://backend.metacritic.com"
GTA6_SLUG = "grand-theft-auto-vi"
PAGE_SIZE = 10  # the reviews endpoint ignores larger limits

# Big open-world and blockbuster launches with day-one embargoes, used to measure how far the
# score moves between embargo day and day 7.
CALIBRATION_SLUGS = [
    "red-dead-redemption-2",
    "grand-theft-auto-v",
    "the-legend-of-zelda-tears-of-the-kingdom",
    "elden-ring",
    "god-of-war-ragnarok",
    "marvels-spider-man-2",
    "cyberpunk-2077",
    "starfield",
    "hogwarts-legacy",
    "ghost-of-tsushima",
    "the-last-of-us-part-ii",
    "baldurs-gate-3",
]


@dataclass(frozen=True)
class Snapshot:
    title: str
    platform: str
    release: str | None
    score: int | None  # what the page displays and what the markets settle on
    exact: float | None  # unrounded weighted score behind the displayed number
    reviews: int


@dataclass(frozen=True)
class Calibration:
    """drift = day-7 mean minus embargo-day mean; z = drift scaled by sampling error."""

    bias: float  # median drift, so one broken launch (Cyberpunk) doesn't set it
    z_scale: float  # RMS of z, so the tails still carry those broken launches
    remaining_share: float  # typical share of day-7 reviews still unpublished on embargo day
    games: int

    @classmethod
    def default(cls):
        # Conservative fallback until `goopslop mc calibrate` runs: no bias, 1.5x sampling noise.
        return cls(bias=0.0, z_scale=1.5, remaining_share=0.25, games=0)


def _product(slug):
    params = {"componentName": "product", "componentDisplayName": "Product", "componentType": "Product"}
    return get_json(f"{BACKEND}/games/metacritic/{slug}/web", params)["data"]["item"]


def snapshot(slug=GTA6_SLUG):
    item = _product(slug)
    summary = item.get("criticScoreSummary") or {}
    return Snapshot(
        title=item.get("title", slug),
        platform=item.get("platform", ""),
        release=item.get("releaseDate"),
        score=summary.get("score"),
        exact=summary.get("normalizedScore"),
        reviews=summary.get("reviewCount") or 0,
    )


def reviews(slug=GTA6_SLUG):
    """Every critic review on the default platform, as dicts with score and date."""
    url = f"{BACKEND}/reviews/metacritic/critic/games/{slug}/web"
    params = {"componentName": "critic-reviews", "componentDisplayName": "critic reviews", "componentType": "ReviewList"}
    out, offset = [], 0
    while True:
        data = get_json(url, {**params, "offset": offset, "limit": PAGE_SIZE})["data"]
        items = data.get("items") or []
        out.extend(i for i in items if i.get("score") is not None)
        offset += PAGE_SIZE
        if not items or offset >= data.get("totalResults", 0):
            return out
        time.sleep(0.2)


def _sampling_sd(sd, n_now, n_final):
    """Standard error of an n_now-review mean relative to the n_final-review mean it is a subset of."""
    return sd * math.sqrt(max(1 / n_now - 1 / n_final, 0.0))


def drift_sample(revs, release):
    """(drift, z) for one past game, or None when there aren't enough embargo-day reviews."""
    release_day = date.fromisoformat(release)
    dated = sorted((date.fromisoformat(r["date"]), r["score"]) for r in revs if r.get("date"))
    window = [(d, s) for d, s in dated if d <= release_day + timedelta(days=7)]
    if len(window) < 15:
        return None
    first_day = window[0][0]
    early = [s for d, s in window if d == first_day]
    final = [s for _, s in window]
    if len(early) < 5 or len(early) == len(final):
        return None
    drift = statistics.mean(final) - statistics.mean(early)
    se = _sampling_sd(statistics.pstdev(final), len(early), len(final))
    return drift, (drift / se if se else 0.0), len(early), len(final)


def calibrate(slugs=CALIBRATION_SLUGS, log=print):
    drifts, zs, shares = [], [], []
    for slug in slugs:
        try:
            snap = snapshot(slug)
            sample = drift_sample(reviews(slug), snap.release)
        except Exception as err:  # one dead slug shouldn't sink the run
            log(f"  {slug}: skipped ({err})")
            continue
        if sample is None:
            log(f"  {slug}: skipped (too few dated reviews)")
            continue
        drift, z, n_early, n_final = sample
        drifts.append(drift)
        zs.append(z)
        shares.append(1 - n_early / n_final)
        log(f"  {snap.title:<40} embargo-day n={n_early:<3} day-7 n={n_final:<3} drift {drift:+.2f}  z {z:+.2f}")
    if len(drifts) < 3:
        return Calibration.default()
    rms_z = math.sqrt(statistics.mean(z * z for z in zs))
    return Calibration(
        bias=statistics.median(drifts),
        z_scale=max(rms_z, 1.0),
        remaining_share=statistics.mean(shares),
        games=len(drifts),
    )


def forecast(exact, n_now, review_sd, calib, n_final=100):
    """Normal forecast (mean, sd) of the unrounded Metascore at settlement.

    Drift comes from reviews not yet published, so the bias shrinks as their share does.
    Metacritic's weighting adds error beyond simple sampling, hence the floor on sd.
    """
    n_final = max(n_final, n_now + 1)
    still_to_come = 1 - n_now / n_final
    bias = calib.bias * min(still_to_come / calib.remaining_share, 1.5)
    sd = calib.z_scale * _sampling_sd(review_sd, max(n_now, 1), n_final)
    return exact + bias, max(sd, 0.35)


def prob_at_least(threshold, mean, sd):
    """P(displayed integer score >= threshold), with the display rounding the unrounded score."""
    z = (threshold - 0.5 - mean) / sd
    return 0.5 * math.erfc(z / math.sqrt(2))
