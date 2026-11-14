from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Tuple
from unittest import mock

from labeled_selections import read_selections, write_selections
from pytradeviz import PyTradeViz
from test_roi import load_price_rows


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class ExportModeTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.viz.export_directory = self.temp_dir.name

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

    def drag_select(self, first: int, last: int) -> None:
        start = self.candle_center(first)
        end = self.candle_center(last)
        press = self.event_at(*start)
        release = self.event_at(*end)
        self.viz.scroll_start(press)
        self.viz.scroll_move(release)
        self.viz.select_candle(release)

    def test_export_button_toggles_mode_and_label(self) -> None:
        self.viz.export_button.invoke()
        self.assertTrue(self.viz.export_mode)
        self.assertIn("select and export mode", self.mode_label_text())
        self.viz.export_button.invoke()
        self.assertFalse(self.viz.export_mode)

    def test_export_mode_disables_select_and_roi(self) -> None:
        self.viz.selection_mode = True
        self.viz.toggle_export_mode()
        self.assertFalse(self.viz.selection_mode)
        self.assertFalse(self.viz.roi_mode)

    def test_box_select_in_export_mode_prompts_for_label(self) -> None:
        self.viz.toggle_export_mode()
        with mock.patch.object(self.viz, "open_label_window") as prompt:
            self.drag_select(2, 4)
        prompt.assert_called_once()
        self.assertEqual(prompt.call_args[0][0], {2, 3, 4})

    def test_saving_label_stores_candle_fields(self) -> None:
        self.viz.save_labeled_selection("breakout", {2, 3})
        records = self.viz.labeled_selections["breakout"]
        self.assertEqual(len(records), 2)
        expected_keys = {
            "open", "high", "low", "close", "rsi", "3d_sma", "7d_sma", "2wk_sma", "1mo_sma",
            "bollinger_middle", "bollinger_upper", "bollinger_lower",
            "top_bol_intersect", "btm_bol_intersect", "rsi_os", "rsi_ob",
        }
        self.assertEqual(set(records[0]), expected_keys)
        self.assertEqual(records[0]["open"], self.viz.price_data[2][1])
        self.assertEqual(records[0]["close"], self.viz.price_data[2][4])

    def test_saved_flags_match_band_and_rsi_rules(self) -> None:
        index = 40
        record = self.viz.labeled_candle_record(index)
        _, upper, lower = self.viz.indicators_object.calculate_bollinger()
        high, low = self.viz.price_data[index][2], self.viz.price_data[index][3]
        self.assertEqual(record["top_bol_intersect"], low <= upper[index] <= high)
        self.assertEqual(record["btm_bol_intersect"], low <= lower[index] <= high)
        previous = self.viz.price_data[index - 1][5]["rsi"]
        current = self.viz.price_data[index][5]["rsi"]
        self.assertEqual(record["rsi_ob"], (previous - 70) * (current - 70) < 0)
        self.assertEqual(record["rsi_os"], (previous - 30) * (current - 30) < 0)

    def test_first_candle_has_no_rsi_cross(self) -> None:
        record = self.viz.labeled_candle_record(0)
        self.assertIsNone(record["rsi_ob"])
        self.assertIsNone(record["rsi_os"])

    def test_saving_clears_the_selection(self) -> None:
        self.viz.set_selection({1, 2}, None)
        self.viz.save_labeled_selection("x", {1, 2})
        self.assertEqual(self.viz.selected_indices, set())

    def test_export_writes_json_and_xml_to_directory(self) -> None:
        self.viz.save_labeled_selection("up", {5})
        with mock.patch("pytradeviz.messagebox") as messages:
            self.viz.export_labeled_selections(self.viz.window, "json")
            self.viz.export_labeled_selections(self.viz.window, "xml")
        self.assertEqual(messages.showinfo.call_count, 2)
        files = sorted(os.listdir(self.temp_dir.name))
        self.assertEqual(len(files), 2)
        self.assertTrue(all(name.startswith("selections_") for name in files))
        for name in files:
            restored = read_selections(os.path.join(self.temp_dir.name, name))
            self.assertEqual(list(restored), ["up"])

    def test_export_with_no_selections_warns(self) -> None:
        with mock.patch("pytradeviz.messagebox") as messages:
            self.viz.export_labeled_selections(self.viz.window, "json")
        messages.showinfo.assert_called_once()
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_add_to_existing_merges_into_chosen_file(self) -> None:
        path = os.path.join(self.temp_dir.name, "selections_existing.json")
        write_selections(path, {"old": [{"open": 1.0, "high": None, "low": None, "close": None,
                                         "rsi": None, "3d_sma": None, "7d_sma": None,
                                         "2wk_sma": None, "1mo_sma": None}]})
        self.viz.save_labeled_selection("new", {3})
        with mock.patch("pytradeviz.filedialog.askopenfilename", return_value=path), \
                mock.patch("pytradeviz.messagebox"):
            self.viz.add_to_existing(self.viz.window)
        restored = read_selections(path)
        self.assertEqual(sorted(restored), ["new", "old"])
        self.assertEqual(len(restored["old"]), 1)

    def find_widget(self, parent, cls, text):
        for child in parent.winfo_children():
            if isinstance(child, cls) and child.cget("text") == text:
                return child
            found = self.find_widget(child, cls, text)
            if found is not None:
                return found
        return None

    def test_clear_removes_all_labeled_selections(self) -> None:
        self.viz.save_labeled_selection("up", {5})
        self.viz.save_labeled_selection("down", {6})
        with mock.patch("pytradeviz.messagebox") as messages:
            messages.askyesno.return_value = True
            self.viz.open_data_window(tk)
            self.addCleanup(self.destroy_toplevels)
            window = self.data_window()
            self.find_widget(window, tk.Button, "Clear").invoke()
        self.assertEqual(self.viz.labeled_selections, {})
        self.assertIsNotNone(self.find_widget(window, tk.Label, "No labeled selections yet."))

    def test_clear_is_kept_when_confirmation_is_declined(self) -> None:
        self.viz.save_labeled_selection("up", {5})
        with mock.patch("pytradeviz.messagebox") as messages:
            messages.askyesno.return_value = False
            self.viz.open_data_window(tk)
            self.addCleanup(self.destroy_toplevels)
            self.find_widget(self.data_window(), tk.Button, "Clear").invoke()
        self.assertEqual(list(self.viz.labeled_selections), ["up"])

    def data_window(self):
        return next(
            child for child in self.viz.window.winfo_children()
            if isinstance(child, tk.Toplevel) and child.title() == "Data"
        )

    def destroy_toplevels(self) -> None:
        for child in list(self.viz.window.winfo_children()):
            if isinstance(child, tk.Toplevel):
                child.destroy()

    def test_escape_exits_each_toolbox_mode(self) -> None:
        for toggle in (self.viz.toggle_selection_mode, self.viz.toggle_roi_mode, self.viz.toggle_export_mode):
            toggle()
            self.assertTrue(self.viz.gesture_active())
            self.press_escape()
            self.assertFalse(self.viz.gesture_active())
            self.assertEqual(self.mode_label_is_shown(), False)

    def test_escape_clears_the_selection(self) -> None:
        self.viz.toggle_selection_mode()
        self.viz.set_selection({1, 2}, None)
        self.press_escape()
        self.assertEqual(self.viz.selected_indices, set())

    def press_escape(self) -> None:
        # Synthesized key events need X keyboard focus, which another test process can
        # hold when tests run in parallel. The <Escape> binding only calls exit_modes().
        self.viz.exit_modes()

    def mode_label_is_shown(self) -> bool:
        return bool(self.viz.select_mode_label.winfo_ismapped())

    def mode_label_text(self) -> str:
        return self.viz.select_mode_label.cget("text")


if __name__ == "__main__":
    unittest.main()
