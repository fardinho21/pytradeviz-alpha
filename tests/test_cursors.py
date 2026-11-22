from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List, Optional

from cursors import (
    CLOSED_HAND_HOTSPOT, CLOSED_HAND_MASK, CLOSED_HAND_PICTURE, CLOSED_HAND_SOURCE, MOVE_CURSOR,
    POINTING_HAND, bitmap_cursor_spec, closed_hand_candidates, closed_hand_xbm_texts,
    first_supported_cursor, xbm_text,
)
from drawings import BOX, TOOLBOX_PADDING
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


class ClosedHandBitmapTests(unittest.TestCase):
    def test_picture_is_square_and_uses_only_known_cells(self) -> None:
        self.assertEqual(len(CLOSED_HAND_PICTURE), 16)
        for row in CLOSED_HAND_PICTURE:
            self.assertEqual(len(row), 16)
            self.assertTrue(set(row) <= set(".#o"), row)
        # The outline is closed around the fill: every filled cell has an outline or fill neighbour
        # on each side, so no white leaks out to the transparent edge.
        for y, row in enumerate(CLOSED_HAND_PICTURE):
            for x, cell in enumerate(row):
                if cell == "o":
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        self.assertIn(CLOSED_HAND_PICTURE[y + dy][x + dx], "#o", (x, y))

    def test_hotspot_is_on_the_hand(self) -> None:
        x, y = CLOSED_HAND_HOTSPOT
        self.assertIn(CLOSED_HAND_PICTURE[y][x], "#o")

    def test_shipped_bitmap_files_match_the_picture(self) -> None:
        source, mask = closed_hand_xbm_texts()
        with open(CLOSED_HAND_SOURCE, encoding="ascii") as file:
            self.assertEqual(file.read(), source)
        with open(CLOSED_HAND_MASK, encoding="ascii") as file:
            self.assertEqual(file.read(), mask)

    def test_xbm_packs_rows_least_significant_bit_first(self) -> None:
        text = xbm_text("t", ("#.......", "......##"), lambda cell: cell == "#", (3, 1))
        self.assertIn("#define t_width 8\n#define t_height 2\n", text)
        self.assertIn("#define t_x_hot 3\n#define t_y_hot 1\n", text)
        self.assertIn("static unsigned char t_bits[] = {\n   0x01, 0xc0};\n", text)

    def test_mask_covers_source(self) -> None:
        source, mask = closed_hand_xbm_texts()

        def bytes_of(text: str) -> List[int]:
            body = text[text.index("{") + 1:text.index("}")]
            return [int(word, 16) for word in body.replace("\n", "").split(",")]

        for outline, covered in zip(bytes_of(source), bytes_of(mask)):
            self.assertEqual(outline & ~covered, 0)


class FakeWidget:
    """Stands in for a Tk widget: rejects the cursors in ``rejected`` the way Tk does."""

    def __init__(self, rejected: Any, cursor: str = "arrow") -> None:
        self.rejected = rejected
        self.cursor = cursor
        self.history: List[str] = []

    def cget(self, option: str) -> str:
        return self.cursor

    def configure(self, cursor: str) -> None:
        if cursor in self.rejected:
            raise tk.TclError(f'bad cursor spec "{cursor}"')
        self.cursor = cursor
        self.history.append(cursor)


