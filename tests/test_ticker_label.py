from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from typing import Any, List, Optional

from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz

AMZN_PATH = Path(__file__).resolve().parents[1] / "data" / "AMZN_10_year_OHLC.csv"


class NoTickerSource:
    has_more = False
    ticker: Optional[str] = None

    def load_next(self) -> List[List[Any]]:
        return []


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class TickerLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": []})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def show(self, source: PaginatedPriceData) -> None:
        self.viz.replace_price_data(source.load_initial(), source)
        self.viz.window.update()

    def test_label_shows_the_file_ticker_and_last_candle_close_at_top_left(self) -> None:
        source = PaginatedPriceData(AMZN_PATH, require_named_columns=True)
        self.show(source)
        expected_close = self.viz.price_data[-1][4]
        self.assertEqual(self.viz.ticker_label.cget("text"), f"AMZN  {expected_close:.8g}")
        placement = self.viz.ticker_label.place_info()
        self.assertEqual((placement["x"], placement["y"], placement["anchor"]), ("0", "0", "nw"))

    def test_label_follows_the_last_candle_loaded(self) -> None:
        source = PaginatedPriceData(AMZN_PATH, require_named_columns=True)
        self.show(source)
        self.viz.load_more_data()
        expected_close = self.viz.price_data[-1][4]
        self.assertEqual(self.viz.ticker_label.cget("text"), f"AMZN  {expected_close:.8g}")

    def test_label_shows_only_the_price_when_the_file_names_no_ticker(self) -> None:
        rows = [[["2024", "01", "02"], 1.0, 3.0, 0.5, 2.5, {"rsi": None}]]
        self.viz.replace_price_data(rows, NoTickerSource())
        self.viz.window.update()
        self.assertEqual(self.viz.ticker_label.cget("text"), "2.5")

    def test_label_is_hidden_when_the_data_is_closed(self) -> None:
        self.show(PaginatedPriceData(AMZN_PATH, require_named_columns=True))
        self.viz.close_data_file()
        self.viz.window.update()
        self.assertFalse(self.viz.ticker_label.place_info())


if __name__ == "__main__":
    unittest.main()
