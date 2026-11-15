import random
import unittest
from unittest import mock

from trend import (
    DOWN, MIXED, SIDEWAYS, UP, Consensus, adx_states, consensus, efficiency_ratio_states,
    moving_average_stack_states, rsi_adx_states, swing_structure_states, trend_series, wilder_rsi,
)


def zigzag(points, leg=4):
    """Closes that move linearly between the turning points, ``leg`` candles per leg."""
    closes = [float(points[0])]
    for start, end in zip(points, points[1:]):
        for step in range(1, leg + 1):
            closes.append(start + (end - start) * step / leg)
    return closes


def bars_from_closes(closes, spread=0.5):
    highs = [close + spread for close in closes]
    lows = [close - spread for close in closes]
    return highs, lows


class EfficiencyRatioTests(unittest.TestCase):
    def test_warm_up_candles_have_no_state(self):
        states = efficiency_ratio_states([float(i) for i in range(30)], period=10)
        self.assertTrue(all(state is None for state in states[:10]))
        self.assertIsNotNone(states[10])

    def test_a_clean_rise_and_fall_are_up_and_down(self):
        rising = efficiency_ratio_states([float(i) for i in range(30)], period=10)
        falling = efficiency_ratio_states([float(-i) for i in range(30)], period=10)
        self.assertEqual(set(rising[10:]), {UP})
        self.assertEqual(set(falling[10:]), {DOWN})

    def test_a_choppy_move_with_a_small_net_change_is_sideways(self):
        # Net gain of 5 over 10 candles, but the path covered is 30, so the ratio is about 0.17.
        closes = [100 + 0.5 * i + (3 if i % 2 else 0) for i in range(21)]
        self.assertEqual(efficiency_ratio_states(closes, period=10)[10], SIDEWAYS)

    def test_a_flat_series_is_sideways(self):
        states = efficiency_ratio_states([100.0] * 25, period=10)
        self.assertEqual(set(states[10:]), {SIDEWAYS})


class SwingStructureTests(unittest.TestCase):
    def test_higher_highs_and_higher_lows_are_up(self):
        closes = zigzag([100, 110, 102, 115, 105, 120, 110, 125, 116])
        highs, lows = bars_from_closes(closes)
        self.assertEqual(swing_structure_states(highs, lows)[-1], UP)

    def test_lower_highs_and_lower_lows_are_down(self):
        closes = zigzag([125, 115, 122, 108, 118, 100, 112, 90, 99])
        highs, lows = bars_from_closes(closes)
        self.assertEqual(swing_structure_states(highs, lows)[-1], DOWN)

    def test_higher_highs_with_lower_lows_are_sideways(self):
        closes = zigzag([100, 110, 95, 115, 90, 120, 85])
        highs, lows = bars_from_closes(closes)
        self.assertEqual(swing_structure_states(highs, lows)[-1], SIDEWAYS)

    def test_the_state_at_each_candle_never_depends_on_later_candles(self):
        rng = random.Random(7)
        closes = [100.0]
        for _ in range(119):
            closes.append(closes[-1] + rng.uniform(-3, 3))
        highs, lows = bars_from_closes(closes, spread=1.0)
        full = swing_structure_states(highs, lows)
        for end in range(5, len(closes) + 1, 7):
            prefix = swing_structure_states(highs[:end], lows[:end])
            self.assertEqual(prefix, full[:end], msg=f"lookahead when cut at {end}")


