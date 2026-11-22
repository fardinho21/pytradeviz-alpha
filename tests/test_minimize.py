from __future__ import annotations

import contextlib
import time
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, Callable, Iterator, List, Tuple
from unittest import mock

from indicators import BOLLINGER_PERIOD
from levels import WINDOW_LOOKBACKS
from pytradeviz import INDICATOR_TITLES, PyTradeViz
from test_roi import load_price_rows
from test_strategies_results import TradeListTestCase
from test_strategies_window import (
    assert_on_one_line, descendants, find_button, in_reading_order, opened_windows, positional_boxes,
    type_order,
)


# The windows that can be minimized, and the labels that lead to the menu item of each.
MENU_PATHS = {
    "Exponential": ("Indicators", "Moving Averages", "Exponential"),
    "Simple": ("Indicators", "Moving Averages", "Simple"),
    **{title: ("Indicators", title) for title in INDICATOR_TITLES.values()},
    "Bollinger Bands": ("Indicators", "Bollinger"),
    "Trend Identification": ("Indicators", "Trend Identification"),
    "Support and Resistance": ("Indicators", "Support and Resistance"),
    "Positional Strategy": ("Strategies", "Positional"),
    "Indicator Based Strategy": ("Strategies", "Indicator Based"),
    "Data": ("Data",),
}
# A point of the chart that the windows, which open over its middle, leave uncovered.
CHART_POINT = (40, 40)
# A point of a window between its edge and what it shows.
PADDING_POINT = (3, 3)


def choose_item(viz: PyTradeViz, *labels: str) -> None:
    """Choose an item of the menu bar, or of a menu under it, by the labels that lead to it."""
    menu = viz.menu_bar
    for label in labels[:-1]:
        menu = menu.nametowidget(menu.entrycget(label, "menu"))
    menu.invoke(labels[-1])
    viz.window.update()


def queue_press(widget: tk.Misc, x: int, y: int) -> None:
    """Have the left button pressed at a point of a widget when the next events are handled."""
    widget.event_generate("<ButtonPress-1>", x=x, y=y, when="tail")


def queue_release(widget: tk.Misc, x: int, y: int) -> None:
    # Tk keeps the mouse to the program from a press beside a window that holds the grab, and
    # lets go of it on a release that says the button was down.
    widget.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100, when="tail")


class MinimizeTestCase(TradeListTestCase):
    """The program on the sample prices, and what the tests of minimized windows do with it."""

    def build_app(self, rows: List[List[Any]], data_source: Any = None) -> None:
        super().build_app(rows, data_source)
        # Where the chart was pressed, which tells the clicks that reach it.
        self.presses: List[Tuple[int, int]] = []
        self.viz.canvas.bind(
            "<ButtonPress-1>", lambda event: self.presses.append((event.x, event.y)), add="+")

    def open_window(self, title: str) -> tk.Toplevel:
        """Choose the menu item of a window, and return the window that it opens."""
        before = opened_windows(self.viz.window)
        choose_item(self.viz, *MENU_PATHS[title])
        (window,) = [w for w in opened_windows(self.viz.window) if w not in before]
        self.assertEqual(window.title(), title)
        return window

    def minimize(self, window: tk.Toplevel) -> None:
        find_button(window, "Minimize").invoke()
        self.viz.window.update()

    def open_minimized(self, title: str) -> tk.Toplevel:
        window = self.open_window(title)
        self.minimize(window)
        return window

    def dock_buttons(self) -> List[ttk.Button]:
        """The buttons of the minimized windows, from left to right."""
        return self.viz.window_bar.pack_slaves()

    def dock(self) -> List[str]:
        return [button.cget("text") for button in self.dock_buttons()]

    def show_again(self, title: str) -> None:
        """Press the button of a minimized window."""
        (button,) = [b for b in self.dock_buttons() if b.cget("text") == title]
        button.invoke()
        self.viz.window.update()

    def click(self, widget: tk.Misc, x: int, y: int) -> None:
        queue_press(widget, x, y)
        queue_release(widget, x, y)
        self.viz.window.update()

    def wait_until(self, happened: Callable[[], bool]) -> None:
        """Handle events until the window manager has done what it was asked for, or two seconds pass."""
        deadline = time.monotonic() + 2
        while not happened() and time.monotonic() < deadline:
            self.viz.window.update()
            time.sleep(0.02)

    @contextlib.contextmanager
    def keyboard_given(self) -> Iterator[List[tk.Misc]]:
        """Collect the widgets that are given the keyboard while the block runs.

        Tk names the widget with the keyboard only while the screen gives the program the
        keys, and the widget that a window would pass them to is the same before and after.
        """
        given: List[tk.Misc] = []
        focus_set = tk.Misc.focus_set

        def record(widget: tk.Misc) -> None:
            given.append(widget)
            focus_set(widget)

        with mock.patch.object(tk.Misc, "focus_set", record):
            yield given

    def assert_minimized(self, *windows: tk.Toplevel) -> None:
        """Windows are hidden, and no window keeps the mouse and the keyboard to itself."""
        for window in windows:
            self.assertEqual(window.state(), "withdrawn", window.title())
        self.assertIsNone(self.viz.window.grab_current())

    def assert_shown(self, *windows: tk.Toplevel) -> None:
        """Windows are on the screen, and the last of them keeps the mouse and the keyboard to itself."""
        for window in windows:
            self.assertTrue(window.winfo_viewable(), window.title())
        self.assertEqual(str(self.viz.window.grab_current()), str(windows[-1]))


