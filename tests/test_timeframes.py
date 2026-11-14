import unittest

from timeframes import DAILY, TIMEFRAMES, resample, shows_day_labels, timeframe_rows


def daily(date, o, h, l, c):
    year, month, day = date.split("-")
    return [[year, month, day], o, h, l, c, {"rsi": None, "ema": None, "sma": None}]


class ResampleTests(unittest.TestCase):
    def test_timeframes_are_ordered_with_daily_first(self):
        self.assertEqual(TIMEFRAMES, ("Daily", "2W", "1M", "2M", "3M", "6M"))

    def test_daily_returns_rows_unchanged(self):
        rows = [daily("2024-01-02", 1, 2, 0.5, 1.5)]
        self.assertIs(resample(rows, DAILY), rows)
        self.assertIs(timeframe_rows(rows, DAILY), rows)

    def test_empty_input_gives_no_candles(self):
        for label in TIMEFRAMES[1:]:
            self.assertEqual(resample([], label), [])

    def test_monthly_candle_aggregates_ohlc(self):
        rows = [
            daily("2024-01-02", 10, 12, 9, 11),
            daily("2024-01-03", 11, 15, 10, 14),
            daily("2024-01-04", 14, 14, 7, 8),
            daily("2024-02-01", 8, 9, 6, 9),
        ]
        candles = resample(rows, "1M")
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0][0], ["2024", "01", "02"])
        self.assertEqual(candles[0][1:5], [10, 15, 7, 8])
        self.assertEqual(candles[1][0], ["2024", "02", "01"])
        self.assertEqual(candles[1][1:5], [8, 9, 6, 9])

    def test_two_month_buckets_pair_consecutive_months(self):
        rows = [
            daily("2024-01-15", 1, 1, 1, 1),
            daily("2024-02-15", 2, 2, 2, 2),
            daily("2024-03-15", 3, 3, 3, 3),
            daily("2024-04-15", 4, 4, 4, 4),
        ]
        candles = resample(rows, "2M")
        self.assertEqual([c[0][:2] for c in candles], [["2024", "01"], ["2024", "03"]])
        self.assertEqual([c[1] for c in candles], [1, 3])

    def test_three_and_six_month_buckets(self):
        rows = [
            daily("2024-03-31", 1, 1, 1, 1),
            daily("2024-04-01", 2, 2, 2, 2),
            daily("2024-06-30", 3, 3, 3, 3),
            daily("2024-07-01", 4, 4, 4, 4),
        ]
        self.assertEqual(len(resample(rows, "3M")), 3)
        self.assertEqual(len(resample(rows, "6M")), 2)

    def test_buckets_do_not_merge_across_years(self):
        rows = [daily("2023-12-29", 1, 1, 1, 1), daily("2024-01-02", 2, 2, 2, 2)]
        self.assertEqual(len(resample(rows, "1M")), 2)
        self.assertEqual(len(resample(rows, "2M")), 2)
        self.assertEqual(len(resample(rows, "6M")), 2)

    def test_two_week_buckets_use_iso_week_pairs(self):
        # 2024-01-01 is ISO week 1; weeks 1-2 share a bucket, week 3 starts the next.
        rows = [
            daily("2024-01-01", 1, 1, 1, 1),
            daily("2024-01-10", 2, 2, 2, 2),
            daily("2024-01-15", 3, 3, 3, 3),
        ]
        candles = resample(rows, "2W")
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0][1], 1)
        self.assertEqual(candles[0][4], 2)
        self.assertEqual(candles[1][1], 3)

    def test_two_week_bucket_across_year_boundary(self):
        # 2024-12-30 belongs to ISO week 1 of 2025, so it pairs with 2025-01-02.
        rows = [daily("2024-12-30", 1, 1, 1, 1), daily("2025-01-02", 2, 2, 2, 2)]
        candles = resample(rows, "2W")
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0][0], ["2024", "12", "30"])

    def test_each_candle_gets_its_own_indicator_dict(self):
        rows = [daily("2024-01-02", 1, 1, 1, 1), daily("2024-02-02", 2, 2, 2, 2)]
        candles = resample(rows, "1M")
        candles[0][5]["rsi"] = 55.0
        self.assertIsNone(candles[1][5]["rsi"])
        self.assertIsNone(rows[0][5]["rsi"])

    def test_day_labels_only_on_daily_and_two_week(self):
        self.assertTrue(shows_day_labels("Daily"))
        self.assertTrue(shows_day_labels("2W"))
        for label in ("1M", "2M", "3M", "6M"):
            self.assertFalse(shows_day_labels(label))


if __name__ == "__main__":
    unittest.main()
