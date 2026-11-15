from __future__ import annotations

import calendar
import contextlib
import csv
import datetime
import math
import io
import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from tkinter import ttk

from data_window import data_window_days, range_difference, row_ordinal, window_index_range
from paginated_price_data import PaginatedPriceData
from timeframes import timeframe_rows
from pytradeviz import PyTradeViz
from test_roi import load_price_rows

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "XRP_4_year_ohlc_no_vol.csv"


def add_months(date: datetime.date, months: int) -> datetime.date:
    month = date.year * 12 + date.month - 1 + months
    year, month = divmod(month, 12)
    month += 1
    return datetime.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


class WindowIndexTests(unittest.TestCase):
    def daily_ordinals(self, count: int):
        start = datetime.date(2020, 1, 1).toordinal()
        return [start + offset for offset in range(count)]

    def test_each_timeframe_tab_has_its_window_span(self):
        for label in ("1M", "2M", "3M", "6M"):
            self.assertEqual(data_window_days(label), 6 * 365, label)
        self.assertEqual(data_window_days("2W"), 4 * 365)
        self.assertEqual(data_window_days("Daily"), 365)

    def test_window_is_half_a_year_either_side_of_the_centre(self):
        ordinals = self.daily_ordinals(1000)
        # 182.5 days either side of day 500: the first day within is 318, the last is 682.
        self.assertEqual(window_index_range(ordinals, 500), (318, 682))

    def test_window_never_spans_more_than_a_year(self):
        ordinals = self.daily_ordinals(1000)
        for centre in (0, 100.4, 365.5, 800, 999):
            first, last = window_index_range(ordinals, centre)
            self.assertLessEqual(ordinals[last] - ordinals[first], 365)

    def test_centre_is_clamped_to_the_loaded_data(self):
        ordinals = self.daily_ordinals(1000)
        first, last = window_index_range(ordinals, -40)
        self.assertEqual(first, 0)
        self.assertGreaterEqual(last, 0)
        first, last = window_index_range(ordinals, 10_000)
        self.assertEqual(last, 999)

    def test_empty_data_gives_an_empty_window(self):
        self.assertEqual(window_index_range([], 3), (0, -1))

    def test_row_ordinal_reads_string_dates(self):
        row = [["2020", "02", "29"], 1.0, 2.0, 0.5, 1.5, {}]
        self.assertEqual(row_ordinal(row), datetime.date(2020, 2, 29).toordinal())

    def test_range_difference_lists_indexes_only_in_the_first_range(self):
        self.assertEqual(range_difference((0, 5), (3, 10)), [0, 1, 2])
        self.assertEqual(range_difference((3, 10), (0, 5)), [6, 7, 8, 9, 10])
        self.assertEqual(range_difference((0, -1), (0, 5)), [])
        self.assertEqual(range_difference((0, 5), (0, -1)), [0, 1, 2, 3, 4, 5])


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class DataWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def states(self, kind: str, index: int) -> set:
        canvas = self.viz.window_canvas(kind)
        return {canvas.itemcget(item, "state") for item in canvas.find_withtag(f"{kind}_{index}")}

    def assert_items_match_window(self) -> None:
        for kind in ("candle", "date", "ind"):
            first, last = self.viz.window_range_for(kind, self.viz._applied_window)
            for index in range(len(self.viz.price_data)):
                expected = {"normal"} if first <= index <= last else {"hidden"}
                actual = self.states(kind, index)
                if actual:
                    self.assertEqual(actual, expected, f"{kind} {index}")

    def scroll_to(self, fraction: float) -> None:
        self.viz.canvas.xview_moveto(fraction)
        self.viz.window.update()

    def test_window_matches_the_centre_of_the_view(self):
        self.assertEqual(self.viz._applied_window, self.viz.data_window_range())
        self.assert_items_match_window()

    def test_start_of_data_shows_candles_from_the_first_day(self):
        self.scroll_to(0.0)
        first, last = self.viz._applied_window
        self.assertEqual(first, 0)
        # The centre of the view sits a few candles in, so the window ends a little past half a year.
        rows = self.viz.price_data
        self.assertLessEqual(row_ordinal(rows[last]) - row_ordinal(rows[0]), 365)
        self.assert_items_match_window()

    def test_window_is_centred_on_the_view_and_spans_a_year(self):
        self.scroll_to(0.5)
        rows = self.viz.price_data
        first, last = self.viz._applied_window
        self.assertLessEqual(row_ordinal(rows[last]) - row_ordinal(rows[first]), 365)
        left, right = self.viz.visible_x_range()
        centre = ((left + right) / 2 / self.viz._scale_x - self.viz.chart_padding_x) / self.viz.chart_grid_divider_v
        centre_day = row_ordinal(rows[round(centre)])
        self.assertLessEqual(abs(row_ordinal(rows[first]) - centre_day), 183)
        self.assertLessEqual(abs(row_ordinal(rows[last]) - centre_day), 183)

    def test_scrolling_away_hides_and_scrolling_back_redraws_without_recreating(self):
        self.scroll_to(0.0)
        count_before = len(self.viz.canvas.find_all())
        self.assertEqual(self.states("candle", 0), {"normal"})

        self.scroll_to(1.0)
        self.assertEqual(self.states("candle", 0), {"hidden"})
        self.assertEqual(self.states("candle", len(self.viz.price_data) - 1), {"normal"})
        self.assert_items_match_window()

        self.scroll_to(0.0)
        self.assertEqual(self.states("candle", 0), {"normal"})
        self.assertEqual(len(self.viz.canvas.find_all()), count_before)
        self.assert_items_match_window()

    def test_indicator_and_date_items_follow_the_window(self):
        self.scroll_to(1.0)
        self.assert_items_match_window()
        drawn = [i for i in range(len(self.viz.price_data)) if self.states("ind", i)]
        self.assertTrue(any(self.states("ind", i) == {"hidden"} for i in drawn))
        self.scroll_to(0.0)
        self.assert_items_match_window()

    def test_level_lines_are_clipped_to_the_window(self):
        self.scroll_to(0.0)
        first, last = self.viz._applied_window
        item = self.viz.horizontal_level_item(0, len(self.viz.price_data) - 1, 0.5, "red",
                                              (), tags=("probe",))
        self.assertIsNotNone(item)
        x_left, _, x_right, _ = self.viz.canvas.coords(item)
        half = self.viz.chart_grid_divider_v * self.viz._scale_x / 2
        self.assertGreaterEqual(x_left, self.viz.candle_x(first) - half - 1)
        self.assertLessEqual(x_right, self.viz.candle_x(last) + half + 1)

    def test_level_outside_the_window_is_not_drawn(self):
        self.scroll_to(0.0)
        last_index = len(self.viz.price_data) - 1
        self.assertIsNone(self.viz.horizontal_level_item(
            last_index - 5, last_index, 0.5, "red", (), tags=("probe",)))

    def test_moving_averages_stay_inside_the_window(self):
        period = next(iter(self.viz.sma_applied))
        self.viz.sma_applied[period]["enabled"] = True
        self.scroll_to(0.0)
        self.viz.draw_overlays()
        first, last = self.viz._applied_window
        items = self.viz.canvas.find_withtag(f"sma_{period}")
        self.assertTrue(items)
        for item in items:
            xs = self.viz.canvas.coords(item)[0::2]
            self.assertGreaterEqual(min(xs), self.viz.candle_x(first) - 1)
            self.assertLessEqual(max(xs), self.viz.candle_x(last) + 1)

    def test_scroll_redraw_keeps_sma_inside_the_window(self):
        period = next(iter(self.viz.sma_applied))
        self.viz.sma_applied[period]["enabled"] = True
        self.scroll_to(0.0)
        self.viz.draw_overlays()
        self.scroll_to(1.0)
        first, last = self.viz._applied_window
        for item in self.viz.canvas.find_withtag(f"sma_{period}"):
            xs = self.viz.canvas.coords(item)[0::2]
            self.assertGreaterEqual(min(xs), self.viz.candle_x(first) - 1)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class LoadAllButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        source = PaginatedPriceData(FIXTURE)
        with FIXTURE.open(newline="", encoding="utf-8-sig") as file:
            self.total = sum(1 for _ in csv.reader(file)) - 1
        self.source = source
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": source.load_initial()}, data_source=source)
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def test_load_all_button_loads_everything_and_jumps_to_the_newest_candles(self):
        self.assertTrue(self.source.has_more)
        self.viz.load_all_button.invoke()
        self.viz.window.update()
        self.assertFalse(self.source.has_more)
        self.assertEqual(len(self.viz.price_data), self.total)
        self.assertEqual(len(self.viz.canvas.find_withtag("candle")), 2 * self.total)
        self.assertAlmostEqual(self.viz.canvas.xview()[1], 1.0)
        self.assertEqual(self.viz._applied_window[1], self.total - 1)
        self.assertTrue(self.viz.load_all_button.instate(["disabled"]))
        self.assertTrue(self.viz.load_more_button.instate(["disabled"]))

    def test_load_more_still_loads_one_three_month_window(self):
        first_day = datetime.date(*(int(part) for part in self.viz.price_data[0][0]))
        self.viz.load_more_button.invoke()
        self.viz.window.update()
        last_day = datetime.date(*(int(part) for part in self.viz.price_data[-1][0]))
        self.assertLess(last_day, add_months(first_day, 12 + 3))
        self.assertGreater(last_day, add_months(first_day, 12))
        self.assertTrue(self.source.has_more)
        self.assertTrue(self.viz.load_all_button.instate(["!disabled"]))

    def test_load_all_on_a_derived_timeframe_rebuilds_the_tab_at_the_newest_candles(self):
        self.viz.select_timeframe("2W")
        self.viz.window.update()
        self.viz.load_all_button.invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.active_timeframe, "2W")
        self.assertEqual(len(self.viz._daily_rows), self.total)
        self.assertEqual(len(self.viz.price_data), len(timeframe_rows(self.viz._daily_rows, "2W")))
        self.assertAlmostEqual(self.viz.canvas.xview()[1], 1.0)
        self.assertEqual(self.viz._applied_window, self.viz.data_window_range())
        self.assertEqual(self.viz._applied_window[1], len(self.viz.price_data) - 1)


