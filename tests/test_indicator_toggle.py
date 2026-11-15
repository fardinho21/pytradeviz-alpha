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
from typing import Any, List

from indicators import (
    ADX_PERIOD, ADX_TREND_LEVEL, Indicators, RSI_OVERBOUGHT, RSI_OVERSOLD, STOCH_D_COLOR,
    STOCH_D_PERIOD, STOCH_K_PERIOD, STOCH_OVERBOUGHT, STOCH_OVERSOLD, WILLIAMS_R_CANVAS_OFFSET,
    WILLIAMS_R_OVERBOUGHT, WILLIAMS_R_OVERSOLD, WILLIAMS_R_PERIOD, adx_components,
    stochastic_components, williams_r_values,
)
from indicators_help import INDICATOR_HELP
from pytradeviz import PyTradeViz


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "XRP_4_year_ohlc_no_vol.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[1:]
    return [
        [row[0].split("-"), *(float(v) for v in row[1:5]), {"rsi": None}]
        for row in rows
    ]


class ADXSeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()[:200]
        self.indicators = Indicators(price_data=self.price_data)

    def test_adx_matches_shared_components(self) -> None:
        highs = [row[2] for row in self.price_data]
        lows = [row[3] for row in self.price_data]
        closes = [row[4] for row in self.price_data]
        expected, _, _ = adx_components(highs, lows, closes, ADX_PERIOD)
        self.assertEqual(self.indicators.calculate_ADX(), expected)

    def test_adx_warms_up_for_two_periods(self) -> None:
        values = self.indicators.calculate_ADX()
        first = next(i for i, value in enumerate(values) if value is not None)
        self.assertEqual(first, 2 * ADX_PERIOD - 1)
        self.assertTrue(all(0 <= v <= 100 for v in values if v is not None))

    def test_adx_cache_is_recomputed_when_rows_are_added(self) -> None:
        short = self.indicators.calculate_ADX()
        self.indicators.price_data = self.price_data + load_price_rows()[200:260]
        longer = self.indicators.calculate_ADX()
        self.assertEqual(len(short), 200)
        self.assertEqual(len(longer), 260)

    def test_render_adx_draws_one_segment_per_value_on_the_100_pixel_scale(self) -> None:
        canvas = tk.Canvas(width=10, height=100)
        self.addCleanup(canvas.destroy)
        self.indicators.render_ADX(canvas, 3, 0, tags=("adx",), fill="black")
        values = [v for v in self.indicators.calculate_ADX() if v is not None]
        items = canvas.find_withtag("adx")
        self.assertEqual(len(items), len(values))
        last_x1, last_y1, last_x2, last_y2 = canvas.coords(items[-1])
        self.assertAlmostEqual(last_y2, 100 - values[-1])
        self.assertAlmostEqual(last_x2, 3 * (len(self.price_data) - 1))


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class StochasticSeriesTests(unittest.TestCase):
    def test_k_places_the_close_in_the_recent_range(self) -> None:
        highs = [10.0, 12.0, 14.0, 13.0]
        lows = [8.0, 9.0, 10.0, 9.0]
        closes = [9.0, 11.0, 12.0, 9.0]
        k, _ = stochastic_components(highs, lows, closes, k_period=3, d_period=2)
        self.assertEqual(k[:2], [None, None])
        # Window of candles 0..2: high 14, low 8, close 12 -> (12 - 8) / 6 * 100
        self.assertAlmostEqual(k[2], 100 * 4 / 6)
        # Window of candles 1..3: high 14, low 9, close 9 -> 0
        self.assertAlmostEqual(k[3], 0.0)

    def test_d_is_the_average_of_the_last_k_values(self) -> None:
        highs = [10.0, 12.0, 14.0, 13.0]
        lows = [8.0, 9.0, 10.0, 9.0]
        closes = [9.0, 11.0, 12.0, 9.0]
        k, d = stochastic_components(highs, lows, closes, k_period=3, d_period=2)
        self.assertIsNone(d[2])
        self.assertAlmostEqual(d[3], (k[2] + k[3]) / 2)

    def test_flat_range_reads_as_the_middle(self) -> None:
        flat = [5.0] * 5
        k, _ = stochastic_components(flat, flat, flat, k_period=3, d_period=3)
        self.assertEqual(k[2:], [50.0, 50.0, 50.0])

    def test_default_periods_match_the_app_settings(self) -> None:
        self.assertEqual((STOCH_K_PERIOD, STOCH_D_PERIOD), (14, 3))
        self.assertEqual((STOCH_OVERBOUGHT, STOCH_OVERSOLD), (80, 20))