class MinimizeAndShowAgainTests(MinimizeTestCase):
    def test_every_window_of_the_menus_has_minimize_at_its_top_right(self) -> None:
        for title in MENU_PATHS:
            window = self.open_window(title)
            minimize = in_reading_order(window, tk.Button)[0]
            self.assertEqual(minimize.cget("text"), "Minimize", title)
            # It ends twelve pixels from the edge, as the rows under it do.
            right_edge = window.winfo_rootx() + window.winfo_width()
            self.assertEqual(right_edge - minimize.winfo_rootx() - minimize.winfo_width(), 12, title)
            # Everything else that the window shows is below it.
            bottom = minimize.winfo_rooty() + minimize.winfo_height()
            for widget in descendants(window, tk.Widget):
                if widget.winfo_viewable() and widget not in (minimize, minimize.master):
                    self.assertGreaterEqual(widget.winfo_rooty(), bottom, f"{title}: {widget}")
            window.destroy()
            self.viz.window.update()

    def test_reset_about_and_label_windows_cannot_be_minimized(self) -> None:
        openers = {
            "Reset": lambda: choose_item(self.viz, "Reset"),
            "About PyTradeViz": lambda: choose_item(self.viz, "File", "About"),
            "Label selection": lambda: self.viz.open_label_window({10, 11, 12}),
        }
        for title, open_it in openers.items():
            open_it()
            self.viz.window.update()
            (window,) = opened_windows(self.viz.window)
            self.assertEqual(window.title(), title)
            texts = [button.cget("text") for button in descendants(window, tk.Button)]
            self.assertNotIn("Minimize", texts, title)
            # A click on the chart is ignored, as it was before windows could be minimized.
            self.click(self.viz.canvas, *CHART_POINT)
            self.assert_shown(window)
            self.assertEqual(self.dock(), [])
            self.assertEqual(self.presses, [])
            window.destroy()
            self.viz.window.update()

    def test_minimize_hides_the_window_and_leaves_a_button_above_the_chart(self) -> None:
        chart_size = (self.viz.canvas.winfo_width(), self.viz.canvas.winfo_height())
        # The row of the buttons is not shown while it is empty.
        self.assertFalse(self.viz.window_bar.winfo_ismapped())
        window = self.open_window("Bollinger Bands")
        self.assert_shown(window)
        with self.keyboard_given() as given:
            self.minimize(window)
        self.assert_minimized(window)
        # The keys go to the main window again.
        self.assertEqual(given, [self.viz.window.focus_lastfor()])
        self.assertIs(given[0].winfo_toplevel(), self.viz.window)
        (button,) = self.dock_buttons()
        self.assertEqual(button.cget("text"), "Bollinger Bands")
        self.assertTrue(button.winfo_viewable())
        # The button is at the top left of the main window, above the chart and left of the tabs.
        self.assertEqual(button.winfo_rootx(), self.viz.window.winfo_rootx())
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), self.viz.canvas.winfo_rooty())
        self.assertLessEqual(
            button.winfo_rootx() + button.winfo_width(), self.viz.timeframe_buttons["Daily"].winfo_rootx())
        # The chart keeps its size.
        self.assertEqual((self.viz.canvas.winfo_width(), self.viz.canvas.winfo_height()), chart_size)

    def test_button_of_a_minimized_window_shows_it_again_as_it_was(self) -> None:
        window = self.open_window("Positional Strategy")
        type_order(window, "0.5", "10", "5")
        self.minimize(window)
        (button,) = self.dock_buttons()
        with self.keyboard_given() as given:
            self.click(button, 5, 5)
        self.assert_shown(window)
        # The button goes, and the row of the buttons with the last of them.
        self.assertEqual(self.dock(), [])
        self.assertFalse(self.viz.window_bar.winfo_ismapped())
        # What was typed is still there, and the keys go to the box that had them.
        boxes = positional_boxes(window)
        self.assertEqual([box.get() for box in boxes], ["0.5", "10", "0.55", "5", "0.475"])
        self.assertEqual(given, [boxes[0]])

    def test_window_is_shown_again_where_it_was(self) -> None:
        window = self.open_window("Bollinger Bands")
        # The window manager chooses the place of a new window, and would choose the same one
        # for a window that is shown again. The window is moved first to tell the two apart.
        x, y = window.winfo_rootx() + 80, window.winfo_rooty() + 60
        window.geometry(f"+{x}+{y}")
        self.wait_until(lambda: window.winfo_rootx() == x)
        # A window that was dragged there has a place that the program never asked for. The
        # request is taken back, or the window manager would keep to it by itself.
        window.positionfrom("")
        self.viz.window.update()
        place = (window.winfo_rootx(), window.winfo_rooty())

        def in_place() -> bool:
            return abs(window.winfo_rootx() - place[0]) <= 2 and abs(window.winfo_rooty() - place[1]) <= 2

        for _ in range(2):
            self.minimize(window)
            self.show_again("Bollinger Bands")
            self.wait_until(in_place)
            self.assertTrue(in_place(), f"{(window.winfo_rootx(), window.winfo_rooty())} is not {place}")

    def test_menu_item_of_a_minimized_window_shows_that_window_again(self) -> None:
        for title in MENU_PATHS:
            window = self.open_minimized(title)
            self.assertEqual(self.dock(), [title])
            choose_item(self.viz, *MENU_PATHS[title])
            # No second window is opened.
            self.assertEqual(opened_windows(self.viz.window), [window], title)
            self.assert_shown(window)
            self.assertEqual(self.dock(), [], title)
            window.destroy()
            self.viz.window.update()

    def test_each_minimized_window_has_a_button_of_its_own(self) -> None:
        titles = ["Bollinger Bands", "Data", "Positional Strategy"]
        windows = [self.open_minimized(title) for title in titles]
        self.assert_minimized(*windows)
        # The buttons stand side by side in the order of minimizing.
        self.assertEqual(self.dock(), titles)
        assert_on_one_line(self, self.dock_buttons())
        # Each shows its own window, and the others stay away.
        self.show_again("Data")
        self.assert_shown(windows[1])
        self.assertEqual([window.state() for window in windows], ["withdrawn", "normal", "withdrawn"])
        self.assertEqual(self.dock(), ["Bollinger Bands", "Positional Strategy"])
        # A window that is minimized again goes to the end of the row.
        self.minimize(windows[1])
        self.assertEqual(self.dock(), ["Bollinger Bands", "Positional Strategy", "Data"])

    def test_minimized_window_that_is_closed_takes_its_button_along(self) -> None:
        bollinger, data = (self.open_minimized(title) for title in ("Bollinger Bands", "Data"))
        bollinger.destroy()
        self.viz.window.update()
        self.assertEqual(self.dock(), ["Data"])
        # Its menu item opens a new window, and leaves the other one minimized.
        window = self.open_window("Bollinger Bands")
        self.assert_shown(window)
        self.assertEqual(data.state(), "withdrawn")
        window.destroy()
        data.destroy()
        self.viz.window.update()
        self.assertEqual(self.dock(), [])
        self.assertFalse(self.viz.window_bar.winfo_ismapped())

    def test_window_is_not_minimized_while_a_window_under_it_is_on_its_way_to_the_screen(self) -> None:
        window = self.open_window("Bollinger Bands")
        pending = tk.Toplevel(window)
        pending.withdraw()
        self.minimize(window)
        self.assert_shown(window)
        self.assertEqual(self.dock(), [])
        # It is minimized as usual once that window is out of the way.
        pending.destroy()
        self.minimize(window)
        self.assert_minimized(window)

    def test_program_closes_with_windows_minimized(self) -> None:
        self.open_minimized("Bollinger Bands")
        # A settings window with its help, and a window that is shown.
        levels = self.open_window("Support and Resistance")
        find_button(levels, "Help").invoke()
        self.viz.window.update()
        self.minimize(opened_windows(levels)[0])
        self.assertEqual(self.dock(), ["Bollinger Bands", "Support and Resistance"])
        self.open_window("Data")
        # The row of the buttons is destroyed before the windows, which then have no button to
        # take along. The close button in the title bar runs the WM_DELETE_WINDOW handler.
        self.viz.window.tk.eval(self.viz.window.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.callback_errors, [])
        # Nor is a call left behind for Tcl to make once the windows are gone.
        self.assertEqual(self.viz.window.tk.eval("after info"), "")


