from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Iterable, Set, Tuple
from unittest import mock

from candle import Candle
from test_minimize import CHART_POINT, MinimizeTestCase, choose_item, queue_press, queue_release
from test_strategies_window import descendants, find_button, opened_windows, positional_boxes, type_order


# Orders as they are typed in the Positional window: the entry price, the ROI and the stop loss.
ORDER = ("0.5", "10", "5")
ONE_TRADE = ("1.9", "100", "50")


class MinimizedTradeListTests(MinimizeTestCase):
    def press_test(self, window: tk.Toplevel) -> Tuple[tk.Toplevel, ttk.Treeview]:
        """Press Test in a strategy window. Return the window that lists the trades, and its list."""
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        return results, tree

    def positional_results(self, *order: str) -> Tuple[tk.Toplevel, tk.Toplevel, ttk.Treeview]:
        """Test an order from a new Positional window. Return that window, the list window and its list."""
        window = self.open_window("Positional Strategy")
        type_order(window, *order)
        return (window, *self.press_test(window))

    def rule_results(self) -> Tuple[tk.Toplevel, tk.Toplevel, ttk.Treeview]:
        """Test the rules that a new Indicator Based window starts with."""
        window = self.open_window("Indicator Based Strategy")
        return (window, *self.press_test(window))

    def holding_candles(self, days: Iterable[int]) -> Set[int]:
        """The candles of the tab that is shown which hold some days of the sample file."""
        # A candle starts on the date it shows and holds the days up to the next candle.
        starts = [row[0] for row in self.viz.price_data]
        return {
            max(index for index, start in enumerate(starts) if start <= self.rows[day][0]) for day in days}

    def assert_highlighted(self, candles: Set[int]) -> None:
        """Some candles of the tab that is shown are drawn as those of trades, and the rest as usual."""
        self.assertEqual(self.viz.trade_indices, candles)
        for index, row in enumerate(self.viz.price_data):
            plain = Candle.color_for(row[1], row[4])
            color = self.viz.highlight_color(plain) if index in candles else plain
            self.assertEqual(self.body_color(index), color, index)

    def test_list_is_minimized_and_shown_again_with_its_strategy_window(self) -> None:
        window, results, tree = self.positional_results(*ORDER)
        self.assert_shown(window, results)
        self.assertEqual(
            [button.cget("text") for button in descendants(results, tk.Button)], ["Minimize", "Close"])
        # A click on the chart puts the two away, under the name of the strategy window.
        self.click(self.viz.canvas, *CHART_POINT)
        self.assert_minimized(window, results)
        self.assertEqual(self.dock(), ["Positional Strategy"])
        self.assertEqual(self.presses, [])
        with self.keyboard_given() as given:
            self.show_again("Positional Strategy")
        self.assert_shown(window, results)
        # The list has the keys again, so the arrow keys step through the trades.
        self.assertEqual(given, [tree])
        # Minimize in the list does what the click did, and the menu item what the button did.
        self.minimize(results)
        self.assert_minimized(window, results)
        choose_item(self.viz, "Strategies", "Positional")
        self.assert_shown(window, results)
        self.assertEqual(opened_windows(self.viz.window), [window])
        # Closing the list leaves an empty Positional window in use, as before.
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assert_shown(window)
        self.assertEqual([box.get() for box in positional_boxes(window)], [""] * 5)
        self.assertEqual(self.dock(), [])
        self.assertEqual(self.viz.window.tk.eval("after info"), "")

    def test_trades_stay_highlighted_on_every_tab_while_the_list_is_minimized(self) -> None:
        window, results, tree = self.positional_results(*ORDER)
        days = set(self.viz.trade_indices)
        self.assertEqual(len(days), 60)
        self.minimize(results)
        self.assert_highlighted(days)
        # Another tab highlights its candles that hold the days of the trades.
        self.viz.timeframe_buttons["2W"].invoke()
        self.viz.window.update()
        candles = self.holding_candles(days)
        self.assertEqual(len(candles), 17)
        self.assert_highlighted(candles)
        # A trade that is selected once the list is shown again is shown on that tab. The trade
        # of 21 December 2020 is in the two weeks that start on the 14th.
        self.show_again("Positional Strategy")
        self.assert_highlighted(candles)
        self.assertEqual(tree.item("20", "values")[0], "2020-12-21")
        self.assertEqual(self.holding_candles({962}), {69})
        tree.selection_set("20")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 69)
        self.minimize(results)
        self.viz.timeframe_buttons["Daily"].invoke()
        self.viz.window.update()
        self.assert_highlighted(days)

    def test_showing_a_list_again_leaves_the_chart_where_it_is(self) -> None:
        window, results, tree = self.positional_results(*ORDER)
        self.minimize(results)
        # The chart is scrolled away from the trade that is selected in the list.
        self.viz.canvas.xview_moveto(0.5)
        self.viz.window.update()
        view = self.viz.canvas.xview()
        self.show_again("Positional Strategy")
        self.assertEqual(tree.selection(), ("0",))
        self.assertEqual(self.viz.canvas.xview(), view)

    def test_trades_of_the_list_that_was_opened_or_shown_last_are_highlighted(self) -> None:
        positional, order_list, _ = self.positional_results(*ORDER)
        order_days = set(self.viz.trade_indices)
        self.minimize(order_list)
        rules, rule_list, _ = self.rule_results()
        rule_days = set(self.viz.trade_indices)
        self.assertEqual((len(order_days), len(rule_days)), (60, 38))
        self.assert_highlighted(rule_days)
        # Minimizing a list changes nothing. Showing the other one highlights its trades.
        self.minimize(rule_list)
        self.assertEqual(self.dock(), ["Positional Strategy", "Indicator Based Strategy"])
        self.assert_highlighted(rule_days)
        self.show_again("Positional Strategy")
        self.assert_highlighted(order_days)
        self.minimize(order_list)
        self.assert_highlighted(order_days)
        self.show_again("Indicator Based Strategy")
        self.assert_highlighted(rule_days)
        # A list that is closed gives the highlights back to the one that is left.
        find_button(rule_list, "Close").invoke()
        self.viz.window.update()
        self.assert_shown(rules)
        self.assert_highlighted(order_days)
        self.minimize(rules)
        self.show_again("Positional Strategy")
        find_button(order_list, "Close").invoke()
        self.viz.window.update()
        self.assert_shown(positional)
        self.assert_highlighted(set())

    def check_data_file_change_closes_the_lists(self, change: Callable[[], Any], candles_left: int) -> None:
        window = self.open_window("Positional Strategy")
        boxes = positional_boxes(window)
        # The stop loss is the last box typed in before Test is pressed.
        boxes[3].focus_set()
        type_order(window, *ORDER)
        results, _ = self.press_test(window)
        self.assertIs(window.focus_lastfor(), boxes[3])
        self.minimize(results)
        bollinger = self.open_minimized("Bollinger Bands")
        change()
        self.viz.window.update()
        self.assertEqual(len(self.viz.price_data), candles_left)
        # The trades were found in the data that is gone, so their list goes with it.
        self.assertFalse(results.winfo_exists())
        self.assert_highlighted(set())
        # The other windows stay minimized.
        self.assert_minimized(window, bollinger)
        self.assertEqual(self.dock(), ["Positional Strategy", "Bollinger Bands"])
        with self.keyboard_given() as given:
            self.show_again("Positional Strategy")
        self.assert_shown(window)
        self.assertEqual(opened_windows(window), [])
        # The Positional window is ready for another order, as it is after its list is closed.
        self.assertEqual([box.get() for box in boxes], [""] * 5)
        self.assertEqual(given, [boxes[0]])
        self.assertIs(window.focus_lastfor(), boxes[0])
        self.assertEqual(self.viz.window.tk.eval("after info"), "")

    def test_opening_a_data_file_closes_the_minimized_lists(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "XRP_4_year_ohlc_no_vol.csv"

        def open_file() -> None:
            with mock.patch("pytradeviz.filedialog.askopenfilename", return_value=str(path)):
                choose_item(self.viz, "File", "Open Data File")

        # A file that is opened shows its first page.
        self.check_data_file_change_closes_the_lists(open_file, 365)

    def test_closing_the_data_file_closes_the_minimized_lists(self) -> None:
        self.check_data_file_change_closes_the_lists(
            lambda: choose_item(self.viz, "File", "Close Data File"), 0)

    def test_load_more_keeps_the_trades_of_a_minimized_list_highlighted(self) -> None:
        self.build_paginated_app()
        tested = "15 trades. 365 daily candles tested, from 2018-05-04 to 2019-05-03."
        window, results, tree = self.positional_results(*ORDER)
        self.assertEqual(self.summary(results).splitlines()[0], tested)
        days = set(self.viz.trade_indices)
        self.assertEqual(len(days), 30)
        self.minimize(results)
        # The button that loads the next page of the file is in reach of the mouse now.
        self.viz.load_more_button.invoke()
        self.viz.window.update()
        self.assertEqual(len(self.viz.price_data), 457)
        self.assert_highlighted(days)
        # The candles of another tab are made again from the days that are loaded.
        self.viz.timeframe_buttons["1M"].invoke()
        self.viz.window.update()
        months = len(self.viz.price_data)
        self.viz.load_more_button.invoke()
        self.viz.window.update()
        self.assertGreater(len(self.viz.price_data), months)
        self.assert_highlighted(self.holding_candles(days))
        # The list still shows the trades of the candles that were tested.
        self.show_again("Positional Strategy")
        self.assert_shown(window, results)
        self.assertEqual(self.summary(results).splitlines()[0], tested)
        self.assertEqual(len(tree.get_children()), 15)

    def check_list_made_while_its_window_is_minimized(self, minimize: Callable[[tk.Toplevel], Any]) -> None:
        self.build_paginated_app()
        window = self.open_window("Indicator Based Strategy")
        load_pages = self.viz.load_pages

        def load_then_minimize(*args: Any, **options: Any) -> None:
            load_pages(*args, **options)
            # What is done while the file loads waits for the event loop, which runs after it.
            minimize(window)

        with mock.patch.object(self.viz, "load_pages", side_effect=load_then_minimize):
            results, tree = self.press_test(window)
        self.assertEqual(len(self.viz.price_data), 1392)
        # The list is made out of sight, and waits with the window that it belongs to.
        self.assert_minimized(window, results)
        self.assertEqual(self.dock(), ["Indicator Based Strategy"])
        self.assertEqual(self.presses, [])
        # Its trades are highlighted and the first of them is selected, as in a list that is shown.
        days = set(self.viz.trade_indices)
        self.assertEqual((len(tree.get_children()), len(days)), (19, 38))
        self.assert_highlighted(days)
        self.assertEqual(tree.selection(), ("0",))
        # That trade is shown in the middle of the chart, no part of which the hidden windows cover.
        dates = ["-".join(row[0]) for row in self.viz.price_data]
        bought = dates.index(tree.item("0", "values")[0])
        width = self.viz.canvas.winfo_width()
        self.assert_shown_within((0, width), bought)
        left, _top, right, _bottom = self.view_box(bought)
        self.assertTrue(left <= width / 2 <= right, (left, right))
        with self.keyboard_given() as given:
            self.show_again("Indicator Based Strategy")
        self.assert_shown(window, results)
        # The list has the keys, as one that is opened on the screen has.
        self.assertEqual(given, [tree])
        self.assertIs(results.focus_lastfor(), tree)
        self.assertEqual(self.viz.window.tk.eval("after info"), "")

    def test_list_of_a_window_minimized_by_its_button_while_the_file_loads_waits_with_it(self) -> None:
        self.check_list_made_while_its_window_is_minimized(
            lambda window: window.after(0, find_button(window, "Minimize").invoke))

    def test_list_of_a_window_minimized_by_a_click_on_the_chart_while_the_file_loads_waits_with_it(
        self,
    ) -> None:
        def click_on_the_chart(_window: tk.Toplevel) -> None:
            queue_press(self.viz.canvas, *CHART_POINT)
            queue_release(self.viz.canvas, *CHART_POINT)

        self.check_list_made_while_its_window_is_minimized(click_on_the_chart)

    def test_selection_made_on_the_chart_while_a_list_is_minimized_is_kept(self) -> None:
        window, results, tree = self.positional_results(*ONE_TRADE)
        self.assertEqual(self.viz.trade_indices, {1076, 1085})
        self.minimize(results)
        plain = self.body_color(11)
        self.viz.set_selection({10, 11, 12}, None)
        self.viz.window.update()
        self.assertNotEqual(self.body_color(11), plain)
        # A list drops the selection of the chart when it is opened, and not when it is shown again.
        self.show_again("Positional Strategy")
        self.assertEqual(self.viz.selected_indices, {10, 11, 12})
        self.assertNotEqual(self.body_color(11), plain)
        self.assertEqual(self.viz.trade_indices, {1076, 1085})
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.selected_indices, {10, 11, 12})
        self.assertEqual(self.viz.trade_indices, set())

    def test_program_closes_with_lists_shown_and_minimized(self) -> None:
        _, results, _ = self.positional_results(*ORDER)
        self.minimize(results)
        self.rule_results()
        # The chart is destroyed before the windows, which then have no candles to restyle. The
        # close button in the title bar runs the WM_DELETE_WINDOW handler.
        self.viz.window.tk.eval(self.viz.window.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.callback_errors, [])
        # Nor is a call left behind for Tcl to make once the windows are gone.
        self.assertEqual(self.viz.window.tk.eval("after info"), "")


if __name__ == "__main__":
    unittest.main()