def long_daily_rows(years: int) -> list:
    """Synthetic daily rows over several years, for windows longer than the fixture."""
    start = datetime.date(2014, 1, 1)
    rows = []
    previous = 1.0
    for offset in range(years * 365):
        day = start + datetime.timedelta(days=offset)
        close = 1.0 + 0.2 * math.sin(offset / 30)
        rows.append([
            [str(day.year), f"{day.month:02d}", f"{day.day:02d}"],
            previous, max(previous, close) + 0.01, min(previous, close) - 0.01, close,
            {"rsi": None},
        ])
        previous = close
    return rows


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class LongHistoryWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": long_daily_rows(12)})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def test_wide_tab_windows_are_centred_on_the_view_with_their_span(self):
        for label, years in (("2W", 4), ("1M", 6)):
            with self.subTest(timeframe=label):
                self.viz.select_timeframe(label)
                self.viz.window.update()
                self.viz.canvas.xview_moveto(0.5)
                self.viz.window.update()
                rows = self.viz.price_data
                first, last = self.viz._applied_window
                self.assertEqual(self.viz._applied_window, self.viz.data_window_range())
                left, right = self.viz.visible_x_range()
                centre = ((left + right) / 2 / self.viz._scale_x - self.viz.chart_padding_x) / self.viz.chart_grid_divider_v
                centre_day = row_ordinal(rows[round(centre)])
                half = years * 365 / 2
                # Sparse rows, so compare against the rows just outside the window too.
                self.assertLessEqual(abs(row_ordinal(rows[first]) - centre_day), half)
                self.assertLessEqual(abs(row_ordinal(rows[last]) - centre_day), half)
                self.assertGreater(abs(row_ordinal(rows[first - 1]) - centre_day), half)
                self.assertGreater(abs(row_ordinal(rows[last + 1]) - centre_day), half)
                self.assertGreater(row_ordinal(rows[last]) - row_ordinal(rows[first]), years * 365 - 365)


if __name__ == "__main__":
    unittest.main()
