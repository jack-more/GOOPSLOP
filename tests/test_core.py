import unittest
from datetime import date, timedelta

from goopslop import cli, kalshi, metacritic, pairs
from goopslop.quotes import Quote, clean_ask, clean_bid


def q(venue, event, outcome, bid, ask):
    return Quote(venue, event, event, outcome, bid, ask, 0.0, "", f"{venue}-{outcome}")


class QuoteTests(unittest.TestCase):
    def test_empty_books_become_none(self):
        self.assertIsNone(clean_bid("0.0000"))
        self.assertIsNone(clean_ask("1.0000"))
        self.assertEqual(clean_bid("0.91"), 0.91)

    def test_no_ask_is_other_side_of_yes_bid(self):
        self.assertEqual(q("kalshi", "E", "x", 0.76, 0.77).no_ask, 0.24)
        self.assertIsNone(q("kalshi", "E", "x", None, 0.77).no_ask)


class KalshiFeeTests(unittest.TestCase):
    def test_fee_peaks_at_even_odds_and_rounds_orders_up(self):
        self.assertAlmostEqual(kalshi.fee_per_contract(0.5), 0.0175)
        self.assertEqual(kalshi.order_fee(0.5, 100), 1.75)
        self.assertEqual(kalshi.order_fee(0.92, 1), 0.01)


class PairTests(unittest.TestCase):
    def test_metacritic_thresholds_line_up_across_venues(self):
        spec = pairs.PAIRS[1]
        ks = [q("kalshi", spec.kalshi_event, "Above 95", 0.76, 0.77), q("kalshi", spec.kalshi_event, "Above 99", 0.02, 0.05)]
        ps = [q("polymarket", spec.pm_event, "96+", 0.73, 0.75), q("polymarket", spec.pm_event, "98+", 0.2, 0.21)]
        matched = pairs.match(spec, ks, ps)
        self.assertEqual([(m.k.outcome, m.p.outcome) for m in matched], [("Above 95", "96+")])

    def test_inverted_pair_buys_yes_on_both_venues(self):
        spec = pairs.PAIRS[0]
        pair = pairs.match(spec, [q("kalshi", spec.kalshi_event, "On time", 0.91, 0.92)], [q("polymarket", spec.pm_event, "Postponed", 0.033, 0.034)])[0]
        desc, cost, kp, pp = pair.best()
        self.assertEqual(desc, "Kalshi YES + Poly YES")
        self.assertAlmostEqual(cost, 0.92 + 0.034 + 0.07 * 0.92 * 0.08)

    def test_song_names_match_despite_curly_apostrophes(self):
        spec = pairs.PAIRS[2]
        matched = pairs.match(spec, [q("kalshi", spec.kalshi_event, "God’s Plan", 0.18, 0.2)], [q("polymarket", spec.pm_event, "God's Plan", 0.2, 0.22)])
        self.assertEqual(len(matched), 1)


class MetacriticTests(unittest.TestCase):
    def test_display_rounding_sets_the_threshold(self):
        # 96.5 unrounded displays as 97, so a dead-certain 96.5 is a coin flip only at the boundary.
        self.assertAlmostEqual(metacritic.prob_at_least(97, 96.5, 0.35), 0.5)
        self.assertGreater(metacritic.prob_at_least(97, 96.67, 0.35), 0.5)
        self.assertLess(metacritic.prob_at_least(98, 96.67, 0.35), 0.01)

    def test_venue_thresholds(self):
        self.assertEqual(cli._threshold(q("kalshi", "KXMC-GTA6", "Above 95", 0.7, 0.8)), 96)
        self.assertEqual(cli._threshold(q("polymarket", "gta-vi-metacritic-score", "96+", 0.7, 0.8)), 96)

    def test_bias_fades_as_reviews_arrive(self):
        calib = metacritic.Calibration(bias=-1.0, z_scale=1.0, remaining_share=0.2, games=5)
        early_mean, early_sd = metacritic.forecast(96.0, 80, 12.0, calib, n_final=100)
        late_mean, late_sd = metacritic.forecast(96.0, 99, 12.0, calib, n_final=100)
        self.assertAlmostEqual(early_mean, 95.0)
        self.assertGreater(late_mean, early_mean)
        self.assertGreater(early_sd, late_sd)

    def test_drift_sample_compares_embargo_day_to_day_seven(self):
        release = date(2026, 11, 19)
        revs = [{"date": (release - timedelta(days=1)).isoformat(), "score": 100}] * 10
        revs += [{"date": (release + timedelta(days=3)).isoformat(), "score": 80}] * 10
        revs += [{"date": (release + timedelta(days=30)).isoformat(), "score": 0}] * 10  # after settlement
        drift, z, n_early, n_final = metacritic.drift_sample(revs, release.isoformat())
        self.assertEqual((n_early, n_final), (10, 20))
        self.assertAlmostEqual(drift, -10.0)


if __name__ == "__main__":
    unittest.main()
