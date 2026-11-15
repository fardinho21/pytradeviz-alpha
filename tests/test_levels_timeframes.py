import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk

from levels import RESISTANCE, SUPPORT, Segment, merge_crowded_segments
from pytradeviz import PyTradeViz
from test_roi import load_price_rows
from timeframes import TIMEFRAMES, candle_ids, candle_last_rows, resample


def pixels(price: float) -> float:
    """1000 px per price unit, so a 14 px gap is 0.014 in price."""
    return -price * 1000.0


def level(start, end, price, kind=SUPPORT, origin=0, touches=1) -> Segment:
    return Segment(start, end, price, kind, origin, touches)


class CandleMappingTests(unittest.TestCase):
    def test_candle_ids_agree_with_resample_on_every_tab(self):
        rows = load_price_rows()
        for label in TIMEFRAMES:
            with self.subTest(label=label):
                ids = candle_ids(rows, label)
                self.assertEqual(len(ids), len(rows))
                last_rows = candle_last_rows(ids)
                self.assertEqual(len(last_rows), len(resample(rows, label)))
                self.assertEqual(last_rows, sorted(last_rows))
                self.assertEqual(last_rows[-1], len(rows) - 1)

    def test_last_row_of_each_candle_is_the_last_row_with_that_id(self):
        rows = load_price_rows()
        ids = candle_ids(rows, "1M")
        for candle, last in enumerate(candle_last_rows(ids)):
            self.assertEqual(ids[last], candle)
            self.assertTrue(last == len(ids) - 1 or ids[last + 1] != candle)


class MergeCrowdedSegmentsTests(unittest.TestCase):
    def test_uncrowded_levels_are_unchanged(self):
        spans = [level(0, 5, 1.0), level(0, 5, 2.0)]
        merged = merge_crowded_segments(spans, pixels)
        self.assertEqual(sorted(m.price for m in merged), [1.0, 2.0])
        self.assertEqual(len(merged), 2)

    def test_crowded_supports_average_to_one_touch_weighted_level(self):
        weak = level(0, 10, 1.000, origin=3, touches=2)
        strong = level(0, 10, 1.010, origin=7, touches=6)
        (merged,) = merge_crowded_segments([weak, strong], pixels)
        self.assertAlmostEqual(merged.price, (1.000 * 2 + 1.010 * 6) / 8)
        self.assertEqual((merged.start, merged.end), (0, 10))
        self.assertEqual((merged.origin, merged.touches), (7, 6))
        self.assertEqual(merged.kind, SUPPORT)

    def test_support_and_resistance_are_never_merged(self):
        merged = merge_crowded_segments(
            [level(0, 10, 1.000, SUPPORT), level(0, 10, 1.005, RESISTANCE)], pixels)
        self.assertEqual(sorted(m.kind for m in merged), [RESISTANCE, SUPPORT])
        self.assertEqual(len(merged), 2)

    def test_levels_farther_apart_than_the_gap_stay_separate(self):
        merged = merge_crowded_segments([level(0, 10, 1.0), level(0, 10, 1.1)], pixels)
        self.assertEqual(len(merged), 2)

    def test_levels_adjacent_in_time_at_the_same_price_join_into_one_span(self):
        merged = merge_crowded_segments(
            [level(0, 4, 1.000), level(5, 9, 1.005)], pixels)
        (only,) = merged
        self.assertEqual((only.start, only.end), (0, 9))

    def test_levels_with_a_gap_in_time_stay_separate(self):
        merged = merge_crowded_segments(
            [level(0, 4, 1.000), level(7, 9, 1.005)], pixels)
        self.assertEqual(len(merged), 2)

    def test_a_chain_of_bands_merges_through_the_middle(self):
        merged = merge_crowded_segments(
            [level(0, 2, 1.000), level(3, 5, 1.005), level(6, 8, 1.010)], pixels)
        (only,) = merged
        self.assertEqual((only.start, only.end), (0, 8))

    def test_result_does_not_depend_on_input_order(self):
        spans = [level(0, 10, 1.000, origin=1, touches=2),
                 level(0, 10, 1.010, origin=2, touches=5),
                 level(0, 10, 1.1)]
        first = merge_crowded_segments(spans, pixels)
        second = merge_crowded_segments(list(reversed(spans)), pixels)
        self.assertEqual(first, second)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class LevelsOnEveryTimeframeTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()
        self.viz.levels_applied["mode"] = "Segments"
        for label in ("1M", "2M", "3M", "6M"):
            self.viz.levels_applied["windows"][label]["enabled"] = True

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def drawn_lines(self) -> int:
        return sum(1 for item in self.viz._levels_items if self.viz.canvas.type(item) == "line")

    def test_levels_are_drawn_on_every_tab(self):
        for label in TIMEFRAMES:
            with self.subTest(tab=label):
                self.viz.select_timeframe(label)
                self.viz.window.update()
                self.viz.draw_levels()
                self.viz.window.update()
                self.assertGreater(self.drawn_lines(), 0)

    def test_status_text_is_the_same_on_every_tab(self):
        texts = set()
        for label in TIMEFRAMES:
            self.viz.select_timeframe(label)
            self.viz.window.update()
            texts.add(self.viz.levels_status_text("6M"))
        self.assertEqual(len(texts), 1)
        self.assertIn("n=", texts.pop())


if __name__ == "__main__":
    unittest.main()
