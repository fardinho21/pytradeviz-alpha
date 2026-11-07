import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace

from pytradeviz import PyTradeViz


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class CandleHeightScaleTests(unittest.TestCase):
    def setUp(self):
        data = [
            [["2022", "01", "01"], 0.7, 0.9, 0.6,
             0.8 if i % 2 else 0.65, {"rsi": 0}]
            for i in range(60)
        ]
        self.viz = PyTradeViz(tk, ttk, {"price_data": data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.update()

    def wheel(self, delta, widget=None):
        canvas = self.viz.canvas
        result = self.viz.scale_candle_height(SimpleNamespace(
            widget=widget or canvas, y=250, delta=delta, num=None
        ))
        self.viz.window.update()
        self.assertEqual(result, "break")

    def test_scale_clamps_and_returns_to_original_geometry(self):
        viz = self.viz
        canvas = viz.canvas
        candle = next(
            item for item in canvas.find_withtag("candle")
            if canvas.type(item) == "rectangle"
        )
        price_label = viz.canvas_price.find_withtag("price_label")[10]
        initial_candle = canvas.coords(candle)
        initial_label = viz.canvas_price.coords(price_label)
        initial_width = viz.chart_grid_space_x
        initial_height = viz.chart_grid_space_y
        initial_indicator = viz.canvas_indicators.coords(
            viz.canvas_indicators.find_withtag("indicator_level")[0]
        )
        for _ in range(20):
            self.wheel(120)
        self.assertEqual(viz.candle_height_scale, 2.5)
        self.assertAlmostEqual(viz.chart_grid_space_y, initial_height * 2.5)
        self.assertAlmostEqual(viz.chart_grid_space_x, initial_width)
        expanded = canvas.coords(candle)
        self.assertAlmostEqual(expanded[0], initial_candle[0])
        self.assertAlmostEqual(expanded[2], initial_candle[2])
        self.assertAlmostEqual(expanded[1], initial_candle[1] * 2.5)
        self.assertAlmostEqual(expanded[3], initial_candle[3] * 2.5)
        self.assertAlmostEqual(
            viz.canvas_price.coords(price_label)[1], initial_label[1] * 2.5
        )
        self.assertEqual(
            viz.canvas_indicators.coords(
                viz.canvas_indicators.find_withtag("indicator_level")[0]
            ), initial_indicator
        )

        canvas.yview_moveto(1)
        viz.window.update()
        for _ in range(20):
            self.wheel(-120)
        self.assertEqual(viz.candle_height_scale, 1.0)
        self.assertAlmostEqual(viz.chart_grid_space_y, initial_height)
        for actual, expected in zip(canvas.coords(candle), initial_candle):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(
            canvas.canvasy(0), viz.canvas_price.canvasy(0), delta=2
        )
        self.assertLess(canvas.canvasy(0), viz.chart_grid_space_y)

    def test_shift_wheel_bindings_and_pointer_anchor(self):
        viz = self.viz
        canvas = viz.canvas
        canvas.yview_moveto(0.25)
        viz.window.update()
        original_y = canvas.canvasy(250)
        canvas.event_generate("<Shift-Button-4>", x=400, y=250)
        viz.window.update()
        self.assertAlmostEqual(viz.candle_height_scale, 1.1)
        self.assertAlmostEqual(canvas.canvasy(250), original_y * 1.1, delta=2)
        self.assertAlmostEqual(canvas.canvasy(0), viz.canvas_price.canvasy(0), delta=2)
        viz.canvas_price.event_generate("<Shift-Button-5>", x=30, y=250)
        viz.window.update()
        self.assertAlmostEqual(viz.candle_height_scale, 1.0)
        for widget in (viz.canvas_date, viz.canvas_indicators):
            widget.event_generate("<Shift-Button-4>", x=30, y=20)
            viz.window.update()
        self.assertAlmostEqual(viz.candle_height_scale, 1.21)

    def test_independent_of_ctrl_zoom_and_window_resize(self):
        viz = self.viz
        self.wheel(120)
        viz.zoom_chart(SimpleNamespace(
            widget=viz.canvas, x=400, y=250, delta=120, num=None
        ))
        viz.window.update()
        viz.window.geometry("1400x900")
        viz.window.update()
        self.assertAlmostEqual(viz.candle_height_scale, 1.1)
        self.assertAlmostEqual(viz.zoom_level, 1.1)
        self.wheel(-120)
        self.assertEqual(viz.candle_height_scale, 1.0)
        self.assertAlmostEqual(viz.zoom_level, 1.1)
        self.assertAlmostEqual(
            viz.chart_grid_space_y, viz.base_chart_height * viz._scale_y
        )
        self.assertAlmostEqual(
            viz.canvas.canvasy(0), viz.canvas_price.canvasy(0), delta=2
        )


if __name__ == "__main__":
    unittest.main()
