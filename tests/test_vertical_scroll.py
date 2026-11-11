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

from pytradeviz import PyTradeViz


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class VerticalScrollStartTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        with path.open(newline="") as file:
            rows = list(csv.reader(file))[2:]
        rows.reverse()
        price_data = [
            [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]),
             {"rsi": None}]
            for row in rows
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.update()

    def test_vertical_thumb_starts_centered(self) -> None:
        first, last = self.viz.canvas.yview()
        self.assertAlmostEqual((first + last) / 2, 0.5, delta=0.01)
        self.assertGreater(first, 0)
        self.assertLess(last, 1)

    def test_scrollbar_reflects_centered_view(self) -> None:
        first, last = (float(v) for v in self.viz.scrollbar_vertical.get())
        self.assertAlmostEqual((first + last) / 2, 0.5, delta=0.01)


if __name__ == "__main__":
    unittest.main()
