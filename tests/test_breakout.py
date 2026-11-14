import datetime as dt
import random
import unittest

from breakout import (
    ATR_REJECTION, BREAKOUT, EXPIRED, MIN_BUCKET_SAMPLES, PENDING, PERCENT_REJECTION,
    REJECTION, RESOLVED, BreakoutStudy, LevelEvent, Odds, average_true_range, bucket_key,
    resolve_outcome, tally,
)
from levels import RESISTANCE, SUPPORT, LevelFinder, LevelSettings


def make_row(high, low, close, offset=0):
    day = dt.date(2024, 1, 1) + dt.timedelta(days=offset)
    return [
        [f"{day.year:04d}", f"{day.month:02d}", f"{day.day:02d}"],
        close, high, low, close, {"rsi": None},
    ]


def random_walk_rows(count, seed):
    rng = random.Random(seed)
    price = 100.0
    rows = []
    for offset in range(count):
        close = max(1.0, price + rng.uniform(-3.0, 3.0))
        high = max(price, close) + rng.uniform(0.0, 1.5)
        low = min(price, close) - rng.uniform(0.0, 1.5)
        rows.append(make_row(high, low, close, offset))
        price = close
    return rows


class AverageTrueRangeTests(unittest.TestCase):
    def test_constant_range_gives_that_range_once_a_full_period_exists(self) -> None:
        rows = [make_row(102.0, 100.0, 101.0, offset) for offset in range(20)]
        atr = average_true_range(rows, period=14)
        self.assertEqual(atr[:13], [None] * 13)
        self.assertAlmostEqual(atr[13], 2.0)
        self.assertAlmostEqual(atr[19], 2.0)

    def test_value_at_a_candle_ignores_later_candles(self) -> None:
        rows = random_walk_rows(60, seed=3)
        full = average_true_range(rows)
        truncated = average_true_range(rows[:30])
        self.assertEqual(full[:30], truncated)


class ResolveOutcomeTests(unittest.TestCase):
    """Support at 100 with a 1% zone, so a close below 99 breaks it."""

    def test_close_through_the_zone_is_a_breakout(self) -> None:
        outcome, resolved_at = resolve_outcome(
            SUPPORT, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[101.0, 101.0, 100.5], lows=[100.5, 100.0, 98.5],
            closes=[101.0, 100.5, 98.9])
        self.assertEqual((outcome, resolved_at), (BREAKOUT, 2))

    def test_high_reaching_one_atr_above_support_is_a_rejection(self) -> None:
        outcome, resolved_at = resolve_outcome(
            SUPPORT, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[101.5, 101.0, 102.5], lows=[100.5, 100.5, 101.0],
            closes=[101.0, 101.0, 101.0])
        self.assertEqual((outcome, resolved_at), (REJECTION, 2))

    def test_percent_rule_uses_two_percent_of_price_not_atr(self) -> None:
        highs = [101.0, 101.5, 101.2, 101.0]
        lows = [100.5] * 4
        closes = [101.0] * 4
        atr_outcome, _ = resolve_outcome(
            SUPPORT, 100.0, 0, 3, ATR_REJECTION, atr=1.0, tolerance=0.01,
            highs=highs, lows=lows, closes=closes)
        percent_outcome, _ = resolve_outcome(
            SUPPORT, 100.0, 0, 3, PERCENT_REJECTION, atr=1.0, tolerance=0.01,
            highs=highs, lows=lows, closes=closes)
        self.assertEqual(atr_outcome, REJECTION)
        self.assertEqual(percent_outcome, EXPIRED)

    def test_breakout_takes_precedence_within_the_same_candle(self) -> None:
        outcome, resolved_at = resolve_outcome(
            SUPPORT, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[101.0, 103.0], lows=[100.0, 98.0], closes=[101.0, 98.9])
        self.assertEqual((outcome, resolved_at), (BREAKOUT, 1))

    def test_resistance_rejects_on_a_low_one_atr_below_and_breaks_above_the_zone(self) -> None:
        rejected, at = resolve_outcome(
            RESISTANCE, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[99.0, 99.0], lows=[99.5, 97.5], closes=[99.0, 99.0])
        self.assertEqual((rejected, at), (REJECTION, 1))
        broke, at = resolve_outcome(
            RESISTANCE, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[99.0, 102.0], lows=[99.5, 100.0], closes=[99.0, 101.5])
        self.assertEqual((broke, at), (BREAKOUT, 1))

    def test_no_decision_within_a_fully_observed_horizon_expires(self) -> None:
        outcome, resolved_at = resolve_outcome(
            SUPPORT, 100.0, 0, 2, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[101.5] * 3, lows=[100.5] * 3, closes=[101.0] * 3)
        self.assertEqual((outcome, resolved_at), (EXPIRED, None))

    def test_no_decision_before_the_horizon_is_observed_is_pending(self) -> None:
        outcome, resolved_at = resolve_outcome(
            SUPPORT, 100.0, 0, 5, ATR_REJECTION, atr=2.0, tolerance=0.01,
            highs=[101.5] * 3, lows=[100.5] * 3, closes=[101.0] * 3)
        self.assertEqual((outcome, resolved_at), (PENDING, None))


