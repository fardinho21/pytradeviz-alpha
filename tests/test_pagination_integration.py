import calendar
import csv
import datetime
import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from tkinter import ttk

from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz


def add_months(date, months):
    month = date.year * 12 + date.month - 1 + months
    year, month = divmod(month, 12)
    month += 1
    return datetime.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class PaginationIntegrationTests(unittest.TestCase):
    def test_sample_file_initial_year_and_three_month_pages(self):
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        with path.open(newline="") as file:
            dates = [
                datetime.date.fromisoformat(row[1].split()[0])
                for row in list(csv.reader(file))[2:]
            ][::-1]
        source = PaginatedPriceData(path)
        initial = source.load_initial()
        start = dates[0]
        first_end = add_months(start, 12)
        self.assertEqual(len(initial), sum(day < first_end for day in dates))
        viz = PyTradeViz(tk, ttk, {"price_data": initial}, data_source=source)
        self.addCleanup(viz.window.destroy)
        viz.window.update()

        for page in range(1, 4):
            viz.load_more_button.invoke()
            viz.window.update()
            end = add_months(start, 12 + page * 3)
            expected = [day for day in dates if day < end]
            actual = [
                datetime.date(*(int(part) for part in row[0]))
                for row in viz.price_data
            ]
            self.assertEqual(actual, expected)
            self.assertEqual(len(viz.canvas.find_withtag("candle")), 2 * len(expected))
        self.assertTrue(source.has_more)
        while source.has_more:
            viz.load_more_button.invoke()
            viz.window.update()
        self.assertTrue(viz.load_more_button.instate(["disabled"]))
        self.assertEqual(len(viz.price_data), len(dates))
        self.assertEqual(
            len(viz.canvas.find_withtag("candle")), 2 * len(dates)
        )


if __name__ == "__main__":
    unittest.main()