class WilliamsRSeriesTests(unittest.TestCase):
    def test_r_places_the_close_in_the_recent_range(self) -> None:
        highs = [10.0, 12.0, 14.0, 13.0]
        lows = [8.0, 9.0, 10.0, 9.0]
        closes = [9.0, 11.0, 12.0, 9.0]
        r = williams_r_values(highs, lows, closes, period=3)
        self.assertEqual(r[:2], [None, None])
        # Window of candles 0..2: high 14, low 8, close 12 -> -100 * (14 - 12) / 6
        self.assertAlmostEqual(r[2], -100 * 2 / 6)
        # Window of candles 1..3: high 14, low 9, close 9 -> -100 * 5 / 5
        self.assertAlmostEqual(r[3], -100.0)

    def test_close_at_the_window_high_reads_zero_and_at_the_low_reads_minus_100(self) -> None:
        highs = [10.0, 11.0, 12.0, 12.0]
        lows = [5.0, 5.0, 5.0, 5.0]
        closes = [7.0, 7.0, 12.0, 5.0]
        r = williams_r_values(highs, lows, closes, period=3)
        self.assertAlmostEqual(r[2], 0.0)
        self.assertAlmostEqual(r[3], -100 * 7 / 7)

    def test_flat_range_reads_as_the_middle(self) -> None:
        flat = [5.0] * 5
        r = williams_r_values(flat, flat, flat, period=3)
        self.assertEqual(r[2:], [-50.0, -50.0, -50.0])

    def test_default_settings_match_the_app(self) -> None:
        self.assertEqual(WILLIAMS_R_PERIOD, 14)
        self.assertEqual((WILLIAMS_R_OVERBOUGHT, WILLIAMS_R_OVERSOLD), (-20, -80))
        self.assertEqual(WILLIAMS_R_CANVAS_OFFSET, 100)


class IndicatorToggleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()
        self.canvas = self.viz.canvas_indicators

    def click_toggle(self, mode: str) -> None:
        x1, y1, x2, y2 = self.viz._indicator_toggle_boxes[mode]
        event = SimpleNamespace(
            widget=self.canvas,
            x=int((x1 + x2) / 2 - self.canvas.canvasx(0)),
            y=int((y1 + y2) / 2),
        )
        self.viz.on_indicators_press(event)

    def level_ys(self) -> List[float]:
        return sorted(self.canvas.coords(item)[1] for item in self.canvas.find_withtag("indicator_level"))

    def test_rsi_is_the_default_and_both_toggle_boxes_exist(self) -> None:
        self.assertEqual(self.viz.indicator_mode, "RSI")
        self.assertEqual(set(self.viz._indicator_toggle_boxes), {"RSI", "ADX", "STOSC", "W%R"})
        self.assertTrue(self.canvas.find_withtag("rsi"))
        self.assertFalse(self.canvas.find_withtag("adx"))

    def test_rsi_levels_sit_where_the_rsi_values_plot(self) -> None:
        # An RSI of 70 plots at y = 30, so the overbought line must be drawn there.
        overbought_item = self.canvas.find_withtag("indicator_level")[0]
        self.assertEqual(self.canvas.itemcget(overbought_item, "fill"), "orange")
        self.assertEqual(self.canvas.coords(overbought_item)[1], 100 - RSI_OVERBOUGHT)

    def test_clicking_adx_switches_the_canvas_to_adx(self) -> None:
        self.click_toggle("ADX")

        self.assertEqual(self.viz.indicator_mode, "ADX")
        self.assertFalse(self.canvas.find_withtag("rsi"))
        self.assertTrue(self.canvas.find_withtag("adx"))
        self.assertEqual(self.level_ys(), [100 - ADX_TREND_LEVEL])

    def test_clicking_rsi_switches_back(self) -> None:
        self.click_toggle("ADX")
        self.click_toggle("RSI")

        self.assertEqual(self.viz.indicator_mode, "RSI")
        self.assertTrue(self.canvas.find_withtag("rsi"))
        self.assertFalse(self.canvas.find_withtag("adx"))
        self.assertEqual(self.level_ys(), [100 - RSI_OVERBOUGHT, 100 - RSI_OVERSOLD])

    def test_adx_series_matches_the_indicator_values(self) -> None:
        self.click_toggle("ADX")
        values = self.viz.indicators_object.calculate_ADX()
        last_value = [v for v in values if v is not None][-1]
        lines = self.canvas.find_withtag("adx")
        self.assertAlmostEqual(self.canvas.coords(lines[-1])[3], 100 - last_value)

    def test_active_box_is_filled_and_inactive_box_is_outlined(self) -> None:
        theme = self.viz.get_theme()
        self.click_toggle("ADX")
        for mode, expected in (("ADX", theme["ink"]), ("RSI", theme["canvas"])):
            x1, y1, _, _ = self.viz._indicator_toggle_boxes[mode]
            rect = self.canvas.find_overlapping(x1 + 1, y1 + 1, x1 + 2, y1 + 2)
            fills = [self.canvas.itemcget(i, "fill") for i in rect if self.canvas.type(i) == "rectangle"]
            self.assertEqual(fills, [expected])

    def test_toggle_click_does_not_scroll_the_chart(self) -> None:
        self.canvas.xview_moveto(0.2)
        self.viz.window.update()
        before = self.viz.canvas.xview()
        self.click_toggle("ADX")
        self.viz.window.update()
        self.assertEqual(self.viz.canvas.xview(), before)

    def test_toggles_stay_at_the_left_edge_after_scrolling(self) -> None:
        self.viz.canvas.xview_moveto(0.5)
        self.viz.window.update()
        self.viz.draw_overlays()
        x1, _, _, _ = self.viz._indicator_toggle_boxes["RSI"]
        self.assertAlmostEqual(x1, self.canvas.canvasx(0) + 4)

    def test_clicking_stosc_draws_k_and_d_with_the_stochastic_levels(self) -> None:
        self.click_toggle("STOSC")

        self.assertEqual(self.viz.indicator_mode, "STOSC")
        self.assertFalse(self.canvas.find_withtag("rsi"))
        self.assertFalse(self.canvas.find_withtag("adx"))
        self.assertTrue(self.canvas.find_withtag("stoch"))
        self.assertTrue(self.canvas.find_withtag("stoch_d"))
        self.assertEqual(self.level_ys(), [100 - STOCH_OVERBOUGHT, 100 - STOCH_OVERSOLD])

    def test_stosc_lines_end_at_the_latest_values(self) -> None:
        self.click_toggle("STOSC")
        k_values, d_values = self.viz.indicators_object.calculate_stochastic()
        last_k = [v for v in k_values if v is not None][-1]
        last_d = [v for v in d_values if v is not None][-1]
        k_line = [i for i in self.canvas.find_withtag("stoch") if i not in self.canvas.find_withtag("stoch_d")][-1]
        d_line = self.canvas.find_withtag("stoch_d")[-1]
        self.assertAlmostEqual(self.canvas.coords(k_line)[3], 100 - last_k)
        self.assertAlmostEqual(self.canvas.coords(d_line)[3], 100 - last_d)
        self.assertEqual(self.canvas.itemcget(d_line, "fill"), STOCH_D_COLOR)
        self.assertEqual(self.canvas.itemcget(d_line, "dash"), "4 4")

    def test_stosc_mode_survives_dark_mode_and_keeps_d_colour(self) -> None:
        self.click_toggle("STOSC")
        self.viz.toggle_dark_mode()
        self.assertEqual(self.viz.indicator_mode, "STOSC")
        d_line = self.canvas.find_withtag("stoch_d")[-1]
        self.assertEqual(self.canvas.itemcget(d_line, "fill"), STOCH_D_COLOR)
        k_line = [i for i in self.canvas.find_withtag("stoch") if i not in self.canvas.find_withtag("stoch_d")][-1]
        self.assertEqual(self.canvas.itemcget(k_line, "fill"), self.viz.get_theme()["ink"])

    def test_switching_away_from_stosc_clears_its_lines(self) -> None:
        self.click_toggle("STOSC")
        self.click_toggle("RSI")
        self.assertFalse(self.canvas.find_withtag("stoch"))
        self.assertFalse(self.canvas.find_withtag("stoch_d"))
        self.assertTrue(self.canvas.find_withtag("rsi"))

    def test_clicking_williams_draws_r_with_its_levels(self) -> None:
        self.click_toggle("W%R")

        self.assertEqual(self.viz.indicator_mode, "W%R")
        self.assertFalse(self.canvas.find_withtag("rsi"))
        self.assertFalse(self.canvas.find_withtag("adx"))
        self.assertFalse(self.canvas.find_withtag("stoch"))
        self.assertTrue(self.canvas.find_withtag("willr"))
        # -20 and -80 sit at 80 and 20 on the shifted canvas scale.
        self.assertEqual(self.level_ys(), sorted([
            100 - (WILLIAMS_R_OVERBOUGHT + WILLIAMS_R_CANVAS_OFFSET),
            100 - (WILLIAMS_R_OVERSOLD + WILLIAMS_R_CANVAS_OFFSET),
        ]))

    def test_williams_line_ends_at_the_latest_value_on_the_shifted_scale(self) -> None:
        self.click_toggle("W%R")
        last_r = [v for v in self.viz.indicators_object.calculate_williams_r() if v is not None][-1]
        line = self.canvas.find_withtag("willr")[-1]
        self.assertAlmostEqual(self.canvas.coords(line)[3], 100 - (last_r + WILLIAMS_R_CANVAS_OFFSET))

    def test_williams_mode_survives_dark_mode_toggle(self) -> None:
        self.click_toggle("W%R")
        self.viz.toggle_dark_mode()
        self.assertEqual(self.viz.indicator_mode, "W%R")
        line = self.canvas.find_withtag("willr")[-1]
        self.assertEqual(self.canvas.itemcget(line, "fill"), self.viz.get_theme()["ink"])

    def test_switching_away_from_williams_clears_its_line(self) -> None:
        self.click_toggle("W%R")
        self.click_toggle("RSI")
        self.assertFalse(self.canvas.find_withtag("willr"))
        self.assertTrue(self.canvas.find_withtag("rsi"))

    def test_adx_mode_survives_dark_mode_toggle(self) -> None:
        self.click_toggle("ADX")
        self.viz.toggle_dark_mode()
        self.assertEqual(self.viz.indicator_mode, "ADX")
        self.assertTrue(self.canvas.find_withtag("adx"))
        self.assertEqual(self.viz.get_theme()["canvas"], self.canvas.cget("background"))

    def info_event(self) -> SimpleNamespace:
        x1, y1, x2, y2 = self.viz._indicator_info_box
        return SimpleNamespace(
            widget=self.canvas,
            x=int((x1 + x2) / 2 - self.canvas.canvasx(0)),
            y=int((y1 + y2) / 2),
        )

    def test_info_box_sits_at_the_right_edge_and_follows_scrolling(self) -> None:
        self.viz.window.update()
        for position in (0.0, 0.5):
            self.viz.canvas.xview_moveto(position)
            self.viz.window.update()
            self.viz.draw_overlays()
            _, _, x2, _ = self.viz._indicator_info_box
            visible_right = self.canvas.canvasx(self.canvas.winfo_width())
            self.assertAlmostEqual(x2, visible_right - 4)
            self.assertTrue(self.canvas.find_withtag("indicator_info"))

    def test_info_click_opens_help_without_changing_the_mode(self) -> None:
        opened = []
        self.viz.open_indicator_help = lambda tk, parent: opened.append((tk, parent))
        self.viz.on_indicators_press(self.info_event())
        self.assertEqual(self.viz.indicator_mode, "RSI")
        self.assertEqual(len(opened), 1)
        self.assertIs(opened[0][1], self.viz.window)

    def test_info_window_opens_with_rsi_and_adx_help(self) -> None:
        self.viz.on_indicators_press(self.info_event())
        self.viz.window.update()
        windows = [
            child for child in self.viz.window.winfo_children()
            if isinstance(child, tk.Toplevel) and child.title() == "Indicator Help"
        ]
        self.assertEqual(len(windows), 1)
        windows[0].destroy()
        self.assertEqual(self.viz.indicator_mode, "RSI")

    def test_indicator_help_describes_both_indicators(self) -> None:
        headings = [heading for heading, _ in INDICATOR_HELP]
        self.assertTrue(any(h.startswith("RSI") for h in headings))
        self.assertTrue(any(h.startswith("ADX") for h in headings))
        self.assertTrue(any(h.startswith("STOSC") for h in headings))
        self.assertTrue(any(h.startswith("W%R") for h in headings))
        body = " ".join(p for _, paragraphs in INDICATOR_HELP for p in paragraphs)
        self.assertIn("25", body)
        self.assertIn("70", body)
        self.assertIn("30", body)
        self.assertIn("-20", body)
        self.assertIn("-80", body)


if __name__ == "__main__":
    unittest.main()
