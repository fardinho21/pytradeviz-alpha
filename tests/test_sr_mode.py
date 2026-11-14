from __future__ import annotations

import contextlib
import datetime as dt
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import List, Tuple

from levels import window_start
from pytradeviz import PyTradeViz
from sr_popups import POPUP_HEIGHT, POPUP_WIDTH, SRPopup, popup_bounds
from test_roi import load_price_rows


class PopupGeometryTests(unittest.TestCase):
    view = (0.0, 0.0, 400.0, 300.0)

    def test_popups_sit_below_and_right_of_cursor(self) -> None:
        boxes = popup_bounds(100, 100, 5, self.view)
        self.assertEqual(len(boxes), 5)
        left, top, right, bottom = boxes[0]
        self.assertGreater(left, 100)
        self.assertGreater(top, 100)
        self.assertEqual(right - left, POPUP_WIDTH)
        self.assertEqual(bottom - top, POPUP_HEIGHT)
        for upper, lower in zip(boxes, boxes[1:]):
            self.assertLess(upper[3], lower[1])

    def test_popups_flip_left_and_stay_in_view_near_right_edge(self) -> None:
        boxes = popup_bounds(395, 100, 5, self.view)
        for left, _, right, _ in boxes:
            self.assertGreaterEqual(left, 0)
            self.assertLessEqual(right, 400)
            self.assertLess(right, 395)

    def test_popups_stay_in_view_near_bottom_edge(self) -> None:
        boxes = popup_bounds(100, 295, 5, self.view)
        self.assertGreaterEqual(min(box[1] for box in boxes), 0)
        self.assertLessEqual(max(box[3] for box in boxes), 300)

    def test_contains_checks_bounds(self) -> None:
        popup = SRPopup("1M", True, (10.0, 10.0, 20.0, 30.0))
        self.assertTrue(popup.contains(15, 20))
        self.assertTrue(popup.contains(10, 10))
        self.assertFalse(popup.contains(21, 20))
        self.assertFalse(popup.contains(15, 31))


