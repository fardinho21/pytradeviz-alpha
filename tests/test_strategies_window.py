from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import traceback
import unittest
from tkinter import ttk
from typing import Any, List
from unittest import mock

from pytradeviz import PyTradeViz
from test_roi import load_price_rows


def collect_callback_errors(test: unittest.TestCase, window: tk.Tk) -> List[str]:
    """Fail ``test`` when it ends if a Tk callback raised an error.

    Tk reports such an error instead of passing it on, so a button whose command fails would
    otherwise go unnoticed. Call this before adding the cleanup that destroys ``window``, so
    that errors raised while it is destroyed are counted too.
    """
    errors: List[str] = []

    def record(*error: Any) -> None:
        errors.append("".join(traceback.format_exception(*error)))

    window.report_callback_exception = record
    # A call that Tcl was left to make later fails without a word when its command is gone by
    # then, because tkinter ignores the errors of the event loop.
    window.tk.createcommand("record_background_error", lambda message, _options: errors.append(message))
    window.tk.call("interp", "bgerror", "", "record_background_error")
    test.addCleanup(lambda: test.assertEqual(errors, []))
    return errors


def descendants(widget: tk.Misc, cls: type) -> List[Any]:
    """The widgets of a class inside a window, leaving out those of windows opened from it."""
    found: List[Any] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Toplevel):
            continue
        if isinstance(child, cls):
            found.append(child)
        found.extend(descendants(child, cls))
    return found


def opened_windows(parent: tk.Misc) -> List[tk.Toplevel]:
    return [child for child in parent.winfo_children() if isinstance(child, tk.Toplevel)]


def strategies_menu(viz: PyTradeViz) -> tk.Menu:
    """The drop-down under Strategies in the menu bar."""
    return viz.menu_bar.nametowidget(viz.menu_bar.entrycget("Strategies", "menu"))


def open_positional_window(viz: PyTradeViz) -> tk.Toplevel:
    """Choose Positional from the Strategies drop-down and return the window it opens."""
    before = opened_windows(viz.window)
    strategies_menu(viz).invoke("Positional")
    viz.window.update()
    (window,) = [w for w in opened_windows(viz.window) if w not in before]
    return window


def positional_boxes(window: tk.Misc) -> List[tk.Entry]:
    """The entry price, ROI, target price, stop loss and stop price boxes, in reading order."""
    return sorted(descendants(window, tk.Entry), key=lambda box: (box.winfo_rooty(), box.winfo_rootx()))


def type_text(box: tk.Entry, text: str) -> None:
    # A key press inserts its character at the cursor, and the box checks each one.
    for character in text:
        box.insert("insert", character)


def type_order(window: tk.Misc, entry_price: str, roi: str, stop_loss: str) -> None:
    """Replace what the three boxes that can be typed in hold."""
    boxes = positional_boxes(window)
    for box, text in ((boxes[0], entry_price), (boxes[1], roi), (boxes[3], stop_loss)):
        box.delete(0, "end")
        type_text(box, text)


def find_button(window: tk.Misc, text: str) -> tk.Button:
    return next(b for b in descendants(window, tk.Button) if b.cget("text") == text)


def in_reading_order(window: tk.Misc, cls: type) -> List[Any]:
    return sorted(descendants(window, cls), key=lambda w: (w.winfo_rooty(), w.winfo_rootx()))


