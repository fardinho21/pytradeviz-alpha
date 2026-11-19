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
    BOX, DASHED, DOTTED, ELLIPSE, LINE, SEGMENT, TOOLBOX_FADE_STIPPLE, TOOLBOX_PADDING,
)
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
        self.viz.update_hover_cursor(self.event_at(160, 140))
        self.assertEqual(self.viz.canvas.cget("cursor"), "fleur")
        self.viz.update_hover_cursor(self.event_at(500, 400))
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

    def toolbox_stipples(self) -> set:
        canvas = self.viz.canvas
        return {canvas.itemcget(item, "stipple") for item in canvas.find_withtag("toolbox")}

    def test_toolbox_fades_while_drawing_and_restores_after_release(self) -> None:
        self.set_tool(SEGMENT)
        self.press(100, 100)
        self.drag(220, 140)
        self.assertEqual(self.toolbox_stipples(), {TOOLBOX_FADE_STIPPLE})
        self.release(220, 140)
        self.viz.window.update()
        self.assertEqual(self.toolbox_stipples(), {""})

    def test_toolbox_fades_while_moving_a_drawing(self) -> None:
        self.set_tool(SEGMENT)
        self.draw((100, 100), (220, 140))
        self.viz.activate_draw_button(("tool", SEGMENT))
        self.press(160, 120)
        self.drag(180, 140)
        self.assertEqual(self.toolbox_stipples(), {TOOLBOX_FADE_STIPPLE})
        self.release(180, 140)
        self.viz.window.update()
        self.assertEqual(self.toolbox_stipples(), {""})

    def test_toolbox_does_not_fade_for_a_click_without_movement(self) -> None:
        self.set_tool(SEGMENT)
        self.press(100, 100)
        self.viz.window.update()
        self.assertEqual(self.toolbox_stipples(), {""})
        self.release(100, 100)

    # Moving the toolbox. Positions are relative to the visible part of the canvas.

    def toolbox_bounds(self) -> Tuple[float, float, float, float]:
        origin_x, origin_y = self.view_origin()
        left, top, right, bottom = self.viz._toolbox.bounds
        return left - origin_x, top - origin_y, right - origin_x, bottom - origin_y

    def empty_toolbox_spot(self) -> Tuple[float, float]:
        """A point in the toolbox padding, clear of every button."""
        left, top, _, _ = self.toolbox_bounds()
        x, y = left + TOOLBOX_PADDING / 2, top + TOOLBOX_PADDING / 2
        self.assertIsNone(self.viz._toolbox.button_at(*self.to_canvas(x, y)))
        return x, y

    def shifted(self, bounds: Tuple[float, float, float, float], dx: float, dy: float):
        return tuple(value + delta for value, delta in zip(bounds, (dx, dy, dx, dy)))

    def assertBoundsEqual(self, first, second) -> None:
        for value, other in zip(first, second):
            self.assertAlmostEqual(value, other, delta=1)

    def test_dragging_an_empty_spot_moves_the_toolbox_and_its_buttons(self) -> None:
        self.enter_mode()
        before = self.toolbox_bounds()
        button_before = self.toolbox_button(("tool", BOX)).bounds
        x, y = self.empty_toolbox_spot()
        self.press(x, y)
        self.drag(x - 200, y - 150)
        self.assertBoundsEqual(self.toolbox_bounds(), self.shifted(before, -200, -150))
        self.release(x - 200, y - 150)
        self.viz.window.update()
        self.assertBoundsEqual(self.toolbox_bounds(), self.shifted(before, -200, -150))
        self.assertBoundsEqual(
            self.toolbox_button(("tool", BOX)).bounds, self.shifted(button_before, -200, -150))
        self.assertIsNone(self.viz.draw_tool)
        self.assertEqual(self.viz.drawings, ())

    def test_toolbox_drag_does_not_scroll_the_chart(self) -> None:
        self.enter_mode()
        view_before = (self.viz.canvas.xview(), self.viz.canvas.yview())
        x, y = self.empty_toolbox_spot()
        self.press(x, y)
        self.drag(x - 100, y - 100)
        self.release(x - 100, y - 100)
        self.viz.window.update()
        self.assertEqual((self.viz.canvas.xview(), self.viz.canvas.yview()), view_before)

    def test_moved_toolbox_stays_fixed_on_screen_while_scrolling(self) -> None:
        self.enter_mode()
        x, y = self.empty_toolbox_spot()
        self.draw((x, y), (x - 200, y - 150))
        moved = self.toolbox_bounds()
        self.viz.canvas.xview_moveto(0.5)
        self.viz.canvas.yview_moveto(0.2)
        self.viz.window.update()
        self.viz.draw_overlays()
        self.assertBoundsEqual(self.toolbox_bounds(), moved)

    def test_moved_toolbox_keeps_its_place_when_draw_mode_is_re_entered(self) -> None:
        self.enter_mode()
        x, y = self.empty_toolbox_spot()
        self.draw((x, y), (x - 200, y - 150))
        moved = self.toolbox_bounds()
        self.viz.exit_modes()
        self.viz.window.update()
        self.viz.fib_button.invoke()
        self.viz.window.update()
        self.assertBoundsEqual(self.toolbox_bounds(), moved)

    def test_toolbox_cannot_be_dragged_out_of_the_view(self) -> None:
        self.enter_mode()
        left, top, right, bottom = self.toolbox_bounds()
        width, height = right - left, bottom - top
        x, y = self.empty_toolbox_spot()
        self.draw((x, y), (x - 5000, y - 5000))
        self.assertBoundsEqual(self.toolbox_bounds(), (0, 0, width, height))
        x, y = self.empty_toolbox_spot()
        self.draw((x, y), (x + 5000, y + 5000))
        view_right = self.viz.canvas.winfo_width()
        view_bottom = self.viz.canvas.winfo_height()
        self.assertBoundsEqual(
            self.toolbox_bounds(),
            (view_right - width, view_bottom - height, view_right, view_bottom))

    def test_toolbox_is_pushed_back_inside_when_the_window_shrinks(self) -> None:
        self.enter_mode()
        x, y = self.empty_toolbox_spot()
        self.draw((x, y), (x + 5000, y + 5000))  # flush with the bottom-right corner
        self.viz.window.geometry("1020x750")
        self.viz.window.update()
        _, _, right, bottom = self.toolbox_bounds()
        self.assertLessEqual(right, self.viz.canvas.winfo_width() + 1)
        self.assertLessEqual(bottom, self.viz.canvas.winfo_height() + 1)

    def test_dragging_from_a_button_does_not_move_the_toolbox(self) -> None:
        self.enter_mode()
        before = self.toolbox_bounds()
        origin_x, origin_y = self.view_origin()
        left, top, right, bottom = self.toolbox_button(("tool", BOX)).bounds
        x, y = (left + right) / 2 - origin_x, (top + bottom) / 2 - origin_y
        self.press(x, y)
        self.drag(x - 200, y - 150)
        self.release(x - 200, y - 150)
        self.viz.window.update()
        self.assertBoundsEqual(self.toolbox_bounds(), before)
        self.assertIsNone(self.viz.draw_tool)

    def test_click_on_an_empty_toolbox_spot_changes_nothing(self) -> None:
        self.set_tool(BOX)
        before = self.toolbox_bounds()
        self.click(*self.empty_toolbox_spot())
        self.viz.window.update()
        self.assertBoundsEqual(self.toolbox_bounds(), before)
        self.assertEqual(self.viz.draw_tool, BOX)
        self.assertEqual(self.viz.drawings, ())

    def test_toolbox_fades_while_it_is_being_dragged(self) -> None:
        self.enter_mode()
        x, y = self.empty_toolbox_spot()
        self.press(x, y)
        self.drag(x - 100, y - 100)
        self.assertEqual(self.toolbox_stipples(), {TOOLBOX_FADE_STIPPLE})
        self.release(x - 100, y - 100)
        self.viz.window.update()
        self.assertEqual(self.toolbox_stipples(), {""})

    def test_hover_over_an_empty_toolbox_spot_shows_move_cursor(self) -> None:
        self.enter_mode()
        self.viz.update_hover_cursor(self.event_at(*self.empty_toolbox_spot()))
        self.assertEqual(self.viz.canvas.cget("cursor"), "fleur")
        origin_x, origin_y = self.view_origin()
        left, top, right, bottom = self.toolbox_button(("tool", BOX)).bounds
        self.viz.update_hover_cursor(
            self.event_at((left + right) / 2 - origin_x, (top + bottom) / 2 - origin_y))
        self.assertEqual(self.viz.canvas.cget("cursor"), "hand2")


if __name__ == "__main__":
    unittest.main()
