import datetime as dt
import random
import unittest

from levels import (
    MAX_LEVELS_PER_SIDE, RESISTANCE, SUPPORT, Level, LevelFinder, LevelSettings, Segment,
    candidate_levels, cluster_prices, find_pivots, nearest_per_side, shift_months,
    window_start,
)


def make_rows(ohlc, start=dt.date(2024, 1, 1)):
    """Build viewer-style rows from (high, low, close) tuples, one calendar day apart."""
    rows = []
    for offset, (high, low, close) in enumerate(ohlc):
        day = start + dt.timedelta(days=offset)
        rows.append([
            [f"{day.year:04d}", f"{day.month:02d}", f"{day.day:02d}"],
            close, high, low, close, {"rsi": None},
        ])
    return rows


def random_walk_rows(count, seed):
    rng = random.Random(seed)
    price = 100.0
    ohlc = []
    for _ in range(count):
        close = max(1.0, price + rng.uniform(-3.0, 3.0))
        high = max(price, close) + rng.uniform(0.0, 1.5)
        low = min(price, close) - rng.uniform(0.0, 1.5)
        ohlc.append((high, low, close))
        price = close
    return make_rows(ohlc)


class ShiftMonthsTests(unittest.TestCase):
    def test_clamps_to_end_of_shorter_month(self):
        self.assertEqual(shift_months(dt.date(2024, 3, 31), 1), dt.date(2024, 2, 29))
        self.assertEqual(shift_months(dt.date(2024, 8, 31), 6), dt.date(2024, 2, 29))

    def test_crosses_year_boundary(self):
        self.assertEqual(shift_months(dt.date(2024, 2, 10), 3), dt.date(2023, 11, 10))

    def test_window_lookbacks(self):
        end = dt.date(2024, 6, 30)
        self.assertEqual(window_start(end, "1M"), dt.date(2024, 5, 30))
        self.assertEqual(window_start(end, "6M"), dt.date(2023, 12, 30))


class PivotTests(unittest.TestCase):
    def test_pivots_need_confirmation_on_both_sides(self):
        highs = [1, 2, 5, 2, 1, 2, 3, 2, 1]
        lows = [0, 1, 4, 1, 0, 1, 2, 1, 0]
        pivots = find_pivots(highs, lows, bars=2)
        # Candle 6 (high 3) is also a swing high: it is above candles 4-5 and 7-8.
        self.assertEqual([(p.index, p.price) for p in pivots], [(2, 5), (4, 0), (6, 3)])

    def test_no_pivots_when_series_is_too_short(self):
        self.assertEqual(find_pivots([1, 2, 1], [0, 1, 0], bars=2), [])


class ClusterTests(unittest.TestCase):
    def test_nearby_prices_merge_into_one_cluster(self):
        clusters = cluster_prices([102, 100, 100.5, 150], width=0.01)
        self.assertEqual(clusters, [(100.25, 2), (102, 1), (150, 1)])

    def test_nearest_per_side_keeps_two_each_way(self):
        prices = [90, 90, 95, 95, 98, 98, 110, 110, 115, 115, 120, 120]
        settings = LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2)
        levels = nearest_per_side(candidate_levels(prices, 100, settings), close=100)
        self.assertEqual(
            [(level.price, level.kind) for level in levels],
            [(98, SUPPORT), (95, SUPPORT), (110, RESISTANCE), (115, RESISTANCE)],
        )
        self.assertEqual(len([l for l in levels if l.kind == SUPPORT]), MAX_LEVELS_PER_SIDE)

    def test_min_touches_filters_single_pivots(self):
        settings = LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2)
        self.assertEqual(candidate_levels([90, 110], close=100, settings=settings), [])


