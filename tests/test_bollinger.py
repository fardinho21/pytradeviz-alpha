from __future__ import annotations

import math
import unittest
from typing import Any, List

from indicators import BOLLINGER_MULTIPLIER, BOLLINGER_PERIOD, Indicators


def make_rows(closes: List[float]) -> List[List[Any]]:
    return [
        [["2025", "01", f"{day:02d}"], close, close, close, close, {"rsi": None}]
        for day, close in enumerate(closes, start=1)
    ]


class BollingerCalculationTests(unittest.TestCase):
    def test_fixed_settings(self) -> None:
        self.assertEqual(BOLLINGER_PERIOD, 20)
        self.assertEqual(BOLLINGER_MULTIPLIER, 2)

    def test_warm_up_rows_are_none(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3, 4, 5]))
        middle, upper, lower = indicators.calculate_bollinger(period=3, multiplier=2)
        self.assertEqual(middle[:2], [None, None])
        self.assertEqual(upper[:2], [None, None])
        self.assertEqual(lower[:2], [None, None])

    def test_middle_band_is_the_simple_average_of_closes(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3, 4, 5]))
        middle, _, _ = indicators.calculate_bollinger(period=3, multiplier=2)
        self.assertEqual(middle[2:], [2.0, 3.0, 4.0])

    def test_bands_use_population_standard_deviation(self) -> None:
        # Window [1, 2, 3]: mean 2, population variance (1 + 0 + 1) / 3.
        indicators = Indicators(price_data=make_rows([1, 2, 3, 4, 5]))
        _, upper, lower = indicators.calculate_bollinger(period=3, multiplier=2)
        spread = 2 * math.sqrt(2 / 3)
        self.assertAlmostEqual(upper[2], 2.0 + spread)
        self.assertAlmostEqual(lower[2], 2.0 - spread)

    def test_flat_prices_give_bands_on_the_middle_line(self) -> None:
        indicators = Indicators(price_data=make_rows([5, 5, 5]))
        middle, upper, lower = indicators.calculate_bollinger(period=3, multiplier=2)
        self.assertEqual(middle[2], 5.0)
        self.assertEqual(upper[2], 5.0)
        self.assertEqual(lower[2], 5.0)

    def test_new_rows_extend_the_cached_bands(self) -> None:
        rows = make_rows([1, 2, 3])
        indicators = Indicators(price_data=rows)
        indicators.calculate_bollinger(period=3, multiplier=2)
        rows.extend(make_rows([4]))
        middle, _, _ = indicators.calculate_bollinger(period=3, multiplier=2)
        self.assertEqual(middle[2:], [2.0, 3.0])

    def test_set_price_data_clears_the_bollinger_cache(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3]))
        indicators.calculate_bollinger(period=3, multiplier=2)
        indicators.set_price_data(make_rows([10, 10, 10]))
        middle, _, _ = indicators.calculate_bollinger(period=3, multiplier=2)
        self.assertEqual(middle[2], 10.0)

    def test_range_covers_the_bands_over_all_rows(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3, 4, 5]))
        low, high = indicators.bollinger_range(period=3, multiplier=2)
        spread = 2 * math.sqrt(2 / 3)
        self.assertAlmostEqual(low, 2.0 - spread)
        self.assertAlmostEqual(high, 4.0 + spread)

    def test_range_is_none_without_a_full_window(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2]))
        self.assertIsNone(indicators.bollinger_range(period=3, multiplier=2))


if __name__ == "__main__":
    unittest.main()
