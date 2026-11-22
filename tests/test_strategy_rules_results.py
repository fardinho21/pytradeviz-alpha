from __future__ import annotations

import tkinter as tk
import unittest
from decimal import Decimal
from tkinter import ttk
from typing import Any, Callable, List, Sequence, Set, Tuple
from unittest import mock

from strategies import price_text
from strategy_rules import RuleTrade, percent_text, rule_strategy, rule_trades, trade_returns
from test_strategies_results import TradeListTestCase
from test_strategies_window import descendants, find_button, opened_windows
from test_strategy_rules import BAND_BUY_ROW, BAND_SELL_ROW, BUY_ROW, SELL_ROW, SOLD_BY_BAND_RULE
from test_strategy_rules_window import (
    ADX_BUY_ROW, ADX_SELL_ROW, exit_boxes, open_indicator_based_window, shown_strategy, type_strategy,
)
from trend import wilder_rsi


# Strategies as they are typed: the buy rules, the sell rules, the ROI and the stop loss.
DEFAULT = ([BUY_ROW], [SELL_ROW], "", "")
WITH_EXITS = ([BUY_ROW], [SELL_ROW], "20", "10")
COMBINED = ([BUY_ROW, ADX_BUY_ROW], [ADX_SELL_ROW], "", "8")
ONE_TRADE = (
    [("RSI", "14", "crosses below", "20", "1")], [("RSI", "14", "crosses above", "70", "1")], "", "")
LEFT_OPEN = (
    [("RSI", "21", "crosses below", "30", "1")], [("RSI", "21", "crosses above", "70", "1")], "", "")
ROI_ALONE = ([BUY_ROW], [], "50", "")
# RSI is never below zero, so it never falls below it.
NEVER_BUYS = ([("RSI", "7", "crosses below", "0", "1")], [SELL_ROW], "", "")
# Bought on a close under the lower Bollinger band and sold on a close over the upper one.
BAND_RULES = ([BAND_BUY_ROW], [BAND_SELL_ROW], "", "")
BAND_RULES_COMBINED = ([BAND_BUY_ROW, ADX_BUY_ROW], [BAND_SELL_ROW], "", "8")
# Bought when RSI(7) has been below 30 for three candles, the first of which took it there. Sold
# when the close has been over the upper band for two candles, or RSI(7) above 70 for the two
# candles that its rise began with.
SOLD_BY_BAND_FOR_TWO = "Bollinger(20, 2): close is above upper band for 2 candles"
SOLD_BY_RSI_FOR_TWO = "RSI(7) crosses above 70 for 2 candles"
SEVERAL_CANDLES = (
    [("RSI", "7", "crosses below", "30", "3")],
    [("Bollinger", "20", "2", "is above", "upper band", "2"), ("RSI", "7", "crosses above", "70", "2")],
    "", "")

SOLD_BY_RSI = "RSI(7) crosses above 70"
# The candles of the sample file, and what buying the first and holding to the last made.
TESTED = "1392 daily candles tested, from 2018-05-04 to 2022-02-23."
HELD = "Buy and hold: +45.16%."
# The least width of each column of the list of trades.
LEAST_WIDTHS = (105, 115, 105, 115, 90, 240)


