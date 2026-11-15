from __future__ import annotations

import contextlib
import io
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, List

from drawings import LINE, SOLID, Drawing
from indicators import SMA_PERIODS, default_indicator_settings
from pytradeviz import PyTradeViz
from test_roi import load_price_rows
from timeframes import DAILY


class ResetTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def descendants(self, widget: tk.Misc, cls: type) -> List[Any]:
        found: List[Any] = []
        for child in widget.winfo_children():
            if isinstance(child, cls):
                found.append(child)
            found.extend(self.descendants(child, cls))
        return found

    def find_button(self, window: tk.Misc, text: str) -> tk.Button:
        return next(b for b in self.descendants(window, tk.Button) if b.cget("text") == text)

    def open_reset_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_reset_window(tk)
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
        self.addCleanup(window.destroy)
        return window

    def change_everything(self) -> None:
        """Move every indicator, drawing and mode away from its default on the daily tab."""
        viz = self.viz
        rsi = dict(viz.indicator_settings["RSI"], period=9)
        viz.apply_indicator_settings("RSI", rsi)
        viz.sma_applied[SMA_PERIODS[0]]["enabled"] = True
        viz.bollinger_applied = {**viz.bollinger_applied, "enabled": True}
        viz.trend_applied = {**viz.trend_applied, "enabled": True}
        viz.levels_applied["windows"]["1M"]["enabled"] = True
        viz.drawings = (Drawing(id=1, kind=LINE, style=SOLID, color="Blue", filled=False,
                                start=(2.0, 100.0), end=(5.0, 100.0)),)
        viz.indicator_mode = "ADX"
        viz.draw_overlays()
        viz.window.update()

    def test_the_menu_bar_has_a_reset_entry_after_data(self) -> None:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        labels = [menu_bar.entrycget(i, "label") for i in range(menu_bar.index("end") + 1)]
        self.assertEqual(labels, ["File", "Indicators", "Strategies", "Data", "Reset"])

    def test_the_reset_entry_opens_a_confirmation_modal(self) -> None:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        before = set(self.viz.window.winfo_children())
        menu_bar.invoke(4)
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
        self.addCleanup(window.destroy)
        self.assertEqual(window.title(), "Reset")
        self.find_button(window, "Confirm")
        self.find_button(window, "Cancel")

    def test_cancel_changes_nothing(self) -> None:
        self.change_everything()
        window = self.open_reset_window()
        self.find_button(window, "Cancel").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.indicator_settings["RSI"]["period"], 9)
        self.assertTrue(self.viz.sma_applied[SMA_PERIODS[0]]["enabled"])
        self.assertTrue(self.viz.trend_applied["enabled"])
        self.assertEqual(len(self.viz.drawings), 1)
        self.assertEqual(self.viz.indicator_mode, "ADX")

    def test_confirm_restores_defaults_and_clears_drawings_on_every_tab(self) -> None:
        self.change_everything()
        self.viz.select_timeframe("2W")
        self.change_everything()
        self.viz.select_timeframe(DAILY)
        window = self.open_reset_window()
        rows_before = len(self.viz.price_data)
        self.find_button(window, "Confirm").invoke()
        self.viz.window.update()
        self.assertFalse(window.winfo_exists())

        self.assertEqual(self.viz.indicator_settings, default_indicator_settings())
        self.assertFalse(any(s["enabled"] for s in self.viz.sma_applied.values()))
        self.assertFalse(self.viz.bollinger_applied["enabled"])
        self.assertFalse(self.viz.trend_applied["enabled"])
        self.assertFalse(self.viz.levels_applied["windows"]["1M"]["enabled"])
        self.assertEqual(self.viz.drawings, ())
        self.assertEqual(self.viz.indicator_mode, "RSI")
        self.assertEqual(len(self.viz.price_data), rows_before)

        self.viz.select_timeframe("2W")
        self.assertEqual(self.viz.drawings, ())
        self.assertEqual(self.viz.indicator_settings, default_indicator_settings())
        self.assertFalse(self.viz.trend_applied["enabled"])

    def test_confirm_keeps_the_zoom_level(self) -> None:
        self.viz.zoom_level = 1.0
        self.viz.apply_view_zoom(1.5, 1.0)
        self.viz.window.update()
        self.change_everything()
        window = self.open_reset_window()
        self.find_button(window, "Confirm").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.zoom_level, 1.5)

    def test_reset_without_loaded_data_does_not_fail(self) -> None:
        self.change_everything()
        self.viz.close_data_file()
        self.viz.window.update()
        self.viz.reset_chart_configuration()
        self.viz.window.update()
        self.assertEqual(self.viz.indicator_settings, default_indicator_settings())
        self.assertFalse(self.viz.trend_applied["enabled"])
        self.assertEqual(self.viz.drawings, ())


if __name__ == "__main__":
    unittest.main()