class LevelFinderTests(unittest.TestCase):
    def setUp(self):
        # Two lows at 100 (candles 1 and 4) form a support; the 109 and 111 highs stay separate.
        ohlc = [
            (108, 105, 106), (103, 100, 101), (109, 106, 107), (108, 105, 106),
            (103, 100, 101), (110, 107, 108), (111, 108, 109), (102, 99, 100.5),
            (100, 97, 98),
        ]
        self.rows = make_rows(ohlc)
        self.settings = LevelSettings(pivot_bars=1, width_pct=1.0, min_touches=2)

    def test_level_is_known_only_after_second_pivot_is_confirmed(self):
        finder = LevelFinder(self.rows, self.settings)
        self.assertEqual(finder.levels_at(2, "6M"), [])
        self.assertEqual(finder.levels_at(5, "6M"), [Level(100, 2, SUPPORT)])

    def test_segment_stops_on_the_last_candle_before_the_break(self):
        # Candle 8 closes at 98, beyond the 100 support's 1% zone, so the line ends at 7.
        finder = LevelFinder(self.rows, self.settings)
        self.assertIn(Segment(5, 7, 100, SUPPORT, 5, 2), finder.segments("6M"))

    def test_segment_runs_to_last_candle_when_not_broken(self):
        finder = LevelFinder(self.rows[:7], self.settings)
        self.assertIn(Segment(5, 6, 100, SUPPORT, 5, 2), finder.segments("6M"))

    def test_window_excludes_pivots_older_than_its_lookback(self):
        # The pivots at 100 are in January. Twenty flat candles from 1 March put the end
        # of the data well past a 1M lookback, but still inside 3M.
        flat = make_rows([(111, 109, 110)] * 20, start=dt.date(2024, 3, 1))
        finder = LevelFinder(self.rows + flat, self.settings)
        last = len(self.rows) + len(flat) - 1
        self.assertEqual(finder.levels_at(last, "1M"), [])
        self.assertIn(Level(100, 2, SUPPORT), finder.levels_at(last, "3M"))

    def test_levels_for_a_candle_ignore_later_candles(self):
        rows = random_walk_rows(150, seed=7)
        settings = LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2)
        full = LevelFinder(rows, settings)
        for label in ("1M", "3M"):
            for index in range(0, len(rows), 7):
                prefix = LevelFinder(rows[:index + 1], settings)
                self.assertEqual(
                    full.levels_at(index, label), prefix.levels_at(index, label),
                    msg=f"look-ahead at candle {index} in {label}",
                )

    def test_no_more_than_two_levels_per_side_on_any_candle(self):
        rows = random_walk_rows(300, seed=5)
        finder = LevelFinder(rows, LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2))
        for label in ("1M", "2M", "3M", "6M"):
            per_side = {SUPPORT: [0] * len(rows), RESISTANCE: [0] * len(rows)}
            for segment in finder.segments(label):
                for index in range(segment.start, segment.end + 1):
                    per_side[segment.kind][index] += 1
            self.assertLessEqual(max(per_side[SUPPORT]), MAX_LEVELS_PER_SIDE, msg=label)
            self.assertLessEqual(max(per_side[RESISTANCE]), MAX_LEVELS_PER_SIDE, msg=label)

    def test_segments_are_well_formed(self):
        rows = random_walk_rows(150, seed=11)
        finder = LevelFinder(rows, LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2))
        for label in ("1M", "2M", "3M", "6M"):
            for segment in finder.segments(label):
                self.assertLessEqual(segment.start, segment.end)
                self.assertTrue(0 <= segment.start and segment.end < len(rows))
                self.assertIn(segment.kind, (SUPPORT, RESISTANCE))

    def test_static_levels_match_latest_candle(self):
        rows = random_walk_rows(60, seed=3)
        finder = LevelFinder(rows, LevelSettings(pivot_bars=2, width_pct=1.0, min_touches=2))
        self.assertEqual(finder.static_levels("6M"), finder.levels_at(len(rows) - 1, "6M"))

    def test_empty_data_has_no_levels(self):
        finder = LevelFinder([], LevelSettings())
        self.assertEqual(finder.segments("1M"), [])
        self.assertEqual(finder.levels_at(0, "1M"), [])


if __name__ == "__main__":
    unittest.main()
