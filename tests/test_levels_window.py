from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, List
from unittest import mock

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

    def show_window(self, window: tk.Misc, label: str, color: str,
                    style: str = "Triangles") -> None:
        group = self.window_group(window, label)
        self.choose(group, "Show")
        self.choose(group, color)
        self.choose(group, style)

    def marker_points(self, item: int) -> List[float]:
        return list(self.viz.canvas.coords(item))

    def level_items(self, label: str) -> List[int]:
        return list(self.viz.canvas.find_withtag(f"levels_{label}"))

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
        for label in ("2W", "1M", "2M", "3M", "6M"):
            self.assertEqual(self.level_items(label), [], label)

    def test_apply_draws_the_chosen_window_in_its_color(self) -> None:
        window = self.open_levels_window()
        self.show_window(window, "6M", "Red")
        self.apply(window)
        items = self.level_items("6M")
        self.assertTrue(items)
        color = self.viz.sma_colors["Red"]
        for item in items:
            self.assertEqual(self.viz.canvas.type(item), "polygon")
            self.assertEqual(self.viz.canvas.itemcget(item, "outline"), color)
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "")
        self.assertEqual(self.level_items("2W"), [])

    def test_support_markers_are_solid_and_point_up(self) -> None:
        self.open_levels_window()
        color = self.viz.sma_colors["Red"]
        self.viz.draw_level_marker(10, 0.7, SUPPORT, color, "6M")
        item = self.viz._levels_items[-1]
        x0, y0, x1, y1, x2, y2 = self.marker_points(item)
        self.assertEqual(self.viz.canvas.itemcget(item, "fill"), color)
        self.assertLess(y0, y1)              # apex above the base
        self.assertEqual(y1, y2)              # flat base
        self.assertLess(x1, x0)
        self.assertLess(x0, x2)

    def test_resistance_markers_are_hollow_and_point_down(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        color = self.viz.sma_colors["Red"]
        resistances = [i for i in self.level_items("6M")
                       if self.viz.canvas.itemcget(i, "fill") == ""]
        self.assertTrue(resistances)
        for item in resistances:
            x0, y0, x1, y1, x2, y2 = self.marker_points(item)
            self.assertEqual(y0, y1)              # flat top
            self.assertLess(y0, y2)               # apex below the top
            self.assertEqual(self.viz.canvas.itemcget(item, "outline"), color)

    def test_style_choices_are_triangles_lines_and_wavy(self) -> None:
        window = self.open_levels_window()
        group = self.window_group(window, "6M")
        radios = {str(r.cget("text")) for r in self.descendants(group, tk.Radiobutton)}
        self.assertTrue({"Triangles", "Lines", "Wavy"} <= radios)
        self.assertFalse(radios & set(self.viz.sma_line_styles))
        self.assertEqual(self.viz.levels_applied["windows"]["6M"]["style"], "Triangles")

    def test_each_window_keeps_its_own_style(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "2M", "Blue", "Triangles")
        self.show_window(window, "6M", "Red", "Lines")
        self.apply(window)
        for item in self.level_items("2M"):
            self.assertEqual(self.viz.canvas.type(item), "polygon")
        self.assertTrue(self.level_items("6M"))
        for item in self.level_items("6M"):
            self.assertEqual(self.viz.canvas.type(item), "line")

    def test_lines_style_draws_solid_zigzag_resistance(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red", "Lines")
        self.apply(window)
        items = self.level_items("6M")
        self.assertTrue(items)
        for item in items:
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "")
            ys = self.marker_points(item)[1::2]
            self.assertGreater(len(ys), 2)
            self.assertGreater(max(ys) - min(ys), 0)  # zigzag, not a flat line
        self.assertGreater(len(self.marker_points(items[0])), 4)

    def test_wavy_style_has_dashed_support_and_solid_wave_resistance(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red", "Wavy")
        self.apply(window)
        for item in self.level_items("6M"):
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "")
            ys = self.marker_points(item)[1::2]
            self.assertGreater(max(ys) - min(ys), 0)

        self.viz.draw_level_line(0, 10, 0.7, SUPPORT, "red", "6M", wavy=True)
        support = self.viz._levels_items[-1]
        self.assertNotEqual(self.viz.canvas.itemcget(support, "dash"), "")
        ys = self.marker_points(support)[1::2]
        self.assertEqual(max(ys), min(ys))    # straight line

    def test_zigzag_and_wave_stay_around_the_level(self) -> None:
        y, amp = 500.0, self.viz.levels_zigzag_amplitude
        zig = self.viz.zigzag_points(0.0, 100.0, y)
        self.assertEqual(zig[:2], [0.0, y])
        self.assertEqual(zig[-2:], [100.0, y])
        xs = zig[0::2]
        self.assertEqual(xs, sorted(xs))
        self.assertTrue(all(abs(v - y) <= amp for v in zig[1::2]))
        wave_amp = self.viz.levels_wave_amplitude
        wave = self.viz.wave_points(0.0, 100.0, y)
        self.assertTrue(all(abs(v - y) <= wave_amp + 1e-9 for v in wave[1::2]))

    def test_lines_are_clipped_to_the_visible_range(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red", "Lines")
        self.apply(window)
        left, right = self.viz.visible_x_range()
        items = self.level_items("6M")
        self.assertTrue(items)
        for item in items:
            xs = self.marker_points(item)[0::2]
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

    def test_static_mode_marks_every_visible_candle_for_each_level(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        finder, _ = self.viz.levels_for_chart()
        first, last = self.viz.visible_candle_range()
        self.assertEqual(
            len(self.level_items("6M")),
            len(finder.static_levels("6M")) * (last - first + 1),
        )

    def test_markers_are_drawn_only_for_visible_candles(self) -> None:
        window = self.open_levels_window()
        self.choose(window, "Static (latest levels across the whole chart)")
        self.show_window(window, "6M", "Red")
        self.apply(window)
        canvas = self.viz.canvas
        first, last = self.viz.visible_candle_range()
        radius = self.viz.levels_marker_radius
        for item in self.level_items("6M"):
            x0, _, _, _, x2, _ = self.marker_points(item)
            self.assertGreaterEqual(x0, self.viz.candle_x(first) - radius - 1e-6)
            self.assertLessEqual(x2, self.viz.candle_x(last) + radius + 1e-6)
        self.assertLessEqual(self.viz.candle_x(last), canvas.canvasx(canvas.winfo_width()) + 1e-6)

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


if __name__ == "__main__":
    unittest.main()