class AdxTests(unittest.TestCase):
    def test_a_steady_rise_is_up_once_the_warm_up_is_over(self):
        closes = [100.0 + i for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        states = adx_states(highs, lows, closes)
        self.assertEqual(states[:27], [None] * 27)
        self.assertEqual(set(states[27:]), {UP})

    def test_a_steady_fall_is_down(self):
        closes = [200.0 - i for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(adx_states(highs, lows, closes)[27:]), {DOWN})

    def test_a_range_bound_market_is_sideways(self):
        closes = [100.0 + (1 if i % 2 else 0) for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(adx_states(highs, lows, closes)[27:]), {SIDEWAYS})

    def test_adx_is_sideways_below_the_threshold_even_with_a_net_move(self):
        # A slow drift with alternating up and down candles keeps ADX low.
        closes = [100.0 + 0.2 * i + (1.5 if i % 2 else 0) for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(adx_states(highs, lows, closes)[27:]), {SIDEWAYS})


class MovingAverageStackTests(unittest.TestCase):
    def test_a_rising_series_stacks_up_and_a_falling_one_stacks_down(self):
        rising = moving_average_stack_states([float(i) for i in range(20)], fast=3, slow=5)
        falling = moving_average_stack_states([float(-i) for i in range(20)], fast=3, slow=5)
        self.assertEqual(rising[:4], [None] * 4)
        self.assertEqual(set(rising[4:]), {UP})
        self.assertEqual(set(falling[4:]), {DOWN})

    def test_a_flat_series_is_sideways(self):
        states = moving_average_stack_states([50.0] * 10, fast=3, slow=5)
        self.assertEqual(set(states[4:]), {SIDEWAYS})


class ConsensusTests(unittest.TestCase):
    def test_all_four_agreeing_is_unanimous(self):
        result = consensus([UP, UP, UP, UP])
        self.assertEqual(result, Consensus(UP, 4, (UP, UP, UP, UP)))
        self.assertTrue(result.unanimous)

    def test_three_agreeing_wins_but_is_not_unanimous(self):
        result = consensus([DOWN, SIDEWAYS, DOWN, DOWN])
        self.assertEqual((result.label, result.agreement), (DOWN, 3))
        self.assertFalse(result.unanimous)

    def test_two_votes_with_no_tie_is_enough(self):
        result = consensus([UP, DOWN, SIDEWAYS, UP])
        self.assertEqual((result.label, result.agreement), (UP, 2))

    def test_a_tie_between_two_labels_is_mixed(self):
        result = consensus([UP, DOWN, UP, DOWN])
        self.assertEqual(result.label, MIXED)

    def test_any_missing_vote_means_no_consensus_yet(self):
        self.assertIsNone(consensus([UP, None, UP, UP]))


class WilderRsiTests(unittest.TestCase):
    def test_warm_up_candles_have_no_value(self):
        self.assertEqual(wilder_rsi([1.0, 2.0, 3.0], period=3), [None, None, None])
        self.assertEqual(wilder_rsi([1.0, 2.0, 3.0, 4.0], period=3)[:3], [None, None, None])

    def test_hand_computed_values_with_period_two(self):
        # Changes are +2, -1, +2. Seeds: avg gain 1.0, avg loss 0.5 -> RSI 200/3.
        # Next change +2 with no loss: avg gain 1.5, avg loss 0.25 -> RSI 600/7.
        rsi = wilder_rsi([10.0, 12.0, 11.0, 13.0], period=2)
        self.assertIsNone(rsi[0])
        self.assertIsNone(rsi[1])
        self.assertAlmostEqual(rsi[2], 200 / 3)
        self.assertAlmostEqual(rsi[3], 600 / 7)

    def test_a_steady_rise_is_100_and_a_steady_fall_is_0(self):
        self.assertEqual(wilder_rsi([100.0 + i for i in range(20)], period=5)[5:], [100.0] * 15)
        self.assertEqual(wilder_rsi([100.0 - i for i in range(20)], period=5)[5:], [0.0] * 15)

    def test_a_flat_series_is_the_midline(self):
        self.assertEqual(wilder_rsi([50.0] * 20, period=5)[5:], [50.0] * 15)


class RsiAdxTests(unittest.TestCase):
    def test_a_steady_rise_is_up_once_the_warm_up_is_over(self):
        closes = [100.0 + i for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        states = rsi_adx_states(highs, lows, closes)
        self.assertEqual(states[:27], [None] * 27)
        self.assertEqual(set(states[27:]), {UP})

    def test_a_steady_fall_is_down(self):
        closes = [200.0 - i for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(rsi_adx_states(highs, lows, closes)[27:]), {DOWN})

    def test_a_range_bound_market_is_sideways_because_adx_is_low(self):
        closes = [100.0 + (1 if i % 2 else 0) for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(rsi_adx_states(highs, lows, closes)[27:]), {SIDEWAYS})

    def test_rsi_on_the_midline_is_sideways_even_with_a_strong_trend(self):
        closes = [100.0 + i for i in range(60)]
        highs, lows = bars_from_closes(closes, spread=0.5)
        self.assertEqual(set(rsi_adx_states(highs, lows, closes)[27:]), {UP})
        with mock.patch("trend.wilder_rsi", return_value=[50.0] * len(closes)):
            self.assertEqual(set(rsi_adx_states(highs, lows, closes)[27:]), {SIDEWAYS})

    def test_the_label_never_depends_on_later_candles(self):
        rng = random.Random(5)
        closes = [100.0]
        for _ in range(109):
            closes.append(closes[-1] + rng.uniform(-3, 3))
        highs, lows = bars_from_closes(closes, spread=1.0)
        full = rsi_adx_states(highs, lows, closes)
        for end in range(10, len(closes) + 1, 9):
            self.assertEqual(rsi_adx_states(highs[:end], lows[:end], closes[:end]), full[:end],
                             msg=f"lookahead when cut at {end}")


class TrendSeriesTests(unittest.TestCase):
    def test_all_four_strategies_can_agree_on_a_steady_rise(self):
        points = [100, 110, 108, 120, 118, 130, 128, 140, 138, 150, 148, 160, 158]
        closes = zigzag(points, leg=5)
        highs, lows = bars_from_closes(closes)
        result = trend_series(highs, lows, closes)[-1]
        self.assertEqual(result.label, UP)
        self.assertTrue(result.unanimous, msg=result.votes)

    def test_the_combined_trend_never_depends_on_later_candles(self):
        rng = random.Random(11)
        closes = [100.0]
        for _ in range(109):
            closes.append(closes[-1] + rng.uniform(-3, 3))
        highs, lows = bars_from_closes(closes, spread=1.0)
        full = trend_series(highs, lows, closes)
        for end in range(10, len(closes) + 1, 9):
            self.assertEqual(trend_series(highs[:end], lows[:end], closes[:end]), full[:end],
                             msg=f"lookahead when cut at {end}")

    def test_warm_up_candles_have_no_consensus(self):
        closes = zigzag([100, 110, 102, 115, 105], leg=4)
        highs, lows = bars_from_closes(closes)
        self.assertIsNone(trend_series(highs, lows, closes)[0])


if __name__ == "__main__":
    unittest.main()
