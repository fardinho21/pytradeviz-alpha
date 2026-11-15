from __future__ import annotations

import contextlib
import io
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, List
from unittest import mock

from pytradeviz import TREND_SHADE_STRENGTH, PyTradeViz
from test_roi import load_price_rows
from trend import DOWN, SIDEWAYS, UP


class TrendWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def open_trend_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_trend_window(tk)
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

    def entry_for(self, window: tk.Misc, label: str) -> tk.Entry:
        # Each setting is a label followed by an entry in the same grid row.
        labels = [w for w in self.descendants(window, tk.Label) if w.cget("text") == label]
        (label_widget,) = labels
        row = label_widget.grid_info()["row"]
        parent = label_widget.master
        return next(w for w in self.descendants(parent, tk.Entry) if w.grid_info()["row"] == row)

    def shading_fills(self) -> List[str]:
        return [self.viz.canvas.itemcget(item, "fill") for item in self.viz.canvas.find_withtag("trend")]

    def expected_fills(self) -> dict:
        theme = self.viz.get_theme()
        return {
            UP: self.viz.blend_colors(theme["canvas"], theme["gain"], TREND_SHADE_STRENGTH),
            DOWN: self.viz.blend_colors(theme["canvas"], theme["loss"], TREND_SHADE_STRENGTH),
            SIDEWAYS: self.viz.blend_colors(theme["canvas"], theme["grid"], TREND_SHADE_STRENGTH),
        }

    def test_the_menu_entry_opens_the_window(self) -> None:
        window = self.open_trend_window()
        self.assertEqual(window.title(), "Trend Identification")

    def test_the_shading_is_off_by_default(self) -> None:
        self.assertFalse(self.viz.trend_applied["enabled"])
        self.assertEqual(self.viz.canvas.find_withtag("trend"), ())

    def test_apply_draws_shading_in_the_state_colours(self) -> None:
        window = self.open_trend_window()
        enabled = next(c for c in self.descendants(window, tk.Checkbutton)
                       if c.cget("text") == "Show trend shading")
        # Keep a reference: a garbage-collected Tk variable unsets its Tcl variable.
        enabled_var = tk.BooleanVar(window, name=str(enabled.cget("variable")))
        enabled_var.set(True)
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

        self.assertTrue(self.viz.trend_applied["enabled"])
        fills = self.shading_fills()
        self.assertGreater(len(fills), 0)
        self.assertTrue(set(fills) <= set(self.expected_fills().values()))
        self.assertIn(self.expected_fills()[UP], fills)
        self.assertIn(self.expected_fills()[DOWN], fills)

    def test_shading_is_drawn_beneath_the_candles(self) -> None:
        self.viz.trend_applied = {**self.viz.trend_applied, "enabled": True}
        self.viz.draw_overlays()
        self.viz.window.update()
        trend_items = self.viz.canvas.find_withtag("trend")
        candle_items = self.viz.canvas.find_withtag("candle")
        self.assertTrue(trend_items and candle_items)
        self.assertLess(self.viz.canvas.find_all().index(trend_items[-1]),
                        self.viz.canvas.find_all().index(candle_items[0]))

    def test_cancel_leaves_the_settings_unchanged(self) -> None:
        window = self.open_trend_window()
        entry = self.entry_for(window, "ADX entry level")
        entry.delete(0, "end")
        entry.insert(0, "35")
        self.find_button(window, "Cancel").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.trend_applied["adx_enter"], 25)
        self.assertFalse(self.viz.trend_applied["enabled"])

    def test_an_invalid_setting_is_rejected_and_nothing_changes(self) -> None:
        window = self.open_trend_window()
        entry = self.entry_for(window, "ADX exit level")
        entry.delete(0, "end")
        entry.insert(0, "30")  # above the entry level of 25
        with mock.patch("pytradeviz.messagebox.showerror") as showerror:
            self.find_button(window, "Apply").invoke()
        self.viz.window.update()
        showerror.assert_called_once()
        self.assertEqual(self.viz.trend_applied["adx_exit"], 20)
        self.assertEqual(self.viz.canvas.find_withtag("trend"), ())

    def test_clicking_the_trend_box_toggles_the_shading(self) -> None:
        self.viz.draw_overlays()
        self.viz.window.update()
        label = self.viz.trend_toggle_label
        self.assertTrue(label.winfo_ismapped())
        self.assertFalse(self.viz.trend_applied["enabled"])
        click = (label.winfo_width() // 2, label.winfo_height() // 2)
        label.event_generate("<Button-1>", x=click[0], y=click[1])
        self.viz.window.update()
        self.assertTrue(self.viz.trend_applied["enabled"])
        self.assertGreater(len(self.viz.canvas.find_withtag("trend")), 0)
        label.event_generate("<Button-1>", x=click[0], y=click[1])
        self.viz.window.update()
        self.assertFalse(self.viz.trend_applied["enabled"])
        self.assertEqual(self.viz.canvas.find_withtag("trend"), ())

    def test_the_trend_box_stays_in_the_same_place_while_scrolling(self) -> None:
        self.viz.draw_overlays()
        self.viz.window.update()
        label = self.viz.trend_toggle_label
        canvas = self.viz.canvas

        def offset_in_view() -> tuple:
            return (label.winfo_rootx() - canvas.winfo_rootx(),
                    label.winfo_rooty() - canvas.winfo_rooty())

        before = offset_in_view()
        canvas.xview_moveto(0.5)
        canvas.yview_moveto(0.3)
        self.viz.window.update()
        self.assertEqual(offset_in_view(), before)
        self.assertTrue(label.winfo_ismapped())

    def test_the_crosshair_shows_the_state_and_adx_when_shading_is_on(self) -> None:
        self.viz.trend_applied = {**self.viz.trend_applied, "enabled": True}
        self.viz.draw_overlays()
        canvas = self.viz.canvas
        # The default view shows only the first candles, which are still warming up.
        canvas.xview_moveto(0.5)
        self.viz.window.update()
        self.viz.draw_overlays()
        details = self.viz.trend_details()
        # Point at a candle that has a state and is on screen, so the crosshair draws.
        visible = [i for i, (state, _adx) in enumerate(details)
                   if state is not None and 0 <= self.viz.candle_x(i) - canvas.canvasx(0) < canvas.winfo_width()]
        self.assertTrue(visible)
        index = visible[-1]
        screen_x = self.viz.candle_x(index) - canvas.canvasx(0)
        self.viz.crosshair_root = (canvas.winfo_rootx() + int(screen_x), canvas.winfo_rooty() + 20)
        self.viz.draw_crosshair()
        texts = [canvas.itemcget(item, "text") for item in canvas.find_withtag("crosshair")
                 if canvas.type(item) == "text"]
        state, adx = details[index]
        self.assertIn(f"{state}  ADX {adx:.1f}", texts)

    def test_the_help_button_opens_the_trend_help(self) -> None:
        window = self.open_trend_window()
        self.find_button(window, "Help").invoke()
        self.viz.window.update()
        # The help window is a child of the trend window, so look for it there.
        help_windows = [w for w in window.winfo_children()
                        if isinstance(w, tk.Toplevel) and w.title() == "Trend Identification Help"]
        self.assertEqual(len(help_windows), 1)
        help_windows[0].destroy()

    def test_the_setting_is_kept_per_tab(self) -> None:
        self.viz.trend_applied = {**self.viz.trend_applied, "enabled": True}
        state = self.viz.capture_tab_state()
        self.assertTrue(state.trend_applied["enabled"])


if __name__ == "__main__":
    unittest.main()
