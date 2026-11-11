from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List

from indicators import HIGH_COLUMN, LOW_COLUMN, Indicators
from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


def make_rows(closes: List[float]) -> List[List[Any]]:
    return [
        [["2025", "01", f"{day:02d}"], close, close, close, close, {"rsi": None}]
        for day, close in enumerate(closes, start=1)
    ]


class SimpleMovingAverageCalculationTests(unittest.TestCase):
    def test_average_of_closes_with_warm_up_rows(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3, 4, 5]))
        self.assertEqual(indicators.calculate_SMA(3), [None, None, 2.0, 3.0, 4.0])

    def test_period_of_one_returns_the_closes(self) -> None:
        indicators = Indicators(price_data=make_rows([5, 6, 7]))
        self.assertEqual(indicators.calculate_SMA(1), [5.0, 6.0, 7.0])

    def test_new_rows_are_appended_to_the_cached_values(self) -> None:
        rows = make_rows([1, 2, 3])
        indicators = Indicators(price_data=rows)
        self.assertEqual(indicators.calculate_SMA(2), [None, 1.5, 2.5])
        rows.extend(make_rows([10]))
        self.assertEqual(indicators.calculate_SMA(2), [None, 1.5, 2.5, 6.5])

    def test_high_and_low_columns_are_averaged_separately(self) -> None:
        rows = [
            [["2025", "01", "01"], 1, 10, 0, 5, {"rsi": None}],
            [["2025", "01", "02"], 2, 20, 4, 6, {"rsi": None}],
            [["2025", "01", "03"], 3, 30, 8, 7, {"rsi": None}],
        ]
        indicators = Indicators(price_data=rows)
        self.assertEqual(indicators.calculate_SMA(2, HIGH_COLUMN), [None, 15.0, 25.0])
        self.assertEqual(indicators.calculate_SMA(2, LOW_COLUMN), [None, 2.0, 6.0])
        self.assertEqual(indicators.calculate_SMA(2), [None, 5.5, 6.5])

    def test_new_price_data_resets_the_cache(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2, 3]))
        indicators.calculate_SMA(2)
        indicators.set_price_data(make_rows([4, 6]))
        self.assertEqual(indicators.calculate_SMA(2), [None, 5.0])

    def test_zero_period_is_rejected(self) -> None:
        indicators = Indicators(price_data=make_rows([1, 2]))
        with self.assertRaises(ValueError):
            indicators.calculate_SMA(0)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class SimpleMovingAverageWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def open_simple_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_moving_average_window(tk, "Simple")
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
        return window

    def descendants(self, widget: tk.Misc, cls: type) -> List[Any]:
        found: List[Any] = []
        for child in widget.winfo_children():
            if isinstance(child, cls):
                found.append(child)
            found.extend(self.descendants(child, cls))
        return found

    def find_button(self, window: tk.Misc, text: str) -> tk.Button:
        return next(b for b in self.descendants(window, tk.Button) if b.cget("text") == text)

    def checkbox_for(self, window: tk.Misc, period: int) -> tk.Checkbutton:
        return next(
            c for c in self.descendants(window, tk.Checkbutton)
            if c.master.cget("text") == f"{period}-candle SMA"
        )

    def radio_for(self, window: tk.Misc, period: int, label: str) -> tk.Radiobutton:
        return next(
            r for r in self.descendants(window, tk.Radiobutton)
            if r.master.cget("text") == f"{period}-candle SMA" and r.cget("text") == label
        )

    def sma_items(self, period: int) -> List[int]:
        return list(self.viz.canvas.find_withtag(f"sma_{period}"))

    def candle_line(self, index: int) -> int:
        return next(i for i in self.viz.canvas.find_withtag(f"candle_{index}")
                    if self.viz.canvas.type(i) == "line")

    def test_simple_window_has_a_checkbox_and_radio_groups_per_period(self) -> None:
        window = self.open_simple_window()
        self.assertEqual(len(self.descendants(window, tk.Checkbutton)), 8)
        self.assertEqual(len(self.descendants(window, tk.Radiobutton)), 4 * (3 + 5))
        titles = [f.cget("text") for f in self.descendants(window, tk.LabelFrame)]
        self.assertEqual(titles, ["3-candle SMA", "7-candle SMA", "14-candle SMA", "30-candle SMA"])

    def test_exponential_window_stays_empty(self) -> None:
        self.viz.open_moving_average_window(tk, "Exponential")
        self.viz.window.update()
        exponential = [w for w in self.viz.window.winfo_children()
                       if isinstance(w, tk.Toplevel) and w.title() == "Exponential"]
        self.assertEqual(len(exponential), 1)
        self.assertEqual(self.descendants(exponential[0], tk.Checkbutton), [])

    def test_changes_apply_only_after_apply_is_pressed(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 3).invoke()
        self.viz.window.update()
        self.assertEqual(self.sma_items(3), [])

        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertEqual(len(self.sma_items(3)), 1)

    def test_line_has_one_point_per_valid_candle_and_aligns_with_candles(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 3).invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

        canvas = self.viz.canvas
        (item,) = self.sma_items(3)
        coords = canvas.coords(item)
        self.assertEqual(len(coords), 2 * (len(self.viz.price_data) - 2))
        self.assertAlmostEqual(coords[0], canvas.coords(self.candle_line(2))[0])
        first_close_avg = sum(row[4] for row in self.viz.price_data[:3]) / 3
        self.assertAlmostEqual(coords[1], self.viz.price_to_y(first_close_avg), places=6)

    def test_style_and_color_radio_buttons_restyle_the_line(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 7).invoke()
        self.radio_for(window, 7, "Dotted").invoke()
        self.radio_for(window, 7, "Green").invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

        (item,) = self.sma_items(7)
        self.assertEqual(self.viz.canvas.itemcget(item, "fill"), "#43a047")
        self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "3 3")
        self.assertEqual(float(self.viz.canvas.itemcget(item, "width")), 3.0)

        self.radio_for(window, 7, "Solid").invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        (item,) = self.sma_items(7)
        self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "")
        self.assertEqual(float(self.viz.canvas.itemcget(item, "width")), 2.0)

        self.radio_for(window, 7, "Dashed").invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        (item,) = self.sma_items(7)
        self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "6 4")
        self.assertEqual(float(self.viz.canvas.itemcget(item, "width")), 2.0)

    def hi_lo_items(self) -> List[int]:
        return list(self.viz.canvas.find_withtag("sma_hi_lo"))

    def hi_lo_checkbox_for(self, window: tk.Misc, period: int) -> tk.Checkbutton:
        return next(b for b in self.descendants(window, tk.Checkbutton)
                    if b.cget("text") == "Show Hi-Low MA"
                    and b.master is self.checkbox_for(window, period).master)

    def test_hi_lo_checkbox_draws_an_x_per_high_and_low_point(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 3).invoke()
        self.hi_lo_checkbox_for(window, 3).invoke()
        self.radio_for(window, 3, "Orange").invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

        canvas = self.viz.canvas
        left, right = canvas.canvasx(0), canvas.canvasx(canvas.winfo_width())
        visible_points = sum(
            1 for i in range(2, len(self.viz.price_data))
            if left - 1 <= self.viz.candle_x(i) <= right + 1
        )
        items = self.hi_lo_items()
        self.assertEqual(len(items), 2 * 2 * visible_points)
        self.assertLess(len(items), 2 * 2 * (len(self.viz.price_data) - 2))
        for item in items:
            self.assertEqual(self.viz.canvas.itemcget(item, "fill"), "#fb8c00")
            self.assertEqual(float(self.viz.canvas.itemcget(item, "width")), 1.0)
        x1, y1, x2, y2 = self.viz.canvas.coords(items[0])
        self.assertAlmostEqual(abs(x2 - x1), 6)
        self.assertAlmostEqual(abs(y2 - y1), 6)

    def test_hi_lo_markers_need_show_and_follow_the_checkbox(self) -> None:
        window = self.open_simple_window()
        self.hi_lo_checkbox_for(window, 3).invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertEqual(self.hi_lo_items(), [])

        self.checkbox_for(window, 3).invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertNotEqual(self.hi_lo_items(), [])

        self.hi_lo_checkbox_for(window, 3).invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertEqual(self.hi_lo_items(), [])

    def test_unchecked_periods_are_removed(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 14).invoke()
        self.find_button(window, "Apply").invoke()
        self.checkbox_for(window, 14).invoke()
        self.find_button(window, "Apply").invoke()
        self.assertEqual(self.sma_items(14), [])

    def test_lines_follow_zoom_and_dark_mode(self) -> None:
        window = self.open_simple_window()
        self.checkbox_for(window, 3).invoke()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

        canvas = self.viz.canvas
        event = SimpleNamespace(delta=120, widget=canvas, x=100, y=100)
        self.viz.zoom_chart(event)
        self.viz.window.update()
        (item,) = self.sma_items(3)
        self.assertAlmostEqual(canvas.coords(item)[0], canvas.coords(self.candle_line(2))[0])

        self.viz.toggle_dark_mode()
        self.viz.window.update()
        self.assertEqual(len(self.sma_items(3)), 1)

    def test_lines_extend_after_loading_more_data(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        source = PaginatedPriceData(path)
        with contextlib.redirect_stdout(io.StringIO()):
            viz = PyTradeViz(tk, ttk, {"price_data": source.load_initial()}, data_source=source)
        self.addCleanup(viz.window.destroy)
        viz.window.update()
        viz.sma_applied[30] = {"enabled": True, "hi_lo": False, "style": "Solid", "color": "Violet"}
        viz.draw_overlays()

        viz.load_more_button.invoke()
        viz.window.update()
        (item,) = viz.canvas.find_withtag("sma_30")
        coords = viz.canvas.coords(item)
        self.assertEqual(len(coords), 2 * (len(viz.price_data) - 29))
        last_index = len(viz.price_data) - 1
        last_line = next(i for i in viz.canvas.find_withtag(f"candle_{last_index}")
                         if viz.canvas.type(i) == "line")
        self.assertAlmostEqual(coords[-2], viz.canvas.coords(last_line)[0])

    def test_close_button_closes_the_window(self) -> None:
        window = self.open_simple_window()
        self.find_button(window, "Close").invoke()
        self.viz.window.update()
        self.assertFalse(window.winfo_exists())


if __name__ == "__main__":
    unittest.main()
