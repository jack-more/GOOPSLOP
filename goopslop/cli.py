"""goopslop: launch-week edge finder for the GTA VI prediction markets."""

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import kalshi, metacritic, pairs, polymarket

CALIBRATION_FILE = Path(__file__).resolve().parent.parent / "data" / "metacritic_calibration.json"


def _px(value):
    return "  -  " if value is None else f"{value:.3f}"


def cmd_board(args):
    quotes = kalshi.fetch_gta() + polymarket.fetch_gta()
    current = None
    for q in sorted(quotes, key=lambda q: (q.venue, q.event_title, -q.volume)):
        if (q.venue, q.event) != current:
            current = (q.venue, q.event)
            print(f"\n[{q.venue}] {q.event_title}  ({q.event})")
        if q.volume >= args.min_volume:
            print(f"   {q.outcome[:38]:<38} bid {_px(q.bid)}  ask {_px(q.ask)}  vol ${q.volume:>10,.0f}")


def cmd_pairs(args):
    matched = pairs.match_all(kalshi.fetch_gta(), polymarket.fetch_gta())
    print(f"{'pair':<44} {'kalshi bid/ask':>15} {'poly bid/ask':>15}  cheapest lock (after Kalshi fee)")
    for pq in matched:
        best = pq.best()
        lock = "book empty" if best is None else f"{best[0]} = {best[1]:.3f}  ->  {1 - best[1]:+.3f}/contract"
        name = f"{pq.spec.name}: {pq.label}"[:44]
        print(f"{name:<44} {_px(pq.k.bid)}/{_px(pq.k.ask)} {_px(pq.p.bid)}/{_px(pq.p.ask)}  {lock}")
    print("\nPositive numbers are locked-in profit per $1 contract before Polymarket fees and capital lockup.")


def _load_calibration():
    try:
        return metacritic.Calibration(**json.loads(CALIBRATION_FILE.read_text()))
    except (OSError, ValueError, TypeError):
        return metacritic.Calibration.default()


def cmd_mc_calibrate(args):
    print("Measuring embargo-day -> day-7 drift on past blockbusters...")
    calib = metacritic.calibrate()
    CALIBRATION_FILE.parent.mkdir(exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(asdict(calib), indent=2) + "\n")
    print(f"\nmedian drift {calib.bias:+.2f} pts, noise scale {calib.z_scale:.2f}x, "
          f"{calib.remaining_share:.0%} of reviews land after embargo day, {calib.games} games -> {CALIBRATION_FILE}")


def _threshold(quote):
    """Integer score a market needs: Kalshi 'Above 95' needs 96, Polymarket '96+' needs 96."""
    number = int(re.search(r"\d+", quote.outcome).group())
    return number + 1 if quote.venue == "kalshi" else number


def _edges(quote, p_yes):
    fee_yes = kalshi.fee_per_contract(quote.ask) if quote.venue == "kalshi" and quote.ask else 0.0
    fee_no = kalshi.fee_per_contract(quote.no_ask) if quote.venue == "kalshi" and quote.no_ask else 0.0
    yes = None if quote.ask is None else p_yes - quote.ask - fee_yes
    no = None if quote.no_ask is None else (1 - p_yes) - quote.no_ask - fee_no
    return yes, no


def mc_tick(args, calib, cache):
    snap = metacritic.snapshot(args.slug)
    stamp = datetime.now().strftime("%H:%M:%S")
    if not snap.reviews or snap.exact is None:
        print(f"{stamp}  {snap.title} ({snap.platform}): no scored reviews yet")
        return
    if cache.get("n") != snap.reviews:  # only re-pull reviews when the count moves
        scores = [r["score"] for r in metacritic.reviews(args.slug)]
        cache.update(n=snap.reviews, sd=statistics.pstdev(scores) if len(scores) > 1 else 10.0)
    mean, sd = metacritic.forecast(snap.exact, snap.reviews, cache["sd"], calib, args.final_reviews)
    print(f"\n{stamp}  {snap.title} ({snap.platform}): shows {snap.score}, exact {snap.exact:.2f}, "
          f"{snap.reviews} reviews -> settle forecast {mean:.2f} ± {sd:.2f}")
    quotes = kalshi.fetch_event("KXMC-GTA6") + polymarket.fetch_event("gta-vi-metacritic-score")
    for q in sorted(quotes, key=lambda q: (_threshold(q), q.venue)):
        need = _threshold(q)
        if need < 85:
            continue
        p_yes = metacritic.prob_at_least(need, mean, sd)
        yes, no = _edges(q, p_yes)
        flags = []
        if yes is not None and yes >= args.min_edge:
            flags.append(f"BUY YES {yes:+.3f}")
        if no is not None and no >= args.min_edge:
            flags.append(f"BUY NO {no:+.3f}")
        print(f"   {q.venue:<10} >= {need:<3} fair {p_yes:.3f}  bid {_px(q.bid)} ask {_px(q.ask)}  {'  '.join(flags)}")


def cmd_mc_watch(args):
    calib = _load_calibration()
    print(f"calibration: bias {calib.bias:+.2f}, noise {calib.z_scale:.2f}x ({calib.games or 'no'} games)")
    cache = {}
    while True:
        try:
            mc_tick(args, calib, cache)
        except Exception as err:  # a flaky request shouldn't kill an all-night watch
            print(f"error: {err}", file=sys.stderr)
        if args.once:
            return
        time.sleep(args.interval)


def cmd_discover(args):
    for ticker, title in kalshi.discover():
        print(f"{ticker:<36} {title}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="goopslop", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    board = sub.add_parser("board", help="every open GTA VI market on Kalshi and Polymarket")
    board.add_argument("--min-volume", type=float, default=0)
    board.set_defaults(func=cmd_board)

    sub.add_parser("pairs", help="same question on both venues, priced as a locked two-leg trade").set_defaults(func=cmd_pairs)
    sub.add_parser("discover", help="full Kalshi scan for new GTA events (slow)").set_defaults(func=cmd_discover)

    mc = sub.add_parser("mc", help="Metacritic tools").add_subparsers(dest="mc_cmd", required=True)
    mc.add_parser("calibrate", help="measure score drift on past launches").set_defaults(func=cmd_mc_calibrate)
    watch = mc.add_parser("watch", help="poll the Metascore and flag mispriced thresholds")
    watch.add_argument("--slug", default=metacritic.GTA6_SLUG, help="any Metacritic game slug, for dry runs")
    watch.add_argument("--interval", type=float, default=30)
    watch.add_argument("--min-edge", type=float, default=0.04)
    watch.add_argument("--final-reviews", type=int, default=120, help="expected review count at settlement")
    watch.add_argument("--once", action="store_true")
    watch.set_defaults(func=cmd_mc_watch)

    args = parser.parse_args(argv)
    args.func(args)