def click_candidates(viz: PyTradeViz) -> List[int]:
    """Visible candle indices, newest first."""
    first, last = viz.visible_candle_range()
    return list(range(last, first - 1, -1))


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class SupportResistanceModeTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def event_at(self, x: float, y: float) -> SimpleNamespace:
        canvas = self.viz.canvas
        local_x = int(x - canvas.canvasx(0))
        local_y = int(y - canvas.canvasy(0))
        return SimpleNamespace(
            widget=canvas, x=local_x, y=local_y,
            x_root=canvas.winfo_rootx() + local_x,
            y_root=canvas.winfo_rooty() + local_y,
        )

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.viz.canvas.bbox(f"candle_{index}")
        return (x1 + x2) / 2, (y1 + y2) / 2

    def click(self, x: float, y: float) -> None:
        event = self.event_at(x, y)
        self.viz.scroll_start(event)
        self.viz.select_candle(event)

    def scroll_to(self, index: int) -> None:
        canvas = self.viz.canvas
        x1 = canvas.bbox(f"candle_{index}")[0]
        total = canvas.bbox("all")[2]
        canvas.xview_moveto(max(0.0, (x1 - canvas.winfo_width() / 2) / total))
        self.viz.window.update()

    def click_candle(self, index: int) -> None:
        self.scroll_to(index)
        self.click(*self.candle_center(index))

    def popup_center(self, position: int) -> Tuple[float, float]:
        left, top, right, bottom = self.viz._sr_popups[position].bounds
        return (left + right) / 2, (top + bottom) / 2

    def enter_mode(self) -> None:
        self.viz.toggle_sr_mode()
        self.viz.window.update()

    def mixed_index(self) -> Tuple[int, List[str], List[str]]:
        """A candle, newest first, whose windows split into some with levels and some without."""
        finder = self.viz.levels_for_chart()[0]
        labels = list(self.viz.sr_window_labels)
        for index in range(len(self.viz.price_data) - 1, -1, -1):
            enabled = [label for label in labels if finder.levels_at(index, label)]
            disabled = [label for label in labels if not finder.levels_at(index, label)]
            if enabled and disabled:
                return index, enabled, disabled
        self.fail("the sample data has no candle with both enabled and disabled windows")

    def test_sr_button_sits_next_to_export_button(self) -> None:
        export_column = self.viz.export_button.grid_info()["column"]
        self.assertEqual(self.viz.sr_button.cget("text"), "S-R")
        self.assertEqual(self.viz.sr_button.grid_info()["column"], export_column + 1)

    def test_button_enters_mode_and_shows_label(self) -> None:
        self.viz.sr_button.invoke()
        self.viz.window.update()
        self.assertTrue(self.viz.sr_mode)
        self.assertEqual(self.viz.select_mode_label.cget("text"), "support/resistance mode")
        self.assertIn("pressed", self.viz.sr_button.state())
        self.assertTrue(self.viz.select_mode_label.place_info())

    def test_candle_click_highlights_and_shows_four_popups(self) -> None:
        self.enter_mode()
        index = click_candidates(self.viz)[0]
        self.click_candle(index)
        self.assertEqual(self.viz.selected_indices, {index})
        self.assertEqual(
            [popup.label for popup in self.viz._sr_popups],
            ["1M", "2M", "3M", "6M"],
        )
        self.assertEqual(len(self.viz._sr_popup_items), 8)
        self.assertIsNone(self.viz._sr_levels)

    def test_popup_enabled_state_matches_available_levels(self) -> None:
        self.enter_mode()
        index, enabled, disabled = self.mixed_index()
        self.click_candle(index)
        states = {popup.label: popup.enabled for popup in self.viz._sr_popups}
        for label in enabled:
            self.assertTrue(states[label])
        for label in disabled:
            self.assertFalse(states[label])

    def test_unavailable_popup_is_dashed_tinted_and_inert(self) -> None:
        self.enter_mode()
        index, enabled, disabled = self.mixed_index()
        self.click_candle(index)
        canvas = self.viz.canvas
        position = [popup.label for popup in self.viz._sr_popups].index(disabled[0])
        box = self.viz._sr_popup_items[2 * position]
        self.assertEqual(canvas.itemcget(box, "fill"), self.viz.get_theme()["sr_unavailable"])
        self.assertTrue(canvas.itemcget(box, "dash"))
        self.click(*self.popup_center(position))
        self.assertIsNone(self.viz._sr_levels)
        self.assertEqual(len(self.viz._sr_popups), 4)

    def test_enabled_popup_click_draws_orange_solid_levels(self) -> None:
        self.enter_mode()
        index, enabled, _ = self.mixed_index()
        self.click_candle(index)
        label = enabled[0]
        position = [popup.label for popup in self.viz._sr_popups].index(label)
        self.click(*self.popup_center(position))
        self.assertEqual(self.viz._sr_popups, ())
        self.assertEqual(self.viz._sr_popup_items, ())
        self.assertEqual(self.viz._sr_levels, (index, label))
        self.assertEqual(self.viz.selected_indices, {index})
        finder = self.viz.levels_for_chart()[0]
        expected = finder.levels_at(index, label)
        self.assertEqual(len(self.viz._sr_items), len(expected))
        orange = self.viz.sma_colors["Orange"]
        for item in self.viz._sr_items:
            self.assertEqual(self.viz.canvas.itemcget(item, "fill"), orange)
            self.assertEqual(self.viz.canvas.itemcget(item, "dash"), "")
            self.assertIn("sr_levels", self.viz.canvas.gettags(item))

    def test_escape_clears_levels_and_exits_mode(self) -> None:
        self.enter_mode()
        index, enabled, _ = self.mixed_index()
        self.click_candle(index)
        label = enabled[0]
        position = [popup.label for popup in self.viz._sr_popups].index(label)
        self.click(*self.popup_center(position))
        self.assertTrue(self.viz.window.bind("<Escape>"))
        self.viz.exit_modes()
        self.viz.window.update()
        self.assertFalse(self.viz.sr_mode)
        self.assertIsNone(self.viz._sr_levels)
        self.assertEqual(self.viz._sr_items, ())
        self.assertEqual(self.viz.selected_indices, set())
        self.assertNotIn("pressed", self.viz.sr_button.state())

    def test_drag_in_sr_mode_scrolls_without_drawing_a_box(self) -> None:
        self.enter_mode()
        index = click_candidates(self.viz)[0]
        start = self.candle_center(index)
        press = self.event_at(*start)
        self.viz.scroll_start(press)
        self.assertIsNone(self.viz._box_origin)
        self.viz.scroll_move(self.event_at(start[0] - 60, start[1]))
        self.assertIsNone(self.viz._selection_box)
        self.assertIsNone(self.viz._box_origin)

    def test_drag_dismisses_popups(self) -> None:
        self.enter_mode()
        self.click_candle(click_candidates(self.viz)[0])
        self.assertTrue(self.viz._sr_popups)
        center = self.popup_center(0)
        self.viz.scroll_start(self.event_at(*center))
        self.viz.scroll_move(self.event_at(center[0] - 40, center[1]))
        self.assertEqual(self.viz._sr_popups, ())

    def test_clicking_empty_space_dismisses_popups(self) -> None:
        self.enter_mode()
        index = click_candidates(self.viz)[0]
        self.click_candle(index)
        first_x = self.candle_center(index)[0]
        gap_x = None
        for candidate in range(-200, 200, 3):
            x = first_x + candidate
            if self.viz.candle_index_at(x, self.viz.canvas.canvasy(0) + 2) is None:
                gap_x = x
                break
        self.assertIsNotNone(gap_x)
        self.viz.dismiss_sr_popups()
        self.assertEqual(self.viz._sr_popups, ())
        self.click(gap_x, self.viz.canvas.canvasy(0) + 2)
        self.assertEqual(self.viz._sr_popups, ())

    def test_resize_and_zoom_dismiss_popups(self) -> None:
        self.enter_mode()
        self.click_candle(click_candidates(self.viz)[0])
        self.assertTrue(self.viz._sr_popups)
        self.viz.fit_chart_to_canvas(self.viz._last_canvas_width + 200,
                                     self.viz._last_canvas_height)
        self.assertEqual(self.viz._sr_popups, ())
        self.click_candle(click_candidates(self.viz)[0])
        self.assertTrue(self.viz._sr_popups)
        canvas = self.viz.canvas
        self.viz.zoom_chart(SimpleNamespace(
            widget=canvas, x=canvas.winfo_width() // 2, y=canvas.winfo_height() // 2,
            delta=120))
        self.assertEqual(self.viz._sr_popups, ())

    def test_other_modes_turn_sr_mode_off(self) -> None:
        self.enter_mode()
        self.viz.toggle_selection_mode()
        self.assertFalse(self.viz.sr_mode)
        self.viz.toggle_sr_mode()
        self.viz.toggle_roi_mode()
        self.assertFalse(self.viz.sr_mode)
        self.viz.toggle_sr_mode()
        self.viz.toggle_export_mode()
        self.assertFalse(self.viz.sr_mode)

    def test_theme_toggle_redraws_popups(self) -> None:
        self.enter_mode()
        self.click_candle(click_candidates(self.viz)[0])
        self.viz.toggle_dark_mode()
        self.assertEqual(len(self.viz._sr_popup_items), 8)
        fill = self.viz.canvas.itemcget(self.viz._sr_popup_items[0], "fill")
        self.assertEqual(fill, self.viz.get_theme()["canvas"])

    def test_window_first_matches_window_start(self) -> None:
        finder = self.viz.levels_for_chart()[0]
        dates: List[dt.date] = finder._dates
        for index in (len(dates) - 1, len(dates) // 2):
            for label in self.viz.sr_window_labels:
                first = finder.window_first(index, label)
                start = window_start(dates[index], label)
                self.assertGreaterEqual(dates[first], start)
                if first > 0:
                    self.assertLess(dates[first - 1], start)


if __name__ == "__main__":
    unittest.main()
