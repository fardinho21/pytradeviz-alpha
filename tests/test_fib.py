from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Tuple

from drawings import (
    BOX, ELLIPSE, FIB, FIB_LEVELS, LINE, SEGMENT, SOLID, Drawing, complementary_color,
    fib_level_ys, hit_test, toolbox_rows,
)
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


class FibGeometryTests(unittest.TestCase):
    def test_levels_run_from_the_end_anchor_to_the_start_anchor(self):
        p1, p2 = (100.0, 300.0), (200.0, 100.0)
        levels = dict(fib_level_ys(p1, p2))
        self.assertEqual(sorted(levels), sorted(FIB_LEVELS))
        self.assertEqual(levels[0.0], 100.0)
        self.assertEqual(levels[1.0], 300.0)
        self.assertAlmostEqual(levels[0.5], 200.0)

    def test_complementary_color_is_opposite_on_the_hue_wheel(self):
        self.assertEqual(complementary_color("#ff0000"), "#00ffff")
        self.assertEqual(complementary_color("#0000ff"), "#ffff00")
        self.assertEqual(complementary_color("#808080"), "#808080")

    def test_complementary_color_round_trips_within_rounding(self):
        original = "#1e88e5"
        back = complementary_color(complementary_color(original))
        for index in (1, 3, 5):
            self.assertLessEqual(abs(int(original[index:index + 2], 16) - int(back[index:index + 2], 16)), 1)

    def test_hit_test_finds_a_level_inside_the_anchor_span(self):
        p1, p2 = (100.0, 300.0), (200.0, 100.0)
        level_y = dict(fib_level_ys(p1, p2))[0.5]
        self.assertTrue(hit_test(FIB, p1, p2, 150.0, level_y))

    def test_hit_test_misses_between_levels_and_outside_the_span(self):
        p1, p2 = (100.0, 300.0), (200.0, 100.0)
        levels = [y for _, y in fib_level_ys(p1, p2)]
        midway = (levels[0] + levels[1]) / 2
        self.assertFalse(hit_test(FIB, p1, p2, 150.0, midway))
        self.assertFalse(hit_test(FIB, p1, p2, 300.0, levels[3]))
        self.assertFalse(hit_test(FIB, p1, p2, 50.0, levels[3]))

    def test_fib_is_the_last_feature_in_the_tool_row(self):
        tool_row = [key for key, _ in toolbox_rows(("Blue",))[0]]
        self.assertEqual(tool_row, [("tool", LINE), ("tool", SEGMENT), ("tool", BOX),
                                    ("tool", ELLIPSE), ("tool", FIB)])

    def test_drawing_kind_is_not_fillable(self):
        drawing = Drawing(1, FIB, "solid", "#000", False, (0, 0), (1, 1))
        self.assertFalse(drawing.filled)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class FibToolTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def view_origin(self) -> Tuple[float, float]:
        return self.viz.canvas.canvasx(0), self.viz.canvas.canvasy(0)

    def event_at(self, x: float, y: float) -> SimpleNamespace:
        canvas = self.viz.canvas
        local_x, local_y = int(x), int(y)
        return SimpleNamespace(
            widget=canvas, x=local_x, y=local_y,
            x_root=canvas.winfo_rootx() + local_x, y_root=canvas.winfo_rooty() + local_y,
        )

    def draw(self, start: Tuple[float, float], end: Tuple[float, float]) -> None:
        self.viz.scroll_start(self.event_at(*start))
        self.viz.scroll_move(self.event_at(*end))
        self.viz.select_candle(self.event_at(*end))

    def press_fib_button(self) -> None:
        self.viz.fib_button.invoke()
        self.viz.window.update()

    def fib_items(self, drawing: Drawing):
        return self.viz.canvas.find_withtag(f"drawing_{drawing.id}")

    def test_fib_button_sits_beside_the_draw_button(self):
        draw_info = self.viz.draw_button.grid_info()
        fib_info = self.viz.fib_button.grid_info()
        self.assertEqual(self.viz.fib_button.cget("text"), "FIB")
        self.assertEqual(fib_info["row"], draw_info["row"])
        self.assertEqual(fib_info["column"], draw_info["column"] + 1)

    def test_fib_button_enters_draw_mode_with_the_fib_tool(self):
        self.press_fib_button()
        self.assertTrue(self.viz.draw_mode)
        self.assertEqual(self.viz.draw_tool, FIB)
        self.assertEqual(self.viz.select_mode_label.cget("text"), "fib mode")
        self.assertIn("pressed", self.viz.fib_button.state())
        self.assertIsNotNone(self.viz._toolbox)

    def test_pressing_fib_again_turns_draw_mode_off(self):
        self.press_fib_button()
        self.press_fib_button()
        self.assertFalse(self.viz.draw_mode)
        self.assertNotIn("pressed", self.viz.fib_button.state())

    def test_fib_button_switches_from_another_tool(self):
        self.viz.toggle_draw_mode()
        self.viz.activate_draw_button(("tool", LINE))
        self.press_fib_button()
        self.assertEqual(self.viz.draw_tool, FIB)
        self.assertTrue(self.viz.draw_mode)

    def test_drawing_a_retracement_creates_levels_and_labels(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        self.viz.window.update()
        self.assertEqual(len(self.viz.drawings), 1)
        drawing = self.viz.drawings[0]
        self.assertEqual(drawing.kind, FIB)
        labels = [i for i in self.fib_items(drawing) if self.viz.canvas.type(i) == "text"]
        self.assertEqual(len(labels), len(FIB_LEVELS))

    def test_labels_show_percentage_and_price(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        drawing = self.viz.drawings[0]
        texts = {self.viz.canvas.itemcget(i, "text")
                 for i in self.fib_items(drawing) if self.viz.canvas.type(i) == "text"}
        end_price = drawing.end[1]
        start_price = drawing.start[1]
        expected = f"50.0%  {end_price - 0.5 * (end_price - start_price):.2f}"
        self.assertIn(expected, texts)
        self.assertIn("0.0%  " + f"{end_price:.2f}", texts)

    def test_anchors_are_joined_by_a_dotted_complementary_diagonal(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        drawing = self.viz.drawings[0]
        (x1, y1), (x2, y2) = self.viz.drawing_points(drawing)
        canvas = self.viz.canvas
        diagonals = [i for i in self.fib_items(drawing)
                     if canvas.type(i) == "line" and canvas.coords(i)[1] != canvas.coords(i)[3]]
        self.assertEqual(len(diagonals), 1)
        item = diagonals[0]
        for actual, expected in zip(canvas.coords(item), (x1, y1, x2, y2)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(canvas.itemcget(item, "dash"), "2 4")
        self.assertEqual(canvas.itemcget(item, "fill"), complementary_color(drawing.color))

    def test_levels_are_solid_inside_the_box_and_dotted_beyond_it(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        drawing = self.viz.drawings[0]
        self.assertEqual(drawing.style, SOLID)
        points = self.viz.drawing_points(drawing)
        left, right = sorted((points[0][0], points[1][0]))
        view_left, _, view_right, _ = self.viz.canvas_view_bounds()
        self.assertLess(view_left, left)
        self.assertLess(right, view_right)
        canvas = self.viz.canvas
        for _, level_y in fib_level_ys(*points):
            segments = []
            for item in self.fib_items(drawing):
                if canvas.type(item) != "line":
                    continue
                x_a, y_a, x_b, y_b = canvas.coords(item)
                if y_a == y_b and abs(y_a - level_y) < 1e-6:
                    segments.append((min(x_a, x_b), max(x_a, x_b), canvas.itemcget(item, "dash")))
            segments.sort()
            solid = [(a, b) for a, b, dash in segments if dash == ""]
            dotted = [(a, b) for a, b, dash in segments if dash == "2 4"]
            self.assertEqual(len(solid), 1)
            self.assertAlmostEqual(solid[0][0], left)
            self.assertAlmostEqual(solid[0][1], right)
            self.assertEqual(len(dotted), 2)
            self.assertAlmostEqual(dotted[0][0], view_left)
            self.assertAlmostEqual(dotted[0][1], left)
            self.assertAlmostEqual(dotted[1][0], right)
            self.assertAlmostEqual(dotted[1][1], view_right)

    def test_retracement_is_not_filled_even_if_fill_was_chosen(self):
        self.press_fib_button()
        self.viz.activate_draw_button(("fill", True))
        self.draw((100, 100), (220, 200))
        self.assertFalse(self.viz.drawings[0].filled)

    def test_retracement_is_removed_by_undo(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        self.viz.activate_draw_button(("undo", None))
        self.assertEqual(self.viz.drawings, ())
        self.assertFalse(self.viz.canvas.find_withtag("drawing"))

    def test_retracement_stays_on_the_tab_it_was_drawn_on(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        self.assertEqual(len(self.viz.drawings), 1)
        self.press_fib_button()  # leave fib mode before switching tabs

        self.viz.select_timeframe("1M")
        self.viz.window.update()
        self.assertEqual(self.viz.drawings, ())
        self.assertFalse(self.viz.canvas.find_withtag("drawing"))

        self.viz.select_timeframe("Daily")
        self.viz.window.update()
        self.assertEqual(len(self.viz.drawings), 1)
        self.assertEqual(self.viz.drawings[0].kind, FIB)
        self.assertTrue(self.viz.canvas.find_withtag("drawing"))

    def test_each_tab_keeps_its_own_retracements(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        self.press_fib_button()
        self.viz.select_timeframe("2M")
        self.viz.window.update()
        self.press_fib_button()
        self.draw((140, 120), (260, 240))
        self.press_fib_button()
        self.assertEqual(len(self.viz.drawings), 1)
        self.viz.select_timeframe("Daily")
        self.viz.window.update()
        self.assertEqual(len(self.viz.drawings), 1)

    def test_reset_clears_retracements_on_every_tab(self):
        self.press_fib_button()
        self.draw((100, 100), (220, 200))
        self.press_fib_button()
        self.viz.reset_chart_configuration()
        self.viz.window.update()
        self.assertEqual(self.viz.drawings, ())
        self.assertFalse(self.viz.canvas.find_withtag("drawing"))


if __name__ == "__main__":
    unittest.main()
