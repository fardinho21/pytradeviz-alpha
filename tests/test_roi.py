from __future__ import annotations

import contextlib
import csv
import io
import itertools
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List, Tuple

from pytradeviz import PyTradeViz


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[2:]
    rows.reverse()
    return [
        [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]), {"rsi": None}]
        for row in rows
    ]


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class RoiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.viz.canvas.bbox(f"candle_{index}")
        return (x1 + x2) / 2, (y1 + y2) / 2

    def event_at(self, x: float, y: float) -> SimpleNamespace:
        canvas = self.viz.canvas
        local_x = int(x - canvas.canvasx(0))
        local_y = int(y - canvas.canvasy(0))
        return SimpleNamespace(
            widget=canvas, x=local_x, y=local_y,
            x_root=canvas.winfo_rootx() + local_x,
            y_root=canvas.winfo_rooty() + local_y,
        )

    def drag(self, start: Tuple[float, float], end: Tuple[float, float]) -> None:
        press = self.event_at(*start)
        release = self.event_at(*end)
        self.viz.scroll_start(press)
        self.viz.scroll_move(release)
        self.viz.select_candle(release)

    def click(self, x: float, y: float) -> None:
        event = self.event_at(x, y)
        self.viz.scroll_start(event)
        self.viz.select_candle(event)

    def visible_y(self, offset: float) -> float:
        return self.viz.canvas.canvasy(0) + offset

    def column_items(self) -> List[int]:
        return list(self.viz.canvas.find_withtag("selection"))

    def test_roi_button_toggles_mode_and_label(self) -> None:
        self.viz.roi_button.invoke()
        self.assertTrue(self.viz.roi_mode)
        self.assertEqual(self.viz.select_mode_label.cget("text"), "ROI mode enabled")
        self.assertTrue(self.viz.select_mode_label.place_info())
        self.assertIn("pressed", self.viz.roi_button.state())

        self.viz.roi_button.invoke()
        self.assertFalse(self.viz.roi_mode)
        self.assertEqual(self.viz.select_mode_label.place_info(), {})

    def test_roi_and_select_modes_are_mutually_exclusive(self) -> None:
        self.viz.toggle_roi_mode()
        self.viz.toggle_selection_mode()
        self.assertFalse(self.viz.roi_mode)
        self.assertTrue(self.viz.selection_mode)
        self.assertEqual(self.viz.select_mode_label.cget("text"), "select mode enabled")

        self.viz.toggle_roi_mode()
        self.assertTrue(self.viz.roi_mode)
        self.assertFalse(self.viz.selection_mode)

    def test_entering_roi_mode_clears_candle_selection(self) -> None:
        self.click(*self.candle_center(10))
        self.assertEqual(self.viz.selected_indices, {10})
        self.viz.toggle_roi_mode()
        self.assertEqual(self.viz.selected_indices, set())
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def expected_results(self, entry_index: int, exit_index: int) -> List[Tuple[str, float]]:
        entry_row = self.price_data[entry_index]
        exit_row = self.price_data[exit_index]
        results = []
        for (_, entry_abbr, entry_col), (_, exit_abbr, exit_col) in itertools.product(
            self.viz.roi_price_fields, repeat=2
        ):
            entry, exit_ = entry_row[entry_col], exit_row[exit_col]
            results.append((f"ent({entry_abbr}):ext({exit_abbr}) -> ",
                            (exit_ - entry) / entry * 100))
        return sorted(results, key=lambda result: -result[1])

    def test_drag_reports_all_ohlc_pairings_from_entry_and_exit_candles(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))

        results = self.viz.roi_results
        self.assertEqual(len(results), 16)
        for (label, percent), (expected_label, expected) in zip(
            results, self.expected_results(10, 40)
        ):
            self.assertEqual(label, expected_label)
            self.assertAlmostEqual(percent, expected, places=6)
        self.assertEqual(self.viz.roi_header,
                         f"Entry: {'-'.join(self.price_data[10][0])}  "
                         f"Exit: {'-'.join(self.price_data[40][0])}")

    def test_pairing_rows_use_ohlc_abbreviations(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        labels = {name.cget("text") for name, _ in self.viz.roi_row_labels}
        self.assertEqual(labels, {f"ent({a}):ext({b}) -> " for a in "OHLC" for b in "OHLC"})
        self.assertIn("ent(O):ext(C) -> ", labels)

    def test_rows_are_sorted_from_highest_roi_to_lowest(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        percents = [percent for _, percent in self.viz.roi_results]
        self.assertEqual(percents, sorted(percents, reverse=True))
        displayed = [name.cget("text") for name, _ in self.viz.roi_row_labels]
        self.assertEqual(displayed, [label for label, _ in self.viz.roi_results])
        self.assertEqual(displayed[0], self.expected_results(10, 40)[0][0])

    def test_row_values_are_green_for_gains_and_red_for_losses(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        theme = self.viz.get_theme()
        for (_, value), (_, percent) in zip(self.viz.roi_row_labels, self.viz.roi_results):
            self.assertEqual(value.cget("text"), f"{percent:+.2f}%")
            if percent > 0:
                self.assertEqual(value.cget("fg"), theme["gain"])
            elif percent < 0:
                self.assertEqual(value.cget("fg"), theme["loss"])

    def test_reversed_drag_uses_press_candle_as_entry(self) -> None:
        self.viz.toggle_roi_mode()
        # Right to left: the press candle (40) is still the entry.
        self.drag((self.candle_center(40)[0], self.visible_y(320)),
                  (self.candle_center(10)[0], self.visible_y(120)))
        for (label, percent), (expected_label, expected) in zip(
            self.viz.roi_results, self.expected_results(40, 10)
        ):
            self.assertEqual(label, expected_label)
            self.assertAlmostEqual(percent, expected, places=6)

    def test_column_spans_full_height_between_click_and_release(self) -> None:
        self.viz.toggle_roi_mode()
        start = (self.candle_center(10)[0], self.visible_y(120))
        end = (self.candle_center(40)[0], self.visible_y(320))
        self.drag(start, end)

        items = self.column_items()
        self.assertEqual(len(items), 1)
        x1, y1, x2, y2 = self.viz.canvas.coords(items[0])
        self.assertAlmostEqual(x1, min(start[0], end[0]), delta=2)
        self.assertAlmostEqual(x2, max(start[0], end[0]), delta=2)
        self.assertEqual(y1, 0)
        self.assertEqual(y2, self.viz.chart_grid_space_y)
        self.assertEqual(self.viz.canvas.type(items[0]), "rectangle")
        self.assertEqual(self.viz.canvas.itemcget(items[0], "dash"), "4 4")

    def test_drag_highlights_candles_inside_column(self) -> None:
        self.viz.toggle_roi_mode()
        start = (self.candle_center(10)[0] - 5, self.visible_y(120))
        end = (self.candle_center(14)[0] + 5, self.visible_y(320))
        self.drag(start, end)
        self.assertEqual(self.viz.selected_indices, set(range(10, 15)))

    def test_roi_panel_replaces_ohlc_popup(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        self.assertTrue(self.viz.roi_panel.place_info())
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def test_mode_label_sits_below_roi_panel(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        self.viz.window.update()
        panel_bottom = 8 + self.viz.roi_panel.winfo_reqheight()
        self.assertGreater(int(self.viz.select_mode_label.place_info()["y"]), panel_bottom)

    def test_click_in_roi_mode_shows_no_ohlc_popup(self) -> None:
        self.viz.toggle_roi_mode()
        self.click(*self.candle_center(10))
        self.assertEqual(self.viz.candle_info_label.place_info(), {})
        self.assertEqual(self.viz.roi_panel.place_info(), {})
        self.assertIsNone(self.viz.roi_results)

    def test_click_without_drag_clears_roi(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        self.click(*self.candle_center(60))
        self.assertIsNone(self.viz.roi_results)
        self.assertEqual(self.viz.selected_indices, set())
        self.assertEqual(self.column_items(), [])
        self.assertEqual(self.viz.roi_panel.place_info(), {})
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def test_leaving_roi_mode_clears_column_and_result(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(40)[0], self.visible_y(320)))
        self.viz.toggle_roi_mode()
        self.assertIsNone(self.viz.roi_results)
        self.assertEqual(self.column_items(), [])
        self.assertEqual(self.viz.roi_panel.place_info(), {})
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def test_roi_drag_does_not_pan_the_chart(self) -> None:
        self.viz.toggle_roi_mode()
        before = self.viz.canvas.xview()
        self.drag((self.candle_center(10)[0], self.visible_y(120)),
                  (self.candle_center(200)[0], self.visible_y(320)))
        self.assertEqual(self.viz.canvas.xview(), before)


if __name__ == "__main__":
    unittest.main()
