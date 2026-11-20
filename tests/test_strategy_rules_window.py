from __future__ import annotations

import contextlib
import io
import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, Callable, List, NamedTuple, Sequence, Tuple
from unittest import mock

from cursors import POINTING_HAND
from pytradeviz import PyTradeViz
from strategy_rules import BUY, MAX_RULES, SELL, default_strategy
from test_roi import load_price_rows
from test_strategies_window import (
    assert_on_one_line, collect_callback_errors, descendants, find_button, in_reading_order,
    opened_windows, strategies_menu, type_text,
)
from test_strategy_rules import BUY_ROW, SELL_ROW


# The rule that a row added for ADX holds on each side.
ADX_BUY_ROW = ("ADX", "14", "is below", "25")
ADX_SELL_ROW = ("ADX", "14", "crosses above", "25")

GROUP_TITLES = {BUY: "Buy when all of these are true", SELL: "Sell when any of these is true"}
EXITS_TITLE = "Also sell at (optional)"


class RuleRow(NamedTuple):
    """The drop-downs, boxes and button of one rule in the Indicator Based window."""
    indicator: ttk.Combobox
    period: tk.Entry
    condition: ttk.Combobox
    level: tk.Entry
    remove: tk.Button


def open_indicator_based_window(viz: PyTradeViz) -> tk.Toplevel:
    """Choose Indicator Based from the Strategies drop-down and return the window it opens."""
    before = opened_windows(viz.window)
    strategies_menu(viz).invoke("Indicator Based")
    viz.window.update()
    (window,) = [w for w in opened_windows(viz.window) if w not in before]
    return window


def group_frame(window: tk.Misc, title: str) -> tk.LabelFrame:
    return next(group for group in descendants(window, tk.LabelFrame) if group.cget("text") == title)


def rule_rows(window: tk.Misc, side: str) -> List[RuleRow]:
    """The rows of the buy rules or of the sell rules, from the top one down."""
    rows = []
    for frame in group_frame(window, GROUP_TITLES[side]).pack_slaves():
        if isinstance(frame, tk.Frame):
            indicator, _label, period, condition, level, remove = frame.pack_slaves()
            rows.append(RuleRow(indicator, period, condition, level, remove))
    return rows


def shown_rules(window: tk.Misc, side: str) -> List[Tuple[str, str, str, str]]:
    """The indicator, period, condition and level that each row of one side shows."""
    return [
        (row.indicator.get(), row.period.get(), row.condition.get(), row.level.get())
        for row in rule_rows(window, side)
    ]


def exit_boxes(window: tk.Misc) -> List[tk.Entry]:
    """The ROI box and the stop loss box."""
    return [w for w in group_frame(window, EXITS_TITLE).pack_slaves() if isinstance(w, tk.Entry)]


def shown_strategy(window: tk.Misc) -> Tuple[Any, ...]:
    """Everything the window holds: the rules of each side, the ROI and the stop loss."""
    return (shown_rules(window, BUY), shown_rules(window, SELL), *(box.get() for box in exit_boxes(window)))


def choose(box: ttk.Combobox, value: str) -> None:
    """Make a choice in a drop-down the way a click in its list does, without showing the list."""
    index = box.tk.splitlist(box.cget("values")).index(value)
    box.tk.call("ttk::combobox::SelectEntry", str(box), index)
    # The drop-down tells of the choice when the event loop next runs.
    box.update()


def retype(box: tk.Entry, text: str) -> None:
    box.delete(0, "end")
    type_text(box, text)


def set_rule(row: RuleRow, indicator: str, period: str, condition: str, level: str) -> None:
    # The indicator is chosen first, because another indicator brings its own period and level.
    choose(row.indicator, indicator)
    retype(row.period, period)
    choose(row.condition, condition)
    retype(row.level, level)


def type_strategy(
    window: tk.Misc, buy_rows: Sequence[Sequence[str]], sell_rows: Sequence[Sequence[str]],
    roi: str = "", stop_loss: str = "",
) -> None:
    """Replace what the window holds: the rules of each side, the ROI and the stop loss."""
    for side, wanted in ((BUY, buy_rows), (SELL, sell_rows)):
        # The only buy rule cannot be removed.
        fewest = 1 if side == BUY else 0
        while len(rule_rows(window, side)) > max(len(wanted), fewest):
            rule_rows(window, side)[-1].remove.invoke()
        while len(rule_rows(window, side)) < len(wanted):
            find_button(window, f"Add {side} rule").invoke()
        for row, values in zip(rule_rows(window, side), wanted):
            set_rule(row, *values)
    for box, text in zip(exit_boxes(window), (roi, stop_loss)):
        retype(box, text)