class ClickOutsideTests(MinimizeTestCase):
    def test_click_on_the_chart_minimizes_the_window_and_is_not_passed_on(self) -> None:
        window = self.open_window("Bollinger Bands")
        self.click(self.viz.canvas, *CHART_POINT)
        self.assert_minimized(window)
        self.assertEqual(self.dock(), ["Bollinger Bands"])
        # The click that put the window away did nothing to the chart. The next one reaches it.
        self.assertEqual(self.presses, [])
        self.click(self.viz.canvas, *CHART_POINT)
        self.assertEqual(self.presses, [CHART_POINT])
        self.assert_minimized(window)

    def test_clicks_inside_the_window_leave_it_open(self) -> None:
        window = self.open_window("Bollinger Bands")
        label, entry = descendants(window, tk.Label)[0], descendants(window, tk.Entry)[0]
        # A click on its padding is reported as a click beside it is, but lies inside it.
        for widget, point in ((window, PADDING_POINT), (label, (2, 2)), (entry, (2, 2))):
            self.click(widget, *point)
            self.assert_shown(window)
        self.assertEqual(self.dock(), [])

    def test_drag_that_starts_or_ends_on_the_window_leaves_it_open(self) -> None:
        window = self.open_window("Bollinger Bands")
        ends = ((self.viz.canvas, *CHART_POINT), (window, *PADDING_POINT))
        for pressed, released in (ends, ends[::-1]):
            queue_press(*pressed)
            queue_release(*released)
            self.viz.window.update()
            self.assert_shown(window)
        self.assertEqual(self.dock(), [])
        self.assertEqual(self.presses, [])
        # A whole click on the chart still minimizes it afterwards.
        self.click(self.viz.canvas, *CHART_POINT)
        self.assert_minimized(window)

    def test_click_on_the_menu_bar_minimizes_the_window(self) -> None:
        window = self.open_window("Bollinger Bands")
        # The bar lies above the top left corner of what the main window holds.
        self.click(self.viz.window, 50, -10)
        self.assert_minimized(window)
        self.assertEqual(self.dock(), ["Bollinger Bands"])

    def test_click_on_the_button_of_another_minimized_window_shows_that_window(self) -> None:
        data = self.open_minimized("Data")
        bollinger = self.open_window("Bollinger Bands")
        (button,) = self.dock_buttons()
        self.click(button, 5, 5)
        self.assert_shown(data)
        self.assertEqual(bollinger.state(), "withdrawn")
        self.assertEqual(self.dock(), ["Bollinger Bands"])

    def test_click_on_a_tab_that_lies_over_a_button_only_minimizes(self) -> None:
        tab = self.viz.timeframe_buttons["2W"]
        x = tab.winfo_rootx() + 5

        def under_the_tab() -> List[ttk.Button]:
            return [
                b for b in self.dock_buttons() if b.winfo_rootx() <= x < b.winfo_rootx() + b.winfo_width()]

        # Windows are minimized until the row of their buttons reaches under the tab.
        titles = iter(MENU_PATHS)
        while not under_the_tab():
            self.open_minimized(next(titles))
        window = self.open_window(next(titles))
        self.click(tab, 5, 5)
        # The window that was shown is minimized, and the one of the button stays minimized.
        self.assert_minimized(*opened_windows(self.viz.window))
        self.assertEqual(self.dock()[-1], window.title())
        # The tab was not told of the click either.
        self.assertEqual(self.viz.active_timeframe, "Daily")


