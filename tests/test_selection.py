from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, List, Tuple

from candle import Candle
from pytradeviz import PyTradeViz


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[2:]
    rows.reverse()
    return [
        [row[1].split(" ")[0].split("-"), *(float(v) for v in row[3:7]), {"rsi": 0}]
        for row in rows
    ]


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def candle_bounds(self, index: int) -> Tuple[float, float, float, float]:
        return self.viz.canvas.bbox(f"candle_{index}")

    def candle_center(self, index: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.candle_bounds(index)
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

    def select_range(self, first: int, last: int) -> None:
        self.viz.toggle_selection_mode()
        left = self.candle_center(first)[0] - 10
        right = self.candle_center(last)[0] + 10
        middle_y = self.candle_center(first)[1]
        self.drag((left, middle_y - 200), (right, middle_y + 200))

    def body_color(self, index: int) -> str:
        item = next(i for i in self.viz.canvas.find_withtag(f"candle_{index}")
                    if self.viz.canvas.type(i) == "rectangle")
        key = "outline" if self.viz.dark_mode else "fill"
        return self.viz.canvas.itemcget(item, key)

    def selection_items(self) -> List[int]:
        return list(self.viz.canvas.find_withtag("selection"))

    def test_toggle_shows_and_hides_select_label(self) -> None:
        self.viz.toggle_selection_mode()
        self.assertTrue(self.viz.selection_mode)
        self.assertTrue(self.viz.select_mode_label.place_info())
        self.assertEqual(self.viz.select_mode_label.cget("text"), "select mode enabled")
        self.viz.toggle_selection_mode()
        self.assertFalse(self.viz.selection_mode)
        self.assertEqual(self.viz.select_mode_label.place_info(), {})

    def test_select_label_sits_below_ohlc_box(self) -> None:
        self.viz.toggle_selection_mode()
        info = self.viz.select_mode_label.place_info()
        self.assertEqual(info["anchor"], "ne")
        self.assertGreater(self.viz.select_label_y, 8)

    def test_select_icon_stays_black_in_dark_mode(self) -> None:
        icon = self.viz.select_icon
        self.assertEqual(icon.get(4, 8), (0, 0, 0))
        self.viz.toggle_dark_mode()
        self.assertIn(str(icon), self.viz.select_button.cget("image"))
        self.assertEqual(icon.get(4, 8), (0, 0, 0))

    def test_ohlc_labels_use_avg_suffix_only_in_selection_mode(self) -> None:
        self.click(*self.candle_center(10))
        self.assertIn("\nO: ", self.viz.candle_info_label.cget("text"))
        self.viz.toggle_selection_mode()
        self.click(*self.candle_center(10))
        self.assertIn("\nO_avg: ", self.viz.candle_info_label.cget("text"))
        self.assertIn("\nC_avg: ", self.viz.candle_info_label.cget("text"))

    def test_box_select_chooses_candles_inside_box(self) -> None:
        self.select_range(10, 14)
        self.assertEqual(self.viz.selected_indices, set(range(10, 15)))

    def test_summary_is_average_of_selected_candles(self) -> None:
        self.select_range(10, 14)
        rows = self.price_data[10:15]
        expected = [round(sum(r[k] for r in rows) / 5, 4) for k in (1, 2, 3, 4)]
        text = self.viz.candle_info_label.cget("text")
        lines = text.split("\n")
        self.assertIn("(5 candles)", lines[0])
        self.assertEqual(lines[1:], [
            f"O_avg: {expected[0]}", f"H_avg: {expected[1]}",
            f"L_avg: {expected[2]}", f"C_avg: {expected[3]}",
        ])
        self.assertTrue(self.viz.candle_info_label.place_info())

    def test_click_selects_single_candle_and_empty_click_clears(self) -> None:
        self.viz.toggle_selection_mode()
        self.click(*self.candle_center(10))
        self.assertEqual(self.viz.selected_indices, {10})
        self.click(self.candle_center(10)[0] + 15, self.candle_center(10)[1])
        self.assertEqual(self.viz.selected_indices, set())
        self.assertEqual(self.viz.candle_info_label.place_info(), {})

    def test_drag_in_selection_mode_does_not_scroll(self) -> None:
        self.viz.toggle_selection_mode()
        before = self.viz.canvas.xview()
        x, y = self.candle_center(10)
        self.drag((x, y), (x + 150, y + 60))
        self.assertEqual(self.viz.canvas.xview(), before)

    def test_box_is_drawn_while_dragging(self) -> None:
        self.viz.toggle_selection_mode()
        x, y = self.candle_center(10)
        press = self.event_at(x, y)
        self.viz.scroll_start(press)
        self.viz.scroll_move(self.event_at(x + 120, y + 80))
        items = self.selection_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(self.viz.canvas.type(items[0]), "rectangle")
        self.assertEqual(self.viz.canvas.itemcget(items[0], "dash"), "4 4")

    def test_box_colors_follow_theme(self) -> None:
        self.viz.toggle_selection_mode()
        x, y = self.candle_center(10)
        self.viz.scroll_start(self.event_at(x, y))
        self.viz.scroll_move(self.event_at(x + 120, y + 80))
        cases = {False: "#8c8c8c", True: "#e0894f"}
        for dark, color in cases.items():
            with self.subTest(dark_mode=dark):
                if self.viz.dark_mode != dark:
                    self.viz.toggle_dark_mode()
                item = self.selection_items()[0]
                self.assertEqual(self.viz.canvas.itemcget(item, "fill"), color)
                self.assertEqual(self.viz.canvas.itemcget(item, "outline"), color)
                self.assertEqual(self.viz.canvas.itemcget(item, "stipple"), "gray50")

    def test_selected_candles_are_highlighted_in_light_mode(self) -> None:
        plain = self.body_color(11)
        self.select_range(10, 12)
        highlighted = self.body_color(11)
        self.assertNotEqual(highlighted, plain)
        self.assertEqual(highlighted, self.viz.highlight_color(plain))

    def test_unselected_candles_keep_base_color(self) -> None:
        plain = self.body_color(20)
        self.select_range(10, 12)
        self.assertEqual(self.body_color(20), plain)

    def test_selected_candles_are_highlighted_in_dark_mode(self) -> None:
        self.viz.toggle_dark_mode()
        plain = self.body_color(11)
        self.select_range(10, 12)
        self.assertEqual(self.body_color(11), self.viz.highlight_color(plain))
        self.assertNotEqual(self.body_color(11), plain)

    def test_toggling_selection_mode_off_clears_selection(self) -> None:
        plain = self.body_color(12)
        self.select_range(10, 14)
        self.viz.toggle_selection_mode()
        self.assertEqual(self.viz.selected_indices, set())
        self.assertEqual(self.viz.candle_info_label.place_info(), {})
        self.assertEqual(self.selection_items(), [])
        self.assertEqual(self.body_color(12), plain)

    def test_selection_survives_theme_toggle(self) -> None:
        self.select_range(10, 12)
        self.viz.toggle_dark_mode()
        self.assertEqual(self.viz.selected_indices, {10, 11, 12})
        base = Candle.color_for(self.price_data[11][1], self.price_data[11][4])
        self.assertEqual(self.body_color(11), self.viz.highlight_color(base))


if __name__ == "__main__":
    unittest.main()