def assert_on_one_line(test: unittest.TestCase, widgets: List[Any]) -> None:
    """Each widget ends before the next one starts, and a level line crosses them all."""
    for left, right in zip(widgets, widgets[1:]):
        test.assertLessEqual(left.winfo_rootx() + left.winfo_width(), right.winfo_rootx())
    tops = [widget.winfo_rooty() for widget in widgets]
    bottoms = [widget.winfo_rooty() + widget.winfo_height() for widget in widgets]
    test.assertLess(max(tops), min(bottoms))


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class PositionalWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_price_rows()})
        collect_callback_errors(self, self.viz.window)
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def test_positional_item_opens_a_modal_window(self) -> None:
        window = open_positional_window(self.viz)
        self.assertEqual(window.title(), "Positional Strategy")
        self.assertTrue(window.winfo_viewable())
        self.assertEqual(str(window.grab_current()), str(window))

    def test_two_rows_hold_the_boxes_of_the_order(self) -> None:
        window = open_positional_window(self.viz)
        boxes = positional_boxes(window)
        labels = in_reading_order(window, tk.Label)
        self.assertEqual(len(boxes), 5)
        self.assertEqual(
            [label.cget("text") for label in labels],
            ["Entry price", "ROI (%)", "Target price", "Stop loss (%)", "Stop price"],
        )
        # Each label is followed by its box. The first three pairs share a line, and the stop
        # loss and stop price share the next one.
        pairs = [widget for pair in zip(labels, boxes) for widget in pair]
        first_row, second_row = pairs[:6], pairs[6:]
        assert_on_one_line(self, first_row)
        assert_on_one_line(self, second_row)
        first_row_bottom = max(widget.winfo_rooty() + widget.winfo_height() for widget in first_row)
        self.assertLessEqual(first_row_bottom, min(widget.winfo_rooty() for widget in second_row))
        # The stop loss is under the ROI, and the stop price under the target price.
        for above, below in zip(first_row[2:], second_row):
            self.assertEqual(above.winfo_rootx(), below.winfo_rootx())
        second_row_bottom = max(widget.winfo_rooty() + widget.winfo_height() for widget in second_row)
        # Minimize is above the boxes, and the buttons of the order are below them.
        minimize, *buttons = in_reading_order(window, tk.Button)
        self.assertEqual(minimize.cget("text"), "Minimize")
        first_row_top = min(widget.winfo_rooty() for widget in first_row)
        self.assertLessEqual(minimize.winfo_rooty() + minimize.winfo_height(), first_row_top)
        self.assertEqual([button.cget("text") for button in buttons], ["Test", "Cancel"])
        assert_on_one_line(self, buttons)
        for button in buttons:
            self.assertGreaterEqual(button.winfo_rooty(), second_row_bottom)

    def test_boxes_start_empty_with_the_entry_price_ready_for_typing(self) -> None:
        window = open_positional_window(self.viz)
        boxes = positional_boxes(window)
        self.assertEqual([box.get() for box in boxes], ["", "", "", "", ""])
        self.assertIs(window.focus_lastfor(), boxes[0])

    def test_target_price_follows_the_entry_price_and_roi(self) -> None:
        window = open_positional_window(self.viz)
        entry_price, roi, target, _stop_loss, stop = positional_boxes(window)
        type_text(roi, "10")
        self.assertEqual(target.get(), "")
        # Every character typed into the entry price moves the target price.
        shown = []
        for character in "19.99":
            type_text(entry_price, character)
            shown.append(target.get())
        self.assertEqual(shown, ["1.1", "20.9", "20.9", "21.89", "21.989"])
        type_text(roi, ".5")
        self.assertEqual(target.get(), "22.08895")
        # It is empty again while the ROI is not a number, here "" and then "-".
        roi.delete(0, "end")
        self.assertEqual(target.get(), "")
        type_text(roi, "-")
        self.assertEqual(target.get(), "")
        type_text(roi, "50")
        self.assertEqual(target.get(), "9.995")
        # The stop price needs the stop loss, which is still empty.
        self.assertEqual(stop.get(), "")

    def test_stop_price_follows_the_entry_price_and_stop_loss(self) -> None:
        window = open_positional_window(self.viz)
        entry_price, _roi, target, stop_loss, stop = positional_boxes(window)
        type_text(stop_loss, "5")
        self.assertEqual(stop.get(), "")
        shown = []
        for character in "19.99":
            type_text(entry_price, character)
            shown.append(stop.get())
        self.assertEqual(shown, ["0.95", "18.05", "18.05", "18.905", "18.9905"])
        type_text(stop_loss, ".5")
        self.assertEqual(stop.get(), "18.89055")
        # It is empty again while the stop loss or the entry price is not a number.
        stop_loss.delete(0, "end")
        self.assertEqual(stop.get(), "")
        type_text(stop_loss, "25")
        self.assertEqual(stop.get(), "14.9925")
        entry_price.delete(0, "end")
        self.assertEqual(stop.get(), "")
        # The target price needs the ROI, which is still empty.
        self.assertEqual(target.get(), "")

    def test_entry_price_box_takes_numbers_only(self) -> None:
        window = open_positional_window(self.viz)
        entry_price = positional_boxes(window)[0]
        for text in ("a", "-", "+", " ", "e", ",", "$", "1e5", "12abc", "１"):
            entry_price.insert("end", text)
            self.assertEqual(entry_price.get(), "", repr(text))
        type_text(entry_price, "12.5")
        self.assertEqual(entry_price.get(), "12.5")
        # A second decimal point is refused, and so is a letter put in the middle.
        entry_price.insert("end", ".")
        entry_price.insert(1, "x")
        self.assertEqual(entry_price.get(), "12.5")
        # A refused edit leaves the box checking the edits that follow.
        self.assertEqual(entry_price.cget("validate"), "key")
        type_text(entry_price, "0")
        self.assertEqual(entry_price.get(), "12.50")

    def test_roi_box_takes_numbers_only_and_may_be_negative(self) -> None:
        window = open_positional_window(self.viz)
        roi = positional_boxes(window)[1]
        for text in ("a", " ", "e", "%", "--", "1e-5"):
            roi.insert("end", text)
            self.assertEqual(roi.get(), "", repr(text))
        type_text(roi, "-7.5")
        self.assertEqual(roi.get(), "-7.5")
        # Only one sign is taken, and only at the start.
        roi.insert("end", "-")
        roi.insert(0, "-")
        roi.insert(2, "+")
        self.assertEqual(roi.get(), "-7.5")
        self.assertEqual(roi.cget("validate"), "key")
        roi.delete(0)
        roi.insert(0, "+")
        self.assertEqual(roi.get(), "+7.5")

    def test_stop_loss_box_takes_numbers_only_and_no_sign(self) -> None:
        window = open_positional_window(self.viz)
        stop_loss = positional_boxes(window)[3]
        for text in ("a", "-", "+", " ", "e", "%", "-5", "+5", "1e5", "５"):
            stop_loss.insert("end", text)
            self.assertEqual(stop_loss.get(), "", repr(text))
        type_text(stop_loss, "2.5")
        self.assertEqual(stop_loss.get(), "2.5")
        # A second decimal point is refused, and so is a sign put at the start.
        stop_loss.insert("end", ".")
        stop_loss.insert(0, "-")
        self.assertEqual(stop_loss.get(), "2.5")
        self.assertEqual(stop_loss.cget("validate"), "key")
        type_text(stop_loss, "0")
        self.assertEqual(stop_loss.get(), "2.50")

    def test_target_and_stop_price_boxes_cannot_be_edited(self) -> None:
        window = open_positional_window(self.viz)
        _entry_price, _roi, target, _stop_loss, stop = positional_boxes(window)
        type_order(window, "100", "5", "2")
        for box, price in ((target, "105"), (stop, "98")):
            self.assertEqual(box.cget("state"), "readonly")
            box.insert("end", "9")
            box.delete(0, "end")
            self.assertEqual(box.get(), price)

    def test_cancel_closes_the_window_and_tests_nothing(self) -> None:
        self.viz.set_selection({10, 11, 12}, None)
        view = self.viz.canvas.xview()
        window = open_positional_window(self.viz)
        type_order(window, "0.5", "10", "5")
        find_button(window, "Cancel").invoke()
        self.viz.window.update()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(opened_windows(self.viz.window), [])
        self.assertIsNone(self.viz.window.grab_current())
        # The chart is as it was. No trade is highlighted, because nothing was tested.
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.viz.selected_indices, {10, 11, 12})
        self.assertEqual(self.viz.canvas.xview(), view)

    def test_closing_the_window_from_its_title_bar_releases_its_variables(self) -> None:
        window = open_positional_window(self.viz)
        boxes = positional_boxes(window)
        type_order(window, "100", "5", "2")
        tcl = self.viz.window.tk
        names = [str(box.cget("textvariable")) for box in boxes]
        self.assertEqual([tcl.globalgetvar(name) for name in names], ["100", "5", "105", "2", "98"])
        # The close button in the title bar runs the window's WM_DELETE_WINDOW handler.
        tcl.eval(window.protocol("WM_DELETE_WINDOW"))
        self.viz.window.update()
        self.assertFalse(window.winfo_exists())
        self.assertIsNone(self.viz.window.grab_current())
        for name in names:
            self.assertFalse(tcl.getboolean(tcl.call("info", "exists", name)), name)

    def test_test_says_when_no_price_data_is_loaded(self) -> None:
        self.viz.close_data_file()
        self.viz.window.update()
        window = open_positional_window(self.viz)
        boxes = positional_boxes(window)
        type_order(window, "0.5", "10", "5")
        with mock.patch("pytradeviz.messagebox.showerror") as showerror:
            find_button(window, "Test").invoke()
            self.viz.window.update()
        showerror.assert_called_once_with("Unable to test", "No price data is loaded.", parent=window)
        # The window stays as it was, for when data has been loaded.
        self.assertEqual(opened_windows(window), [])
        self.assertEqual([box.get() for box in boxes], ["0.5", "10", "0.55", "5", "0.475"])
        self.assertEqual(str(window.grab_current()), str(window))

    def test_test_names_the_box_that_cannot_be_tested(self) -> None:
        window = open_positional_window(self.viz)
        boxes = positional_boxes(window)
        cases = (
            (("", "10", "5"), "Entry price must be a number greater than 0."),
            (("0.5", "-10", "5"), "ROI must be a number greater than 0."),
            (("0.5", "10", "100"), "Stop loss must be a number greater than 0 and less than 100."),
        )
        for order, message in cases:
            with self.subTest(order=order):
                type_order(window, *order)
                typed = [box.get() for box in boxes]
                with mock.patch("pytradeviz.messagebox.showerror") as showerror:
                    find_button(window, "Test").invoke()
                    self.viz.window.update()
                showerror.assert_called_once_with("Invalid setting", message, parent=window)
                # Nothing was tested, and the boxes keep what was typed so it can be put right.
                self.assertEqual(opened_windows(window), [])
                self.assertEqual(self.viz.trade_indices, set())
                self.assertEqual([box.get() for box in boxes], typed)
                self.assertEqual(str(window.grab_current()), str(window))


if __name__ == "__main__":
    unittest.main()