class IndicatorBasedResultsTests(TradeListTestCase):
    def run_strategy(
        self, window: tk.Toplevel, buy_rows: Sequence[Sequence[str]], sell_rows: Sequence[Sequence[str]],
        roi: str = "", stop_loss: str = "",
    ) -> Tuple[tk.Toplevel, ttk.Treeview]:
        """Type a strategy into the Indicator Based window and press Test.

        Return the results window and its list of trades.
        """
        type_strategy(window, buy_rows, sell_rows, roi, stop_loss)
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        return results, tree

    def open_results(self, *strategy: Any) -> Tuple[tk.Toplevel, tk.Toplevel, ttk.Treeview]:
        """Test a strategy from a new Indicator Based window. Return it, the results and their list."""
        window = open_indicator_based_window(self.viz)
        return (window, *self.run_strategy(window, *strategy))

    def expected_listing(self, rows: List[List[Any]], *strategy: Any) -> List[Tuple[str, ...]]:
        """What the list shows for the trades that the rules module finds for a strategy."""
        def date(index: int) -> str:
            return "-".join(rows[index][0])

        trades = rule_trades(rows, rule_strategy(*strategy))
        return [
            (date(trade.buy_index), price_text(trade.buy_price), "Still open", "", percent_text(made), "")
            if trade.sell_index is None else
            (date(trade.buy_index), price_text(trade.buy_price),
             date(trade.sell_index), price_text(trade.sell_price), percent_text(made), trade.sold_by)
            for trade, made in zip(trades, trade_returns(rows, trades))
        ]

    def trade_days(self, *strategy: Any) -> Set[int]:
        """The daily candles that the trades of a strategy were bought and sold on."""
        trades = rule_trades(self.rows, rule_strategy(*strategy))
        return {
            index for trade in trades for index in (trade.buy_index, trade.sell_index)
            if index is not None
        }

    def holding_candle(self, day: int) -> int:
        """The candle of the tab that is shown which holds a day of the sample file."""
        # A candle starts on the date it shows and holds the days up to the next candle.
        starts = [row[0] for row in self.viz.price_data]
        return max(index for index, start in enumerate(starts) if start <= self.rows[day][0])

    def assert_strategy_kept(self, window: tk.Toplevel, *strategy: Any) -> None:
        """The Indicator Based window still holds a strategy, and is ready for another test."""
        self.assertTrue(window.winfo_viewable())
        self.assertEqual(opened_windows(window), [])
        self.assertEqual(shown_strategy(window), strategy)
        self.assertEqual(str(window.grab_current()), str(window))

    def test_test_lists_the_trades_in_a_modal_window(self) -> None:
        window, results, tree = self.open_results(*DEFAULT)
        self.assertEqual(results.title(), "Indicator Based Strategy Results")
        self.assertIs(results.master, window)
        self.assertTrue(results.winfo_viewable())
        self.assertEqual(str(results.grab_current()), str(results))
        columns = self.viz.window.tk.splitlist(tree.cget("columns"))
        self.assertEqual(
            [tree.heading(column, "text") for column in columns],
            ["Entry date", "Entry price", "Sell date", "Sell price", "Return", "Sold by"],
        )
        listing = self.listing(tree)
        self.assertEqual(len(listing), 19)
        # Each is bought at the open after RSI(7) fell below 30, and sold at the open after it
        # rose above 70.
        self.assertEqual(listing[:3], [
            ("2018-05-23", "0.63782", "2018-07-18", "0.50651", "-20.59%", SOLD_BY_RSI),
            ("2018-08-08", "0.37863", "2018-09-20", "0.32718", "-13.59%", SOLD_BY_RSI),
            ("2018-10-12", "0.38319", "2018-11-06", "0.5022", "+31.06%", SOLD_BY_RSI),
        ])
        self.assertEqual(listing[18], ("2022-01-06", "0.7725", "2022-02-08", "0.8314", "+7.62%", SOLD_BY_RSI))
        self.assertEqual(listing, self.expected_listing(self.rows, *DEFAULT))
        self.assertEqual(
            self.summary(results),
            f"19 trades, 8 profitable. {TESTED}\n"
            f"Total return: -24.82%. {HELD}\n"
            "Select a trade to show it on the chart.",
        )
        self.assertEqual(
            [button.cget("text") for button in descendants(results, tk.Button)], ["Minimize", "Close"])

    def test_one_trade_is_counted_as_one_trade(self) -> None:
        window, results, tree = self.open_results(*ONE_TRADE)
        self.assertEqual(self.listing(tree), [
            ("2018-08-14", "0.2743", "2018-09-21", "0.44877", "+63.61%", "RSI(14) crosses above 70"),
        ])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"1 trade, 1 profitable. {TESTED}", f"Total return: +63.61%. {HELD}"],
        )
        self.assertEqual(self.viz.trade_indices, {102, 140})

    def test_sale_at_the_roi_or_the_stop_loss_says_so(self) -> None:
        window, results, tree = self.open_results(*WITH_EXITS)
        listing = self.listing(tree)
        self.assertEqual(len(listing), 46)
        # The first trade lost its 10 % on the day it was bought, and the second made its 20 %.
        # The sixth was sold by the rule before it had done either.
        self.assertEqual(listing[:2], [
            ("2018-05-23", "0.63782", "2018-05-23", "0.574038", "-10.00%", "Stop loss"),
            ("2018-05-29", "0.54689", "2018-06-03", "0.656268", "+20.00%", "ROI"),
        ])
        self.assertEqual(
            listing[5], ("2018-07-11", "0.44247", "2018-07-18", "0.50651", "+14.47%", SOLD_BY_RSI))
        self.assertEqual(listing, self.expected_listing(self.rows, *WITH_EXITS))
        sold_by = [row[5] for row in listing]
        self.assertEqual([sold_by.count(name) for name in ("Stop loss", "ROI", SOLD_BY_RSI)], [28, 12, 6])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"46 trades, 18 profitable. {TESTED}", f"Total return: -15.76%. {HELD}"],
        )
        # A trade bought and sold on one candle highlights that candle.
        self.assertEqual(self.viz.trade_indices, self.trade_days(*WITH_EXITS))
        self.assertIn(19, self.viz.trade_indices)

    def test_rules_of_two_indicators_are_tested_together(self) -> None:
        # Bought when RSI(7) falls below 30 while ADX(14) is below 25, and sold when ADX(14)
        # rises above 25 or the price has fallen 8 %.
        window, results, tree = self.open_results(*COMBINED)
        listing = self.listing(tree)
        self.assertEqual(len(listing), 18)
        sold_by_adx = "ADX(14) crosses above 25"
        self.assertEqual(
            listing[0], ("2018-08-08", "0.37863", "2018-08-08", "0.3483396", "-8.00%", "Stop loss"))
        self.assertEqual(
            listing[4], ("2019-04-25", "0.29971", "2019-05-16", "0.45723", "+52.56%", sold_by_adx))
        self.assertEqual(listing, self.expected_listing(self.rows, *COMBINED))
        sold_by = [row[5] for row in listing]
        self.assertEqual([sold_by.count(name) for name in ("Stop loss", sold_by_adx)], [13, 5])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"18 trades, 5 profitable. {TESTED}", f"Total return: +2.78%. {HELD}"],
        )

    def test_bollinger_rules_buy_under_the_lower_band_and_sell_over_the_upper_band(self) -> None:
        window, results, tree = self.open_results(*BAND_RULES)
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*BAND_RULES))
        listing = self.listing(tree)
        self.assertEqual(len(listing), 17)
        # Each is bought at the open after the close fell under the lower band, and sold at the
        # open after it rose over the upper band.
        self.assertEqual(listing[:3], [
            ("2018-05-29", "0.54689", "2018-09-21", "0.44877", "-17.94%", SOLD_BY_BAND_RULE),
            ("2018-10-12", "0.38319", "2018-11-06", "0.5022", "+31.06%", SOLD_BY_BAND_RULE),
            ("2018-11-23", "0.42766", "2018-12-25", "0.40075", "-6.29%", SOLD_BY_BAND_RULE),
        ])
        self.assertEqual(
            listing[16], ("2022-01-22", "0.6368", "2022-02-08", "0.8314", "+30.56%", SOLD_BY_BAND_RULE))
        self.assertEqual(listing, self.expected_listing(self.rows, *BAND_RULES))
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"17 trades, 8 profitable. {TESTED}", f"Total return: +2.34%. {HELD}"],
        )
        # The bands are the ones that the chart draws for the same period and multiplier. The
        # first trade was bought on candle 25 and sold on candle 140, after the closes that
        # went under the lower band and over the upper band.
        self.assertEqual(self.viz.bollinger_parameters(), (20, 2))
        _, upper, lower = self.viz.indicators_object.calculate_bollinger(20, 2)
        closes = [row[4] for row in self.rows]
        self.assertTrue(closes[23] >= lower[23] and closes[24] < lower[24])
        self.assertTrue(closes[138] <= upper[138] and closes[139] > upper[139])
        self.assertEqual(self.viz.trade_indices, self.trade_days(*BAND_RULES))
        self.assertEqual(len(self.viz.trade_indices), 34)
        self.assertTrue({25, 140} <= self.viz.trade_indices)
        # The column is widened for the name of the rule that sold.
        self.assert_columns_fit(tree, LEAST_WIDTHS)

    def test_bollinger_rules_are_tested_with_the_rules_of_other_indicators(self) -> None:
        # Bought when the close falls under the lower band while ADX(14) is below 25, and sold
        # when the close rises over the upper band or the price has fallen 8 %.
        window, results, tree = self.open_results(*BAND_RULES_COMBINED)
        listing = self.listing(tree)
        self.assertEqual(len(listing), 20)
        self.assertEqual(
            listing[0], ("2018-08-07", "0.41328", "2018-08-07", "0.3802176", "-8.00%", "Stop loss"))
        self.assertEqual(listing, self.expected_listing(self.rows, *BAND_RULES_COMBINED))
        sold_by = [row[5] for row in listing]
        self.assertEqual([sold_by.count(name) for name in ("Stop loss", SOLD_BY_BAND_RULE)], [14, 6])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"20 trades, 6 profitable. {TESTED}", f"Total return: -17.02%. {HELD}"],
        )

    def test_rules_for_several_candles_wait_for_the_last_of_them(self) -> None:
        window, results, tree = self.open_results(*SEVERAL_CANDLES)
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*SEVERAL_CANDLES))
        listing = self.listing(tree)
        self.assertEqual(len(listing), 9)
        # A sale names its rule with the candles that the rule asks for.
        self.assertEqual(listing[:2], [
            ("2018-06-25", "0.47418", "2018-09-21", "0.44877", "-5.36%", SOLD_BY_RSI_FOR_TWO),
            ("2018-11-26", "0.38186", "2019-02-20", "0.3225", "-15.54%", SOLD_BY_BAND_FOR_TWO),
        ])
        self.assertEqual(listing, self.expected_listing(self.rows, *SEVERAL_CANDLES))
        sold_by = [row[5] for row in listing]
        self.assertEqual(
            [sold_by.count(name) for name in (SOLD_BY_BAND_FOR_TWO, SOLD_BY_RSI_FOR_TWO)], [8, 1])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"9 trades, 6 profitable. {TESTED}", f"Total return: +177.88%. {HELD}"],
        )
        closes = [row[4] for row in self.rows]
        rsi = wilder_rsi(closes, 7)
        # The fall of RSI(7) below 30 on candle 18, which a rule for one candle buys on, lasted
        # two candles. The fall on candle 49 lasted to candle 51, so candle 52 is the first buy.
        self.assertTrue(rsi[17] >= 30 and max(rsi[18:20]) < 30 and rsi[20] >= 30)
        self.assertTrue(rsi[48] >= 30 and max(rsi[49:52]) < 30)
        self.assertEqual(self.viz.trade_indices, self.trade_days(*SEVERAL_CANDLES))
        self.assertEqual(min(self.viz.trade_indices), 52)
        # RSI(7) rose above 70 on candle 138 and was still there on candle 139, so the trade was
        # sold on candle 140. The close of candle 139 was the first one over the upper band,
        # which is a candle too few for the other rule.
        self.assertTrue(rsi[137] <= 70 and min(rsi[138:140]) > 70)
        _, upper, _ = self.viz.indicators_object.calculate_bollinger(20, 2)
        self.assertTrue(closes[138] <= upper[138] and closes[139] > upper[139])
        self.assertIn(140, self.viz.trade_indices)
        # The column is widened for the name of the rule that sold.
        self.assert_columns_fit(tree, LEAST_WIDTHS)
        # The candles are still in their boxes when the list is closed.
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assert_strategy_kept(window, *SEVERAL_CANDLES)

    def test_position_still_open_at_the_end_is_valued_at_the_last_close(self) -> None:
        window, results, tree = self.open_results(*LEFT_OPEN)
        self.assertEqual(self.listing(tree), [
            ("2018-08-09", "0.33197", "2018-09-22", "0.56399", "+69.89%", "RSI(21) crosses above 70"),
            ("2019-12-18", "0.1831", "2020-02-13", "0.30427", "+66.18%", "RSI(21) crosses above 70"),
            ("2020-03-13", "0.13536", "2020-07-30", "0.24323", "+79.69%", "RSI(21) crosses above 70"),
            ("2022-01-23", "0.5966", "Still open", "", "+21.66%", ""),
        ])
        self.assertEqual(self.summary(results).splitlines()[:2], [
            f"4 trades, 4 profitable. {TESTED}",
            f"Total return: +517.17%. {HELD} The open trade is valued at the last close.",
        ])
        self.assertEqual(self.viz.trade_indices, {97, 141, 593, 650, 679, 818, 1360})
        # Its buy candle is shown like that of any other trade.
        tree.selection_set("3")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 1360)

    def test_trade_that_breaks_even_is_not_counted_as_profitable(self) -> None:
        window = open_indicator_based_window(self.viz)
        # No rule sells a trade of the sample file at the price it was bought at, so the trades
        # are given to the results window as they are.
        price = Decimal("0.5")
        trades = [RuleTrade(10, price, 20, price, SOLD_BY_RSI), RuleTrade(30, price, 40, 2 * price, "ROI")]
        self.viz.open_indicator_based_results_window(tk, window, trades)
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        self.assertEqual(self.listing(tree), [
            ("2018-05-14", "0.5", "2018-05-24", "0.5", "0.00%", SOLD_BY_RSI),
            ("2018-06-03", "0.5", "2018-06-13", "1", "+100.00%", "ROI"),
        ])
        self.assertEqual(
            self.summary(results).splitlines()[:2],
            [f"2 trades, 1 profitable. {TESTED}", f"Total return: +100.00%. {HELD}"],
        )

    def test_columns_are_widened_for_texts_too_long_for_them(self) -> None:
        window, results, tree = self.open_results(*DEFAULT)
        self.assert_columns_fit(tree, LEAST_WIDTHS)
        find_button(results, "Close").invoke()
        self.viz.window.update()
        # Prices, a return and a rule that need more room than those of the sample file.
        price, sold_by = Decimal("61855.795241"), "ADX(9999) crosses above 99.75"
        half = Decimal("0.5")
        self.viz.open_indicator_based_results_window(
            tk, window, [RuleTrade(10, half, 20, half, "ROI"), RuleTrade(30, price, 40, 2 * price, sold_by)])
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        self.assertEqual(self.listing(tree), [
            ("2018-05-14", "0.5", "2018-05-24", "0.5", "0.00%", "ROI"),
            ("2018-06-03", "61855.795241", "2018-06-13", "123711.590482", "+100.00%", sold_by),
        ])
        self.assert_columns_fit(tree, LEAST_WIDTHS)

    def test_strategy_without_sell_rules_sells_at_its_roi(self) -> None:
        window, results, tree = self.open_results(*ROI_ALONE)
        self.assertEqual(self.listing(tree), [
            ("2018-05-23", "0.63782", "2021-04-06", "0.95673", "+50.00%", "ROI"),
            ("2021-05-20", "1.0565", "Still open", "", "-31.30%", ""),
        ])
        self.assertEqual(self.summary(results).splitlines()[:2], [
            f"2 trades, 1 profitable. {TESTED}",
            f"Total return: +3.05%. {HELD} The open trade is valued at the last close.",
        ])

    def test_strategy_that_never_buys_lists_no_trades(self) -> None:
        view = self.viz.canvas.xview()
        window, results, tree = self.open_results(*NEVER_BUYS)
        self.assertEqual(self.listing(tree), [])
        self.assertEqual(
            self.summary(results),
            f"No trades. {TESTED}\n"
            f"{HELD}\n"
            "No candle before the last met every buy rule.",
        )
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.viz.canvas.xview(), view)
        # The columns of the empty list are not narrowed to their headings.
        self.assert_columns_fit(tree, LEAST_WIDTHS)
        # Closing the empty list leaves the rules in the window like any other.
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        self.assert_strategy_kept(window, *NEVER_BUYS)

    def test_candles_of_the_trades_are_highlighted(self) -> None:
        plain = {index: self.body_color(index) for index in (18, 19, 75, 1343, 1376)}
        self.open_results(*DEFAULT)
        self.assertEqual(self.viz.trade_indices, self.trade_days(*DEFAULT))
        self.assertEqual(len(self.viz.trade_indices), 38)
        # The first trade was bought on candle 19 and sold on candle 75. The candles of 2022 are
        # not drawn until the chart is scrolled to them, and are highlighted too.
        for index in (19, 75, 1343, 1376):
            self.assertNotEqual(self.body_color(index), plain[index], index)
            self.assertEqual(self.body_color(index), self.viz.highlight_color(plain[index]), index)
        # The candle whose close met the buy rule is not part of the trade.
        self.assertEqual(self.body_color(18), plain[18])

    def test_first_trade_is_selected_and_shown_beside_the_windows(self) -> None:
        # The trade of this strategy is three months into the chart, out of view at first.
        self.assertGreater(self.view_box(102)[0], self.viz.canvas.winfo_width())
        window, results, tree = self.open_results(*ONE_TRADE)
        self.assertEqual(tree.selection(), ("0",))
        self.assertEqual(tree.focus(), "0")
        # The list has the keyboard, so the arrow keys step through the trades straight away.
        self.assertIs(results.focus_lastfor(), tree)
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 102)

    def test_selecting_a_trade_scrolls_the_chart_to_it(self) -> None:
        window, results, tree = self.open_results(*DEFAULT)
        # The last trade is too far from the first one for its candles to be drawn.
        self.assertEqual(tree.item("18", "values")[0], "2022-01-06")
        self.assertIsNone(self.viz.canvas.bbox("candle_1343"))
        tree.selection_set("18")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 1343)
        # The first trade is shown again when it is selected again.
        tree.selection_set("0")
        self.viz.window.update()
        self.assertIsNone(self.viz.canvas.bbox("candle_1343"))
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 19)

    def check_closing_the_results(self, close: Callable[[tk.Toplevel], Any]) -> None:
        plain = {index: self.body_color(index) for index in (19, 75)}
        window = open_indicator_based_window(self.viz)
        # The stop loss is the last box typed in before Test is pressed.
        stop_loss = exit_boxes(window)[1]
        stop_loss.focus_set()
        results, tree = self.run_strategy(window, *WITH_EXITS)
        self.assertIs(window.focus_lastfor(), stop_loss)
        for index, color in plain.items():
            self.assertNotEqual(self.body_color(index), color, index)
        close(results)
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        # No candle is highlighted any more.
        self.assertEqual(self.viz.trade_indices, set())
        for index, color in plain.items():
            self.assertEqual(self.body_color(index), color, index)
        # The rules, the ROI and the stop loss are still there, to be changed and tested again.
        self.assert_strategy_kept(window, *WITH_EXITS)
        self.assertIs(window.focus_lastfor(), stop_loss)

    def test_close_button_clears_the_highlights_and_keeps_the_strategy(self) -> None:
        self.check_closing_the_results(lambda results: find_button(results, "Close").invoke())

    def test_closing_the_results_from_the_title_bar_does_the_same(self) -> None:
        # The close button in the title bar runs the window's WM_DELETE_WINDOW handler.
        self.check_closing_the_results(
            lambda results: self.viz.window.tk.eval(results.protocol("WM_DELETE_WINDOW")))

    def test_another_strategy_can_be_tested_after_the_results_are_closed(self) -> None:
        window, results, tree = self.open_results(*DEFAULT)
        find_button(results, "Close").invoke()
        self.viz.window.update()
        results, tree = self.run_strategy(window, *ONE_TRADE)
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *ONE_TRADE))
        # Only the candles of the new trade are highlighted.
        self.assertEqual(self.viz.trade_indices, {102, 140})
        self.assertEqual(str(results.grab_current()), str(results))

    def test_closing_the_strategy_window_closes_the_results_too(self) -> None:
        plain = self.body_color(19)
        window, results, tree = self.open_results(*DEFAULT)
        # The results window is the modal one, but a title bar still takes a click on its close button.
        self.viz.window.tk.eval(window.protocol("WM_DELETE_WINDOW"))
        self.viz.window.update()
        self.assertFalse(results.winfo_exists())
        self.assertFalse(window.winfo_exists())
        self.assertEqual(opened_windows(self.viz.window), [])
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.body_color(19), plain)
        self.assertIsNone(self.viz.window.grab_current())

    def test_closing_the_program_with_the_results_open_raises_nothing(self) -> None:
        self.open_results(*DEFAULT)
        # The chart is destroyed before the two windows, which then have no candles to restyle.
        self.viz.window.tk.eval(self.viz.window.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.callback_errors, [])
        # Nor is a call left behind for Tcl to make once the windows are gone.
        self.assertEqual(self.viz.window.tk.eval("after info"), "")

    def test_daily_candles_are_tested_whichever_tab_is_shown(self) -> None:
        self.viz.select_timeframe("2W")
        self.viz.window.update()
        # The fourteenth trade was bought on 2020-12-16, the 958th day of the file.
        candle = self.holding_candle(957)
        self.assertEqual(self.viz.price_data[candle][0], ["2020", "12", "14"])
        plain = self.body_color(candle)
        window, results, tree = self.open_results(*DEFAULT)
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *DEFAULT))
        self.assertEqual(self.summary(results).splitlines()[0], f"19 trades, 8 profitable. {TESTED}")
        # The candles that hold the days of the trades are highlighted.
        self.assertEqual(
            self.viz.trade_indices, {self.holding_candle(day) for day in self.trade_days(*DEFAULT)})
        self.assertEqual(self.body_color(candle), self.viz.highlight_color(plain))
        self.assertIsNone(self.viz.canvas.bbox(f"candle_{candle}"))
        tree.selection_set("13")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), candle)
        find_button(results, "Close").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.body_color(candle), plain)

    def test_second_click_on_test_while_the_results_open_is_ignored(self) -> None:
        window = open_indicator_based_window(self.viz)
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
        self.assertEqual(len(self.viz.trade_indices), 38)

    def test_tested_strategy_is_shown_when_the_window_is_opened_again(self) -> None:
        tested = ([("RSI", "07", "crosses below", "30.50", "1"), ADX_BUY_ROW], [], "20.0", "")
        window, results, tree = self.open_results(*tested)
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*tested))
        find_button(results, "Close").invoke()
        # Rules that are typed after the test and not tested are forgotten.
        type_strategy(window, *WITH_EXITS)
        find_button(window, "Cancel").invoke()
        self.viz.window.update()
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*tested))
        window = open_indicator_based_window(self.viz)
        # The numbers are shown as they were understood, without the zeros that change nothing.
        shown = ([("RSI", "7", "crosses below", "30.5", "1"), ADX_BUY_ROW], [], "20", "")
        self.assertEqual(shown_strategy(window), shown)
        # They give the same trades when they are tested as they are.
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *tested))

    def test_tested_bollinger_rules_are_shown_when_the_window_is_opened_again(self) -> None:
        dip = ("RSI", "7", "is below", "30", "1")
        sell_rows = [("Bollinger", "10", "1.5", "crosses above", "upper band", "1"), ADX_SELL_ROW]
        tested = ([dip, ("Bollinger", "020", "2.50", "is below", "lower band", "1")], sell_rows, "", "")
        window, results, tree = self.open_results(*tested)
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*tested))
        self.assertEqual(len(self.listing(tree)), 15)
        find_button(results, "Close").invoke()
        find_button(window, "Cancel").invoke()
        self.viz.window.update()
        window = open_indicator_based_window(self.viz)
        # Each row has the parts of its rule, with the numbers as they were understood.
        shown = ([dip, ("Bollinger", "20", "2.5", "is below", "lower band", "1")], sell_rows, "", "")
        self.assertEqual(shown_strategy(window), shown)
        # They give the same trades when they are tested as they are.
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *tested))

    def test_tested_candles_are_shown_when_the_window_is_opened_again(self) -> None:
        band_row = ("Bollinger", "20", "2", "crosses above", "upper band")
        tested = ([("RSI", "7", "crosses below", "30", "03")], [band_row + ("002",), ADX_SELL_ROW], "", "")
        window, results, tree = self.open_results(*tested)
        self.assertEqual(self.viz.rule_strategy, rule_strategy(*tested))
        self.assertEqual(len(self.listing(tree)), 13)
        find_button(results, "Close").invoke()
        find_button(window, "Cancel").invoke()
        self.viz.window.update()
        window = open_indicator_based_window(self.viz)
        # Each rule is for the candles that were understood, and the one that was left alone for one.
        shown = ([("RSI", "7", "crosses below", "30", "3")], [band_row + ("2",), ADX_SELL_ROW], "", "")
        self.assertEqual(shown_strategy(window), shown)
        # They give the same trades when they are tested as they are.
        find_button(window, "Test").invoke()
        self.viz.window.update()
        (results,) = opened_windows(window)
        (tree,) = descendants(results, ttk.Treeview)
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *tested))

    def test_test_loads_the_rest_of_the_file_first(self) -> None:
        source = self.build_paginated_app()
        window, results, tree = self.open_results(*DEFAULT)
        self.assertFalse(source.has_more)
        self.assertEqual(len(self.viz.price_data), 1392)
        # Nothing is left for the two buttons that load more of the file.
        for button in (self.viz.load_more_button, self.viz.load_all_button):
            self.assertTrue(button.instate(["disabled"]))
        self.assertEqual(self.summary(results).splitlines()[0], f"19 trades, 8 profitable. {TESTED}")
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *DEFAULT))
        self.assertEqual(self.viz.trade_indices, self.trade_days(*DEFAULT))
        # A candle that was not loaded when Test was pressed is shown like any other.
        tree.selection_set("18")
        self.viz.window.update()
        self.assert_shown_within(self.viz.uncovered_chart_span((window, results)), 1343)

    def test_chart_stays_where_it_was_when_the_loaded_file_has_no_trade_to_show(self) -> None:
        self.build_paginated_app()
        self.viz.canvas.xview_moveto(0.3)
        self.viz.window.update()
        left = self.viz.canvas.canvasx(0)
        self.assertGreater(left, 0)
        self.open_results(*NEVER_BUYS)
        self.assertEqual(len(self.viz.price_data), 1392)
        self.assertAlmostEqual(self.viz.canvas.canvasx(0), left, delta=3)

    def test_candles_that_cannot_be_loaded_are_named_and_the_loaded_ones_tested(self) -> None:
        source = self.build_paginated_app()
        load_next = source.load_next
        message = "CSV record ending on line 551: invalid OHLC values"
        pages: List[List[Any]] = []

        def fail_on_third_page() -> List[Any]:
            if len(pages) == 2:
                raise ValueError(message)
            pages.append(load_next())
            return pages[-1]

        window = open_indicator_based_window(self.viz)
        with mock.patch.object(source, "load_next", side_effect=fail_on_third_page):
            with mock.patch("pytradeviz.messagebox.showerror") as showerror:
                results, tree = self.run_strategy(window, *DEFAULT)
        # The error is shown over the window that Test was pressed in.
        showerror.assert_called_once_with("Unable to load price data", message, parent=window)
        self.assertEqual(365 + sum(len(page) for page in pages), 549)
        self.assertEqual(len(self.viz.price_data), 549)
        self.assertEqual(self.summary(results).splitlines()[:2], [
            "8 trades, 4 profitable. 549 daily candles tested, from 2018-05-04 to 2019-11-03.",
            "Total return: +1.76%. Buy and hold: -41.95%.",
        ])
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows[:549], *DEFAULT))
        # The rest of the file is still there to be loaded.
        self.assertTrue(source.has_more)
        self.assertFalse(self.viz.load_all_button.instate(["disabled"]))

    def test_cancel_pressed_while_the_file_loads_lists_no_trades(self) -> None:
        self.build_paginated_app()
        window = open_indicator_based_window(self.viz)
        load_pages = self.viz.load_pages

        def load_then_cancel(*args: Any, **options: Any) -> None:
            load_pages(*args, **options)
            # A click made while the file loads waits for the event loop, which runs after it.
            window.after(0, find_button(window, "Cancel").invoke)

        with mock.patch.object(self.viz, "load_pages", side_effect=load_then_cancel):
            find_button(window, "Test").invoke()
            self.viz.window.update()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(opened_windows(self.viz.window), [])
        self.assertEqual(self.viz.trade_indices, set())
        self.assertIsNone(self.viz.window.grab_current())
        # The file was loaded all the same.
        self.assertEqual(len(self.viz.price_data), 1392)

    def test_closing_the_program_while_the_file_loads_raises_nothing(self) -> None:
        self.build_paginated_app()
        window = open_indicator_based_window(self.viz)
        root = self.viz.window
        load_pages = self.viz.load_pages

        def load_then_close(*args: Any, **options: Any) -> None:
            load_pages(*args, **options)
            window.after(0, lambda: root.tk.eval(root.protocol("WM_DELETE_WINDOW")))

        with mock.patch.object(self.viz, "load_pages", side_effect=load_then_close):
            find_button(window, "Test").invoke()
        self.assertEqual(self.callback_errors, [])
        # Tk no longer answers for the windows of a program that was closed.
        with self.assertRaises(tk.TclError):
            window.winfo_exists()

    def test_second_click_on_test_while_the_file_loads_is_ignored(self) -> None:
        self.build_paginated_app()
        window = open_indicator_based_window(self.viz)
        test_button = find_button(window, "Test")
        load_pages = self.viz.load_pages
        loads = []

        def load_then_click_again(*args: Any, **options: Any) -> None:
            loads.append(options)
            load_pages(*args, **options)
            window.after(0, test_button.invoke)

        with mock.patch.object(self.viz, "load_pages", side_effect=load_then_click_again):
            test_button.invoke()
            self.viz.window.update()
        self.assertEqual(len(loads), 1)
        self.assertEqual(len(opened_windows(window)), 1)
        self.assertEqual(len(self.viz.trade_indices), 38)

    def test_strategy_that_cannot_be_tested_loads_nothing(self) -> None:
        source = self.build_paginated_app()
        window = open_indicator_based_window(self.viz)
        type_strategy(window, [BUY_ROW], [])
        with mock.patch("pytradeviz.messagebox.showerror") as showerror:
            find_button(window, "Test").invoke()
            self.viz.window.update()
        showerror.assert_called_once_with(
            "Invalid setting", "A strategy needs a sell rule, an ROI or a stop loss to sell on.",
            parent=window,
        )
        self.assertEqual(len(self.viz.price_data), 365)
        self.assertTrue(source.has_more)

    def test_file_is_loaded_and_tested_from_another_tab(self) -> None:
        source = self.build_paginated_app()
        self.viz.select_timeframe("1M")
        self.viz.window.update()
        months = len(self.viz.price_data)
        window, results, tree = self.open_results(*DEFAULT)
        self.assertFalse(source.has_more)
        self.assertEqual(self.summary(results).splitlines()[0], f"19 trades, 8 profitable. {TESTED}")
        self.assertEqual(self.listing(tree), self.expected_listing(self.rows, *DEFAULT))
        # The tab now has the months of the whole file, and the ones with trades are highlighted.
        self.assertGreater(len(self.viz.price_data), months)
        self.assertEqual(
            self.viz.trade_indices, {self.holding_candle(day) for day in self.trade_days(*DEFAULT)})
        self.assertIn(self.holding_candle(1376), self.viz.trade_indices)


if __name__ == "__main__":
    unittest.main()