class CursorResolutionTests(unittest.TestCase):
    def test_bitmap_spec_braces_paths_so_spaces_survive(self) -> None:
        self.assertEqual(
            bitmap_cursor_spec("/a b/hand.xbm", "/a b/mask.xbm"),
            "{@/a b/hand.xbm} {/a b/mask.xbm} black white",
        )

    def test_candidates_prefer_a_real_closed_hand_and_end_with_the_move_cursor(self) -> None:
        candidates = closed_hand_candidates()
        self.assertEqual(candidates[0], "closedhand")
        self.assertEqual(candidates[1], bitmap_cursor_spec(CLOSED_HAND_SOURCE, CLOSED_HAND_MASK))
        self.assertEqual(candidates[-1], MOVE_CURSOR)

    def test_first_supported_skips_rejected_specs_and_restores_the_widget(self) -> None:
        widget = FakeWidget(rejected={"closedhand", "nope"})
        self.assertEqual(first_supported_cursor(widget, ("closedhand", "nope", "fleur", "hand2")), "fleur")
        self.assertEqual(widget.cursor, "arrow")
        self.assertEqual(widget.history, ["fleur", "arrow"])

    def test_first_supported_returns_empty_when_nothing_is_accepted(self) -> None:
        widget = FakeWidget(rejected={"a", "b"})
        self.assertEqual(first_supported_cursor(widget, ("a", "b")), "")
        self.assertEqual(widget.cursor, "arrow")


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class CursorTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    # Helpers. Coordinates are relative to the visible part of the given canvas.

    def event_at(self, x: float, y: float, widget: Optional[tk.Canvas] = None) -> SimpleNamespace:
        canvas = self.viz.canvas if widget is None else widget
        return SimpleNamespace(
            widget=canvas, x=int(x), y=int(y),
            x_root=canvas.winfo_rootx() + int(x), y_root=canvas.winfo_rooty() + int(y),
        )

    def cursor_of(self, widget: tk.Misc) -> str:
        return str(widget.cget("cursor"))

    def descendants(self, widget: tk.Misc, cls: type) -> List[Any]:
        found: List[Any] = []
        for child in widget.winfo_children():
            if isinstance(child, cls):
                found.append(child)
            found.extend(self.descendants(child, cls))
        return found

    def hover(self, x: float, y: float, widget: Optional[tk.Canvas] = None) -> str:
        event = self.event_at(x, y, widget)
        self.viz.track_crosshair(event)
        return self.cursor_of(event.widget)

    def drag(self, widget: tk.Canvas, start: tuple, end: tuple) -> str:
        """Press, drag and report the cursor shown mid-drag; the button stays down."""
        self.viz.scroll_start(self.event_at(*start, widget=widget))
        self.viz.scroll_move(self.event_at(*end, widget=widget))
        return self.cursor_of(widget)

    def release(self, widget: tk.Canvas, x: float, y: float) -> None:
        event = self.event_at(x, y, widget)
        if widget is self.viz.canvas:
            self.viz.select_candle(event)
        self.viz.end_canvas_drag(event)

    # Pointing hand over buttons.

    def test_every_button_around_the_chart_shows_the_pointing_hand(self) -> None:
        buttons = self.descendants(self.viz.window, ttk.Button)
        expected = [
            self.viz.select_button, self.viz.roi_button, self.viz.export_button, self.viz.sr_button,
            self.viz.dark_mode_button, self.viz.draw_button, self.viz.fib_button,
            self.viz.load_more_button, self.viz.load_all_button,
            *self.viz.timeframe_buttons.values(),
        ]
        for button in expected:
            self.assertIn(button, buttons)
        for button in buttons:
            self.assertEqual(self.cursor_of(button), POINTING_HAND, button)
        self.assertEqual(self.cursor_of(self.viz.trend_toggle_label), POINTING_HAND)

    def test_menu_bar_and_its_menus_show_the_pointing_hand(self) -> None:
        root = self.viz.window
        self.assertEqual(self.cursor_of(self.viz.menu_bar), POINTING_HAND)
        for index in range(self.viz.menu_bar.index("end") + 1):
            if self.viz.menu_bar.type(index) == "cascade":
                path = self.viz.menu_bar.entrycget(index, "menu")
                self.assertEqual(str(root.tk.call(path, "cget", "-cursor")), POINTING_HAND, path)
        # Tk draws the bar along the top of the window from a copy of the menu; it must match.
        copies = [child for child in root.tk.call("winfo", "children", ".")
                  if root.tk.call("winfo", "class", child) == "Menu"]
        self.assertGreaterEqual(len(copies), 2)
        for path in copies:
            self.assertEqual(str(root.tk.call(path, "cget", "-cursor")), POINTING_HAND, path)

    def test_buttons_in_a_settings_window_show_the_pointing_hand(self) -> None:
        before = set(self.viz.window.winfo_children())
        self.viz.open_bollinger_window(tk)
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children()
                     if w not in before and isinstance(w, tk.Toplevel)]
        self.addCleanup(window.destroy)
        buttons = self.descendants(window, tk.Button)
        self.assertEqual(sorted(b.cget("text") for b in buttons), ["Apply", "Close", "Help", "Minimize"])
        for button in buttons:
            self.assertEqual(self.cursor_of(button), POINTING_HAND)
        # Checkboxes and radio buttons are not buttons, so they keep the arrow.
        for widget in self.descendants(window, tk.Checkbutton) + self.descendants(window, tk.Radiobutton):
            self.assertEqual(self.cursor_of(widget), "")

    def toolbox_point(self, key: tuple) -> tuple:
        button = next(b for b in self.viz._toolbox.buttons if b.key == key)
        left, top, right, bottom = button.bounds
        return ((left + right) / 2 - self.viz.canvas.canvasx(0), (top + bottom) / 2 - self.viz.canvas.canvasy(0))

    def test_toolbox_buttons_show_the_pointing_hand_but_inert_ones_do_not(self) -> None:
        self.viz.toggle_draw_mode()
        self.viz.window.update()
        self.assertEqual(self.hover(*self.toolbox_point(("tool", BOX))), POINTING_HAND)
        self.assertEqual(self.hover(*self.toolbox_point(("color", "Red"))), POINTING_HAND)
        self.assertEqual(self.hover(*self.toolbox_point(("undo", None))), POINTING_HAND)
        # The fill row is inert until a box or ellipse is the feature.
        self.assertEqual(self.hover(*self.toolbox_point(("fill", True))), "")
        self.viz.activate_draw_button(("tool", BOX))
        self.assertEqual(self.hover(*self.toolbox_point(("fill", True))), POINTING_HAND)
        # The padding between buttons drags the toolbox, and the open chart is plain.
        left, top, _, _ = self.viz._toolbox.bounds
        padding = (left - self.viz.canvas.canvasx(0) + TOOLBOX_PADDING / 2,
                   top - self.viz.canvas.canvasy(0) + TOOLBOX_PADDING / 2)
        self.assertEqual(self.hover(*padding), MOVE_CURSOR)
        self.assertEqual(self.hover(100, 100), "")

    def test_indicator_boxes_show_the_pointing_hand(self) -> None:
        canvas = self.viz.canvas_indicators
        for mode, (x1, y1, x2, y2) in self.viz._indicator_toggle_boxes.items():
            x = (x1 + x2) / 2 - canvas.canvasx(0)
            self.assertEqual(self.hover(x, (y1 + y2) / 2, canvas), POINTING_HAND, mode)
        x1, y1, x2, y2 = self.viz._indicator_info_box
        self.assertEqual(self.hover((x1 + x2) / 2 - canvas.canvasx(0), (y1 + y2) / 2, canvas), POINTING_HAND)
        self.assertEqual(self.hover(200, 80, canvas), "")

    def test_support_resistance_popups_show_the_pointing_hand_when_enabled(self) -> None:
        self.viz.toggle_sr_mode()
        self.viz.window.update()
        first, last = self.viz.visible_candle_range()
        index = (first + last) // 2
        x = self.viz.candle_x(index)
        y = self.viz.canvas.canvasy(self.viz.canvas.winfo_height() / 2)
        self.viz.show_sr_popups(index, x, y)
        self.viz.draw_overlays()
        self.assertEqual(len(self.viz._sr_popups), 4)
        origin_x, origin_y = self.viz.canvas.canvasx(0), self.viz.canvas.canvasy(0)
        for popup in self.viz._sr_popups:
            left, top, right, bottom = popup.bounds
            cursor = self.hover((left + right) / 2 - origin_x, (top + bottom) / 2 - origin_y)
            self.assertEqual(cursor, POINTING_HAND if popup.enabled else "", popup.label)

    # Closed fist while dragging.

    def test_drag_cursor_is_the_shipped_fist_on_x11(self) -> None:
        self.assertNotEqual(self.viz.drag_cursor, "")
        if self.viz.window.tk.call("tk", "windowingsystem") == "x11":
            self.assertEqual(self.viz.drag_cursor, bitmap_cursor_spec(CLOSED_HAND_SOURCE, CLOSED_HAND_MASK))
        self.assertEqual(self.cursor_of(self.viz.window), "")

    def test_dragging_the_chart_shows_the_fist_until_release(self) -> None:
        canvas = self.viz.canvas
        self.assertEqual(self.drag(canvas, (300, 300), (340, 320)), self.viz.drag_cursor)
        self.viz.scroll_move(self.event_at(380, 330))
        self.assertEqual(self.cursor_of(canvas), self.viz.drag_cursor)
        self.release(canvas, 380, 330)
        self.assertEqual(self.cursor_of(canvas), "")

    def test_dragging_an_axis_shows_the_fist_on_that_axis(self) -> None:
        for canvas in (self.viz.canvas_price, self.viz.canvas_date, self.viz.canvas_indicators):
            self.assertEqual(self.drag(canvas, (20, 60), (20, 90)), self.viz.drag_cursor, canvas)
            self.assertEqual(self.cursor_of(self.viz.canvas), "")
            self.release(canvas, 20, 90)
            self.assertEqual(self.cursor_of(canvas), "", canvas)

    def test_box_selection_drag_does_not_show_the_fist(self) -> None:
        self.viz.toggle_selection_mode()
        self.assertEqual(self.drag(self.viz.canvas, (300, 300), (400, 360)), "")
        self.release(self.viz.canvas, 400, 360)

    def test_fist_gives_way_to_the_hover_cursor_on_release(self) -> None:
        # Dragging the chart in draw mode, then releasing over a toolbox button.
        self.viz.toggle_draw_mode()
        self.viz.window.update()
        self.assertEqual(self.drag(self.viz.canvas, (100, 100), (130, 120)), self.viz.drag_cursor)
        x, y = self.toolbox_point(("tool", BOX))
        self.release(self.viz.canvas, x, y)
        self.assertEqual(self.cursor_of(self.viz.canvas), POINTING_HAND)


if __name__ == "__main__":
    unittest.main()
