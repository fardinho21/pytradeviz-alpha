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
from typing import Any, List, Tuple

from pytradeviz import PyTradeViz


class FakeSource:
    def __init__(self, rows: List[List[Any]], batch_size: int = 100) -> None:
        self.rows = rows
        self.batch_size = batch_size

    @property
    def has_more(self) -> bool:
        return bool(self.rows)

    def load_next(self) -> List[List[Any]]:
        batch, self.rows = self.rows[:self.batch_size], self.rows[self.batch_size:]
        return batch


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[2:]
    rows.reverse()
    return [
        [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]), {"rsi": None}]
        for row in rows
    ]


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class DarkModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def candle_items(self) -> Tuple[List[int], List[int]]:
        canvas = self.viz.canvas
        items = canvas.find_withtag("candle")
        bodies = [i for i in items if canvas.type(i) == "rectangle"]
        wicks = [i for i in items if canvas.type(i) == "line"]
        return bodies, wicks

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.viz.canvas.bbox(f"candle_{index}")
        return (x1 + x2) / 2, (y1 + y2) / 2

    def click(self, x: float, y: float) -> None:
        canvas = self.viz.canvas
        event = SimpleNamespace(
            widget=canvas,
            x=int(x - canvas.canvasx(0)),
            y=int(y - canvas.canvasy(0)),
        )
        self.viz.scroll_start(event)
        self.viz.select_candle(event)

    def test_toggle_inverts_background_and_ink(self) -> None:
        self.viz.dark_mode_button.invoke()

        self.assertEqual(self.viz.window.cget("bg"), "black")
        for canvas in (
            self.viz.canvas, self.viz.canvas_price,
            self.viz.canvas_date, self.viz.canvas_indicators,
        ):
            self.assertEqual(canvas.cget("background"), "black")
            for item in canvas.find_withtag("ink"):
                self.assertEqual(canvas.itemcget(item, "fill"), "white")
            for item in canvas.find_withtag("grid"):
                self.assertEqual(canvas.itemcget(item, "fill"), "#4a4a4a")
        self.assertEqual(self.viz.candle_info_label.cget("bg"), "black")
        self.assertEqual(self.viz.candle_info_label.cget("fg"), "white")

        self.viz.dark_mode_button.invoke()

        self.assertEqual(self.viz.window.cget("bg"), "black")
        for canvas in (
            self.viz.canvas, self.viz.canvas_price,
            self.viz.canvas_date, self.viz.canvas_indicators,
        ):
            self.assertEqual(canvas.cget("background"), "white")
            for item in canvas.find_withtag("ink"):
                self.assertEqual(canvas.itemcget(item, "fill"), "black")
            for item in canvas.find_withtag("grid"):
                self.assertEqual(canvas.itemcget(item, "fill"), "black")

    def test_candles_are_hollow_in_dark_mode_and_keep_colors(self) -> None:
        bodies, wicks = self.candle_items()
        light_colors = (
            [self.viz.canvas.itemcget(i, "fill") for i in bodies],
            [self.viz.canvas.itemcget(i, "fill") for i in wicks],
        )

        self.viz.toggle_dark_mode()
        canvas = self.viz.canvas
        bodies, wicks = self.candle_items()
        self.assertTrue(all(canvas.itemcget(i, "fill") == canvas.cget("background") for i in bodies))
        self.assertEqual(
            [canvas.itemcget(i, "outline") for i in bodies], light_colors[0]
        )
        self.assertEqual(
            [canvas.itemcget(i, "fill") for i in wicks], light_colors[1]
        )
        self.assertTrue(set(light_colors[0]) <= {"green", "red", "grey"})

        self.viz.toggle_dark_mode()
        bodies, _ = self.candle_items()
        self.assertEqual(
            [canvas.itemcget(i, "fill") for i in bodies], light_colors[0]
        )
        self.assertTrue(all(canvas.itemcget(i, "outline") == "black" for i in bodies))

    def test_clicking_candle_works_in_dark_mode(self) -> None:
        self.viz.toggle_dark_mode()
        self.click(*self.candle_center(10))
        date, open_, high, low, close = self.price_data[10][:5]
        self.assertEqual(
            self.viz.candle_info_label.cget("text"),
            f"{'-'.join(date)}\nO: {open_}\nH: {high}\nL: {low}\nC: {close}",
        )

    def test_candles_loaded_in_dark_mode_are_hollow(self) -> None:
        source = FakeSource(self.price_data[100:200], batch_size=100)
        with contextlib.redirect_stdout(io.StringIO()):
            viz = PyTradeViz(
                tk, ttk, {"price_data": self.price_data[:100]}, data_source=source,
            )
        self.addCleanup(viz.window.destroy)
        viz.window.update()
        self.viz = viz

        self.viz.toggle_dark_mode()
        self.viz.load_more_button.invoke()
        self.viz.window.update()

        canvas = self.viz.canvas
        bodies, wicks = self.candle_items()
        self.assertEqual(len(bodies), 200)
        self.assertTrue(all(canvas.itemcget(i, "fill") == canvas.cget("background") for i in bodies))
        for c in (self.viz.canvas_date, self.viz.canvas_indicators, canvas):
            grid_items = c.find_withtag("grid")
            self.assertTrue(grid_items)
            self.assertTrue(all(c.itemcget(i, "fill") == "#4a4a4a" for i in grid_items))
            ink_items = c.find_withtag("ink")
            self.assertTrue(all(c.itemcget(i, "fill") == "white" for i in ink_items))