@unittest.skipUnless(
    os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"),
    "A graphical display is required for Tk integration tests",
)
class IndicatorBasedWindowTests(unittest.TestCase):
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

    def test_indicator_based_item_opens_a_modal_window(self) -> None:
        window = open_indicator_based_window(self.viz)
        self.assertEqual(window.title(), "Indicator Based Strategy")
        self.assertTrue(window.winfo_viewable())
        self.assertEqual(str(window.grab_current()), str(window))

    def test_window_starts_with_one_rsi_rule_on_each_side(self) -> None:
        window = open_indicator_based_window(self.viz)
        self.assertEqual(shown_rules(window, BUY), [BUY_ROW])
        self.assertEqual(shown_rules(window, SELL), [SELL_ROW])
        self.assertEqual([box.get() for box in exit_boxes(window)], ["", ""])
        # Typing starts in the period of the buy rule, and no text in the window is selected.
        (buy_row,) = rule_rows(window, BUY)
        self.assertIs(window.focus_lastfor(), buy_row.period)
        boxes = descendants(window, tk.Entry)
        self.assertEqual(len(boxes), 10)
        for box in boxes:
            self.assertFalse(box.selection_present(), box)

    def test_each_rule_is_one_line_of_its_group(self) -> None:
        window = open_indicator_based_window(self.viz)
        find_button(window, "Add buy rule").invoke()
        window.update()
        groups = in_reading_order(window, tk.LabelFrame)
        self.assertEqual(
            [group.cget("text") for group in groups],
            [GROUP_TITLES[BUY], GROUP_TITLES[SELL], EXITS_TITLE],
        )
        for above, below in zip(groups, groups[1:]):
            self.assertLessEqual(above.winfo_rooty() + above.winfo_height(), below.winfo_rooty())
        for side, count in ((BUY, 2), (SELL, 1)):
            rows = rule_rows(window, side)
            self.assertEqual(len(rows), count)
            lines = [row.indicator.master for row in rows]
            for row, line in zip(rows, lines):
                # A drop-down, the period with its label, a drop-down, the level and the button.
                indicator, label, period, condition, level, remove = line.pack_slaves()
                self.assertEqual(row, (indicator, period, condition, level, remove))
                self.assertEqual(label.cget("text"), "Period")
                self.assertEqual(remove.cget("text"), "Remove")
                assert_on_one_line(self, line.pack_slaves())
            # The rows lie one under another with their parts lined up, above the button that adds one.
            add_button = find_button(window, f"Add {side} rule")
            for above, below in zip(lines, lines[1:] + [add_button]):
                self.assertLessEqual(above.winfo_rooty() + above.winfo_height(), below.winfo_rooty())
            for above, below in zip(rows, rows[1:]):
                self.assertEqual(
                    [widget.winfo_rootx() for widget in above], [widget.winfo_rootx() for widget in below])
            group = group_frame(window, GROUP_TITLES[side])
            self.assertLessEqual(
                add_button.winfo_rooty() + add_button.winfo_height(),
                group.winfo_rooty() + group.winfo_height())
        # The ROI and the stop loss share a line, each after its label.
        exits = group_frame(window, EXITS_TITLE)
        roi_label, roi_box, stop_loss_label, stop_loss_box = exits.pack_slaves()
        self.assertEqual((roi_label.cget("text"), stop_loss_label.cget("text")), ("ROI (%)", "Stop loss (%)"))
        self.assertEqual(exit_boxes(window), [roi_box, stop_loss_box])
        assert_on_one_line(self, exits.pack_slaves())
        # Test and Cancel are at the bottom.
        buttons = [find_button(window, "Test"), find_button(window, "Cancel")]
        assert_on_one_line(self, buttons)
        for button in buttons:
            self.assertGreaterEqual(button.winfo_rooty(), exits.winfo_rooty() + exits.winfo_height())
            self.assertLessEqual(
                button.winfo_rooty() + button.winfo_height(), window.winfo_rooty() + window.winfo_height())

    def test_drop_downs_hold_the_indicators_and_the_conditions(self) -> None:
        window = open_indicator_based_window(self.viz)
        conditions = ("crosses above", "crosses below", "is above", "is below")
        for side in (BUY, SELL):
            (row,) = rule_rows(window, side)
            for box, values in ((row.indicator, ("RSI", "ADX")), (row.condition, conditions)):
                self.assertEqual(box.tk.splitlist(box.cget("values")), values)
                # A choice is made from the list, and nothing can be typed.
                self.assertEqual(str(box.cget("state")), "readonly")
                # The text of a choice is not offered to other programs as the selection.
                self.assertFalse(box.tk.getboolean(box.cget("exportselection")))

    def test_period_box_takes_whole_numbers_only(self) -> None:
        window = open_indicator_based_window(self.viz)
        period = rule_rows(window, BUY)[0].period
        period.delete(0, "end")
        for text in ("a", "-", "+", ".", " ", "e", "1.5", "1e3", "12abc", "１"):
            period.insert("end", text)
            self.assertEqual(period.get(), "", repr(text))
        type_text(period, "1234")
        self.assertEqual(period.get(), "1234")
        # A fifth digit is refused, and so is a letter put in the middle.
        period.insert("end", "5")
        period.insert(1, "x")
        self.assertEqual(period.get(), "1234")
        # A refused edit leaves the box checking the edits that follow.
        self.assertEqual(period.cget("validate"), "key")
        period.delete(3)
        type_text(period, "0")
        self.assertEqual(period.get(), "1230")

    def test_level_roi_and_stop_loss_boxes_take_numbers_only_and_no_sign(self) -> None:
        window = open_indicator_based_window(self.viz)
        level = rule_rows(window, SELL)[0].level
        for box in (level, *exit_boxes(window)):
            box.delete(0, "end")
            for text in ("a", "-", "+", " ", "e", "%", "-5", "+5", "1e5", "５"):
                box.insert("end", text)
                self.assertEqual(box.get(), "", repr(text))
            type_text(box, "2.5")
            self.assertEqual(box.get(), "2.5")
            # A second decimal point is refused, and so is a sign put at the start.
            box.insert("end", ".")
            box.insert(0, "-")
            self.assertEqual(box.get(), "2.5")
            self.assertEqual(box.cget("validate"), "key")
            type_text(box, "0")
            self.assertEqual(box.get(), "2.50")

    def test_added_row_holds_an_indicator_the_side_does_not_use_yet(self) -> None:
        window = open_indicator_based_window(self.viz)
        add_buy, add_sell = (find_button(window, f"Add {side} rule") for side in (BUY, SELL))
        add_buy.invoke()
        add_sell.invoke()
        self.assertEqual(shown_rules(window, BUY), [BUY_ROW, ADX_BUY_ROW])
        self.assertEqual(shown_rules(window, SELL), [SELL_ROW, ADX_SELL_ROW])
        # A side that uses both indicators gets another RSI rule.
        add_buy.invoke()
        self.assertEqual(shown_rules(window, BUY), [BUY_ROW, ADX_BUY_ROW, BUY_ROW])

    def test_added_row_is_for_rsi_when_the_side_uses_only_adx(self) -> None:
        window = open_indicator_based_window(self.viz)
        choose(rule_rows(window, SELL)[0].indicator, "ADX")
        find_button(window, "Add sell rule").invoke()
        self.assertEqual(shown_rules(window, SELL), [ADX_SELL_ROW, SELL_ROW])

    def test_period_of_an_added_row_is_ready_for_typing(self) -> None:
        window = open_indicator_based_window(self.viz)
        for side in (SELL, BUY):
            find_button(window, f"Add {side} rule").invoke()
            window.update()
            self.assertIs(window.focus_lastfor(), rule_rows(window, side)[1].period, side)

    def test_no_side_takes_more_than_six_rules(self) -> None:
        self.assertEqual(MAX_RULES, 6)
        window = open_indicator_based_window(self.viz)
        for side in (BUY, SELL):
            with self.subTest(side):
                add_button = find_button(window, f"Add {side} rule")
                for _ in range(5):
                    self.assertEqual(str(add_button.cget("state")), "normal")
                    add_button.invoke()
                self.assertEqual(len(rule_rows(window, side)), 6)
                self.assertEqual(str(add_button.cget("state")), "disabled")
                add_button.invoke()
                self.assertEqual(len(rule_rows(window, side)), 6)
                # Removing a rule makes room for another.
                rule_rows(window, side)[2].remove.invoke()
                self.assertEqual(len(rule_rows(window, side)), 5)
                self.assertEqual(str(add_button.cget("state")), "normal")

    def test_only_buy_rule_cannot_be_removed(self) -> None:
        window = open_indicator_based_window(self.viz)
        (only,) = rule_rows(window, BUY)
        self.assertEqual(str(only.remove.cget("state")), "disabled")
        only.remove.invoke()
        self.assertEqual(shown_rules(window, BUY), [BUY_ROW])
        find_button(window, "Add buy rule").invoke()
        first, second = rule_rows(window, BUY)
        self.assertEqual([str(row.remove.cget("state")) for row in (first, second)], ["normal", "normal"])
        # Either of the two can be removed, and the one that is left cannot.
        first.remove.invoke()
        self.assertEqual(shown_rules(window, BUY), [ADX_BUY_ROW])
        self.assertEqual(str(second.remove.cget("state")), "disabled")

    def test_every_sell_rule_can_be_removed(self) -> None:
        window = open_indicator_based_window(self.viz)
        (only,) = rule_rows(window, SELL)
        self.assertEqual(str(only.remove.cget("state")), "normal")
        only.remove.invoke()
        self.assertEqual(rule_rows(window, SELL), [])
        # The strategy then sells at its ROI or its stop loss alone. A rule can be added again.
        find_button(window, "Add sell rule").invoke()
        self.assertEqual(shown_rules(window, SELL), [SELL_ROW])

    def test_removing_a_row_leaves_the_others_as_typed(self) -> None:
        window = open_indicator_based_window(self.viz)
        add_button = find_button(window, "Add buy rule")
        add_button.invoke()
        add_button.invoke()
        rows = rule_rows(window, BUY)
        set_rule(rows[0], "RSI", "9", "is below", "35")
        set_rule(rows[2], "ADX", "20", "is above", "40.5")
        rows[1].remove.invoke()
        window.update()
        self.assertFalse(rows[1].period.winfo_exists())
        self.assertEqual(
            shown_rules(window, BUY), [("RSI", "9", "is below", "35"), ("ADX", "20", "is above", "40.5")])
        self.assertEqual(shown_rules(window, SELL), [SELL_ROW])

    def test_window_grows_and_shrinks_with_its_rows(self) -> None:
        window = open_indicator_based_window(self.viz)
        height = window.winfo_height()
        find_button(window, "Add sell rule").invoke()
        window.update()
        self.assertGreater(window.winfo_height(), height)
        # The buttons under the rows are still inside the window.
        cancel = find_button(window, "Cancel")
        self.assertLessEqual(
            cancel.winfo_rooty() + cancel.winfo_height(), window.winfo_rooty() + window.winfo_height())
        rule_rows(window, SELL)[1].remove.invoke()
        window.update()
        self.assertEqual(window.winfo_height(), height)

    def test_choosing_another_indicator_brings_its_usual_rule(self) -> None:
        window = open_indicator_based_window(self.viz)
        (buy,), (sell,) = rule_rows(window, BUY), rule_rows(window, SELL)
        set_rule(buy, "RSI", "9", "is below", "35")
        choose(buy.indicator, "ADX")
        self.assertEqual(shown_rules(window, BUY), [ADX_BUY_ROW])
        choose(sell.indicator, "ADX")
        self.assertEqual(shown_rules(window, SELL), [ADX_SELL_ROW])
        # Going back to RSI brings the usual RSI rule, not the one that was typed before.
        choose(buy.indicator, "RSI")
        self.assertEqual(shown_rules(window, BUY), [BUY_ROW])

    def test_choosing_the_indicator_a_row_already_has_keeps_what_was_typed(self) -> None:
        window = open_indicator_based_window(self.viz)
        (buy,) = rule_rows(window, BUY)
        for typed in (("RSI", "9", "is below", "35"), ("ADX", "20", "is above", "40")):
            with self.subTest(typed[0]):
                set_rule(buy, *typed)
                choose(buy.indicator, typed[0])
                self.assertEqual(shown_rules(window, BUY), [typed])

    def test_text_of_a_choice_is_not_left_selected(self) -> None:
        window = open_indicator_based_window(self.viz)
        (buy,) = rule_rows(window, BUY)
        # The indicator is changed and then chosen again, and the condition is changed.
        for box, value in ((buy.indicator, "ADX"), (buy.indicator, "ADX"), (buy.condition, "is above")):
            choose(box, value)
            self.assertEqual(box.get(), value)
            self.assertFalse(box.selection_present(), value)

    def test_buttons_show_the_pointing_hand(self) -> None:
        window = open_indicator_based_window(self.viz)
        # The buttons of a row that is added later show it too.
        find_button(window, "Add buy rule").invoke()
        buttons = descendants(window, tk.Button)
        self.assertEqual(
            sorted(button.cget("text") for button in buttons),
            ["Add buy rule", "Add sell rule", "Cancel", "Remove", "Remove", "Remove", "Test"],
        )
        for button in buttons:
            self.assertEqual(str(button.cget("cursor")), POINTING_HAND, button.cget("text"))

    def check_closing_tests_nothing(self, close: Callable[[tk.Toplevel], Any]) -> None:
        self.viz.set_selection({10, 11, 12}, None)
        view = self.viz.canvas.xview()
        window = open_indicator_based_window(self.viz)
        type_strategy(window, [("RSI", "9", "is below", "35"), ADX_BUY_ROW], [], roi="20", stop_loss="10")
        close(window)
        self.viz.window.update()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(opened_windows(self.viz.window), [])
        self.assertIsNone(self.viz.window.grab_current())
        # The chart is as it was. No trade is highlighted, because nothing was tested.
        self.assertEqual(self.viz.trade_indices, set())
        self.assertEqual(self.viz.selected_indices, {10, 11, 12})
        self.assertEqual(self.viz.canvas.xview(), view)
        # Rules that were never tested are not kept for the next time the window is opened.
        self.assertEqual(self.viz.rule_strategy, default_strategy())
        window = open_indicator_based_window(self.viz)
        self.assertEqual(shown_strategy(window), ([BUY_ROW], [SELL_ROW], "", ""))

    def test_cancel_closes_the_window_and_tests_nothing(self) -> None:
        self.check_closing_tests_nothing(lambda window: find_button(window, "Cancel").invoke())

    def test_closing_the_window_from_its_title_bar_does_the_same(self) -> None:
        # The close button in the title bar runs the window's WM_DELETE_WINDOW handler.
        self.check_closing_tests_nothing(
            lambda window: self.viz.window.tk.eval(window.protocol("WM_DELETE_WINDOW")))

    def test_test_says_when_no_price_data_is_loaded(self) -> None:
        self.viz.close_data_file()
        self.viz.window.update()
        window = open_indicator_based_window(self.viz)
        type_strategy(window, [BUY_ROW, ADX_BUY_ROW], [SELL_ROW], roi="20")
        typed = shown_strategy(window)
        with mock.patch("pytradeviz.messagebox.showerror") as showerror:
            find_button(window, "Test").invoke()
            self.viz.window.update()
        showerror.assert_called_once_with("Unable to test", "No price data is loaded.", parent=window)
        # The window stays as it was, for when data has been loaded.
        self.assertEqual(opened_windows(window), [])
        self.assertEqual(shown_strategy(window), typed)
        self.assertEqual(str(window.grab_current()), str(window))

    def test_test_names_the_rule_or_box_that_cannot_be_tested(self) -> None:
        window = open_indicator_based_window(self.viz)
        cases = (
            (([("RSI", "", "crosses below", "30")], [SELL_ROW]),
             "Buy rule 1: Period must be a whole number from 2 to 9999."),
            (([BUY_ROW, ("ADX", "1", "is below", "25")], [SELL_ROW]),
             "Buy rule 2: Period must be a whole number from 2 to 9999."),
            (([BUY_ROW], [("RSI", "7", "crosses above", "100.5")]),
             "Sell rule 1: Level must be a number from 0 to 100."),
            (([BUY_ROW], [SELL_ROW, ("ADX", "14", "crosses above", "")]),
             "Sell rule 2: Level must be a number from 0 to 100."),
            (([BUY_ROW], [SELL_ROW], "0"), "ROI must be empty or a number greater than 0."),
            (([BUY_ROW], [SELL_ROW], "", "100"),
             "Stop loss must be empty or a number greater than 0 and less than 100."),
            (([BUY_ROW], []), "A strategy needs a sell rule, an ROI or a stop loss to sell on."),
        )
        for strategy, message in cases:
            with self.subTest(message):
                type_strategy(window, *strategy)
                typed = shown_strategy(window)
                with mock.patch("pytradeviz.messagebox.showerror") as showerror:
                    find_button(window, "Test").invoke()
                    self.viz.window.update()
                showerror.assert_called_once_with("Invalid setting", message, parent=window)
                # Nothing was tested, and the window keeps what was typed so it can be put right.
                self.assertEqual(opened_windows(window), [])
                self.assertEqual(self.viz.trade_indices, set())
                self.assertEqual(self.viz.rule_strategy, default_strategy())
                self.assertEqual(shown_strategy(window), typed)
                self.assertEqual(str(window.grab_current()), str(window))


if __name__ == "__main__":
    unittest.main()
