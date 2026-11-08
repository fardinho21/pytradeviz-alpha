from __future__ import annotations

import contextlib
import copy
import datetime
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

from pytradeviz import PyTradeViz
from indicators import Indicators


def make_rows(
    start: datetime.date, count: int, high: float = 1.0, low: float = 0.5
) -> List[List[Any]]:
    rows = []
    for i in range(count):
        date = start + datetime.timedelta(days=i)
        opening = 0.7
        closing = 0.8 if i % 2 else 0.6
        rows.append([
            [str(date.year), f"{date.month:02}", f"{date.day:02}"],
            opening, high, low, closing, {"rsi": 0, "ema": 0, "sma": 0}
        ])
    return rows


class Source:
    def __init__(self, pages: List[List[List[Any]]]) -> None:
        self.pages = pages

    @property
    def has_more(self) -> bool:
        return bool(self.pages)

    def load_next(self) -> List[List[Any]]:
        return self.pages.pop(0)


class IncrementalIndicatorTests(unittest.TestCase):
    def test_incremental_rsi_matches_full_calculation(self) -> None:
        complete = make_rows(datetime.date(2020, 1, 1), 37)
        expected = copy.deepcopy(complete)
        Indicators(price_data=expected).calculate_RSI_full()
        incremental = copy.deepcopy(complete[:4])
        indicator = Indicators(price_data=incremental)
        indicator.calculate_RSI_incremental()
        for start, end in ((4, 9), (9, 14), (14, 37)):
            incremental.extend(copy.deepcopy(complete[start:end]))
            indicator.calculate_RSI_incremental()
        self.assertEqual(
            [row[5]["rsi"] for row in incremental],
            [row[5]["rsi"] for row in expected],
        )

    def test_rsi_handles_short_and_only_rising_data(self) -> None:
        data = make_rows(datetime.date(2020, 1, 1), 3)
        indicator = Indicators(price_data=data)
        indicator.calculate_RSI_incremental()
        for row in data:
            row[4] = 0.8
        data.extend(make_rows(datetime.date(2020, 1, 4), 4))
        for row in data:
            row[4] = 0.8
        indicator.calculate_RSI_incremental()
        self.assertEqual(data[6][5]["rsi"], 100)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class PaginationChartTests(unittest.TestCase):
    def setUp(self) -> None:
        initial = make_rows(datetime.date(2020, 1, 1), 365)
        page = make_rows(datetime.date(2020, 12, 31), 90, high=3.0, low=-0.5)
        self.source = Source([page])
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(
                tk, ttk, {"price_data": initial}, data_source=self.source
            )
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1400x900")
        self.viz.window.update()

    def test_append_after_zoom_preserves_chart_and_extends_bounds(self) -> None:
        viz = self.viz
        canvas = viz.canvas
        viz.zoom_chart(SimpleNamespace(widget=canvas, x=300, y=250, delta=120, num=None))
        viz.window.update()
        canvas.xview_moveto(0.3)
        viz.window.update()
        old_left = canvas.canvasx(0)
        old_width = viz.chart_grid_space_x
        original_candles = tuple(canvas.find_withtag("candle"))
        original_rsi = tuple(viz.canvas_indicators.find_withtag("rsi"))
        first_rectangle = next(i for i in original_candles if canvas.type(i) == "rectangle")
        old_y = canvas.coords(first_rectangle)[1]
        viz.load_more_button.invoke()
        viz.window.update()

        self.assertEqual(len(viz.price_data), 455)
        self.assertGreater(viz.chart_grid_space_x, old_width)
        self.assertGreater(viz.price_upper, 3.0)
        self.assertLess(viz.price_lower, -0.5)
        self.assertTrue(viz.load_more_button.instate(["disabled"]))
        self.assertEqual(tuple(canvas.find_withtag("candle"))[:len(original_candles)], original_candles)
        current_rsi = tuple(viz.canvas_indicators.find_withtag("rsi"))
        self.assertEqual(current_rsi[:len(original_rsi)], original_rsi)
        self.assertGreater(len(current_rsi), len(original_rsi))
        previous_line = viz.canvas_indicators.coords(original_rsi[-1])
        first_new_line = viz.canvas_indicators.coords(current_rsi[len(original_rsi)])
        self.assertAlmostEqual(previous_line[2], first_new_line[0])
        self.assertAlmostEqual(previous_line[3], first_new_line[1])
        self.assertNotEqual(canvas.coords(first_rectangle)[1], old_y)
        expected_open_y = (
            (viz.price_upper - viz.price_data[0][1])
            / (viz.price_upper - viz.price_lower) * viz.chart_grid_space_y
        )
        self.assertAlmostEqual(canvas.coords(first_rectangle)[1], expected_open_y)
        price_label = viz.canvas_price.find_withtag("price_label")[0]
        self.assertEqual(
            viz.canvas_price.itemcget(price_label, "text"),
            f"{viz.price_upper:.2f}",
        )
        self.assertAlmostEqual(canvas.canvasx(0), old_left, delta=3)
        self.assertAlmostEqual(canvas.canvasx(0), viz.canvas_date.canvasx(0), delta=3)
        self.assertAlmostEqual(canvas.canvasy(0), viz.canvas_price.canvasy(0), delta=3)
        last_wick = canvas.find_withtag("candle")[-2]
        x, high_y, _, low_y = canvas.coords(last_wick)
        self.assertGreater(x, old_width)
        self.assertGreater(high_y, 0)
        self.assertLess(low_y, viz.chart_grid_space_y)
        self.assertAlmostEqual(
            x, (viz.chart_padding_x + 454 * viz.chart_grid_divider_v) * viz._scale_x
        )
        grid = canvas.find_withtag("horizontal_grid")
        self.assertTrue(grid)
        self.assertAlmostEqual(canvas.coords(grid[0])[2], viz.chart_grid_space_x)

    def test_button_is_disabled_when_source_is_exhausted(self) -> None:
        self.viz.load_more_button.invoke()
        size = len(self.viz.price_data)
        self.viz.load_more_button.invoke()
        self.assertEqual(len(self.viz.price_data), size)

    def test_load_error_is_visible_and_keeps_existing_chart(self) -> None:
        size = len(self.viz.price_data)
        with patch.object(self.source, "load_next", side_effect=OSError("read failed")):
            with patch("pytradeviz.messagebox.showerror") as showerror:
                self.viz.load_more_data()
        showerror.assert_called_once()
        self.assertIn("read failed", showerror.call_args.args[1])
        self.assertEqual(len(self.viz.price_data), size)
        self.assertFalse(self.viz.load_more_button.instate(["disabled"]))

    def test_calendar_labels_continue_across_page_boundary(self) -> None:
        self.viz.load_more_button.invoke()
        dates = self.viz.canvas_date
        x = (
            self.viz.chart_padding_x + 366 * self.viz.chart_grid_divider_v
        ) * self.viz._scale_x
        year_labels = [
            item for item in dates.find_all()
            if dates.type(item) == "text"
            and dates.itemcget(item, "text") == "Y21"
        ]
        self.assertEqual(len(year_labels), 1)
        self.assertAlmostEqual(dates.coords(year_labels[0])[0], x)

    def test_multiple_pages_preserve_existing_canvas_items(self) -> None:
        extra = make_rows(datetime.date(2021, 3, 31), 10, high=4.0)
        self.source.pages.append(extra)
        self.viz.load_more_button.invoke()
        first_page_items = self.viz.canvas.find_withtag("candle")
        self.assertFalse(self.viz.load_more_button.instate(["disabled"]))
        self.viz.load_more_button.invoke()
        self.assertEqual(len(self.viz.price_data), 465)
        self.assertEqual(
            self.viz.canvas.find_withtag("candle")[:len(first_page_items)],
            first_page_items,
        )
        self.assertGreater(self.viz.price_upper, 4)
        self.assertTrue(self.viz.load_more_button.instate(["disabled"]))

    def test_resize_and_zoom_after_loading_keep_new_candles_reachable(self) -> None:
        viz = self.viz
        viz.load_more_button.invoke()
        viz.window.update()
        viz.window.geometry("1600x1000")
        viz.window.update()
        for _ in range(10):
            viz.zoom_chart(SimpleNamespace(
                widget=viz.canvas, x=400, y=250, delta=-120, num=None
            ))
        viz.window.update()
        viz.canvas.xview_moveto(1)
        viz.window.update()
        last_candle = viz.canvas.find_withtag("candle")[-1]
        self.assertLessEqual(
            viz.canvas.bbox(last_candle)[2],
            viz.canvas.canvasx(viz.canvas.winfo_width()),
        )
        self.assertAlmostEqual(
            viz.canvas.canvasx(0), viz.canvas_date.canvasx(0), delta=3
        )

    def test_load_page_after_candle_height_scaling(self) -> None:
        viz = self.viz
        canvas = viz.canvas
        for _ in range(5):
            viz.scale_candle_height(SimpleNamespace(
                widget=canvas, y=250, delta=120, num=None
            ))
        viz.window.update()
        height_scale = viz.candle_height_scale
        viz.load_more_button.invoke()
        viz.window.update()
        self.assertAlmostEqual(viz.candle_height_scale, height_scale)
        last_wick = canvas.find_withtag("candle")[-2]
        x, high_y, _, low_y = canvas.coords(last_wick)
        self.assertAlmostEqual(
            high_y,
            (viz.price_upper - viz.price_data[-1][2])
            / (viz.price_upper - viz.price_lower) * viz.chart_grid_space_y,
        )
        self.assertAlmostEqual(
            low_y,
            (viz.price_upper - viz.price_data[-1][3])
            / (viz.price_upper - viz.price_lower) * viz.chart_grid_space_y,
        )
        self.assertLess(x, viz.chart_grid_space_x)
        self.assertAlmostEqual(
            canvas.canvasy(0), viz.canvas_price.canvasy(0), delta=2
        )

    def test_short_initial_data_renders_first_rsi_when_page_arrives(self) -> None:
        initial = make_rows(datetime.date(2020, 1, 1), 3)
        next_rows = make_rows(datetime.date(2020, 1, 4), 8)
        viz = PyTradeViz(
            tk, ttk, {"price_data": initial}, data_source=Source([next_rows])
        )
        self.addCleanup(viz.window.destroy)
        viz.window.update()
        self.assertFalse(viz.canvas_indicators.find_withtag("rsi"))
        viz.load_more_button.invoke()
        viz.window.update()
        self.assertTrue(viz.canvas_indicators.find_withtag("rsi"))


if __name__ == "__main__":
    unittest.main()
