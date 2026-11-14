from __future__ import annotations

import datetime
import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace

from drawings import LINE, SOLID, Drawing
from indicators import SMA_PERIODS
from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz
from test_roi import load_price_rows
from timeframes import DAILY, timeframe_rows

MONTH_NAMES = {datetime.date(2000, m, 1).strftime("%b")[:2] for m in range(1, 13)}
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "data.csv"
SMA_PERIOD = SMA_PERIODS[0]


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class TimeframeTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_price_rows()
        self.viz = PyTradeViz(tk, ttk, {"price_data": self.rows})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800+0+0")
        self.viz.window.update()

    def tab(self, label: str) -> None:
        self.viz.timeframe_buttons[label].invoke()
        self.viz.window.update()

    def wheel(self, delta: int) -> None:
        self.viz.zoom_chart(SimpleNamespace(
            widget=self.viz.canvas, x=400, y=250, delta=delta, num=None
        ))
        self.viz.window.update()

    def test_daily_is_pressed_and_tabs_are_in_top_row(self) -> None:
        viz = self.viz
        self.assertEqual(viz.active_timeframe, DAILY)
        self.assertTrue(viz.timeframe_buttons[DAILY].instate(["pressed"]))
        self.assertFalse(viz.timeframe_buttons["1M"].instate(["pressed"]))
        self.assertEqual(int(viz.timeframe_bar.grid_info()["row"]), 0)
        self.assertEqual(
            [viz.timeframe_buttons[label].cget("text") for label in ("Daily", "2W", "1M", "2M", "3M", "6M")],
            ["Daily", "2W", "1M", "2M", "3M", "6M"],
        )

    def test_switching_tabs_charts_aggregated_candles_and_rsi(self) -> None:
        viz = self.viz
        self.tab("1M")
        monthly = timeframe_rows(self.rows, "1M")
        self.assertEqual(viz.active_timeframe, "1M")
        self.assertEqual(len(viz.price_data), len(monthly))
        self.assertEqual(len(viz.canvas.find_withtag("candle")), 2 * len(monthly))
        self.assertTrue(viz.timeframe_buttons["1M"].instate(["pressed"]))
        self.assertFalse(viz.timeframe_buttons[DAILY].instate(["pressed"]))
        rsi = [row[5]["rsi"] for row in viz.price_data if row[5]["rsi"] is not None]
        self.assertTrue(rsi, "RSI should be computed on the monthly candles")
        self.assertTrue(all(0 <= value <= 100 for value in rsi))

    def test_every_tab_charts_its_own_candles(self) -> None:
        viz = self.viz
        for label in ("2W", "1M", "2M", "3M", "6M", DAILY):
            self.tab(label)
            expected = timeframe_rows(self.rows, label)
            self.assertEqual(len(viz.price_data), len(expected), label)
            self.assertEqual(len(viz.canvas.find_withtag("candle")), 2 * len(expected), label)

    def test_returning_to_daily_restores_daily_rows(self) -> None:
        viz = self.viz
        self.tab("2M")
        self.tab(DAILY)
        self.assertIs(viz.price_data, viz._daily_rows)
        self.assertEqual(len(viz.price_data), len(self.rows))
        self.assertEqual(len(viz.canvas.find_withtag("candle")), 2 * len(self.rows))

    def test_drawings_are_kept_per_tab(self) -> None:
        viz = self.viz
        drawing = Drawing(id=1, kind=LINE, style=SOLID, color="Blue", filled=False,
                          start=(2.0, 100.0), end=(5.0, 100.0))
        viz.drawings = (drawing,)
        self.tab("1M")
        self.assertEqual(viz.drawings, ())
        self.tab(DAILY)
        self.assertEqual(viz.drawings, (drawing,))

    def test_indicator_settings_start_from_current_then_diverge(self) -> None:
        viz = self.viz
        viz.sma_applied[SMA_PERIOD]["enabled"] = True
        self.tab("3M")
        self.assertTrue(viz.sma_applied[SMA_PERIOD]["enabled"])
        viz.sma_applied[SMA_PERIOD]["enabled"] = False
        self.tab(DAILY)
        self.assertTrue(viz.sma_applied[SMA_PERIOD]["enabled"])
        self.tab("3M")
        self.assertFalse(viz.sma_applied[SMA_PERIOD]["enabled"])

    def test_zoom_and_candle_scale_restored_per_tab(self) -> None:
        viz = self.viz
        self.wheel(120)
        viz.scale_candle_height(SimpleNamespace(
            widget=viz.canvas, y=250, delta=120, num=None
        ))
        viz.window.update()
        zoom, candle = viz.zoom_level, viz.candle_height_scale
        grid_x, grid_y = viz.chart_grid_space_x, viz.chart_grid_space_y
        self.assertNotEqual(zoom, 1.0)
        self.assertNotEqual(candle, 1.0)

        self.tab("6M")
        self.assertEqual((viz.zoom_level, viz.candle_height_scale), (1.0, 1.0))
        self.tab(DAILY)
        self.assertAlmostEqual(viz.zoom_level, zoom)
        self.assertAlmostEqual(viz.candle_height_scale, candle)
        self.assertAlmostEqual(viz.chart_grid_space_x, grid_x)
        self.assertAlmostEqual(viz.chart_grid_space_y, grid_y)

    def test_scroll_position_restored_per_tab(self) -> None:
        viz = self.viz
        self.wheel(120)
        viz.canvas.xview_moveto(0.3)
        viz.window.update()
        position = viz.canvas.xview()[0]
        self.tab("2M")
        self.tab(DAILY)
        self.assertAlmostEqual(viz.canvas.xview()[0], position, places=2)

    def test_monthly_tabs_show_month_and_year_labels_only(self) -> None:
        self.tab("1M")
        texts = self.date_texts()
        self.assertTrue(texts)
        for text in texts:
            self.assertTrue(text in MONTH_NAMES or text.startswith("Y"), text)
        self.tab(DAILY)
        day_texts = self.date_texts()
        self.assertTrue(any(text.isdigit() for text in day_texts))

    def date_texts(self):
        canvas = self.viz.canvas_date
        return [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]

    def test_switching_tab_leaves_draw_and_sr_modes(self) -> None:
        viz = self.viz
        viz.toggle_sr_mode()
        viz.window.update()
        self.assertTrue(viz.sr_mode)
        self.tab("1M")
        self.assertFalse(viz.sr_mode)

    def test_tabs_are_inert_without_data(self) -> None:
        viz = self.viz
        viz.replace_price_data([], None)
        viz.window.update()
        for button in viz.timeframe_buttons.values():
            self.assertTrue(button.instate(["disabled"]))
        viz.select_timeframe("1M")
        self.assertEqual(viz.active_timeframe, DAILY)

    def test_loading_a_new_file_resets_tabs_to_daily(self) -> None:
        viz = self.viz
        self.tab("1M")
        viz.replace_price_data(self.rows, None)
        viz.window.update()
        self.assertEqual(viz.active_timeframe, DAILY)
        self.assertEqual(viz._tab_states.keys(), {DAILY})
        self.assertTrue(viz.timeframe_buttons[DAILY].instate(["pressed"]))


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class DerivedTabLoadMoreTests(unittest.TestCase):
    def test_load_more_on_monthly_tab_extends_daily_rows_and_keeps_view(self) -> None:
        source = PaginatedPriceData(DATA_PATH)
        initial = source.load_initial()
        viz = PyTradeViz(tk, ttk, {"price_data": initial}, data_source=source)
        self.addCleanup(viz.window.destroy)
        viz.window.geometry("1200x800+0+0")
        viz.window.update()
        viz.timeframe_buttons["1M"].invoke()
        viz.window.update()
        daily_before = len(viz._daily_rows)
        monthly_before = len(viz.price_data)
        self.assertTrue(source.has_more)

        viz.load_more_button.invoke()
        viz.window.update()

        self.assertGreater(len(viz._daily_rows), daily_before)
        self.assertEqual(viz.active_timeframe, "1M")
        self.assertGreater(len(viz.price_data), monthly_before)
        self.assertEqual(
            len(viz.price_data), len(timeframe_rows(viz._daily_rows, "1M"))
        )
        self.assertEqual(len(viz.canvas.find_withtag("candle")), 2 * len(viz.price_data))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class AxisCrowdingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800+0+0")
        self.viz.window.update()

    def zoom_out(self, steps: int) -> None:
        for _ in range(steps):
            self.viz.zoom_chart(SimpleNamespace(
                widget=self.viz.canvas, x=400, y=250, delta=-1, num=None
            ))
        self.viz.window.update()

    def visible_price_ys(self):
        canvas = self.viz.canvas_price
        return sorted(
            canvas.coords(item)[1]
            for item in canvas.find_withtag("price_label")
            if canvas.itemcget(item, "state") != "hidden"
        )

    def test_zoomed_out_price_labels_keep_a_readable_gap(self) -> None:
        self.zoom_out(30)
        self.assertEqual(self.viz.zoom_level, self.viz.min_zoom_level)
        ys = self.visible_price_ys()
        self.assertGreater(len(ys), 1)
        gaps = [later - earlier for earlier, later in zip(ys, ys[1:])]
        self.assertTrue(all(gap >= self.viz.min_price_label_gap - 1e-6 for gap in gaps), gaps)

    def test_zoomed_in_price_labels_are_all_visible(self) -> None:
        total = len(self.viz.canvas_price.find_withtag("price_label"))
        self.assertEqual(len(self.visible_price_ys()), total)
