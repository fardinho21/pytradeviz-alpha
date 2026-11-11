from __future__ import annotations

import contextlib
import csv
import io
import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Any

from candle import Candle
from indicators import Indicators
from pytradeviz import PyTradeViz


class DrawingCanvas:
    def __init__(self) -> None:
        self.lines = []

    def create_line(self, *coordinates: float, **options: Any) -> None:
        self.lines.append(coordinates)


class ChartBoundsTests(unittest.TestCase):
    def test_price_range_includes_positive_and_negative_extremes(self) -> None:
        viz = PyTradeViz.__new__(PyTradeViz)
        viz.price_data = [[None, 0, 3, -2, 1, {}]]
        viz.calculate_price_range()
        self.assertGreater(viz.price_upper, 3)
        self.assertLess(viz.price_lower, -2)
        price_per_pixel = (viz.price_upper - viz.price_lower) / viz.chart_grid_space_y
        candle = Candle(
            0, 3, -2, 1, 30, price_per_pixel,
            viz.price_upper / price_per_pixel,
        )
        self.assertGreater(candle.render_high, 0)
        self.assertLess(candle.render_low, viz.chart_grid_space_y)

    def test_first_and_last_candles_have_horizontal_margin(self) -> None:
        viz = PyTradeViz.__new__(PyTradeViz)
        data = {"price_data": [None] * 100}
        viz.calculate_grid_space_x(data)
        first = viz.chart_padding_x
        last = first + 99 * viz.chart_grid_divider_v
        self.assertGreater(first - Candle.candle_width, 0)
        self.assertLess(last + Candle.candle_width, viz.chart_grid_space_x)

    def test_indicator_uses_same_horizontal_offset(self) -> None:
        data = [[None, 0, 0, 0, 0, {"rsi": 50}]]
        canvas = DrawingCanvas()
        Indicators(price_data=data).render_RSI(canvas, 30, 30)
        self.assertEqual(canvas.lines, [(30, 100, 30, 50)])

    def test_zero_rsi_is_drawn_and_missing_rsi_is_not(self) -> None:
        data = [
            [None, 0, 0, 0, 0, {"rsi": None}],
            [None, 0, 0, 0, 0, {"rsi": 0}],
        ]
        canvas = DrawingCanvas()
        Indicators(price_data=data).render_RSI(canvas, 30, 30)
        self.assertEqual(canvas.lines, [(30, 100, 60, 100)])


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class TkChartBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        with path.open(newline="") as file:
            rows = list(csv.reader(file))[2:]
        rows.reverse()
        self.price_data = [
            [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]),
             {"rsi": None}]
            for row in rows
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.update()

    def test_sample_data_candles_and_date_labels_are_reachable(self) -> None:
        canvas = self.viz.canvas
        rectangles = [
            item for item in canvas.find_all()
            if canvas.type(item) == "rectangle"
        ]
        self.assertEqual(len(rectangles), len(self.price_data))
        for item in rectangles:
            x1, y1, x2, y2 = canvas.bbox(item)
            self.assertGreater(x1, 0)
            self.assertLess(x2, self.viz.chart_grid_space_x)
            self.assertGreater(y1, 0)
            self.assertLess(y2, self.viz.chart_grid_space_y)

        highest_index = max(
            range(len(self.price_data)), key=lambda i: self.price_data[i][2]
        )
        first_wick = rectangles[0] - 1
        highest_wick = rectangles[highest_index] - 1
        self.assertGreater(canvas.bbox(first_wick)[0], 0)
        self.assertGreater(canvas.bbox(highest_wick)[1], 0)
        dates = self.viz.canvas_date
        text_items = [item for item in dates.find_all() if dates.type(item) == "text"]
        self.assertGreater(dates.bbox(text_items[0])[0], 0)
        self.assertLess(dates.bbox(text_items[-1])[2], self.viz.chart_grid_space_x)
        self.assertAlmostEqual(
            dates.coords(text_items[0])[0], canvas.coords(first_wick)[0]
        )

        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self.viz.window.update()
        self.assertGreaterEqual(canvas.bbox(first_wick)[0], canvas.canvasx(0))
        self.assertGreaterEqual(canvas.bbox(highest_wick)[1], canvas.canvasy(0))
        canvas.xview_moveto(1)
        self.viz.window.update()
        self.assertLessEqual(
            canvas.bbox(rectangles[-1])[2], canvas.canvasx(canvas.winfo_width())
        )
        self.assertLessEqual(
            dates.bbox(text_items[-1])[2], dates.canvasx(dates.winfo_width())
        )

        for _ in range(12):
            self.viz.zoom_chart(SimpleNamespace(
                widget=canvas, x=400, y=250, delta=-120, num=None
            ))
        self.viz.window.update()
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self.viz.window.update()
        self.assertGreaterEqual(canvas.bbox(first_wick)[0], canvas.canvasx(0))
        self.assertGreaterEqual(canvas.bbox(highest_wick)[1], canvas.canvasy(0))
        self.assertGreaterEqual(dates.bbox(text_items[0])[0], dates.canvasx(0))
        canvas.xview_moveto(1)
        self.viz.window.update()
        self.assertLessEqual(
            canvas.bbox(rectangles[-1])[2], canvas.canvasx(canvas.winfo_width())
        )


if __name__ == "__main__":
    unittest.main()
