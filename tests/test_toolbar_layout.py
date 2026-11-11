from __future__ import annotations

import contextlib
import io
import os
import platform
import sys
import tkinter as tk
import tkinter.font as tkfont
import unittest
from tkinter import ttk

from pytradeviz import PyTradeViz
from test_roi import load_price_rows


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class ToolbarLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def test_roi_button_is_sized_to_its_text(self) -> None:
        text_width = tkfont.nametofont("TkDefaultFont").measure("ROI")
        self.assertLessEqual(self.viz.roi_button.winfo_reqwidth(), text_width + 16)

    def test_price_canvas_fills_its_column(self) -> None:
        frame = self.viz.frame_canvas_price
        self.assertEqual(frame.winfo_x(), self.viz.mode_button_frame.winfo_x())
        self.assertEqual(frame.winfo_x() + frame.winfo_width(), self.viz.scrollbar_vertical.winfo_x())
        self.assertEqual(self.viz.canvas_price.winfo_width(), frame.winfo_width())

    def destroy_window(self) -> None:
        # The Exit menu item may already have destroyed the window.
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def menu_labels(self, menu: tk.Menu) -> list:
        last = menu.index("end")
        if last is None:
            return []
        return [menu.entrycget(i, "label") for i in range(last + 1)]

    def test_menu_bar_structure(self) -> None:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        self.assertEqual(self.menu_labels(menu_bar), ["File", "Indicators", "Strategies"])
        indicators = menu_bar.nametowidget(menu_bar.entrycget(1, "menu"))
        self.assertEqual(self.menu_labels(indicators), ["Moving Averages", "RSI", "Bollinger"])
        moving_averages = indicators.nametowidget(indicators.entrycget(0, "menu"))
        self.assertEqual(self.menu_labels(moving_averages), ["Exponential", "Simple"])

    def file_menu(self) -> tk.Menu:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        return menu_bar.nametowidget(menu_bar.entrycget(0, "menu"))

    def test_strategies_item_does_nothing(self) -> None:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        before = set(self.viz.window.winfo_children())
        menu_bar.invoke(2)
        self.viz.window.update()
        self.assertTrue(self.viz.window.winfo_exists())
        self.assertEqual(set(self.viz.window.winfo_children()), before)

    def test_file_menu_items(self) -> None:
        self.assertEqual(
            self.menu_labels(self.file_menu()),
            ["Open Data File", "Close Data File", "About", "Exit"],
        )

    def test_about_item_opens_modal_with_program_info(self) -> None:
        before = set(self.viz.window.winfo_children())
        self.file_menu().invoke(2)
        self.viz.window.update()
        opened = [w for w in self.viz.window.winfo_children()
                  if isinstance(w, tk.Toplevel) and w not in before]
        self.assertEqual([w.title() for w in opened], ["About PyTradeViz"])
        text = " ".join(label.cget("text") for label in opened[0].winfo_children()
                        if isinstance(label, tk.Label))
        self.assertIn("alpha 0.0.1", text)
        self.assertIn(platform.python_version(), text)

    def test_exit_item_closes_program(self) -> None:
        self.file_menu().invoke(3)
        with self.assertRaises(tk.TclError):
            self.viz.window.winfo_exists()

    def test_open_and_close_data_file_items_do_nothing(self) -> None:
        self.file_menu().invoke(0)
        self.file_menu().invoke(1)
        self.assertTrue(self.viz.window.winfo_exists())

    def test_moving_average_item_opens_modal_window(self) -> None:
        menu_bar = self.viz.window.nametowidget(self.viz.window.cget("menu"))
        indicators = menu_bar.nametowidget(menu_bar.entrycget(1, "menu"))
        moving_averages = indicators.nametowidget(indicators.entrycget(0, "menu"))
        before = set(self.viz.window.winfo_children())
        moving_averages.invoke(1)
        self.viz.window.update()
        opened = [w for w in self.viz.window.winfo_children()
                  if isinstance(w, tk.Toplevel) and w not in before]
        self.assertEqual([w.title() for w in opened], ["Simple"])
        self.assertTrue(opened[0].winfo_children(), "Simple window should show its controls")


if __name__ == "__main__":
    unittest.main()