class OddsTests(unittest.TestCase):
    def test_probability_is_hidden_below_the_minimum_sample_count(self) -> None:
        sparse = Odds(MIN_BUCKET_SAMPLES - 2, 1)
        self.assertFalse(sparse.reliable)
        self.assertIsNone(sparse.probability)
        self.assertIsNone(Odds(0, 0).rate)

    def test_probability_is_the_breakout_share_once_reliable(self) -> None:
        odds = Odds(7, 3)
        self.assertTrue(odds.reliable)
        self.assertAlmostEqual(odds.probability, 0.7)

    def test_tally_counts_only_resolved_events_by_bucket(self) -> None:
        def event(outcome, touches=2):
            return LevelEvent("6M", 10, SUPPORT, 100.0, touches, 0.5, outcome, 12)

        odds = tally([event(BREAKOUT), event(REJECTION), event(EXPIRED), event(PENDING),
                      event(BREAKOUT, touches=9)])
        self.assertEqual(odds[("6M", SUPPORT, 2, 0)], Odds(1, 1))
        self.assertEqual(odds[("6M", SUPPORT, 4, 0)], Odds(1, 0))
        self.assertEqual(set(RESOLVED), {BREAKOUT, REJECTION})


class BreakoutStudyTests(unittest.TestCase):
    def test_rejects_unknown_horizon_or_rejection_rule(self) -> None:
        rows = random_walk_rows(120, seed=1)
        finder = LevelFinder(rows, LevelSettings())
        with self.assertRaises(ValueError):
            BreakoutStudy(rows, finder, "6M", horizon=7, rejection=ATR_REJECTION)
        with self.assertRaises(ValueError):
            BreakoutStudy(rows, finder, "6M", horizon=5, rejection="3%")

    def test_every_event_resolves_after_its_origin_and_outcomes_are_known(self) -> None:
        rows = random_walk_rows(400, seed=7)
        study = BreakoutStudy(rows, LevelFinder(rows, LevelSettings()), "2M",
                              horizon=10, rejection=ATR_REJECTION)
        self.assertTrue(study.events)
        for event in study.events:
            self.assertIn(event.outcome, (BREAKOUT, REJECTION, EXPIRED, PENDING))
            if event.resolved_at is not None:
                self.assertGreater(event.resolved_at, event.origin)

    def test_odds_are_unavailable_before_the_first_atr(self) -> None:
        rows = random_walk_rows(120, seed=2)
        study = BreakoutStudy(rows, LevelFinder(rows, LevelSettings()), "6M",
                              horizon=5, rejection=ATR_REJECTION)
        self.assertIsNone(study.odds_at(3, 100.0, SUPPORT, 2))

    def test_walk_forward_is_none_without_events(self) -> None:
        rows = random_walk_rows(5, seed=4)
        study = BreakoutStudy(rows, LevelFinder(rows, LevelSettings()), "6M",
                              horizon=5, rejection=ATR_REJECTION)
        self.assertIsNone(study.walk_forward())

    def test_odds_at_a_candle_count_only_outcomes_resolved_by_then(self) -> None:
        rows = random_walk_rows(400, seed=5)
        study = BreakoutStudy(rows, LevelFinder(rows, LevelSettings()), "2M",
                              horizon=10, rejection=ATR_REJECTION)
        atr = average_true_range(rows)
        closes = [float(row[4]) for row in rows]
        checked = 0
        for event in study.events[:60]:
            for index in (event.origin, event.origin + 15, len(rows) - 1):
                if atr[index] is None:
                    continue
                distance = abs(event.price - closes[index]) / atr[index]
                key = bucket_key("2M", event.kind, event.touches, distance)
                breakouts = rejections = 0
                for other in study.events:
                    if other.outcome not in RESOLVED or other.resolved_at > index:
                        continue
                    if bucket_key(other.window, other.kind, other.touches,
                                  other.atr_distance) != key:
                        continue
                    if other.outcome == BREAKOUT:
                        breakouts += 1
                    else:
                        rejections += 1
                actual = study.odds_at(index, event.price, event.kind, event.touches)
                self.assertEqual(actual, Odds(breakouts, rejections))
                checked += 1
        self.assertGreater(checked, 0)

    def test_level_features_at_a_candle_do_not_depend_on_later_candles(self) -> None:
        rows = random_walk_rows(400, seed=11)
        cut = 250
        settings = LevelSettings()
        full = LevelFinder(rows, settings).tracks("2M")
        truncated = LevelFinder(rows[:cut], settings).tracks("2M")

        def features(tracks):
            return sorted(
                (t.start, t.kind, round(t.price, 9), t.touches)
                for t in tracks if t.start < cut
            )

        self.assertTrue(features(full))
        self.assertEqual(features(full), features(truncated))


if __name__ == "__main__":
    unittest.main()
