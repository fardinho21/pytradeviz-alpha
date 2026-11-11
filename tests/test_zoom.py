from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Optional, Tuple

from indicators import SMA_PERIODS
from pytradeviz import PyTradeViz


class CanvasStub:
    def __init__(self, width: int, height: int, region: Tuple[float, float, float, float]) -> None:
        self.width = width
        self.height = height
        self.region = region
        self.left = 0
        self.top = 0
        self.points = [(0.0, 0.0), (float(region[2]), float(region[3]))]

    def winfo_width(self) -> int:
        return self.width

    def winfo_height(self) -> int:
        return self.height

    def canvasx(self, x: float) -> float:
        return self.left + x

    def canvasy(self, y: float) -> float:
        return self.top + y

    def xview(self) -> Tuple[float, int]:
        return (self.left / self.region[2], 0)

    def yview(self) -> Tuple[float, int]:
        return (self.top / self.region[3], 0)

    def xview_moveto(self, fraction: float) -> None:
        self.left = max(0, min(
            fraction * self.region[2], self.region[2] - self.width
        ))

    def yview_moveto(self, fraction: float) -> None:
        self.top = max(0, min(
            fraction * self.region[3], self.region[3] - self.height
        ))

    def scale(
        self, tag: str, origin_x: float, origin_y: float, factor_x: float, factor_y: float
    ) -> None:
        self.points = [
            (origin_x + (x - origin_x) * factor_x,
             origin_y + (y - origin_y) * factor_y)
            for x, y in self.points
        ]

    def configure(self, *, scrollregion: Tuple[float, float, float, float]) -> None:
        self.region = scrollregion
        self.xview_moveto(self.left / self.region[2])
        self.yview_moveto(self.top / self.region[3])


class ZoomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.viz = PyTradeViz.__new__(PyTradeViz)
        self.viz.zoom_level = 1.0
        self.viz._scale_x = 1.0
        self.viz._scale_y = 1.0
        self.viz.chart_grid_space_x = 2000
        self.viz.chart_grid_space_y = 1000
        self.viz.canvas = CanvasStub(900, 500, (0, 0, 2000, 1000))
        self.viz.canvas_price = CanvasStub(100, 500, (0, 0, 100, 1000))
        self.viz.canvas_date = CanvasStub(900, 50, (0, 0, 2000, 50))
        self.viz.canvas_indicators = CanvasStub(900, 100, (0, 0, 2000, 100))
        self.viz.sma_applied = {period: {"enabled": False} for period in SMA_PERIODS}
        self.viz._sma_items = []

    def zoom(
        self, delta: int, widget: Optional[object] = None,
        x: int = 400, y: int = 250, num: Optional[int] = None,
    ) -> str:
        return self.viz.zoom_chart(SimpleNamespace(
            widget=widget or self.viz.canvas, delta=delta, num=num, x=x, y=y
        ))

    def assert_boundaries_match(self) -> None:
        chart = self.viz.canvas
        self.assertAlmostEqual(chart.points[0][0], 0)
        self.assertAlmostEqual(chart.points[0][1], 0)
        self.assertAlmostEqual(chart.points[1][0], self.viz.chart_grid_space_x)
        self.assertAlmostEqual(chart.points[1][1], self.viz.chart_grid_space_y)
        self.assertAlmostEqual(self.viz.canvas_price.points[1][1], chart.points[1][1])
        self.assertAlmostEqual(self.viz.canvas_date.points[1][0], chart.points[1][0])
        self.assertAlmostEqual(self.viz.canvas_indicators.points[1][0], chart.points[1][0])

    def test_zoom_back_out_at_bottom_right_preserves_boundaries(self) -> None:
        for _ in range(25):
            self.zoom(120)
        self.assertEqual(self.viz.zoom_level, self.viz.max_zoom_level)
        self.viz.canvas.xview_moveto(1)
        self.viz.canvas.yview_moveto(1)

        for _ in range(30):
            self.zoom(-120, x=800, y=450)
            self.assert_boundaries_match()

        self.assertEqual(self.viz.zoom_level, self.viz.min_zoom_level)
        self.assertLessEqual(self.viz.canvas.left, self.viz.chart_grid_space_x - 900)
        self.assertLessEqual(
            self.viz.canvas.top, max(0, self.viz.chart_grid_space_y - 500)
        )

    def test_zoom_keeps_pointer_position_away_from_edges(self) -> None:
        self.viz.canvas.xview_moveto(0.25)
        self.viz.canvas.yview_moveto(0.25)
        chart_x = self.viz.canvas.canvasx(400)
        chart_y = self.viz.canvas.canvasy(250)
        self.zoom(120)
        self.assertAlmostEqual(self.viz.canvas.canvasx(400), chart_x * 1.1)
        self.assertAlmostEqual(self.viz.canvas.canvasy(250), chart_y * 1.1)
        self.assert_boundaries_match()

    def test_linux_wheel_and_zoom_on_each_axis(self) -> None:
        for widget in (
            self.viz.canvas, self.viz.canvas_price,
            self.viz.canvas_date, self.viz.canvas_indicators,
        ):
            self.assertEqual(self.zoom(0, widget, x=30, y=30, num=4), "break")
            self.assert_boundaries_match()
            self.assertEqual(self.zoom(0, widget, x=30, y=30, num=5), "break")
            self.assertAlmostEqual(self.viz.zoom_level, 1)
            self.assert_boundaries_match()


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class TkZoomTests(unittest.TestCase):
    def setUp(self) -> None:
        price_data = [
            [["2022", "01", "01"], 0.7, 0.9, 0.6,
             0.8 if i % 2 else 0.65, {"rsi": None}]
            for i in range(60)
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1600x1000")
        self.viz.window.update()

    def zoom(self, delta: int) -> None:
        canvas = self.viz.canvas
        self.viz.zoom_chart(SimpleNamespace(
            widget=canvas, x=canvas.winfo_width() // 2,
            y=canvas.winfo_height() // 2, delta=delta, num=None
        ))
        self.viz.window.update()

    def test_zoom_out_after_scrolling_to_bottom(self) -> None:
        canvas = self.viz.canvas
        first_grid_line = canvas.find_all()[0]
        for _ in range(25):
            self.zoom(120)
        canvas.xview_moveto(1)
        canvas.yview_moveto(1)
        self.viz.window.update()
        for _ in range(30):
            self.zoom(-120)

        x1, y1, x2, y2 = canvas.coords(first_grid_line)
        self.assertAlmostEqual(x1, 0)
        self.assertAlmostEqual(x2, 0)
        self.assertAlmostEqual(y1, 0)
        self.assertAlmostEqual(y2, self.viz.chart_grid_space_y)
        self.assertLess(canvas.canvasx(0), self.viz.chart_grid_space_x)
        self.assertLess(canvas.canvasy(0), self.viz.chart_grid_space_y)
        self.assertAlmostEqual(
            canvas.canvasx(0), self.viz.canvas_date.canvasx(0), delta=2
        )
        self.assertAlmostEqual(
            canvas.canvasy(0), self.viz.canvas_price.canvasy(0), delta=2
        )

    def test_ctrl_wheel_binding_and_resize_after_zoom(self) -> None:
        canvas = self.viz.canvas
        canvas.xview_moveto(0.25)
        canvas.yview_moveto(0.25)
        self.viz.window.update()
        x, y = 400, 250
        original_x, original_y = canvas.canvasx(x), canvas.canvasy(y)
        canvas.event_generate("<Control-Button-4>", x=x, y=y)
        self.viz.window.update()
        self.assertAlmostEqual(self.viz.zoom_level, 1.1)
        self.assertAlmostEqual(canvas.canvasx(x), original_x * 1.1, delta=2)
        self.assertAlmostEqual(canvas.canvasy(y), original_y * 1.1, delta=2)

        self.viz.window.geometry("1200x800")
        self.viz.window.update()
        canvas.xview_moveto(1)
        canvas.yview_moveto(1)
        self.viz.window.update()
        for _ in range(20):
            self.zoom(-120)

        first_grid_line = canvas.find_all()[0]
        x1, y1, x2, y2 = canvas.coords(first_grid_line)
        self.assertAlmostEqual(x1, 0)
        self.assertAlmostEqual(y1, 0)
        self.assertAlmostEqual(x2, 0)
        self.assertAlmostEqual(y2, self.viz.chart_grid_space_y)
        self.assertLess(canvas.canvasx(0), self.viz.chart_grid_space_x)
        self.assertLess(canvas.canvasy(0), self.viz.chart_grid_space_y)
        self.assertAlmostEqual(
            canvas.canvasx(0), self.viz.canvas_indicators.canvasx(0), delta=2
        )
        self.assertAlmostEqual(
            canvas.canvasy(0), self.viz.canvas_price.canvasy(0), delta=2
        )


if __name__ == "__main__":
    unittest.main()
