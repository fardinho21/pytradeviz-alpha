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

from drawings import BOX, DASHED, DOTTED, ELLIPSE, LINE, SEGMENT
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class DrawModeTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    # Helpers. Coordinates passed to them are relative to the visible part of the candle canvas.

    def view_origin(self) -> Tuple[float, float]:
        return self.viz.canvas.canvasx(0), self.viz.canvas.canvasy(0)

    def to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        origin_x, origin_y = self.view_origin()
        return x + origin_x, y + origin_y

    def event_at(self, x: float, y: float) -> SimpleNamespace:
        canvas = self.viz.canvas
        local_x = int(x)
        local_y = int(y)
        return SimpleNamespace(
            widget=canvas, x=local_x, y=local_y,
            x_root=canvas.winfo_rootx() + local_x,
            y_root=canvas.winfo_rooty() + local_y,
        )

    def press(self, x: float, y: float) -> None:
        self.viz.scroll_start(self.event_at(x, y))

    def drag(self, x: float, y: float) -> None:
        self.viz.scroll_move(self.event_at(x, y))

    def release(self, x: float, y: float) -> None:
        self.viz.select_candle(self.event_at(x, y))

    def click(self, x: float, y: float) -> None:
        self.press(x, y)
        self.release(x, y)

    def draw(self, start: Tuple[float, float], end: Tuple[float, float]) -> None:
        self.press(*start)
        self.drag(*end)
        self.release(*end)

    def toolbox_button(self, key: Tuple[str, object]):
        return next(button for button in self.viz._toolbox.buttons if button.key == key)

    def press_toolbox(self, key: Tuple[str, object]) -> None:
        left, top, right, bottom = self.toolbox_button(key).bounds
        origin_x, origin_y = self.view_origin()
        self.click((left + right) / 2 - origin_x, (top + bottom) / 2 - origin_y)

    def enter_mode(self) -> None:
        self.viz.toggle_draw_mode()
        self.viz.window.update()

    def set_tool(self, tool: str) -> None:
        self.enter_mode()
        self.press_toolbox(("tool", tool))

    def drawing_items(self, drawing_id: int):
        return self.viz.canvas.find_withtag(f"drawing_{drawing_id}")

    def test_draw_button_enters_mode_and_shows_label(self) -> None:
        self.viz.draw_button.invoke()
        self.viz.window.update()
        self.assertTrue(self.viz.draw_mode)
        self.assertEqual(self.viz.select_mode_label.cget("text"), "draw mode")
        self.assertIn("pressed", self.viz.draw_button.state())
        self.assertIsNotNone(self.viz._toolbox)

    def test_draw_mode_is_exclusive_with_support_resistance_mode(self) -> None:
        self.viz.toggle_sr_mode()
        self.enter_mode()
        self.assertTrue(self.viz.draw_mode)
        self.assertFalse(self.viz.sr_mode)

    def test_toolbox_hidden_outside_draw_mode(self) -> None:
        self.enter_mode()
        self.viz.exit_modes()
        self.assertIsNone(self.viz._toolbox)
        self.assertFalse(self.viz.canvas.find_withtag("toolbox"))

    def test_feature_buttons_are_mutually_exclusive_and_toggle_off(self) -> None:
        self.enter_mode()
        self.press_toolbox(("tool", BOX))
        self.assertEqual(self.viz.draw_tool, BOX)
        self.press_toolbox(("tool", SEGMENT))
        self.assertEqual(self.viz.draw_tool, SEGMENT)
        self.press_toolbox(("tool", SEGMENT))
        self.assertIsNone(self.viz.draw_tool)

    def test_style_buttons_are_mutually_exclusive(self) -> None:
        self.enter_mode()
        self.press_toolbox(("style", DASHED))
        self.assertEqual(self.viz.draw_style, DASHED)
        self.press_toolbox(("style", DOTTED))
        self.assertEqual(self.viz.draw_style, DOTTED)

    def test_fill_is_inert_unless_box_or_ellipse_selected(self) -> None:
        self.set_tool(LINE)
        self.assertFalse(self.viz.toolbox_enabled(("fill", True)))
        self.press_toolbox(("fill", True))
        self.assertFalse(self.viz.draw_filled)
        self.viz.activate_draw_button(("tool", ELLIPSE))
        self.assertTrue(self.viz.toolbox_enabled(("fill", True)))
        self.press_toolbox(("fill", True))
        self.assertTrue(self.viz.draw_filled)

    def test_box_draws_with_current_style_and_fill(self) -> None:
        self.set_tool(BOX)
        self.press_toolbox(("style", DASHED))
        self.press_toolbox(("fill", True))
        self.draw((100, 100), (220, 180))
        self.assertEqual(len(self.viz.drawings), 1)
        drawing = self.viz.drawings[0]
        self.assertEqual((drawing.kind, drawing.style, drawing.filled), (BOX, DASHED, True))
        self.assertEqual(self.viz.canvas.itemcget(self.drawing_items(drawing.id)[0], "dash"), "8 4")

    def test_line_spans_full_viewport(self) -> None:
        self.set_tool(LINE)
        self.draw((100, 100), (200, 100))
        drawing = self.viz.drawings[-1]
        items = self.drawing_items(drawing.id)
        self.assertEqual(len(items), 1)
        x1, _, x2, _ = self.viz.canvas.coords(items[0])
        left, _ = self.view_origin()
        right = left + self.viz.canvas.winfo_width()
        self.assertAlmostEqual(min(x1, x2), left, delta=1)
        self.assertAlmostEqual(max(x1, x2), right, delta=1)

    def test_segment_has_hollow_circles_at_both_ends(self) -> None:
        self.set_tool(SEGMENT)
        self.draw((100, 100), (220, 140))
        drawing = self.viz.drawings[-1]
        types = [self.viz.canvas.type(item) for item in self.drawing_items(drawing.id)]
        self.assertEqual(types.count("line"), 1)
        self.assertEqual(types.count("oval"), 2)
        for item in self.drawing_items(drawing.id):
            if self.viz.canvas.type(item) == "oval":
                self.assertEqual(self.viz.canvas.itemcget(item, "fill"), self.viz.get_theme()["canvas"])

    def test_undo_delete_and_clear(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (160, 150))
        self.draw((200, 100), (260, 150))
        self.assertEqual(len(self.viz.drawings), 2)

        self.viz.activate_draw_button(("undo", None))
        self.assertEqual(len(self.viz.drawings), 1)

        self.viz.activate_draw_button(("undo", None))
        self.assertEqual(self.viz.drawings, ())

        self.draw((100, 100), (160, 150))
        self.draw((200, 100), (260, 150))
        self.click(130, 125)  # select the first box
        self.press_toolbox(("delete", None))
        self.assertEqual(len(self.viz.drawings), 1)

        self.press_toolbox(("clear", None))
        self.assertEqual(self.viz.drawings, ())
        self.press_toolbox(("undo", None))
        self.assertEqual(len(self.viz.drawings), 1)

    def test_escape_exits_mode_and_keeps_drawings(self) -> None:
        self.set_tool(SEGMENT)
        self.draw((100, 100), (220, 140))
        kept = self.viz.drawings
        self.viz.exit_modes()
        self.viz.window.update()
        self.assertFalse(self.viz.draw_mode)
        self.assertEqual(self.viz.drawings, kept)
        self.assertTrue(self.viz.canvas.find_withtag("drawing"))

    def test_drawings_do_not_move_outside_draw_mode(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (220, 180))
        before = self.viz.drawings
        self.viz.exit_modes()
        self.press(160, 140)
        self.drag(200, 160)
        self.release(200, 160)
        self.assertEqual(self.viz.drawings, before)

    def test_drawing_moves_in_draw_mode(self) -> None:
        self.set_tool(SEGMENT)
        self.draw((100, 100), (220, 140))
        original = self.viz.drawings[-1]
        self.viz.activate_draw_button(("tool", SEGMENT))  # turn the feature off
        self.click(160, 120)  # select without a tool in draw mode
        self.press(160, 120)
        self.drag(180, 140)
        self.release(180, 140)
        moved = self.viz.drawings[-1]
        self.assertNotEqual(moved.start, original.start)
        index_before, price_before = self.viz.chart_point(*self.to_canvas(160, 120))
        index_after, price_after = self.viz.chart_point(*self.to_canvas(180, 140))
        self.assertAlmostEqual(moved.start[0] - original.start[0], index_after - index_before, places=6)
        self.assertAlmostEqual(moved.start[1] - original.start[1], price_after - price_before, places=6)

    def test_hover_over_drawing_shows_move_cursor(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (220, 180))
        self.viz.activate_draw_button(("tool", BOX))
        self.viz.update_draw_cursor(self.event_at(160, 140))
        self.assertEqual(self.viz.canvas.cget("cursor"), "fleur")
        self.viz.update_draw_cursor(self.event_at(500, 400))
        self.assertEqual(self.viz.canvas.cget("cursor"), "")

    def test_cursor_resets_when_leaving_draw_mode(self) -> None:
        self.enter_mode()
        self.viz.canvas.configure(cursor="fleur")
        self.viz.exit_modes()
        self.viz.update_mode_widgets()
        self.assertEqual(self.viz.canvas.cget("cursor"), "")

    def test_drawings_are_stored_in_chart_units(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (220, 180))
        drawing = self.viz.drawings[-1]
        expected_start = self.viz.chart_point(*self.to_canvas(100, 100))
        self.assertAlmostEqual(drawing.start[0], expected_start[0], places=6)
        self.assertAlmostEqual(drawing.start[1], expected_start[1], places=6)
        self.viz._scale_x *= 2.0
        self.viz.draw_drawings()
        self.assertEqual(self.viz.drawings[-1], drawing)

    def test_opening_new_data_clears_drawings(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (220, 180))
        self.assertTrue(self.viz.drawings)
        self.viz.replace_price_data(load_price_rows(), None)
        self.assertEqual(self.viz.drawings, ())
        self.assertFalse(self.viz.canvas.find_withtag("drawing"))

    def test_toolbox_press_must_release_on_same_button(self) -> None:
        self.enter_mode()
        origin_x, origin_y = self.view_origin()
        left, top, right, bottom = self.toolbox_button(("tool", BOX)).bounds
        self.press((left + right) / 2 - origin_x, (top + bottom) / 2 - origin_y)
        other = self.toolbox_button(("tool", LINE)).bounds
        self.release((other[0] + other[2]) / 2 - origin_x, (other[1] + other[3]) / 2 - origin_y)
        self.assertIsNone(self.viz.draw_tool)

    def test_new_drawings_default_to_blue(self) -> None:
        self.set_tool(LINE)
        self.draw((100, 100), (200, 100))
        self.assertEqual(self.viz.drawings[-1].color, "#1e88e5")

    def test_swatch_click_sets_colour_for_new_drawings(self) -> None:
        self.enter_mode()
        self.press_toolbox(("color", "Orange"))
        self.assertEqual(self.viz.draw_color_name, "Orange")
        self.press_toolbox(("tool", LINE))
        self.draw((100, 100), (200, 100))
        self.assertEqual(self.viz.drawings[-1].color, "#fb8c00")
        self.assertEqual(
            self.viz.canvas.itemcget(self.drawing_items(self.viz.drawings[-1].id)[0], "fill"),
            "#fb8c00",
        )

    def test_colour_change_keeps_existing_drawings_colour(self) -> None:
        self.set_tool(LINE)
        self.draw((100, 100), (200, 100))
        first = self.viz.drawings[-1]
        self.press_toolbox(("color", "Red"))
        self.assertEqual(self.viz.drawings[-1].color, first.color)
        self.assertEqual(first.color, "#1e88e5")

    def test_active_swatch_has_heavier_outline(self) -> None:
        self.enter_mode()
        canvas = self.viz.canvas
        hex_by_name = self.viz.sma_colors

        def swatch_width(name: str) -> int:
            for item in canvas.find_withtag("toolbox"):
                if canvas.type(item) == "rectangle" and canvas.itemcget(item, "fill") == hex_by_name[name]:
                    return int(float(canvas.itemcget(item, "width")))
            raise AssertionError(f"no swatch drawn for {name}")

        self.assertEqual(swatch_width("Blue"), 3)
        self.assertEqual(swatch_width("Red"), 1)
        self.press_toolbox(("color", "Red"))
        self.viz.update_mode_widgets()
        self.assertEqual(swatch_width("Red"), 3)
        self.assertEqual(swatch_width("Blue"), 1)

    def test_filled_box_and_ellipse_use_translucent_stipple(self) -> None:
        self.set_tool(BOX)
        self.press_toolbox(("fill", True))
        self.draw((100, 100), (220, 180))
        self.assertEqual(
            self.viz.canvas.itemcget(self.drawing_items(self.viz.drawings[-1].id)[0], "stipple"),
            "gray50",
        )
        self.press_toolbox(("tool", ELLIPSE))
        self.draw((240, 100), (340, 180))
        self.assertEqual(
            self.viz.canvas.itemcget(self.drawing_items(self.viz.drawings[-1].id)[0], "stipple"),
            "gray50",
        )

    def test_hollow_box_has_no_stipple(self) -> None:
        self.set_tool(BOX)
        self.draw((100, 100), (220, 180))
        item = self.drawing_items(self.viz.drawings[-1].id)[0]
        self.assertEqual(self.viz.canvas.itemcget(item, "stipple"), "")


if __name__ == "__main__":
    unittest.main()
