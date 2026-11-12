from __future__ import annotations

import contextlib
import datetime
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from typing import Any, List
from unittest.mock import patch
from uuid import uuid4

from pytradeviz import PyTradeViz


def csv_text(days: int) -> str:
    """Descending daily OHLC rows with an extra column that must be ignored."""
    lines = ["Source line", "unix,Date,Symbol,OPEN,High,low,Close,Volume"]
    start = datetime.date(2020, 1, 1)
    for offset in range(days - 1, -1, -1):
        date = start + datetime.timedelta(days=offset)
        lines.append(f"0,{date.isoformat()} 00:00:00,XRP,1.0,2.0,0.5,1.5,99")
    return "\n".join(lines) + "\n"


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class DataFileWorkflowTests(unittest.TestCase):
    def make_viz(self, rows: List[List[Any]] | None = None) -> PyTradeViz:
        with contextlib.redirect_stdout(io.StringIO()):
            viz = PyTradeViz(tk, ttk, {"price_data": rows or []})
        self.addCleanup(viz.window.destroy)
        viz.window.update()
        return viz

    def make_file(self, text: str) -> Path:
        path = Path(__file__).parent / f".data-file-test-{uuid4().hex}.csv"
        path.write_text(text, encoding="utf-8", newline="")
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def open_file(self, viz: PyTradeViz, path: Path) -> None:
        with patch("pytradeviz.filedialog.askopenfilename", return_value=str(path)):
            viz.open_data_file()
        viz.window.update()

    def test_startup_without_data_shows_empty_chart_and_popup(self) -> None:
        viz = self.make_viz()
        self.assertFalse(viz.canvas.find_withtag("candle"))
        self.assertFalse(viz.canvas_indicators.find_withtag("rsi"))
        self.assertFalse(viz.canvas_price.find_withtag("price_label"))
        self.assertFalse(viz.canvas_date.find_withtag("ink"))
        self.assertTrue(viz.no_data_label.winfo_ismapped())
        self.assertIn("disabled", viz.load_more_button.state())

    def test_ascending_dollar_csv_with_plain_dates_opens(self) -> None:
        lines = ["Date,Volume,Open,High,Low,Close"]
        start = datetime.date(2020, 1, 1)
        for offset in range(30):
            date = start + datetime.timedelta(days=offset)
            lines.append(f"{date.isoformat()},10,$1.0,$2.0,$0.5,$1.5")
        viz = self.make_viz()
        self.open_file(viz, self.make_file("\n".join(lines) + "\n"))
        self.assertEqual(len(viz.price_data), 30)
        self.assertEqual(viz.price_data[0][0], ["2020", "01", "01"])
        self.assertFalse(viz.no_data_label.winfo_ismapped())

    def test_opening_a_file_loads_candles_and_hides_popup(self) -> None:
        viz = self.make_viz()
        path = self.make_file(csv_text(30))
        self.open_file(viz, path)
        self.assertEqual(len(viz.price_data), 30)
        self.assertEqual(len(viz.canvas.find_withtag("candle_29")), 2)
        self.assertTrue(viz.canvas_price.find_withtag("price_label"))
        self.assertTrue(viz.canvas_indicators.find_withtag("rsi"))
        self.assertFalse(viz.no_data_label.winfo_ismapped())

    def test_opened_chart_fits_current_window_size(self) -> None:
        viz = self.make_viz()
        viz.window.geometry("1400x900")
        viz.window.update()
        self.open_file(viz, self.make_file(csv_text(400)))
        self.assertEqual(viz._last_canvas_width, viz.canvas.winfo_width())
        self.assertEqual(viz._scale_x, viz.canvas.winfo_width() / viz.canvas_width)
        self.assertAlmostEqual(
            float(viz.canvas.cget("scrollregion").split()[2]), viz.chart_grid_space_x
        )

    def test_reopening_resets_zoom_and_view(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(400)))
        viz.zoom_level = 2.0
        viz.candle_height_scale = 1.5
        viz.canvas.xview_moveto(0.5)
        self.open_file(viz, self.make_file(csv_text(60)))
        self.assertEqual(viz.zoom_level, 1.0)
        self.assertEqual(viz.candle_height_scale, 1.0)
        self.assertEqual(viz.canvas.xview()[0], 0.0)
        self.assertEqual(len(viz.price_data), 60)
        self.assertEqual(len(viz.canvas.find_withtag("candle_59")), 2)

    def test_long_file_enables_paging_button(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(800)))
        self.assertNotIn("disabled", viz.load_more_button.state())
        viz.load_more_button.invoke()
        viz.window.update()
        self.assertGreater(len(viz.price_data), 365)

    def test_cancelled_open_keeps_current_state(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(10)))
        with patch("pytradeviz.filedialog.askopenfilename", return_value=""):
            viz.open_data_file()
        self.assertEqual(len(viz.price_data), 10)

    def test_invalid_file_reports_error_and_keeps_current_state(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(10)))
        bad = self.make_file("when,amount\n2020-01-01 00:00:00,5\n")
        with patch("pytradeviz.filedialog.askopenfilename", return_value=str(bad)), \
                patch("pytradeviz.messagebox.showerror") as showerror:
            viz.open_data_file()
        showerror.assert_called_once()
        self.assertEqual(len(viz.price_data), 10)
        self.assertEqual(len(viz.canvas.find_withtag("candle_9")), 2)

    def test_close_clears_data_selections_and_shows_popup(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(400)))
        viz.labeled_selections["sample"] = [{"open": 1.0}]
        viz.selected_indices = {0, 1}
        viz.close_data_file()
        viz.window.update()
        self.assertEqual(viz.price_data, [])
        self.assertEqual(viz.labeled_selections, {})
        self.assertIsNone(viz.data_source)
        self.assertFalse(viz.selected_indices)
        self.assertFalse(viz.canvas.find_withtag("candle"))
        self.assertFalse(viz.canvas_indicators.find_withtag("rsi"))
        self.assertFalse(viz.canvas_price.find_withtag("price_label"))
        self.assertFalse(viz.canvas_date.find_withtag("ink"))
        self.assertTrue(viz.no_data_label.winfo_ismapped())
        self.assertIn("disabled", viz.load_more_button.state())

    def test_close_then_reopen_restores_chart(self) -> None:
        viz = self.make_viz()
        self.open_file(viz, self.make_file(csv_text(40)))
        viz.close_data_file()
        self.open_file(viz, self.make_file(csv_text(25)))
        self.assertEqual(len(viz.price_data), 25)
        self.assertEqual(len(viz.canvas.find_withtag("candle_24")), 2)
        self.assertFalse(viz.canvas.find_withtag("candle_25"))
        self.assertFalse(viz.no_data_label.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
