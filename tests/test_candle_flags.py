from __future__ import annotations

import unittest

from indicators import RSI_OVERBOUGHT, RSI_OVERSOLD, band_intersects, rsi_crosses_level


class BandIntersectsTests(unittest.TestCase):
    def test_band_inside_the_range_intersects(self) -> None:
        self.assertTrue(band_intersects(low=9, high=11, band=10))

    def test_band_on_the_edges_intersects(self) -> None:
        self.assertTrue(band_intersects(low=9, high=11, band=9))
        self.assertTrue(band_intersects(low=9, high=11, band=11))

    def test_band_outside_the_range_does_not_intersect(self) -> None:
        self.assertFalse(band_intersects(low=9, high=11, band=12))
        self.assertFalse(band_intersects(low=9, high=11, band=8))

    def test_missing_values_give_none(self) -> None:
        self.assertIsNone(band_intersects(low=9, high=11, band=None))
        self.assertIsNone(band_intersects(low=None, high=11, band=10))


class RsiCrossTests(unittest.TestCase):
    def test_upward_cross_through_overbought(self) -> None:
        self.assertTrue(rsi_crosses_level(65, 72, RSI_OVERBOUGHT))

    def test_downward_cross_through_overbought(self) -> None:
        self.assertTrue(rsi_crosses_level(75, 68, RSI_OVERBOUGHT))

    def test_cross_through_oversold_in_either_direction(self) -> None:
        self.assertTrue(rsi_crosses_level(35, 28, RSI_OVERSOLD))
        self.assertTrue(rsi_crosses_level(25, 33, RSI_OVERSOLD))

    def test_staying_beyond_the_level_is_not_a_cross(self) -> None:
        self.assertFalse(rsi_crosses_level(72, 75, RSI_OVERBOUGHT))
        self.assertFalse(rsi_crosses_level(25, 20, RSI_OVERSOLD))

    def test_staying_on_one_side_is_not_a_cross(self) -> None:
        self.assertFalse(rsi_crosses_level(50, 55, RSI_OVERBOUGHT))

    def test_missing_previous_or_current_gives_none(self) -> None:
        self.assertIsNone(rsi_crosses_level(None, 72, RSI_OVERBOUGHT))
        self.assertIsNone(rsi_crosses_level(65, None, RSI_OVERBOUGHT))


if __name__ == "__main__":
    unittest.main()
