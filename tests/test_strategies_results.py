from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, Callable, List, Set, Tuple
from unittest import mock

from candle import Candle
from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz
from strategies import positional_levels, positional_trades, price_text
from test_roi import load_price_rows
from test_strategies_window import (
    collect_callback_errors, descendants, find_button, open_positional_window, opened_windows,
    positional_boxes, type_order,
)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class PositionalResultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_price_rows()
        self.build_app(self.rows)

    def build_app(self, rows: List[List[Any]], data_source: Any = None) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": rows}, data_source=data_source)
        self.callback_errors = collect_callback_errors(self, self.viz.window)
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def run_order(
        self, window: tk.Toplevel, entry_price: str, roi: str, stop_loss: str,
    ) -> Tuple[tk.Toplevel, ttk.Treeview]:
        """Type an order into the Positional window and press Test. Return the results window and its list."""
        type_order(window, entry_price, roi, stop_loss)
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        return results, tree

    def open_results(
        self, entry_price: str, roi: str, stop_loss: str,
    ) -> Tuple[tk.Toplevel, tk.Toplevel, ttk.Treeview]:
        """Test an order from a new Positional window. Return that window, the results window and its list."""
        window = open_positional_window(self.viz)
        return (window, *self.run_order(window, entry_price, roi, stop_loss))

    def listing(self, tree: ttk.Treeview) -> List[Tuple[str, ...]]:
        return [tuple(tree.item(item, "values")) for item in tree.get_children()]

    def summary(self, results: tk.Toplevel) -> str:
        (label,) = descendants(results, tk.Label)
        return label.cget("text")

    def expected_listing(self, rows: List[List[Any]], *order: str) -> List[Tuple[str, ...]]:
        """What the list shows for the trades that the strategy module finds for an order."""
        def date(index: int) -> str:
            return "-".join(rows[index][0])

        return [
            (date(trade.buy_index), price_text(trade.buy_price), "Still open", "")
            if trade.sell_index is None else
            (date(trade.buy_index), price_text(trade.buy_price),
             date(trade.sell_index), price_text(trade.sell_price))
            for trade in positional_trades(rows, *positional_levels(*order))
        ]

    def trade_days(self, *order: str) -> Set[int]:
        """The daily candles that the trades of an order were bought and sold on."""
        trades = positional_trades(self.rows, *positional_levels(*order))
        return {
            index for trade in trades for index in (trade.buy_index, trade.sell_index)
            if index is not None
        }

    def body_color(self, index: int) -> str:
        item = next(i for i in self.viz.canvas.find_withtag(f"candle_{index}")
                    if self.viz.canvas.type(i) == "rectangle")
        return self.viz.canvas.itemcget(item, "fill")

    def view_box(self, index: int) -> Tuple[float, float, float, float]:
        """The bounds of a candle measured from the top left corner of the chart view."""
        canvas = self.viz.canvas
        x1, y1, x2, y2 = canvas.bbox(f"candle_{index}")
        x, y = canvas.canvasx(0), canvas.canvasy(0)
        return x1 - x, y1 - y, x2 - x, y2 - y

    def view_middle_x(self, *candles: int) -> float:
        """How far across the chart view the middle of some candles is."""
        boxes = [self.view_box(index) for index in candles]
        return (min(box[0] for box in boxes) + max(box[2] for box in boxes)) / 2

    def view_y(self, price: float) -> float:
        """How far down the chart view a price is."""
        return self.viz.price_to_y(price) - self.viz.canvas.canvasy(0)

    def assert_shown_within(self, span: Tuple[float, float], index: int) -> None:
        """A candle is drawn, and lies in a part of the chart view from side to side."""
        self.assertIsNotNone(self.viz.canvas.bbox(f"candle_{index}"), "the candle is hidden")
        left, _top, right, _bottom = self.view_box(index)
        self.assertLessEqual(span[0], left)
        self.assertLessEqual(right, span[1])

    def cover(self, x: int, y: int, width: int, height: int) -> SimpleNamespace:
        """Stand in for a window lying over the chart, placed from the chart's top left corner."""
        canvas = self.viz.canvas
        return SimpleNamespace(
            winfo_rootx=lambda: canvas.winfo_rootx() + x, winfo_rooty=lambda: canvas.winfo_rooty() + y,
            winfo_width=lambda: width, winfo_height=lambda: height,
        )

    def drag_across(self, first: int, last: int) -> None:
        """Press on one candle of the chart and release on another."""
        canvas = self.viz.canvas

        def event_on(index: int, y: int) -> SimpleNamespace:
            x = int(self.view_middle_x(index))
            return SimpleNamespace(
                widget=canvas, x=x, y=y,
                x_root=canvas.winfo_rootx() + x, y_root=canvas.winfo_rooty() + y,
            )

        press, release = event_on(first, 120), event_on(last, 320)
        self.viz.scroll_start(press)
        self.viz.scroll_move(release)
        self.viz.select_candle(release)

    def assert_order_reset(self, window: tk.Toplevel) -> None:
        """The Positional window is empty again, and ready for another order."""
        boxes = positional_boxes(window)
        self.assertTrue(window.winfo_viewable())
        self.assertEqual(opened_windows(window), [])
        self.assertEqual([box.get() for box in boxes], ["", "", "", "", ""])
        self.assertIs(window.focus_lastfor(), boxes[0])
        self.assertEqual(str(window.grab_current()), str(window))
        # The boxes that are typed in still take numbers only.
        for box in (boxes[0], boxes[1], boxes[3]):
            self.assertEqual(box.cget("validate"), "key")
            box.insert("end", "x")
            self.assertEqual(box.get(), "")

    def test_test_lists_the_trades_in_a_modal_window(self) -> None:
        window, results, tree = self.open_results("0.5", "10", "5")
        self.assertEqual(results.title(), "Positional Strategy Results")
        self.assertIs(results.master, window)
        self.assertTrue(results.winfo_viewable())
        self.assertEqual(str(results.grab_current()), str(results))
        columns = self.viz.window.tk.splitlist(tree.cget("columns"))
        self.assertEqual(
            [tree.heading(column, "text") for column in columns],
            ["Entry date", "Entry price", "Sell date", "Sell price"],
        )
        listing = self.listing(tree)
        self.assertEqual(len(listing), 30)
        # The order is filled at 0.5, and sold at 0.55 for its 10 % or at 0.475 for a loss of 5 %.
        self.assertEqual(listing[:4], [
            ("2018-05-04", "0.5", "2018-05-05", "0.55"),
            ("2018-06-22", "0.5", "2018-06-23", "0.475"),
            ("2018-06-24", "0.5", "2018-06-25", "0.475"),
            ("2018-07-03", "0.5", "2018-07-05", "0.475"),
        ])
        self.assertEqual(listing[20], ("2020-12-21", "0.5", "2020-12-22", "0.475"))
        self.assertEqual(listing, self.expected_listing(self.rows, "0.5", "10", "5"))
        self.assertEqual(
            self.summary(results),
            "30 trades. 1392 daily candles tested, from 2018-05-04 to 2022-02-23.\n"
            "Select a trade to show it on the chart.",
        )
        self.assertEqual([button.cget("text") for button in descendants(results, tk.Button)], ["Close"])

    def test_one_trade_is_counted_as_one_trade(self) -> None:
        window, results, tree = self.open_results("1.9", "100", "50")
        self.assertEqual(self.listing(tree), [("2021-04-14", "1.9", "2021-04-23", "0.95")])
        self.assertEqual(
            self.summary(results).splitlines()[0],
            "1 trade. 1392 daily candles tested, from 2018-05-04 to 2022-02-23.",
        )
        self.assertEqual(self.viz.trade_indices, {1076, 1085})

    def test_position_still_open_at_the_end_is_listed_without_a_sale(self) -> None:
        # The price never reaches the target of 5.5, so each sale is at the stop price.
        window, results, tree = self.open_results("0.5", "1000", "50")
        self.assertEqual(self.listing(tree), [
            ("2018-05-04", "0.5", "2018-08-14", "0.25"),
            ("2018-09-21", "0.5", "2019-08-14", "0.25"),
            ("2020-11-23", "0.5", "2020-12-23", "0.25"),
            ("2021-01-30", "0.5", "Still open", ""),
        ])
        self.assertEqual(self.summary(results).splitlines()[0][:9], "4 trades.")
        self.assertEqual(self.viz.trade_indices, {0, 102, 140, 467, 934, 964, 1002})
        # Its buy candle is shown like that of any other trade.
        tree.selection_set("3")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 1002)

    def test_order_that_is_never_filled_lists_no_trades(self) -> None:
        view = self.viz.canvas.xview()
        window, results, tree = self.open_results("3", "10", "5")
        self.assertEqual(self.listing(tree), [])
        self.assertEqual(
            self.summary(results),
            "No trades. 1392 daily candles tested, from 2018-05-04 to 2022-02-23.\n"
            "No candle reached the entry price.",
        )
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.viz.canvas.xview(), view)
        # Closing the empty list resets the order like any other.
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        self.assert_order_reset(window)

    def test_candles_of_the_trades_are_highlighted(self) -> None:
        plain = {index: self.body_color(index) for index in (0, 1, 2, 962, 963)}
        self.open_results("0.5", "10", "5")
        self.assertEqual(self.viz.trade_indices, self.trade_days("0.5", "10", "5"))
        self.assertEqual(len(self.viz.trade_indices), 60)
        # The first trade was bought on the first candle and sold on the second. The candles of
        # December 2020 are not drawn until the chart is scrolled to them, and are highlighted too.
        for index in (0, 1, 962, 963):
            self.assertNotEqual(self.body_color(index), plain[index], index)
            self.assertEqual(self.body_color(index), self.viz.highlight_color(plain[index]), index)
        self.assertEqual(self.body_color(2), plain[2])

    def test_candles_of_the_trades_are_filled_in_dark_mode(self) -> None:
        self.viz.toggle_dark_mode()
        background = self.viz.get_theme()["canvas"]
        # Candle bodies are hollow in dark mode, which would hide the highlight.
        self.assertEqual([self.body_color(index) for index in (0, 1, 2)], [background] * 3)
        window, results, tree = self.open_results("0.5", "10", "5")
        for index in (0, 1):
            base = Candle.color_for(self.rows[index][1], self.rows[index][4])
            self.assertEqual(self.body_color(index), self.viz.highlight_color(base), index)
        self.assertEqual(self.body_color(2), background)
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertEqual([self.body_color(index) for index in (0, 1, 2)], [background] * 3)

    def test_selection_on_the_chart_is_dropped(self) -> None:
        plain = self.body_color(11)
        self.viz.set_selection({10, 11, 12}, None)
        self.assertNotEqual(self.body_color(11), plain)
        self.assertTrue(self.viz.candle_info_label.place_info())
        self.open_results("1.9", "100", "50")
        # Only the candles of the trade are highlighted while the list is open.
        self.assertEqual(self.viz.selected_indices, set())
        self.assertEqual(self.body_color(11), plain)
        self.assertEqual(self.viz.candle_info_label.place_info(), {})
        self.assertEqual(self.viz.trade_indices, {1076, 1085})

    def test_roi_measurement_on_the_chart_is_dropped(self) -> None:
        self.viz.toggle_roi_mode()
        self.drag_across(10, 14)
        self.assertEqual(self.viz.selected_indices, set(range(10, 15)))
        self.assertTrue(self.viz.roi_panel.place_info())
        self.assertEqual(len(self.viz.canvas.find_withtag("selection")), 1)
        self.open_results("1.9", "100", "50")
        self.assertEqual(self.viz.selected_indices, set())
        self.assertIsNone(self.viz.roi_results)
        self.assertIsNone(self.viz.roi_header)
        self.assertEqual(self.viz.roi_panel.place_info(), {})
        self.assertEqual(self.viz.canvas.find_withtag("selection"), ())
        # The chart stays in ROI mode for the next measurement.
        self.assertTrue(self.viz.roi_mode)

    def test_first_trade_is_selected_and_shown_beside_the_windows(self) -> None:
        # The first trade of this order is three months into the chart, out of view at first.
        self.assertGreater(self.view_box(99)[0], self.viz.canvas.winfo_width())
        window, results, tree = self.open_results("0.3", "20", "10")
        self.assertEqual(self.listing(tree)[0], ("2018-08-11", "0.3", "2018-08-14", "0.27"))
        self.assertEqual(tree.selection(), ("0",))
        self.assertEqual(tree.focus(), "0")
        # The list has the keyboard, so the arrow keys step through the trades straight away.
        self.assertIs(results.focus_lastfor(), tree)
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 99)

    def test_first_trade_is_shown_once_the_results_window_has_its_size(self) -> None:
        # The chart is scrolled to lie beside the two windows, so it has to wait for their size.
        show_trade_on_chart = self.viz.show_trade_on_chart
        sizes = []

        def record_sizes(buy: int, sell: Any, entry_price: float, windows: Any) -> None:
            sizes.append([(w.winfo_width(), w.winfo_height()) for w in windows])
            show_trade_on_chart(buy, sell, entry_price, windows)

        with mock.patch.object(self.viz, "show_trade_on_chart", side_effect=record_sizes):
            window, results, tree = self.open_results("0.3", "20", "10")
        self.assertEqual(sizes, [[
            (window.winfo_width(), window.winfo_height()),
            (results.winfo_width(), results.winfo_height()),
        ]])

    def test_selecting_a_trade_scrolls_the_chart_to_it(self) -> None:
        window, results, tree = self.open_results("0.5", "10", "5")
        # The trade of December 2020 is too far from the first one for its candles to be drawn.
        self.assertEqual(tree.item("20", "values")[0], "2020-12-21")
        self.assertIsNone(self.viz.canvas.bbox("candle_962"))
        tree.selection_set("20")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 962)
        # The first trade is shown again when it is selected again.
        tree.selection_set("0")
        self.viz.window.update()
        self.assertIsNone(self.viz.canvas.bbox("candle_962"))
        self.assertLess(self.view_box(1)[2], self.viz.canvas.winfo_width())

    def test_selecting_a_trade_too_long_for_the_chart_shows_its_buy_candle(self) -> None:
        window, results, tree = self.open_results("1", "50", "40")
        # Bought on 19 May 2021 and sold 34 days later, which is more candles than the chart shows.
        self.assertEqual(self.listing(tree)[3], ("2021-05-19", "1", "2021-06-22", "0.6"))
        tree.selection_set("3")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 1111)
        # The entry price of the trade is halfway up the chart.
        self.assertAlmostEqual(self.view_y(1.0), self.viz.canvas.winfo_height() / 2, delta=2)

    def test_trade_is_shown_in_the_middle_of_the_uncovered_part_of_the_chart(self) -> None:
        width, height = self.viz.canvas.winfo_width(), self.viz.canvas.winfo_height()
        cases = (
            ("nothing covered", [], width / 2),
            ("right side covered", [self.cover(500, 100, 800, 300)], 250),
            ("left side covered", [self.cover(-100, 100, 700, 300)], (600 + width) / 2),
        )
        # Bought on 6 April 2021 at 1 and sold five days later, by the order 1 / 50 % / 40 %.
        for name, windows, middle in cases:
            with self.subTest(name):
                self.viz.show_trade_on_chart(1068, 1073, 1.0, windows)
                self.viz.window.update()
                self.assertAlmostEqual(self.view_middle_x(1068, 1073), middle, delta=2)
                # The view is halfway between the highest and the lowest price of the two candles.
                buy, sell = self.view_box(1068), self.view_box(1073)
                self.assertAlmostEqual((min(buy[1], sell[1]) + max(buy[3], sell[3])) / 2, height / 2, delta=2)

    def test_trade_is_shown_in_the_middle_of_a_zoomed_chart(self) -> None:
        canvas = self.viz.canvas
        self.viz.zoom_chart(SimpleNamespace(widget=canvas, x=300, y=250, delta=120, num=None))
        self.viz.window.update()
        self.viz.show_trade_on_chart(1068, 1073, 1.0, [self.cover(500, 100, 800, 300)])
        self.viz.window.update()
        self.assertAlmostEqual(self.view_middle_x(1068, 1073), 250, delta=2)
        buy, sell = self.view_box(1068), self.view_box(1073)
        self.assertAlmostEqual(
            (min(buy[1], sell[1]) + max(buy[3], sell[3])) / 2, canvas.winfo_height() / 2, delta=2)

    def test_candles_too_far_apart_leave_the_buy_candle_in_the_middle(self) -> None:
        # Bought on 19 May 2021 at 1 and sold 34 days later, by the order 1 / 50 % / 40 %.
        self.viz.show_trade_on_chart(1111, 1145, 1.0, [self.cover(500, 100, 800, 300)])
        self.viz.window.update()
        self.assertAlmostEqual(self.view_middle_x(1111), 250, delta=2)
        self.assertAlmostEqual(self.view_y(1.0), self.viz.canvas.winfo_height() / 2, delta=2)

    def test_candles_too_tall_for_the_chart_stay_side_by_side(self) -> None:
        # Bought on 5 April 2021 at 0.9 and sold eight days later at 1.8, by the order
        # 0.9 / 100 % / 30 %. The two candles span more prices than the chart shows at once.
        height = self.viz.canvas.winfo_height()
        buy, sell = self.rows[1067], self.rows[1075]
        self.assertGreater(self.viz.price_to_y(buy[3]) - self.viz.price_to_y(sell[2]), height)
        self.viz.show_trade_on_chart(1067, 1075, 0.9, [self.cover(500, 100, 800, 300)])
        self.viz.window.update()
        self.assertAlmostEqual(self.view_middle_x(1067, 1075), 250, delta=2)
        self.assertAlmostEqual(self.view_y(0.9), height / 2, delta=2)

    def test_open_trade_is_shown_at_its_buy_candle(self) -> None:
        # Bought on 8 February 2022 at 0.9 and never sold, by the order 0.9 / 100 % / 30 %.
        width, height = self.viz.canvas.winfo_width(), self.viz.canvas.winfo_height()
        self.viz.show_trade_on_chart(1376, None, 0.9, [self.cover(-100, 100, 700, 300)])
        self.viz.window.update()
        self.assertAlmostEqual(self.view_middle_x(1376), (600 + width) / 2, delta=2)
        self.assertAlmostEqual(self.view_y(0.9), height / 2, delta=2)

    def test_uncovered_part_of_the_chart_is_its_widest_gap_between_the_windows(self) -> None:
        width, height = self.viz.canvas.winfo_width(), self.viz.canvas.winfo_height()
        cover = self.cover
        cases = (
            ("no windows", [], (0, width)),
            ("right side covered", [cover(500, 100, 800, 300)], (0, 500)),
            ("left side covered", [cover(-200, 100, 600, 300)], (400, width)),
            ("middle covered", [cover(300, 100, 200, 300)], (500, width)),
            ("window over the top edge", [cover(500, -50, 800, 100)], (0, 500)),
            ("window over the bottom edge", [cover(500, height - 50, 800, 100)], (0, 500)),
            ("windows that overlap", [cover(500, 100, 400, 100), cover(700, 150, 600, 300)], (0, 500)),
            ("window inside another", [cover(300, 0, 600, 100), cover(400, 50, 100, 100)], (0, 300)),
            ("two windows apart", [cover(700, 0, 200, 100), cover(200, 0, 200, 100)], (400, 700)),
            ("window above the chart", [cover(500, -300, 800, 300)], (0, width)),
            ("window below the chart", [cover(500, height, 800, 100)], (0, width)),
            ("window left of the chart", [cover(-500, 100, 400, 100)], (0, width)),
            ("window right of the chart", [cover(width + 50, 100, 300, 100)], (0, width)),
            # With no room left for a candle, the whole chart is used.
            ("whole chart covered", [cover(-10, 0, width + 20, 100)], (0, width)),
            ("gap narrower than a candle", [cover(20, 0, width, 100)], (0, width)),
        )
        for name, windows, expected in cases:
            with self.subTest(name):
                self.assertEqual(self.viz.uncovered_chart_span(windows), expected)

    def check_closing_the_results(self, close: Callable[[tk.Toplevel], Any]) -> None:
        plain = {index: self.body_color(index) for index in (0, 1)}
        window = open_positional_window(self.viz)
        # The stop loss is the last box typed in before Test is pressed.
        stop_loss = positional_boxes(window)[3]
        stop_loss.focus_set()
        results, tree = self.run_order(window, "0.5", "10", "5")
        self.assertIs(window.focus_lastfor(), stop_loss)
        self.assertNotEqual(self.body_color(1), plain[1])
        close(results)
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        # No candle is highlighted any more.
        self.assertEqual(self.viz.trade_indices, set())
        for index, color in plain.items():
            self.assertEqual(self.body_color(index), color, index)
        self.assert_order_reset(window)

    def test_close_button_clears_the_highlights_and_resets_the_order(self) -> None:
        self.check_closing_the_results(lambda results: find_button(results, "Close").invoke())

    def test_closing_the_results_from_the_title_bar_does_the_same(self) -> None:
        # The close button in the title bar runs the window's WM_DELETE_WINDOW handler.
        self.check_closing_the_results(
            lambda results: self.viz.window.tk.eval(results.protocol("WM_DELETE_WINDOW")))

    def test_another_order_can_be_tested_after_the_results_are_closed(self) -> None:
        window, results, tree = self.open_results("0.5", "10", "5")
        find_button(results, "Close").invoke()
        self.viz.window.update()
        results, tree = self.run_order(window, "1.9", "100", "50")
        self.assertEqual(self.listing(tree), [("2021-04-14", "1.9", "2021-04-23", "0.95")])
        # Only the candles of the new trade are highlighted.
        self.assertEqual(self.viz.trade_indices, {1076, 1085})
        self.assertEqual(str(results.grab_current()), str(results))

    def test_closing_the_positional_window_closes_the_results_too(self) -> None:
        plain = self.body_color(1)
        window, results, tree = self.open_results("0.5", "10", "5")
        # The results window is the modal one, but a title bar still takes a click on its close button.
        self.viz.window.tk.eval(window.protocol("WM_DELETE_WINDOW"))
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        self.assertFalse(window.winfo_exists())
        self.assertEqual(opened_windows(self.viz.window), [])
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.body_color(1), plain)
        self.assertIsNone(self.viz.window.grab_current())

    def test_closing_the_program_with_the_results_open_raises_nothing(self) -> None:
        self.open_results("0.5", "10", "5")
        # The chart is destroyed before the two windows, which then have no candles to restyle.
        self.viz.window.tk.eval(self.viz.window.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.callback_errors, [])

    def test_candles_holding_the_trade_days_are_highlighted_on_another_tab(self) -> None:
        self.viz.select_timeframe("2W")
        self.viz.window.update()
        plain = self.body_color(69)
        window, results, tree = self.open_results("0.5", "10", "5")
        # The daily candles are tested whichever tab is shown, so the list is that of the Daily tab.
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, "0.5", "10", "5"))
        # A candle of this tab starts on the date it shows and holds the days up to the next candle.
        starts = [row[0] for row in self.viz.price_data]

        def holder(day: int) -> int:
            return max(index for index, start in enumerate(starts) if start <= self.rows[day][0])

        self.assertEqual(self.viz.trade_indices, {holder(day) for day in self.trade_days("0.5", "10", "5")})
        self.assertEqual(len(self.viz.trade_indices), 17)
        # The trade of 21 December 2020 is in the two weeks that start on the 14th.
        self.assertEqual(starts[69], ["2020", "12", "14"])
        self.assertIn(69, self.viz.trade_indices)
        self.assertEqual(self.body_color(69), self.viz.highlight_color(plain))
        self.assertIsNone(self.viz.canvas.bbox("candle_69"))
        tree.selection_set("20")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 69)
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.body_color(69), plain)

    def test_second_click_on_test_while_the_results_open_is_ignored(self) -> None:
        window = open_positional_window(self.viz)
        type_order(window, "0.5", "10", "5")
        test_button = find_button(window, "Test")
        open_modal_window = self.viz.open_modal_window
        opened = []

        def click_again_while_opening(*args: Any, **options: Any) -> Any:
            # A modal window runs the event loop until it is on screen, which lets in a second
            # click on the button that is opening it.
            opened.append(args)
            if len(opened) == 1:
                test_button.invoke()
            return open_modal_window(*args, **options)

        with mock.patch.object(self.viz, "open_modal_window", side_effect=click_again_while_opening):
            test_button.invoke()
            self.viz.window.update()
        self.assertEqual(len(opened), 1)
        self.assertEqual(len(opened_windows(window)), 1)
        self.assertEqual(len(self.viz.trade_indices), 60)

    def test_only_the_loaded_candles_are_tested(self) -> None:
        # A data file is read a page at a time, and the pages still to come are not tested.
        self.viz.window.destroy()
        data_file = Path(__file__).resolve().parents[1] / "data" / "XRP_4_year_ohlc_no_vol.csv"
        source = PaginatedPriceData(data_file)
        self.build_app(source.load_initial(), source)
        self.assertEqual(len(self.viz.price_data), 365)
        window, results, tree = self.open_results("0.5", "10", "5")
        self.assertEqual(
            self.summary(results).splitlines()[0],
            "15 trades. 365 daily candles tested, from 2018-05-04 to 2019-05-03.",
        )
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows[:365], "0.5", "10", "5"))
        # Load More is out of reach while the two windows are open. The next test covers its page.
        find_button(results, "Close").invoke()
        find_button(window, "Cancel").invoke()
        self.viz.load_more_button.invoke()
        self.viz.window.update()
        loaded = len(self.viz.price_data)
        self.assertGreater(loaded, 365)
        window, results, tree = self.open_results("0.5", "10", "5")
        self.assertIn(f" {loaded} daily candles tested, ", self.summary(results))
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows[:loaded], "0.5", "10", "5"))


if __name__ == "__main__":
    unittest.main()