class MinimizedHelpTests(MinimizeTestCase):
    def press_indicator_info(self) -> None:
        """Press the box at the right of the indicator chart, which opens Indicator Help."""
        canvas = self.viz.canvas_indicators
        x1, y1, x2, y2 = self.viz._indicator_info_box
        self.viz.on_indicators_press(SimpleNamespace(
            widget=canvas, x=int((x1 + x2) / 2 - canvas.canvasx(0)), y=int((y1 + y2) / 2)))
        self.viz.window.update()

    def test_help_is_minimized_and_shown_again_with_its_settings_window(self) -> None:
        levels = self.open_window("Support and Resistance")
        find_button(levels, "Help").invoke()
        self.viz.window.update()
        (help_window,) = opened_windows(levels)
        self.assert_shown(levels, help_window)
        # The two go together, under the name of the settings window.
        self.minimize(help_window)
        self.assert_minimized(levels, help_window)
        self.assertEqual(self.dock(), ["Support and Resistance"])
        self.show_again("Support and Resistance")
        self.assert_shown(levels, help_window)
        # A click on the settings window is not a click beside the two.
        self.click(levels, *PADDING_POINT)
        self.assert_shown(levels, help_window)
        # A click on the chart is, and the menu item brings the two back as the button does.
        self.click(self.viz.canvas, *CHART_POINT)
        self.assert_minimized(levels, help_window)
        choose_item(self.viz, *MENU_PATHS["Support and Resistance"])
        self.assert_shown(levels, help_window)
        self.assertEqual(opened_windows(self.viz.window), [levels])
        # Closing help leaves the settings window in use, as before.
        find_button(help_window, "Close").invoke()
        self.viz.window.update()
        self.assert_shown(levels)
        self.assertEqual(self.dock(), [])
        self.assertEqual(self.viz.window.tk.eval("after info"), "")

    def test_help_closed_while_it_is_minimized_leaves_the_settings_window_minimized(self) -> None:
        levels = self.open_window("Support and Resistance")
        find_button(levels, "Help").invoke()
        self.viz.window.update()
        (help_window,) = opened_windows(levels)
        self.minimize(help_window)
        help_window.destroy()
        self.viz.window.update()
        # The settings window does not take the mouse and the keyboard until it is shown.
        self.assert_minimized(levels)
        self.assertEqual(self.viz.window.tk.eval("after info"), "")
        self.show_again("Support and Resistance")
        self.assert_shown(levels)

    def test_indicator_help_of_the_chart_is_shown_again_instead_of_opened_twice(self) -> None:
        self.press_indicator_info()
        (help_window,) = opened_windows(self.viz.window)
        self.assertEqual(help_window.title(), "Indicator Help")
        self.minimize(help_window)
        self.assertEqual(self.dock(), ["Indicator Help"])
        self.press_indicator_info()
        self.assertEqual(opened_windows(self.viz.window), [help_window])
        self.assert_shown(help_window)
        self.assertEqual(self.dock(), [])


