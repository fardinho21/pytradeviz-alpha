from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

from pytradeviz import PyTradeViz


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[2:]
    rows.reverse()
    return [
        [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]), {"rsi": 0}]
        for row in rows
    ]


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class CrosshairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def crosshair_items(self, canvas: tk.Canvas, kind: Optional[str] = None) -> List[int]:
        return [
            item for item in canvas.find_withtag("crosshair")
            if kind is None or canvas.type(item) == kind
        ]

    def crosshair_text(self, canvas: tk.Canvas) -> List[str]:
        return [canvas.itemcget(item, "text")
                for item in self.crosshair_items(canvas, "text")]

    def point_at_root(self, canvas: tk.Canvas, x: int, y: int) -> SimpleNamespace:
        root_x = canvas.winfo_rootx() + x
        root_y = canvas.winfo_rooty() + y
        return SimpleNamespace(x_root=root_x, y_root=root_y, x=x, y=y,
                               widget=canvas)

    def move_to(self, canvas: tk.Canvas, x: int, y: int) -> None:
        self.viz.track_crosshair(self.point_at_root(canvas, x, y))

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.viz.canvas.bbox(f"candle_{index}")
        return (x1 + x2) / 2, (y1 + y2) / 2

    def column_of_candle(self, index: int) -> Tuple[int, int]:
        canvas = self.viz.canvas
        x, _ = self.candle_center(index)
        return int(x - canvas.canvasx(0)), 200

    def test_motion_event_draws_lines_at_cursor(self) -> None:
        canvas = self.viz.canvas
        x, y = self.column_of_candle(10)
        canvas.event_generate("<Motion>", x=x, y=y)
        self.viz.window.update()
        lines = [canvas.coords(item)
                 for item in self.crosshair_items(canvas, "line")]
        self.assertEqual(len(lines), 2)
        verticals = [line for line in lines if line[0] == line[2]]
        self.assertEqual(len(verticals), 1)
        self.assertAlmostEqual(verticals[0][0], canvas.canvasx(x), delta=1)

    def test_leave_clears_crosshair(self) -> None:
        self.move_to(self.viz.canvas, 200, 200)
        self.assertTrue(self.crosshair_items(self.viz.canvas))
        self.viz.hide_crosshair(None)
        for canvas in (self.viz.canvas, self.viz.canvas_price,
                       self.viz.canvas_date, self.viz.canvas_indicators):
            self.assertEqual(self.crosshair_items(canvas), [])

    def test_date_label_matches_nearest_candle(self) -> None:
        index = 10
        self.move_to(self.viz.canvas, *self.column_of_candle(index))
        self.assertIn("-".join(self.price_data[index][0]),
                      self.crosshair_text(self.viz.canvas))

    def test_no_date_label_outside_candle_range(self) -> None:
        self.assertIsNone(self.viz.date_index_at(-500))
        self.assertIsNone(
            self.viz.date_index_at(
                (self.viz.chart_padding_x
                 + len(self.price_data) * self.viz.chart_grid_divider_v + 500)
                * self.viz._scale_x
            )
        )

    def test_price_label_matches_axis_tick(self) -> None:
        tick = self.viz.canvas_price.find_withtag("price_label")[3]
        tick_text = self.viz.canvas_price.itemcget(tick, "text")
        tick_y = self.viz.canvas_price.coords(tick)[1]
        self.move_to(self.viz.canvas_price, 50, int(tick_y))
        self.assertIn(tick_text, self.crosshair_text(self.viz.canvas_price))

    def test_price_label_sits_at_right_end_of_horizontal_line(self) -> None:
        self.move_to(self.viz.canvas, 200, 200)
        price_canvas = self.viz.canvas_price
        hlines = [
            price_canvas.coords(item)
            for item in self.crosshair_items(price_canvas, "line")
        ]
        self.assertEqual(len(hlines), 1)
        label = self.crosshair_items(price_canvas, "text")[0]
        self.assertEqual(price_canvas.itemcget(label, "anchor"), "e")
        self.assertAlmostEqual(
            price_canvas.coords(label)[0], hlines[0][2], delta=2
        )

    def test_light_and_dark_colors(self) -> None:
        self.move_to(self.viz.canvas, 200, 200)
        canvas = self.viz.canvas
        line = self.crosshair_items(canvas, "line")[0]
        label = self.crosshair_items(canvas, "text")[0]
        self.assertEqual(canvas.itemcget(line, "fill"), "black")
        self.assertEqual(canvas.itemcget(label, "fill"), "white")
        self.viz.toggle_dark_mode()
        line = self.crosshair_items(canvas, "line")[0]
        label = self.crosshair_items(canvas, "text")[0]
        self.assertEqual(canvas.itemcget(line, "fill"), "#f4a261")
        self.assertEqual(canvas.itemcget(label, "fill"), "black")


if __name__ == "__main__":
    unittest.main()
