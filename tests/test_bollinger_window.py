from __future__ import annotations

import contextlib
import io
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, List

from pytradeviz import PyTradeViz
from test_roi import load_price_rows


class BollingerWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def open_bollinger_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_bollinger_window(tk)
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
        self.addCleanup(window.destroy)
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

    def control_variables(self, window: tk.Misc) -> dict:
        # Tk variables are looked up by the name the checkbox and radio buttons use.
        show = next(c for c in self.descendants(window, tk.Checkbutton)
                    if c.cget("text") == "Show")
        style = next(r for r in self.descendants(window, tk.Radiobutton)
                     if r.cget("text") == "Dashed")
        color = next(r for r in self.descendants(window, tk.Radiobutton)
                     if r.cget("text") == "Red")
        return {
            "enabled": tk.BooleanVar(window, name=str(show.cget("variable"))),
            "style": tk.StringVar(window, name=str(style.cget("variable"))),
            "color": tk.StringVar(window, name=str(color.cget("variable"))),
        }

    def bollinger_items(self, name: str) -> List[int]:
        return list(self.viz.canvas.find_withtag(f"bollinger_{name}"))

    def test_indicators_bollinger_menu_opens_the_window(self) -> None:
        self.viz.open_bollinger_window(tk)
        self.viz.window.update()
        titles = [w.title() for w in self.viz.window.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertIn("Bollinger Bands", titles)
        for window in self.viz.window.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.destroy()

    def test_apply_draws_three_bands_with_the_chosen_style(self) -> None:
        window = self.open_bollinger_window()
        variables = self.control_variables(window)
        variables["enabled"].set(True)
        variables["style"].set("Dashed")
        variables["color"].set("Red")
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        for name in ("middle", "upper", "lower"):
            self.assertTrue(self.bollinger_items(name), name)
        upper = self.bollinger_items("upper")[0]
        self.assertEqual(self.viz.canvas.itemcget(upper, "fill"), self.viz.sma_colors["Red"])
        self.assertEqual(self.viz.canvas.itemcget(upper, "dash"), "6 4")

    def test_nothing_is_drawn_until_shown(self) -> None:
        window = self.open_bollinger_window()
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertEqual(self.bollinger_items("middle"), [])

    def test_hiding_removes_the_bands(self) -> None:
        window = self.open_bollinger_window()
        variables = self.control_variables(window)
        variables["enabled"].set(True)
        self.find_button(window, "Apply").invoke()
        variables["enabled"].set(False)
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertEqual(self.bollinger_items("upper"), [])

    def test_showing_bands_expands_the_price_scale_to_cover_them(self) -> None:
        self.viz.bollinger_applied["enabled"] = False
        self.viz.calculate_price_range()
        without_bands = (self.viz.price_upper, self.viz.price_lower)
        self.viz.bollinger_applied["enabled"] = True
        self.viz.calculate_price_range()
        band_low, band_high = self.viz.indicators_object.bollinger_range()
        self.assertGreaterEqual(self.viz.price_upper, band_high)
        self.assertLessEqual(self.viz.price_lower, band_low)
        self.assertGreaterEqual(self.viz.price_upper, without_bands[0])
        self.assertLessEqual(self.viz.price_lower, without_bands[1])

    def test_hiding_bands_returns_the_price_scale(self) -> None:
        self.viz.bollinger_applied["enabled"] = False
        self.viz.calculate_price_range()
        without_bands = (self.viz.price_upper, self.viz.price_lower)
        window = self.open_bollinger_window()
        variables = self.control_variables(window)
        variables["enabled"].set(True)
        self.find_button(window, "Apply").invoke()
        variables["enabled"].set(False)
        self.find_button(window, "Apply").invoke()
        self.assertEqual((self.viz.price_upper, self.viz.price_lower), without_bands)

    def test_labeled_candles_store_bollinger_values(self) -> None:
        self.viz.save_labeled_selection("bands", {25})
        record = self.viz.labeled_selections["bands"][0]
        middle, upper, lower = self.viz.indicators_object.calculate_bollinger()
        self.assertEqual(record["bollinger_middle"], middle[25])
        self.assertEqual(record["bollinger_upper"], upper[25])
        self.assertEqual(record["bollinger_lower"], lower[25])


if __name__ == "__main__":
    unittest.main()
