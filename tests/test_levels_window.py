from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, List
from unittest import mock

from breakout import ATR_REJECTION, average_true_range
from drawings import DASHED, DOTTED, STYLE_DASHES
from levels import SUPPORT
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class LevelsWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def open_levels_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_levels_window(tk)
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

    def window_group(self, window: tk.Misc, label: str) -> tk.Misc:
        return next(g for g in self.descendants(window, tk.LabelFrame)
                    if str(g.cget("text")).startswith(f"{label} window"))

    def choose(self, widget: tk.Misc, text: str) -> None:
        """Select the radio button or checkbox with this text inside the widget."""
        control = next(c for c in self.descendants(widget, (tk.Radiobutton, tk.Checkbutton))
                       if c.cget("text") == text)
        control.invoke()

    def show_window(self, window: tk.Misc, label: str, color: str) -> None:
        group = self.window_group(window, label)
        self.choose(group, "Show")
        self.choose(group, color)

    def item_coords(self, item: int) -> List[float]:
        return list(self.viz.canvas.coords(item))

    def level_items(self, label: str) -> List[int]:
        """Level and rejection lines for a window; odds labels are listed by odds_labels."""
        return [item for item in self.viz.canvas.find_withtag(f"levels_{label}")
                if self.viz.canvas.type(item) != "text"]

    def items_tagged(self, label: str, tag: str) -> List[int]:
        return [item for item in self.level_items(label) if tag in self.viz.canvas.gettags(item)]

    def odds_labels(self, label: str) -> List[int]:
        return [item for item in self.viz.canvas.find_withtag(f"levels_{label}")
                if self.viz.canvas.type(item) == "text"]

    def apply(self, window: tk.Misc) -> None:
        self.find_button(window, "Apply").invoke()
        self.viz.window.update()

    def test_indicators_menu_opens_the_window(self) -> None:
        self.viz.open_levels_window(tk)
        self.viz.window.update()
        titles = [w.title() for w in self.viz.window.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertIn("Support and Resistance", titles)
        for window in self.viz.window.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.destroy()

    def test_nothing_is_drawn_until_a_window_is_shown(self) -> None:
        window = self.open_levels_window()
        self.apply(window)
        for label in ("1M", "2M", "3M", "6M"):
            self.assertEqual(self.level_items(label), [], label)

    def test_apply_draws_the_chosen_window_in_its_color(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "6M", "Red")
        self.apply(window)
        items = self.level_items("6M")
        self.assertTrue(items)
        color = self.viz.sma_colors["Red"]
        for item in items:
            self.assertEqual(self.viz.canvas.itemcget(item, "fill"), color)

    def test_no_style_control_is_offered(self) -> None:
        window = self.open_levels_window()
        group = self.window_group(window, "6M")
        radios = {str(r.cget("text")) for r in self.descendants(group, tk.Radiobutton)}
        self.assertFalse(radios & {"Triangles", "Lines", "Wavy"})
        self.assertNotIn("style", self.viz.levels_applied["windows"]["6M"])

    def test_support_is_solid_and_resistance_is_dashed(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        resistances = self.items_tagged("6M", "level_resistance")
        # The latest candle of this data has only resistance above price, so the support
        # style is checked directly on the visible range as well.
        self.assertTrue(resistances)
        dashed = " ".join(str(v) for v in STYLE_DASHES[DASHED])
        for item in resistances:
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), dashed)
        first, last = self.viz.visible_candle_range()
        price = self.viz.price_data[last][4]
        support = self.viz.level_line_item(first, last, price, SUPPORT, "red", tags=("probe",))
        self.assertIsNotNone(support)
        self.assertEqual(self.viz.canvas.itemcget(support, "dash"), "")

    def test_rejection_lines_are_dotted_at_the_rejection_distance(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        dotted = " ".join(str(v) for v in STYLE_DASHES[DOTTED])
        rejections = self.items_tagged("6M", "level_rejection")
        for item in rejections:
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), dotted)
        finder, _, _ = self.viz.levels_for_chart()
        study = self.viz.breakout_study("6M")
        last = len(self.viz.price_data) - 1
        expected = []
        for level in finder.static_levels("6M"):
            distance = study.rejection_distance(last, level.price)
            above = level.kind == SUPPORT
            price = level.price + distance if above else level.price - distance
            expected.append(self.viz.price_to_y(price))
        actual = sorted(self.item_coords(item)[1] for item in rejections)
        self.assertEqual(len(actual), len(expected))
        for got, want in zip(actual, sorted(expected)):
            self.assertAlmostEqual(got, want, places=6)

    def test_rejection_distance_follows_the_rejection_rule(self) -> None:
        rows = self.viz.price_data
        last = len(rows) - 1
        self.viz.levels_applied = {**self.viz.levels_applied, "rejection": "2%"}
        percent = self.viz.breakout_study("6M")
        self.assertAlmostEqual(percent.rejection_distance(last, 0.7), 0.014)
        self.viz.levels_applied = {**self.viz.levels_applied, "rejection": ATR_REJECTION}
        atr = self.viz.breakout_study("6M")
        self.assertAlmostEqual(atr.rejection_distance(last, 0.7), average_true_range(rows)[last])
        self.assertIsNone(atr.rejection_distance(5, 0.7))

    def test_lines_are_clipped_to_the_visible_range(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        left, right = self.viz.visible_x_range()
        items = self.level_items("6M")
        self.assertTrue(items)
        for item in items:
            xs = self.item_coords(item)[0::2]
            self.assertGreaterEqual(min(xs), left - 1)
            self.assertLessEqual(max(xs), right + 1)

    def test_each_window_is_drawn_separately(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "2M", "Blue")
        self.show_window(window, "3M", "Green")
        self.apply(window)
        self.assertTrue(self.level_items("2M"))
        self.assertTrue(self.level_items("3M"))
        self.assertEqual(self.level_items("1M"), [])

    def test_hiding_a_window_removes_its_levels(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "6M", "Red")
        self.apply(window)
        self.choose(self.window_group(window, "6M"), "Show")
        self.apply(window)
        self.assertEqual(self.level_items("6M"), [])

    def test_static_mode_draws_a_level_and_a_rejection_line_per_level(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        finder, _, _ = self.viz.levels_for_chart()
        self.assertEqual(len(self.level_items("6M")), 2 * len(finder.static_levels("6M")))

    def test_invalid_settings_are_rejected_and_not_applied(self) -> None:
        window = self.open_levels_window()
        entry = self.descendants(window, tk.Entry)[0]
        entry.delete(0, "end")
        entry.insert(0, "zero")
        before = self.viz.levels_applied["settings"]
        with mock.patch("pytradeviz.messagebox.showerror") as showerror:
            self.apply(window)
        showerror.assert_called_once()
        self.assertEqual(self.viz.levels_applied["settings"], before)

    def test_apply_stores_the_detection_settings(self) -> None:
        window = self.open_levels_window()
        entries = self.descendants(window, tk.Entry)
        for entry, value in zip(entries, ("3", "0.5", "4")):
            entry.delete(0, "end")
            entry.insert(0, value)
        self.apply(window)
        settings = self.viz.levels_applied["settings"]
        self.assertEqual((settings.pivot_bars, settings.width_pct, settings.min_touches),
                         (3, 0.5, 4))

    def test_breakout_switches_are_stored_on_apply(self) -> None:
        window = self.open_levels_window()
        group = next(g for g in self.descendants(window, tk.LabelFrame)
                     if g.cget("text") == "Breakout odds")
        self.choose(group, "5 candles")
        self.choose(group, "2%")
        self.apply(window)
        self.assertEqual(self.viz.levels_applied["horizon"], 5)
        self.assertEqual(self.viz.levels_applied["rejection"], "2%")

    def test_odds_labels_show_probability_or_sample_size(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "6M", "Red")
        self.apply(window)
        color = self.viz.sma_colors["Red"]
        labels = self.odds_labels("6M")
        self.assertTrue(labels)
        for label in labels:
            self.assertEqual(self.viz.canvas.itemcget(label, "fill"), color)
        texts = [self.viz.canvas.itemcget(label, "text") for label in labels]
        pattern = re.compile(r"^(n/a|n=\d+ \(too few\)|\d+% n=\d+)$")
        for text in texts:
            self.assertRegex(text, pattern)

    def test_overlapping_odds_labels_are_dropped(self) -> None:
        occupied: list = []
        self.viz.draw_level_odds(5, 0.7, "red", "6M", "33% n=57", occupied)
        self.viz.draw_level_odds(5, 0.7, "red", "3M", "41% n=12", occupied)
        self.assertEqual(len(self.odds_labels("6M")), 1)
        self.assertEqual(self.odds_labels("3M"), [])

    def test_replacing_the_data_clears_the_levels(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "6M", "Red")
        self.apply(window)
        stale = self.level_items("6M")
        self.assertTrue(stale)
        self.viz.replace_price_data(load_price_rows()[:200], None)
        self.viz.window.update()
        self.assertFalse(set(stale) & set(self.viz.canvas.find_all()))
        self.assertEqual(self.viz._levels_cache[0][0], 200)


    def open_help_window(self, window: tk.Toplevel) -> tk.Toplevel:
        self.find_button(window, "Help").invoke()
        self.viz.window.update()
        (help_window,) = [w for w in window.winfo_children()
                          if isinstance(w, tk.Toplevel) and w.title() == "Support and Resistance Help"]
        self.addCleanup(lambda: help_window.destroy() if help_window.winfo_exists() else None)
        return help_window

    def test_help_button_opens_the_help_modal(self) -> None:
        window = self.open_levels_window()
        help_window = self.open_help_window(window)
        self.assertTrue(help_window.winfo_viewable())
        self.assertIs(help_window.master, window)

    def test_help_text_describes_every_setting(self) -> None:
        window = self.open_levels_window()
        help_window = self.open_help_window(window)
        (text_widget,) = self.descendants(help_window, tk.Text)
        content = text_widget.get("1.0", "end")
        for term in ("Pivot bars", "Cluster width", "Min touches", "Causal", "Static",
                     "Support", "Resistance", "solid", "dashed", "dotted", "Show", "Color",
                     "1M", "6M", "Horizon", "Rejection", "1 ATR", "2%", "too few", "Apply"):
            self.assertIn(term, content)

    def test_closing_help_returns_the_grab_to_the_levels_window(self) -> None:
        window = self.open_levels_window()
        help_window = self.open_help_window(window)
        self.find_button(help_window, "Close").invoke()
        self.viz.window.update()
        self.assertFalse(help_window.winfo_exists())
        self.assertEqual(str(window.grab_current()), str(window))


if __name__ == "__main__":
    unittest.main()
