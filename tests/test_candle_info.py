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
from typing import Tuple

from pytradeviz import PyTradeViz


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class CandleInfoTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        with path.open(newline="") as file:
            rows = list(csv.reader(file))[2:]
        rows.reverse()
        self.price_data = [
            [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]),
             {"rsi": 0}]
            for row in rows
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.viz.canvas.bbox(f"candle_{index}")
        return (x1 + x2) / 2, (y1 + y2) / 2

    def event_at(self, x: float, y: float) -> SimpleNamespace:
        canvas = self.viz.canvas
        return SimpleNamespace(
            widget=canvas,
            x=int(x - canvas.canvasx(0)),
            y=int(y - canvas.canvasy(0)),
        )

    def click(self, x: float, y: float) -> None:
        event = self.event_at(x, y)
        self.viz.scroll_start(event)
        self.viz.select_candle(event)

    def test_clicking_candle_shows_its_date_and_ohlc(self) -> None:
        for index in (10, 200):
            with self.subTest(index=index):
                self.click(*self.candle_center(index))
                date, open_, high, low, close = self.price_data[index][:5]
                self.assertEqual(
                    self.viz.candle_info_label.cget("text"),
                    f"{'-'.join(date)}\nO: {open_}\nH: {high}\nL: {low}\nC: {close}",
                )
                self.assertTrue(self.viz.candle_info_label.place_info())

    def test_drag_does_not_select_a_candle(self) -> None:
        x, y = self.candle_center(10)
        press = self.event_at(x, y)
        release = SimpleNamespace(widget=press.widget, x=press.x + 40, y=press.y)
        self.viz.scroll_start(press)
        self.viz.select_candle(release)
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def test_click_between_candles_selects_nothing(self) -> None:
        x, y = self.candle_center(10)
        self.click(x + 15, y)
        self.assertEqual(self.viz.candle_info_label.place_info(), {})