class ShownAgainTests(MinimizeTestCase):
    def test_data_window_lists_the_selections_labeled_while_it_was_minimized(self) -> None:
        nothing = ["No labeled selections yet."]
        data = self.open_window("Data")
        self.assertEqual([label.cget("text") for label in descendants(data, tk.Label)], nothing)
        self.minimize(data)
        self.viz.save_labeled_selection("Breakout", {10, 11, 12})
        self.show_again("Data")
        (listing,) = descendants(data, tk.Listbox)
        self.assertEqual(listing.get(0, "end"), ("Breakout: 3 candles",))
        self.assertEqual(descendants(data, tk.Label), [])
        # The selections go with the data file.
        self.minimize(data)
        choose_item(self.viz, "File", "Close Data File")
        self.show_again("Data")
        self.assertEqual(descendants(data, tk.Listbox), [])
        self.assertEqual([label.cget("text") for label in descendants(data, tk.Label)], nothing)

    def test_levels_window_reports_on_the_data_that_is_loaded_when_it_is_shown_again(self) -> None:
        levels = self.open_window("Support and Resistance")
        no_data = "No price data loaded"

        def texts() -> List[str]:
            return [label.cget("text") for label in descendants(levels, tk.Label)]

        self.assertNotIn(no_data, texts())
        self.minimize(levels)
        choose_item(self.viz, "File", "Close Data File")
        self.show_again("Support and Resistance")
        # One for each window of candles that levels are looked for in.
        self.assertEqual(texts().count(no_data), len(WINDOW_LOOKBACKS))
        self.minimize(levels)
        self.viz.replace_price_data(load_price_rows(), None)
        self.show_again("Support and Resistance")
        self.assertNotIn(no_data, texts())

    def test_trend_window_offers_volume_when_the_data_it_is_shown_again_on_has_it(self) -> None:
        trend = self.open_window("Trend Identification")
        (box,) = [b for b in descendants(trend, tk.Checkbutton) if b.cget("text") == "Include volume"]

        def notes() -> List[str]:
            return [text for text in (label.cget("text") for label in descendants(trend, tk.Label))
                    if "volume" in text]

        # The sample file has no volume.
        self.assertEqual(str(box.cget("state")), "disabled")
        self.assertEqual(notes(), ["The loaded data has no volume column."])
        self.minimize(trend)
        with_volume = [
            row[:5] + [dict(row[5], volume=1000.0 + index)] for index, row in enumerate(load_price_rows())]
        self.viz.replace_price_data(with_volume, None)
        self.show_again("Trend Identification")
        self.assertEqual(str(box.cget("state")), "normal")
        self.assertEqual(notes(), [])
        self.minimize(trend)
        self.viz.replace_price_data(load_price_rows(), None)
        self.show_again("Trend Identification")
        self.assertEqual(str(box.cget("state")), "disabled")
        self.assertEqual(notes(), ["The loaded data has no volume column."])

    def test_settings_typed_before_minimizing_are_applied_to_the_tab_that_is_shown(self) -> None:
        window = self.open_window("Bollinger Bands")
        period = descendants(window, tk.Entry)[0]
        period.delete(0, "end")
        period.insert(0, "30")
        self.minimize(window)
        self.viz.timeframe_buttons["2W"].invoke()
        self.viz.window.update()
        self.show_again("Bollinger Bands")
        # The window still holds what was typed, and Apply gives it to the tab that is shown.
        self.assertEqual(period.get(), "30")
        find_button(window, "Apply").invoke()
        find_button(window, "Close").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.bollinger_applied["period"], 30)
        self.viz.timeframe_buttons["Daily"].invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.bollinger_applied["period"], BOLLINGER_PERIOD)


if __name__ == "__main__":
    unittest.main()
