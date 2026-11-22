from __future__ import annotations

import math
import statistics
import unittest
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest import mock

from indicators import BOLLINGER_SETTING_FIELDS, Indicators, adx_components
from strategy_rules import (
    ADX, BANDS, BOLLINGER, BUY, CONDITIONS, CROSSES_ABOVE, CROSSES_BELOW, DEFAULT_RULES, INDICATORS,
    IS_ABOVE, IS_BELOW, LOWER_BAND, MAX_MULTIPLIER, MIN_MULTIPLIER, RSI, SELL, UPPER_BAND, AnyRule,
    BandRule, Rule, RuleStrategy, RuleTrade, band_signals, band_values, buy_and_hold_return,
    compound_return, condition_signals, default_strategy, indicator_values, is_period_text,
    next_default_rule, percent_text, rule_strategy, rule_text, rule_trades, trade_returns,
)
from test_strategies import NOT_NUMBER_TEXT, candles, load_price_rows
from trend import wilder_rsi

# The rows of the window as it opens: buy on RSI(7) falling below 30, sell on it rising above 70.
# A row ends with how many candles in a row its rule asks for, which is one.
BUY_ROW = ("RSI", "7", "crosses below", "30", "1")
SELL_ROW = ("RSI", "7", "crosses above", "70", "1")
BUY_RULE = Rule(RSI, 7, CROSSES_BELOW, Decimal(30))
SELL_RULE = Rule(RSI, 7, CROSSES_ABOVE, Decimal(70))
SOLD_BY_RULE = "RSI(7) crosses above 70"

# The row that Bollinger brings on each side: buy on a close under the lower band, sell on a
# close over the upper band.
BAND_BUY_ROW = ("Bollinger", "20", "2", "crosses below", "lower band", "1")
BAND_SELL_ROW = ("Bollinger", "20", "2", "crosses above", "upper band", "1")
BAND_BUY_RULE = BandRule(20, Decimal(2), CROSSES_BELOW, LOWER_BAND)
BAND_SELL_RULE = BandRule(20, Decimal(2), CROSSES_ABOVE, UPPER_BAND)
SOLD_BY_BAND_RULE = "Bollinger(20, 2): close crosses above upper band"

# A candle that opens at 100 and reaches neither a stop 5% under it nor a target 10% over it.
QUIET = (100, 101, 99, 100)


def row_of(rule: AnyRule) -> Tuple[str, ...]:
    """The row of the window that holds the rule."""
    count = str(rule.candles)
    if isinstance(rule, BandRule):
        return (rule.indicator, str(rule.period), str(rule.multiplier), rule.condition, rule.band, count)
    return (rule.indicator, str(rule.period), rule.condition, str(rule.level), count)


def closing_at(*prices: float) -> List[List[Any]]:
    """Candles that close at the given prices, each after opening a quarter under its close."""
    return candles(*((price - 0.25, price + 0.5, price - 0.5, price) for price in prices))


def opening_at(*prices: float) -> List[List[Any]]:
    """Candles that open at the given prices and move half a unit either way."""
    return candles(*((price, price + 0.5, price - 0.5, price) for price in prices))


def scripted_trades(
    values: Dict[Tuple[str, int], Sequence[Optional[float]]], rows: List[List[Any]],
    strategy: RuleStrategy,
) -> List[RuleTrade]:
    """The trades over ``rows`` when each indicator has the given value on every candle."""
    with mock.patch(
        "strategy_rules.indicator_values",
        side_effect=lambda _rows, indicator, period: list(values[indicator, period]),
    ):
        return rule_trades(rows, strategy)


class PeriodTextTests(unittest.TestCase):
    def test_period_text_is_up_to_four_digits(self) -> None:
        for text in ("", "7", "14", "007", "9999", "0000"):
            self.assertTrue(is_period_text(text), repr(text))
        for text in NOT_NUMBER_TEXT + ("12345", "1.5", "7.", ".", "-7", "+7"):
            self.assertFalse(is_period_text(text), repr(text))


class RuleTextTests(unittest.TestCase):
    def test_a_rule_reads_as_indicator_period_condition_and_level(self) -> None:
        self.assertEqual(rule_text(BUY_RULE), "RSI(7) crosses below 30")
        self.assertEqual(rule_text(Rule(ADX, 14, IS_ABOVE, Decimal("25"))), "ADX(14) is above 25")

    def test_the_level_is_written_in_plain_digits(self) -> None:
        for level, text in (("30.0", "30"), ("29.50", "29.5"), ("0", "0"), ("100", "100"), (".5", "0.5")):
            self.assertEqual(rule_text(Rule(RSI, 7, IS_BELOW, Decimal(level))), f"RSI(7) is below {text}")

    def test_a_bollinger_rule_reads_as_its_bands_and_what_the_close_does(self) -> None:
        self.assertEqual(rule_text(BAND_BUY_RULE), "Bollinger(20, 2): close crosses below lower band")
        self.assertEqual(rule_text(BAND_SELL_RULE), SOLD_BY_BAND_RULE)
        self.assertEqual(
            rule_text(BandRule(10, Decimal("1.50"), IS_ABOVE, LOWER_BAND)),
            "Bollinger(10, 1.5): close is above lower band",
        )

    def test_a_rule_for_several_candles_says_how_many(self) -> None:
        self.assertEqual(
            rule_text(Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 3)), "RSI(7) crosses below 30 for 3 candles")
        self.assertEqual(
            rule_text(Rule(ADX, 14, IS_ABOVE, Decimal("22.50"), 2)), "ADX(14) is above 22.5 for 2 candles")
        self.assertEqual(
            rule_text(BandRule(20, Decimal(2), CROSSES_ABOVE, UPPER_BAND, 3)),
            "Bollinger(20, 2): close crosses above upper band for 3 candles",
        )
        self.assertEqual(
            rule_text(BandRule(10, Decimal("1.5"), IS_BELOW, LOWER_BAND, 9999)),
            "Bollinger(10, 1.5): close is below lower band for 9999 candles",
        )

    def test_a_rule_for_one_candle_is_the_rule_on_its_own(self) -> None:
        self.assertEqual(rule_text(Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 1)), "RSI(7) crosses below 30")
        self.assertEqual(rule_text(BandRule(20, Decimal(2), CROSSES_ABOVE, UPPER_BAND, 1)), SOLD_BY_BAND_RULE)
        # A rule is for one candle when it does not say.
        self.assertEqual(Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 1), BUY_RULE)
        self.assertEqual(BandRule(20, Decimal(2), CROSSES_ABOVE, UPPER_BAND, 1), BAND_SELL_RULE)


class DefaultRuleTests(unittest.TestCase):
    def test_the_first_strategy_buys_on_oversold_rsi_and_sells_on_overbought_rsi(self) -> None:
        self.assertEqual(default_strategy(), RuleStrategy((BUY_RULE,), (SELL_RULE,), None, None))

    def test_every_side_and_indicator_has_a_rule_that_can_be_tested(self) -> None:
        self.assertEqual(set(DEFAULT_RULES), {(side, name) for side in (BUY, SELL) for name in INDICATORS})
        for (side, name), rule in DEFAULT_RULES.items():
            row = row_of(rule)
            self.assertEqual(rule.indicator, name)
            self.assertEqual(rule_strategy([row], [row], "", "").buy_rules, (rule,), (side, name))

    def test_adx_buys_without_a_trend_and_sells_when_one_starts(self) -> None:
        self.assertEqual(DEFAULT_RULES[BUY, ADX], Rule(ADX, 14, IS_BELOW, Decimal(25)))
        self.assertEqual(DEFAULT_RULES[SELL, ADX], Rule(ADX, 14, CROSSES_ABOVE, Decimal(25)))

    def test_bollinger_buys_under_the_lower_band_and_sells_over_the_upper_band(self) -> None:
        self.assertEqual(DEFAULT_RULES[BUY, BOLLINGER], BAND_BUY_RULE)
        self.assertEqual(DEFAULT_RULES[SELL, BOLLINGER], BAND_SELL_RULE)
        self.assertEqual((row_of(BAND_BUY_RULE), row_of(BAND_SELL_RULE)), (BAND_BUY_ROW, BAND_SELL_ROW))

    def test_the_rule_of_a_new_row_is_for_one_candle(self) -> None:
        self.assertEqual({rule.candles for rule in DEFAULT_RULES.values()}, {1})

    def test_a_new_row_is_for_the_first_indicator_the_side_does_not_use(self) -> None:
        self.assertEqual(next_default_rule(BUY, []), BUY_RULE)
        self.assertEqual(next_default_rule(BUY, [RSI]), DEFAULT_RULES[BUY, ADX])
        self.assertEqual(next_default_rule(SELL, [RSI, RSI]), DEFAULT_RULES[SELL, ADX])
        self.assertEqual(next_default_rule(SELL, [ADX]), SELL_RULE)
        self.assertEqual(next_default_rule(BUY, [RSI, ADX]), BAND_BUY_RULE)
        self.assertEqual(next_default_rule(SELL, [ADX, RSI, ADX]), BAND_SELL_RULE)
        self.assertEqual(next_default_rule(SELL, [BOLLINGER, RSI]), DEFAULT_RULES[SELL, ADX])

    def test_a_new_row_is_for_rsi_when_the_side_uses_every_indicator(self) -> None:
        self.assertEqual(next_default_rule(BUY, [RSI, ADX, BOLLINGER]), BUY_RULE)
        self.assertEqual(next_default_rule(SELL, [BOLLINGER, ADX, RSI, ADX]), SELL_RULE)


class RuleStrategyTests(unittest.TestCase):
    def assert_refused(self, message: str, *boxes: Any) -> None:
        with self.assertRaises(ValueError, msg=boxes) as raised:
            rule_strategy(*boxes)
        self.assertEqual(str(raised.exception), message, boxes)

    def test_the_rows_as_the_window_opens_are_the_first_strategy(self) -> None:
        self.assertEqual(rule_strategy([BUY_ROW], [SELL_ROW], "", ""), default_strategy())

    def test_every_row_is_one_rule_in_the_order_of_the_rows(self) -> None:
        strategy = rule_strategy(
            [BUY_ROW, ("ADX", "14", "is below", "25", "1")],
            [SELL_ROW, ("ADX", "20", "crosses above", "22.5", "1"), ("RSI", "14", "is above", "80", "1")],
            "", "",
        )
        self.assertEqual(strategy.buy_rules, (BUY_RULE, Rule(ADX, 14, IS_BELOW, Decimal(25))))
        self.assertEqual(strategy.sell_rules, (
            SELL_RULE, Rule(ADX, 20, CROSSES_ABOVE, Decimal("22.5")), Rule(RSI, 14, IS_ABOVE, Decimal(80)),
        ))

    def test_the_roi_and_the_stop_loss_are_kept_as_typed(self) -> None:
        for roi, stop_loss, kept in (
            ("12.5", "7.25", (Decimal("12.5"), Decimal("7.25"))),
            ("", "5", (None, Decimal(5))),
            ("1000", "", (Decimal(1000), None)),
        ):
            strategy = rule_strategy([BUY_ROW], [SELL_ROW], roi, stop_loss)
            self.assertEqual((strategy.roi_percent, strategy.stop_loss_percent), kept)

    def test_a_period_is_a_whole_number_from_2_to_9999(self) -> None:
        for period in ("2", "007", "9999"):
            row = ("RSI", period, "is below", "30", "1")
            self.assertEqual(rule_strategy([row], [SELL_ROW], "", "").buy_rules[0].period, int(period))
        for period in ("", "0", "1", "10000", "7.0", "7.", "-7", "+7", " 7", "seven"):
            self.assert_refused(
                "Buy rule 1: Period must be a whole number from 2 to 9999.",
                [("RSI", period, "is below", "30", "1")], [SELL_ROW], "", "")

    def test_a_level_is_a_number_from_0_to_100(self) -> None:
        for level in ("0", "0.0", "100", "100.00", "29.5", ".5"):
            row = ("ADX", "14", "is above", level, "1")
            self.assertEqual(rule_strategy([BUY_ROW], [row], "", "").sell_rules[0].level, Decimal(level))
        for level in ("", ".", "-1", "-0.01", "100.01", "101", "1e1", "thirty"):
            self.assert_refused(
                "Sell rule 1: Level must be a number from 0 to 100.",
                [BUY_ROW], [("ADX", "14", "is above", level, "1")], "", "")

    def test_the_indicator_and_the_condition_are_ones_the_window_offers(self) -> None:
        self.assertEqual(INDICATORS, (RSI, ADX, BOLLINGER))
        for indicator in (RSI, ADX):
            for condition in CONDITIONS:
                row = (indicator, "7", condition, "50", "1")
                rule = rule_strategy([row], [SELL_ROW], "", "").buy_rules[0]
                self.assertEqual((rule.indicator, rule.condition), (indicator, condition))
        self.assert_refused(
            "Buy rule 1: The indicator must be RSI, ADX or Bollinger.",
            [("MACD", "7", "is below", "30", "1")], [SELL_ROW], "", "")
        self.assert_refused(
            "Buy rule 1: The condition must be crosses above, crosses below, is above or is below.",
            [("RSI", "7", "equals", "30", "1")], [SELL_ROW], "", "")

    def test_a_row_can_ask_for_several_candles_in_a_row(self) -> None:
        strategy = rule_strategy(
            [("RSI", "7", "crosses below", "30", "3"), ("ADX", "14", "is below", "25", "10")],
            [("Bollinger", "20", "2", "is above", "upper band", "2")], "", "",
        )
        self.assertEqual(strategy.buy_rules, (
            Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 3), Rule(ADX, 14, IS_BELOW, Decimal(25), 10),
        ))
        self.assertEqual(strategy.sell_rules, (BandRule(20, Decimal(2), IS_ABOVE, UPPER_BAND, 2),))

    def test_candles_are_a_whole_number_from_1_to_9999(self) -> None:
        # The row of each kind without its last text, which is the candles.
        for start in (BUY_ROW[:-1], BAND_BUY_ROW[:-1]):
            for count in ("1", "3", "007", "9999"):
                rule = rule_strategy([start + (count,)], [SELL_ROW], "", "").buy_rules[0]
                self.assertEqual(rule.candles, int(count), start)
            for count in ("", "0", "0000", "10000", "2.5", "3.", "-1", "+3", " 3", "three"):
                self.assert_refused(
                    "Buy rule 1: Candles must be a whole number from 1 to 9999.",
                    [start + (count,)], [SELL_ROW], "", "")
        self.assert_refused(
            "Sell rule 2: Candles must be a whole number from 1 to 9999.",
            [BUY_ROW], [SELL_ROW, BAND_SELL_ROW[:-1] + ("0",)], "", "")

    def test_a_bollinger_row_is_a_rule_for_the_close_and_a_band(self) -> None:
        strategy = rule_strategy([BAND_BUY_ROW], [BAND_SELL_ROW], "", "")
        self.assertEqual(strategy, RuleStrategy((BAND_BUY_RULE,), (BAND_SELL_RULE,), None, None))
        self.assertEqual(BANDS, ("upper band", "lower band"))
        for condition in CONDITIONS:
            for band in BANDS:
                row = ("Bollinger", "10", "2.5", condition, band, "1")
                self.assertEqual(
                    rule_strategy([row], [SELL_ROW], "", "").buy_rules,
                    (BandRule(10, Decimal("2.5"), condition, band),))
        # Bollinger rows stand among the rows of the other indicators.
        strategy = rule_strategy([BUY_ROW, BAND_BUY_ROW], [BAND_SELL_ROW, SELL_ROW], "", "")
        self.assertEqual(strategy.buy_rules, (BUY_RULE, BAND_BUY_RULE))
        self.assertEqual(strategy.sell_rules, (BAND_SELL_RULE, SELL_RULE))

    def test_a_multiplier_is_a_number_from_a_tenth_to_10(self) -> None:
        for multiplier in ("0.1", ".1", "0.10", "1", "2", "2.5", "10", "10.0"):
            row = ("Bollinger", "20", multiplier, "is below", "lower band", "1")
            rule = rule_strategy([row], [SELL_ROW], "", "").buy_rules[0]
            self.assertEqual(rule.multiplier, Decimal(multiplier))
        for multiplier in ("", ".", "0", "0.09", "0.099", "10.01", "11", "-2", "1e1", "two"):
            self.assert_refused(
                "Buy rule 1: Std. dev. must be a number from 0.1 to 10.",
                [("Bollinger", "20", multiplier, "is below", "lower band", "1")], [SELL_ROW], "", "")

    def test_the_multiplier_has_the_range_of_the_chart_bands(self) -> None:
        ((_, _, _, low, high),) = [field for field in BOLLINGER_SETTING_FIELDS if field[0] == "multiplier"]
        self.assertEqual((float(MIN_MULTIPLIER), float(MAX_MULTIPLIER)), (low, high))

    def test_the_band_and_the_condition_of_a_bollinger_row_are_ones_the_window_offers(self) -> None:
        for band in ("middle band", "upper", "", "30"):
            self.assert_refused(
                "Sell rule 1: The band must be upper band or lower band.",
                [BUY_ROW], [("Bollinger", "20", "2", "crosses above", band, "1")], "", "")
        self.assert_refused(
            "Sell rule 1: The condition must be crosses above, crosses below, is above or is below.",
            [BUY_ROW], [("Bollinger", "20", "2", "touches", "upper band", "1")], "", "")

    def test_a_bollinger_row_is_read_from_left_to_right(self) -> None:
        for period in ("", "1", "10000", "2.5"):
            self.assert_refused(
                "Buy rule 2: Period must be a whole number from 2 to 9999.",
                [BUY_ROW, ("Bollinger", period, "", "touches", "middle band", "")], [SELL_ROW], "", "")
        self.assert_refused(
            "Buy rule 1: Std. dev. must be a number from 0.1 to 10.",
            [("Bollinger", "2", "", "touches", "middle band", "")], [SELL_ROW], "", "")
        self.assert_refused(
            "Buy rule 1: The condition must be crosses above, crosses below, is above or is below.",
            [("Bollinger", "9999", "2", "touches", "middle band", "")], [SELL_ROW], "", "")
        self.assert_refused(
            "Buy rule 1: The band must be upper band or lower band.",
            [("Bollinger", "9999", "2", "is above", "middle band", "")], [SELL_ROW], "", "")
        # The candles box is the last of the row.
        self.assert_refused(
            "Buy rule 1: Candles must be a whole number from 1 to 9999.",
            [("Bollinger", "9999", "2", "is above", "upper band", "")], [SELL_ROW], "", "")

    def test_the_row_at_fault_is_named_by_its_side_and_number(self) -> None:
        bad = ("RSI", "7", "is above", "", "1")
        self.assert_refused(
            "Buy rule 2: Level must be a number from 0 to 100.", [BUY_ROW, bad], [SELL_ROW], "", "")
        self.assert_refused(
            "Sell rule 3: Level must be a number from 0 to 100.",
            [BUY_ROW], [SELL_ROW, SELL_ROW, bad], "", "")
        # The buy rules are read first, and a row is read from left to right.
        self.assert_refused(
            "Buy rule 1: Period must be a whole number from 2 to 9999.",
            [("RSI", "", "is above", "", "")], [bad], "", "")
        self.assert_refused(
            "Buy rule 1: Level must be a number from 0 to 100.",
            [("RSI", "7", "is above", "", "")], [bad], "", "")
        # The candles box is the last of the row.
        self.assert_refused(
            "Buy rule 1: Candles must be a whole number from 1 to 9999.",
            [("RSI", "7", "is above", "70", "")], [bad], "", "")

    def test_a_strategy_needs_a_buy_rule(self) -> None:
        self.assert_refused("A strategy needs at least one buy rule.", [], [SELL_ROW], "10", "5")

    def test_the_roi_is_empty_or_above_zero(self) -> None:
        for roi in ("0", "0.00", ".", "-5", "+", "ten"):
            self.assert_refused(
                "ROI must be empty or a number greater than 0.", [BUY_ROW], [SELL_ROW], roi, "5")

    def test_the_stop_loss_is_empty_or_between_0_and_100(self) -> None:
        for stop_loss in ("0", ".", "100", "100.0", "150", "-5", "five"):
            self.assert_refused(
                "Stop loss must be empty or a number greater than 0 and less than 100.",
                [BUY_ROW], [SELL_ROW], "10", stop_loss)
        self.assertEqual(
            rule_strategy([BUY_ROW], [SELL_ROW], "", "99.99").stop_loss_percent, Decimal("99.99"))

    def test_a_strategy_needs_a_way_to_sell(self) -> None:
        self.assert_refused(
            "A strategy needs a sell rule, an ROI or a stop loss to sell on.", [BUY_ROW], [], "", "")
        for sell_rows, roi, stop_loss in (([SELL_ROW], "", ""), ([], "10", ""), ([], "", "5")):
            strategy = rule_strategy([BUY_ROW], sell_rows, roi, stop_loss)
            self.assertEqual(len(strategy.sell_rules), len(sell_rows))

    def test_an_roi_too_large_to_work_out_cannot_be_tested(self) -> None:
        self.assert_refused("ROI is too large to test.", [BUY_ROW], [SELL_ROW], "9" * 1_000_001, "")
        # A long number that can be worked out is tested.
        self.assertEqual(
            rule_strategy([BUY_ROW], [SELL_ROW], "9" * 400, "").roi_percent, Decimal("9" * 400))


class ConditionSignalsTests(unittest.TestCase):
    def test_is_above_is_true_on_every_candle_over_the_level(self) -> None:
        self.assertEqual(
            condition_signals([29, 30, 30.01, 80, 30, 31], IS_ABOVE, 30),
            [False, False, True, True, False, True],
        )

    def test_is_below_is_true_on_every_candle_under_the_level(self) -> None:
        self.assertEqual(
            condition_signals([31, 30, 29.99, 5, 30, 29], IS_BELOW, 30),
            [False, False, True, True, False, True],
        )

    def test_crosses_above_is_true_only_on_the_candle_that_goes_over_the_level(self) -> None:
        self.assertEqual(
            condition_signals([60, 75, 80, 65, 71, 71, 69], CROSSES_ABOVE, 70),
            [False, True, False, False, True, False, False],
        )

    def test_crosses_below_is_true_only_on_the_candle_that_goes_under_the_level(self) -> None:
        self.assertEqual(
            condition_signals([40, 25, 20, 35, 29, 29, 31], CROSSES_BELOW, 30),
            [False, True, False, False, True, False, False],
        )

    def test_a_candle_that_only_touches_the_level_has_not_crossed_it(self) -> None:
        # The crossing is on the candle that leaves the level for the far side.
        self.assertEqual(
            condition_signals([60, 70, 70, 71], CROSSES_ABOVE, 70), [False, False, False, True])
        self.assertEqual(
            condition_signals([40, 30, 30, 29], CROSSES_BELOW, 30), [False, False, False, True])
        # Coming back from the level to the side it started on is not a crossing.
        self.assertEqual(condition_signals([60, 70, 65], CROSSES_ABOVE, 70), [False, False, False])
        self.assertEqual(condition_signals([40, 30, 35], CROSSES_BELOW, 30), [False, False, False])

    def test_a_candle_without_a_value_is_never_true(self) -> None:
        for condition in CONDITIONS:
            self.assertEqual(condition_signals([None, None, None], condition, 50), [False] * 3, condition)
        self.assertEqual(condition_signals([None, None, 80, 85], IS_ABOVE, 70), [False, False, True, True])
        self.assertEqual(condition_signals([None, None, 20, 15], IS_BELOW, 30), [False, False, True, True])

    def test_the_first_candle_with_a_value_is_not_a_crossing(self) -> None:
        self.assertEqual(
            condition_signals([None, 80, 60, 80], CROSSES_ABOVE, 70), [False, False, False, True])
        self.assertEqual(
            condition_signals([None, 20, 40, 20], CROSSES_BELOW, 30), [False, False, False, True])
        self.assertEqual(condition_signals([80], CROSSES_ABOVE, 70), [False])
        self.assertEqual(condition_signals([], CROSSES_ABOVE, 70), [])

    def test_is_above_for_several_candles_is_true_from_the_last_of_them_on(self) -> None:
        # Four candles over the level, one on it, and three more over it.
        values = [60, 71, 72, 73, 74, 70, 75, 76, 77]
        self.assertEqual(
            condition_signals(values, IS_ABOVE, 70, 2),
            [False, False, True, True, True, False, False, True, True],
        )
        self.assertEqual(
            condition_signals(values, IS_ABOVE, 70, 3),
            [False, False, False, True, True, False, False, False, True],
        )
        self.assertEqual(condition_signals(values, IS_ABOVE, 70, 4), [False] * 4 + [True] + [False] * 4)
        self.assertEqual(condition_signals(values, IS_ABOVE, 70, 5), [False] * 9)

    def test_is_below_for_several_candles_is_true_from_the_last_of_them_on(self) -> None:
        values = [40, 29, 28, 27, 26, 30, 25, 24, 23]
        self.assertEqual(
            condition_signals(values, IS_BELOW, 30, 2),
            [False, False, True, True, True, False, False, True, True],
        )
        self.assertEqual(
            condition_signals(values, IS_BELOW, 30, 3),
            [False, False, False, True, True, False, False, False, True],
        )
        self.assertEqual(condition_signals(values, IS_BELOW, 30, 5), [False] * 9)

    def test_a_crossing_for_several_candles_is_true_only_on_the_last_of_them(self) -> None:
        # The indicator goes over the level for four candles, for two, and then for three.
        values = [60, 71, 72, 73, 74, 65, 80, 81, 69, 90, 91, 92]
        self.assertEqual(
            condition_signals(values, CROSSES_ABOVE, 70, 2),
            [False, False, True, False, False, False, False, True, False, False, True, False],
        )
        self.assertEqual(
            condition_signals(values, CROSSES_ABOVE, 70, 3),
            [False, False, False, True, False, False, False, False, False, False, False, True],
        )
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 4), [False] * 4 + [True] + [False] * 7)
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 5), [False] * 12)
        # The same under a level.
        values = [40, 29, 28, 27, 26, 35, 20, 19, 31, 10, 9, 8]
        self.assertEqual(
            condition_signals(values, CROSSES_BELOW, 30, 2),
            [False, False, True, False, False, False, False, True, False, False, True, False],
        )
        self.assertEqual(
            condition_signals(values, CROSSES_BELOW, 30, 3),
            [False, False, False, True, False, False, False, False, False, False, False, True],
        )

    def test_the_candle_that_crosses_the_level_is_the_first_of_the_candles(self) -> None:
        # The second candle is on the level, so the third is the one that crosses it.
        self.assertEqual(
            condition_signals([60, 70, 71, 72, 73], CROSSES_ABOVE, 70, 3), [False, False, False, False, True])
        self.assertEqual(
            condition_signals([40, 30, 29, 28, 27], CROSSES_BELOW, 30, 3), [False, False, False, False, True])

    def test_candles_beyond_the_level_are_counted_again_after_one_that_is_not(self) -> None:
        # Two candles over the level, one on it and two more over it are never three in a row.
        for condition in (IS_ABOVE, CROSSES_ABOVE):
            self.assertEqual(
                condition_signals([60, 71, 72, 70, 73, 74], condition, 70, 3), [False] * 6, condition)
        for condition in (IS_BELOW, CROSSES_BELOW):
            self.assertEqual(
                condition_signals([40, 29, 28, 30, 27, 26], condition, 30, 3), [False] * 6, condition)

    def test_a_candle_without_a_value_ends_the_candles_in_a_row(self) -> None:
        values = [60, 71, 72, None, 73, 74, 75]
        self.assertEqual(condition_signals(values, IS_ABOVE, 70, 3), [False] * 6 + [True])
        # The candle after it is the first with a value again, which is not a crossing.
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 3), [False] * 7)
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 2), [False, False, True] + [False] * 4)

    def test_candles_in_a_row_from_the_first_value_on_are_not_a_crossing(self) -> None:
        values = [None, 80, 81, 82, 60, 83, 84, 85]
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 3), [False] * 7 + [True])
        self.assertEqual(
            condition_signals(values, IS_ABOVE, 70, 3),
            [False, False, False, True, False, False, False, True],
        )
        self.assertEqual(condition_signals([80, 81, 82], CROSSES_ABOVE, 70, 3), [False] * 3)
        self.assertEqual(condition_signals([80, 81, 82], IS_ABOVE, 70, 3), [False, False, True])

    def test_more_candles_than_any_run_has_is_never_true(self) -> None:
        values = [50, 80, 80, 80, 20, 20, 20]
        for condition in CONDITIONS:
            self.assertEqual(condition_signals(values, condition, 50, 4), [False] * 7, condition)
            self.assertEqual(condition_signals(values, condition, 50, 9999), [False] * 7, condition)
            self.assertEqual(condition_signals([], condition, 50, 3), [], condition)
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 50, 3), [False] * 3 + [True] + [False] * 3)
        self.assertEqual(condition_signals(values, CROSSES_BELOW, 50, 3), [False] * 6 + [True])

    def test_one_candle_is_the_condition_on_its_own(self) -> None:
        values = [None, 60, 75, 80, 70, 71, 71, 69, None, 72, 30, 80]
        for condition in CONDITIONS:
            for_one = condition_signals(values, condition, 70, 1)
            self.assertEqual(for_one, condition_signals(values, condition, 70), condition)
        self.assertEqual(
            condition_signals(values, CROSSES_ABOVE, 70, 1),
            [False, False, True, False, False, True, False, False, False, False, False, True],
        )

    def test_a_value_that_is_not_a_number_is_on_neither_side_of_the_level(self) -> None:
        values = [math.nan, 80, 81, 60, 82, 83]
        self.assertEqual(condition_signals(values, IS_ABOVE, 70), [False, True, True, False, True, True])
        self.assertEqual(condition_signals(values, IS_ABOVE, 70, 2), [False, False, True, False, False, True])
        # The candle after it has not come from the level or from the other side of it.
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70), [False] * 4 + [True, False])
        self.assertEqual(condition_signals(values, CROSSES_ABOVE, 70, 2), [False] * 5 + [True])
        values = [math.nan, 20, 19, 40, 18, 17]
        self.assertEqual(condition_signals(values, CROSSES_BELOW, 30), [False] * 4 + [True, False])
        self.assertEqual(condition_signals(values, CROSSES_BELOW, 30, 2), [False] * 5 + [True])


class IndicatorValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_price_rows()

    def test_rsi_is_the_rsi_of_the_closes(self) -> None:
        closes = [row[4] for row in self.rows]
        for period in (2, 7, 14):
            values = indicator_values(self.rows, RSI, period)
            self.assertEqual(values, wilder_rsi(closes, period))
            self.assertEqual(values[:period], [None] * period)
            self.assertNotIn(None, values[period:])

    def test_adx_is_the_adx_of_the_highs_lows_and_closes(self) -> None:
        highs, lows, closes = ([row[column] for row in self.rows] for column in (2, 3, 4))
        for period in (7, 14):
            values = indicator_values(self.rows, ADX, period)
            self.assertEqual(values, adx_components(highs, lows, closes, period)[0])
            self.assertEqual(values[:2 * period - 1], [None] * (2 * period - 1))
            self.assertNotIn(None, values[2 * period - 1:])

    def test_rows_too_few_for_the_period_have_no_values(self) -> None:
        rows = self.rows[:5]
        self.assertEqual(indicator_values(rows, RSI, 7), [None] * 5)
        self.assertEqual(indicator_values(rows, ADX, 7), [None] * 5)
        self.assertEqual(indicator_values(rows, RSI, 9999), [None] * 5)
        self.assertEqual(indicator_values([], RSI, 7), [])
        self.assertEqual(indicator_values([], ADX, 14), [])


class BandValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_price_rows()

    def test_the_bands_are_the_ones_the_chart_draws(self) -> None:
        for period, multiplier in ((20, "2"), (10, "1.5"), (2, "0.1")):
            _, upper, lower = Indicators(price_data=self.rows).calculate_bollinger(period, float(multiplier))
            self.assertEqual(
                band_values(self.rows, period, Decimal(multiplier)), {UPPER_BAND: upper, LOWER_BAND: lower})

    def test_the_bands_are_standard_deviations_from_the_average_close(self) -> None:
        closes = [row[4] for row in self.rows]
        bands = band_values(self.rows, 20, Decimal("2.5"))
        self.assertEqual(set(bands), set(BANDS))
        for index in (19, 20, 500, len(closes) - 1):
            window = closes[index - 19:index + 1]
            average, deviation = statistics.fmean(window), statistics.pstdev(window)
            self.assertAlmostEqual(bands[UPPER_BAND][index], average + 2.5 * deviation, places=9)
            self.assertAlmostEqual(bands[LOWER_BAND][index], average - 2.5 * deviation, places=9)

    def test_the_first_rows_have_no_bands(self) -> None:
        for band in band_values(self.rows, 20, Decimal(2)).values():
            self.assertEqual(len(band), len(self.rows))
            self.assertEqual(band[:19], [None] * 19)
            self.assertNotIn(None, band[19:])
        none = {UPPER_BAND: [None] * 5, LOWER_BAND: [None] * 5}
        self.assertEqual(band_values(self.rows[:5], 20, Decimal(2)), none)
        self.assertEqual(band_values(self.rows[:5], 9999, Decimal(2)), none)
        self.assertEqual(band_values([], 20, Decimal(2)), {UPPER_BAND: [], LOWER_BAND: []})


class BandSignalsTests(unittest.TestCase):
    def test_is_above_and_is_below_compare_each_close_with_the_band_of_its_candle(self) -> None:
        rows = closing_at(10, 12, 12, 9, 11)
        band = [11, 11, 12.5, 10, 10.5]
        self.assertEqual(band_signals(rows, band, IS_ABOVE), [False, True, False, False, True])
        self.assertEqual(band_signals(rows, band, IS_BELOW), [True, False, True, True, False])

    def test_a_crossing_is_only_on_the_candle_that_closes_beyond_the_band(self) -> None:
        rows = closing_at(10, 12, 13, 9, 9, 8, 12)
        band = [11] * 7
        self.assertEqual(
            band_signals(rows, band, CROSSES_ABOVE), [False, True, False, False, False, False, True])
        self.assertEqual(
            band_signals(rows, band, CROSSES_BELOW), [False, False, False, True, False, False, False])

    def test_a_band_that_moves_past_the_close_is_crossed_too(self) -> None:
        # The close stays at 10 while the band rises from under it to over it, and then falls back.
        rows = closing_at(10, 10, 10, 10, 10)
        band = [9, 9.5, 10.5, 11, 9]
        self.assertEqual(band_signals(rows, band, CROSSES_BELOW), [False, False, True, False, False])
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE), [False, False, False, False, True])

    def test_a_close_on_the_band_is_on_neither_side_of_it(self) -> None:
        rows = closing_at(10, 11, 11, 12, 11, 10)
        band = [11] * 6
        self.assertEqual(band_signals(rows, band, IS_ABOVE), [False, False, False, True, False, False])
        self.assertEqual(band_signals(rows, band, IS_BELOW), [True, False, False, False, False, True])
        # The crossing is on the candle that leaves the band for the far side.
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE), [False, False, False, True, False, False])
        self.assertEqual(band_signals(rows, band, CROSSES_BELOW), [False, False, False, False, False, True])

    def test_a_candle_without_a_band_is_never_true(self) -> None:
        rows = closing_at(10, 10, 12, 13)
        for condition in CONDITIONS:
            self.assertEqual(band_signals(rows, [None] * 4, condition), [False] * 4, condition)
        band = [None, None, 11, 11]
        self.assertEqual(band_signals(rows, band, IS_ABOVE), [False, False, True, True])
        # The first candle with a band is not a crossing.
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE), [False] * 4)
        self.assertEqual(band_signals([], [], CROSSES_ABOVE), [])

    def test_several_candles_are_closes_in_a_row_beyond_the_band_of_each(self) -> None:
        on_third = [False, False, True, False, False, False]
        on_fourth = [False, False, False, True, False, False]
        # The band rises with the closes, which are over it from the second candle to the fourth
        # and on the last.
        rows = closing_at(10, 12, 13, 14, 11, 13)
        band = [11, 11, 12, 13, 12, 12]
        self.assertEqual(band_signals(rows, band, IS_ABOVE, 2), [False, False, True, True, False, False])
        self.assertEqual(band_signals(rows, band, IS_ABOVE, 3), on_fourth)
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE, 2), on_third)
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE, 3), on_fourth)
        for condition in (IS_ABOVE, CROSSES_ABOVE):
            self.assertEqual(band_signals(rows, band, condition, 4), [False] * 6, condition)
        # The same under a band that falls with the closes.
        rows = closing_at(10, 8, 7, 6, 9, 7)
        band = [9, 9, 8, 7, 8, 8]
        self.assertEqual(band_signals(rows, band, IS_BELOW, 2), [False, False, True, True, False, False])
        self.assertEqual(band_signals(rows, band, IS_BELOW, 3), on_fourth)
        self.assertEqual(band_signals(rows, band, CROSSES_BELOW, 2), on_third)
        self.assertEqual(band_signals(rows, band, CROSSES_BELOW, 3), on_fourth)

    def test_a_close_on_the_band_ends_the_closes_in_a_row(self) -> None:
        rows = closing_at(10, 12, 12, 11, 12, 12, 12)
        band = [11] * 7
        self.assertEqual(band_signals(rows, band, IS_ABOVE, 3), [False] * 6 + [True])
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE, 3), [False] * 6 + [True])
        self.assertEqual(
            band_signals(rows, band, CROSSES_ABOVE, 2), [False, False, True, False, False, True, False])

    def test_closes_in_a_row_from_the_first_band_on_are_not_a_crossing(self) -> None:
        rows = closing_at(10, 12, 12, 12, 10, 12, 12)
        band = [None, 11, 11, 11, 11, 11, 11]
        self.assertEqual(
            band_signals(rows, band, IS_ABOVE, 2), [False, False, True, True, False, False, True])
        self.assertEqual(band_signals(rows, band, CROSSES_ABOVE, 2), [False] * 6 + [True])


class RuleTradesTests(unittest.TestCase):
    """Trades for indicator values that are set by hand, so that each candle is known."""

    def rsi_trades(
        self, values: Sequence[Optional[float]], rows: List[List[Any]],
        strategy: RuleStrategy = default_strategy(),
    ) -> List[RuleTrade]:
        return scripted_trades({(RSI, 7): values}, rows, strategy)

    def held_trades(self, *later: Sequence[float], roi: Any = 10, stop_loss: Any = 5) -> List[RuleTrade]:
        """The trades of a position bought at 100 on the third candle, over the candles after it.

        Only its ROI and its stop loss can sell it: none of the candles meets a sell rule.
        """
        rows = candles(QUIET, QUIET, QUIET, *later)
        strategy = RuleStrategy(
            (BUY_RULE,), (SELL_RULE,),
            None if roi is None else Decimal(roi), None if stop_loss is None else Decimal(stop_loss),
        )
        return self.rsi_trades([50, 25] + [40] * (len(rows) - 2), rows, strategy)

    def test_a_buy_is_at_the_open_after_the_candle_that_met_the_buy_rule(self) -> None:
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 40], opening_at(10, 11, 12, 13)), [RuleTrade(2, Decimal(12))])

    def test_a_sale_is_at_the_open_after_the_candle_that_met_the_sell_rule(self) -> None:
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 75, 60], opening_at(10, 11, 12, 13, 14)),
            [RuleTrade(2, Decimal(12), 4, Decimal(14), SOLD_BY_RULE)],
        )

    def test_rules_met_on_the_last_candle_are_not_acted_on(self) -> None:
        self.assertEqual(self.rsi_trades([50, 50, 25], opening_at(10, 11, 12)), [])
        # The position is still open, although the last candle met the sell rule.
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 75], opening_at(10, 11, 12, 13)), [RuleTrade(2, Decimal(12))])

    def test_nothing_is_bought_before_a_buy_rule_is_met(self) -> None:
        self.assertEqual(self.rsi_trades([50, 40, 31, 30, 45], opening_at(10, 11, 12, 13, 14)), [])
        self.assertEqual(self.rsi_trades([], []), [])

    def test_a_buy_needs_every_buy_rule_on_the_same_candle(self) -> None:
        strategy = RuleStrategy((BUY_RULE, Rule(ADX, 14, IS_BELOW, Decimal(25))), (SELL_RULE,))
        values = {
            # RSI falls below 30 on the second and the fifth candle. ADX is under 25 from the third.
            (RSI, 7): [50, 25, 26, 50, 25, 40, 40],
            (ADX, 14): [30, 30, 20, 20, 20, 20, 20],
        }
        self.assertEqual(
            scripted_trades(values, opening_at(10, 11, 12, 13, 14, 15, 16), strategy),
            [RuleTrade(5, Decimal(15))],
        )

    def test_any_sell_rule_sells(self) -> None:
        adx_rule = Rule(ADX, 14, CROSSES_ABOVE, Decimal(25))
        strategy = RuleStrategy((BUY_RULE,), (SELL_RULE, adx_rule))
        rows = opening_at(10, 11, 12, 13, 14)
        for rsi, adx, sold_by in (
            ([50, 25, 40, 40, 40], [10, 10, 10, 30, 30], "ADX(14) crosses above 25"),
            ([50, 25, 40, 75, 60], [10, 10, 10, 10, 10], SOLD_BY_RULE),
        ):
            self.assertEqual(
                scripted_trades({(RSI, 7): rsi, (ADX, 14): adx}, rows, strategy),
                [RuleTrade(2, Decimal(12), 4, Decimal(14), sold_by)],
            )

    def test_the_first_sell_rule_that_was_met_is_named(self) -> None:
        adx_rule = Rule(ADX, 14, CROSSES_ABOVE, Decimal(25))
        values = {(RSI, 7): [50, 25, 40, 75, 60], (ADX, 14): [10, 10, 10, 30, 30]}
        rows = opening_at(10, 11, 12, 13, 14)
        for sell_rules, sold_by in (
            ((SELL_RULE, adx_rule), SOLD_BY_RULE), ((adx_rule, SELL_RULE), "ADX(14) crosses above 25"),
        ):
            self.assertEqual(
                scripted_trades(values, rows, RuleStrategy((BUY_RULE,), sell_rules)),
                [RuleTrade(2, Decimal(12), 4, Decimal(14), sold_by)],
            )

    def test_a_buy_rule_met_while_a_position_is_held_buys_nothing(self) -> None:
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 25, 40, 75, 60], opening_at(10, 11, 12, 13, 14, 15, 16)),
            [RuleTrade(2, Decimal(12), 6, Decimal(16), SOLD_BY_RULE)],
        )

    def test_a_sell_rule_met_while_nothing_is_held_sells_nothing(self) -> None:
        self.assertEqual(
            self.rsi_trades([50, 75, 60, 25, 40], opening_at(10, 11, 12, 13, 14)),
            [RuleTrade(4, Decimal(14))],
        )

    def test_trades_follow_one_another_to_the_last_candle(self) -> None:
        self.assertEqual(
            self.rsi_trades(
                [50, 25, 40, 75, 60, 25, 75, 25, 40], opening_at(10, 11, 12, 13, 14, 15, 16, 17, 18)),
            [
                RuleTrade(2, Decimal(12), 4, Decimal(14), SOLD_BY_RULE),
                RuleTrade(6, Decimal(16), 7, Decimal(17), SOLD_BY_RULE),
                RuleTrade(8, Decimal(18)),
            ],
        )

    def test_a_candle_that_sells_does_not_buy_at_the_same_open(self) -> None:
        # RSI is under 30 on every candle, and ADX is over 25 on the third.
        strategy = RuleStrategy(
            (Rule(RSI, 7, IS_BELOW, Decimal(30)),), (Rule(ADX, 14, IS_ABOVE, Decimal(25)),))
        values = {(RSI, 7): [20] * 5, (ADX, 14): [10, 10, 40, 10, 10]}
        sold = RuleTrade(1, Decimal(11), 3, Decimal(13), "ADX(14) is above 25")
        self.assertEqual(scripted_trades(values, opening_at(10, 11, 12, 13), strategy), [sold])
        # The buy rule is read again when the candle that sold closes.
        self.assertEqual(
            scripted_trades(values, opening_at(10, 11, 12, 13, 14), strategy),
            [sold, RuleTrade(4, Decimal(14))],
        )

    def test_a_candle_that_reaches_the_stop_sells_at_the_stop_price(self) -> None:
        self.assertEqual(self.held_trades((99, 100, 95.01, 96)), [RuleTrade(2, Decimal(100))])
        stopped = [RuleTrade(2, Decimal(100), 3, Decimal(95), "Stop loss")]
        for low in (95, 94.99, 80):
            self.assertEqual(self.held_trades((99, 100, low, 96)), stopped, low)

    def test_a_candle_that_reaches_the_target_sells_at_the_target_price(self) -> None:
        self.assertEqual(self.held_trades((101, 109.99, 100, 109)), [RuleTrade(2, Decimal(100))])
        sold = [RuleTrade(2, Decimal(100), 3, Decimal(110), "ROI")]
        for high in (110, 110.01, 150):
            self.assertEqual(self.held_trades((101, high, 100, 109)), sold, high)

    def test_a_candle_that_opens_beyond_a_price_sells_at_its_open(self) -> None:
        self.assertEqual(
            self.held_trades((90, 92, 88, 91)), [RuleTrade(2, Decimal(100), 3, Decimal(90), "Stop loss")])
        self.assertEqual(
            self.held_trades((115, 118, 114, 116)), [RuleTrade(2, Decimal(100), 3, Decimal(115), "ROI")])
        # A candle that opens on the price sells at it either way.
        self.assertEqual(
            self.held_trades((95, 96, 94, 95)), [RuleTrade(2, Decimal(100), 3, Decimal(95), "Stop loss")])
        self.assertEqual(
            self.held_trades((110, 111, 109, 110)), [RuleTrade(2, Decimal(100), 3, Decimal(110), "ROI")])

    def test_a_candle_that_reaches_both_prices_sells_at_the_stop(self) -> None:
        stopped = [RuleTrade(2, Decimal(100), 3, Decimal(95), "Stop loss")]
        self.assertEqual(self.held_trades((100, 112, 94, 105)), stopped)
        self.assertEqual(self.held_trades((109.99, 112, 94, 105)), stopped)
        # It reached the target first when it opened there.
        self.assertEqual(
            self.held_trades((110, 112, 94, 105)), [RuleTrade(2, Decimal(100), 3, Decimal(110), "ROI")])
        self.assertEqual(
            self.held_trades((111, 112, 94, 105)), [RuleTrade(2, Decimal(100), 3, Decimal(111), "ROI")])

    def test_the_candle_that_buys_can_sell_at_the_stop_or_the_target(self) -> None:
        for bought_on, sale in (
            ((100, 101, 94, 96), (Decimal(95), "Stop loss")),
            ((100, 111, 99, 105), (Decimal(110), "ROI")),
            ((100, 111, 94, 105), (Decimal(95), "Stop loss")),
        ):
            rows = candles(QUIET, QUIET, bought_on, QUIET)
            strategy = RuleStrategy((BUY_RULE,), (), Decimal(10), Decimal(5))
            self.assertEqual(
                self.rsi_trades([50, 25, 40, 40], rows, strategy), [RuleTrade(2, Decimal(100), 2, *sale)])

    def test_a_price_that_is_not_set_is_never_reached(self) -> None:
        crash, surge = (99, 100, 1, 2), (101, 5000, 100, 4000)
        self.assertEqual(
            self.held_trades(crash, surge, roi=None, stop_loss=None), [RuleTrade(2, Decimal(100))])
        self.assertEqual(
            self.held_trades(surge, crash, roi=None),
            [RuleTrade(2, Decimal(100), 4, Decimal(95), "Stop loss")],
        )
        self.assertEqual(
            self.held_trades(crash, surge, stop_loss=None),
            [RuleTrade(2, Decimal(100), 4, Decimal(110), "ROI")],
        )

    def test_a_sell_rule_sells_at_the_open_before_the_stop_or_the_target_is_looked_at(self) -> None:
        strategy = RuleStrategy((BUY_RULE,), (SELL_RULE,), Decimal(10), Decimal(5))
        for opened in ((90, 92, 88, 91), (115, 118, 114, 116), (100, 112, 94, 105)):
            rows = candles(QUIET, QUIET, QUIET, QUIET, opened)
            self.assertEqual(
                self.rsi_trades([50, 25, 40, 75, 60], rows, strategy),
                [RuleTrade(2, Decimal(100), 4, Decimal(opened[0]), SOLD_BY_RULE)],
            )

    def test_the_stop_and_the_target_are_measured_from_the_price_of_each_buy(self) -> None:
        # RSI is under 30 on every candle, so each sale is followed by a buy at the next open.
        strategy = RuleStrategy((Rule(RSI, 7, IS_BELOW, Decimal(30)),), (), Decimal(10), Decimal(5))
        rows = candles(
            QUIET, QUIET, (100, 111, 99, 105), (200, 201, 199, 200), (200, 219, 191, 210),
            (210, 221, 209, 220), (40, 41, 39, 40), (40, 41, 38, 39),
        )
        self.assertEqual(self.rsi_trades([20] * len(rows), rows, strategy), [
            RuleTrade(1, Decimal(100), 2, Decimal(110), "ROI"),
            RuleTrade(3, Decimal(200), 5, Decimal(220), "ROI"),
            RuleTrade(6, Decimal(40), 7, Decimal(38), "Stop loss"),
        ])

    def test_prices_are_compared_with_the_exact_target_and_stop(self) -> None:
        # In float arithmetic the target of 0.1 at 10 is 0.11000000000000001, which a high of
        # 0.11 does not reach, and the stop of 20 at 7 is 18.599999999999998, which a low of
        # 18.6 does not reach.
        flat = (0.1, 0.1, 0.1, 0.1)
        rows = candles(flat, flat, flat, (0.1, 0.11, 0.1, 0.1))
        strategy = RuleStrategy((BUY_RULE,), (), Decimal(10), None)
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 40], rows, strategy),
            [RuleTrade(2, Decimal("0.1"), 3, Decimal("0.11"), "ROI")],
        )
        flat = (20, 20, 20, 20)
        rows = candles(flat, flat, flat, (20, 20, 18.6, 19))
        strategy = RuleStrategy((BUY_RULE,), (), None, Decimal(7))
        self.assertEqual(
            self.rsi_trades([50, 25, 40, 40], rows, strategy),
            [RuleTrade(2, Decimal(20), 3, Decimal("18.6"), "Stop loss")],
        )

    def test_trades_carry_the_exact_prices(self) -> None:
        strategy = RuleStrategy((Rule(RSI, 7, IS_BELOW, Decimal(30)),), (), Decimal("7.5"), Decimal("7.5"))
        rows = candles(
            (19.99, 20, 19.9, 19.99), (19.99, 22, 19.5, 21), (19.99, 20.5, 19.5, 20), (19, 19.5, 18, 18.2))
        self.assertEqual(
            [(trade.buy_price, trade.sell_price) for trade in self.rsi_trades([20] * 4, rows, strategy)],
            [(Decimal("19.99"), Decimal("21.48925")), (Decimal("19.99"), Decimal("18.49075"))],
        )

    def test_nothing_is_bought_at_an_open_of_zero(self) -> None:
        strategy = RuleStrategy((Rule(RSI, 7, IS_BELOW, Decimal(30)),), (SELL_RULE,))
        rows = candles((1, 1, 0, 0), (0, 1, 0, 1), (5, 6, 4, 5))
        self.assertEqual(self.rsi_trades([20, 20, 20], rows, strategy), [RuleTrade(2, Decimal(5))])

    def test_a_strategy_without_buy_rules_never_buys(self) -> None:
        strategy = RuleStrategy((), (SELL_RULE,), Decimal(10), Decimal(5))
        self.assertEqual(self.rsi_trades([20] * 4, opening_at(10, 11, 12, 13), strategy), [])

    def test_a_buy_rule_for_several_candles_buys_at_the_open_after_the_last_of_them(self) -> None:
        strategy = RuleStrategy((Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 3),), (SELL_RULE,))
        rows = opening_at(10, 11, 12, 13, 14, 15)
        # RSI falls below 30 on the second candle and is still there on the fourth.
        values = [50, 25, 26, 27, 40, 40]
        self.assertEqual(self.rsi_trades(values, rows, strategy), [RuleTrade(4, Decimal(14))])
        # The rule for one candle buys two opens sooner.
        self.assertEqual(self.rsi_trades(values, rows), [RuleTrade(2, Decimal(12))])
        # Two candles under 30 are one too few, and so are two and two with a candle between them.
        self.assertEqual(self.rsi_trades([50, 25, 26, 40, 40, 40], rows, strategy), [])
        self.assertEqual(self.rsi_trades([50, 25, 26, 30, 27, 28], rows, strategy), [])
        # The third candle under 30 is the last one, so no candle follows it to buy on.
        self.assertEqual(self.rsi_trades([50, 50, 50, 25, 26, 27], rows, strategy), [])

    def test_a_sell_rule_for_several_candles_sells_at_the_open_after_the_last_of_them(self) -> None:
        strategy = RuleStrategy((BUY_RULE,), (Rule(RSI, 7, IS_ABOVE, Decimal(70), 2),))
        rows = opening_at(10, 11, 12, 13, 14, 15, 16, 17)
        # RSI is over 70 on the fourth candle alone, and then on the sixth and the seventh.
        values = [50, 25, 40, 75, 60, 75, 80, 60]
        self.assertEqual(
            self.rsi_trades(values, rows, strategy),
            [RuleTrade(2, Decimal(12), 7, Decimal(17), "RSI(7) is above 70 for 2 candles")],
        )
        # The rule for one candle sells after the fourth candle.
        one = RuleStrategy((BUY_RULE,), (Rule(RSI, 7, IS_ABOVE, Decimal(70)),))
        self.assertEqual(
            self.rsi_trades(values, rows, one),
            [RuleTrade(2, Decimal(12), 4, Decimal(14), "RSI(7) is above 70")],
        )

    def test_candles_from_before_the_buy_count_towards_a_sell_rule(self) -> None:
        # RSI is over 70 on every candle and under 80 on the first four. The trade bought at
        # the second open is sold after the third candle, which is the third in a row over 70.
        strategy = RuleStrategy(
            (Rule(RSI, 7, IS_BELOW, Decimal(80)),), (Rule(RSI, 7, IS_ABOVE, Decimal(70), 3),))
        self.assertEqual(
            self.rsi_trades([75, 75, 75, 75, 85, 85], opening_at(10, 11, 12, 13, 14, 15), strategy),
            [
                RuleTrade(1, Decimal(11), 3, Decimal(13), "RSI(7) is above 70 for 3 candles"),
                RuleTrade(4, Decimal(14), 5, Decimal(15), "RSI(7) is above 70 for 3 candles"),
            ],
        )

    def test_each_buy_rule_is_met_for_its_own_candles(self) -> None:
        calm = Rule(ADX, 14, IS_BELOW, Decimal(25), 3)
        strategy = RuleStrategy((Rule(RSI, 7, IS_BELOW, Decimal(30), 2), calm), (SELL_RULE,))
        rows = opening_at(10, 11, 12, 13, 14, 15)
        # RSI is under 30 on every candle. ADX is under 25 from the second, so for three on the fourth.
        values = {(RSI, 7): [20] * 6, (ADX, 14): [30, 20, 20, 20, 20, 20]}
        self.assertEqual(scripted_trades(values, rows, strategy), [RuleTrade(4, Decimal(14))])
        # RSI falls below 30 on the second candle, so a crossing for two candles is true on the
        # third alone, which is one candle before the ADX rule is true.
        crossing = RuleStrategy((Rule(RSI, 7, CROSSES_BELOW, Decimal(30), 2), calm), (SELL_RULE,))
        values = {(RSI, 7): [50, 20, 20, 20, 20, 20], (ADX, 14): [30, 20, 20, 20, 20, 20]}
        self.assertEqual(scripted_trades(values, rows, crossing), [])

    def test_rules_that_share_an_indicator_and_a_period_share_its_values(self) -> None:
        strategy = RuleStrategy(
            (BUY_RULE, Rule(RSI, 14, IS_BELOW, Decimal(50))),
            (SELL_RULE, Rule(RSI, 14, IS_ABOVE, Decimal(60))),
        )
        rows = opening_at(10, 11, 12)
        with mock.patch("strategy_rules.indicator_values", return_value=[50, 50, 50]) as values:
            rule_trades(rows, strategy)
        self.assertEqual(
            [call.args for call in values.call_args_list], [(rows, RSI, 7), (rows, RSI, 14)])

    def test_bollinger_rules_that_share_a_period_and_a_multiplier_share_their_bands(self) -> None:
        strategy = RuleStrategy(
            (BAND_BUY_RULE, BandRule(10, Decimal(2), IS_BELOW, LOWER_BAND)),
            (
                BAND_SELL_RULE, BandRule(20, Decimal("2.0"), IS_ABOVE, LOWER_BAND),
                BandRule(20, Decimal(3), IS_ABOVE, UPPER_BAND),
            ),
        )
        rows = opening_at(10, 11, 12)
        none = {UPPER_BAND: [None] * 3, LOWER_BAND: [None] * 3}
        with mock.patch("strategy_rules.indicator_values") as values:
            with mock.patch("strategy_rules.band_values", return_value=none) as bands:
                rule_trades(rows, strategy)
        self.assertEqual(
            [call.args for call in bands.call_args_list],
            [(rows, 20, Decimal(2)), (rows, 10, Decimal(2)), (rows, 20, Decimal(3))],
        )
        # A Bollinger rule needs the closes and no other indicator.
        values.assert_not_called()

    def test_bollinger_rules_are_worked_out_from_the_closes(self) -> None:
        # With a period of 2 and half a standard deviation, the bands lie a quarter of the last
        # change in the close from the average of the last two closes. A close that fell is
        # under the lower band, one that rose is over the upper band, and one that stayed is
        # on both.
        rows = closing_at(10, 10, 8, 8, 12, 12, 12)
        strategy = RuleStrategy(
            (BandRule(2, Decimal("0.5"), CROSSES_BELOW, LOWER_BAND),),
            (BandRule(2, Decimal("0.5"), CROSSES_ABOVE, UPPER_BAND),),
        )
        sold_by = "Bollinger(2, 0.5): close crosses above upper band"
        self.assertEqual(
            rule_trades(rows, strategy), [RuleTrade(3, Decimal("7.75"), 5, Decimal("11.75"), sold_by)])
        # The fall is not a close over the upper band, and the rise is not one under the lower band.
        swapped = RuleStrategy(strategy.sell_rules, strategy.buy_rules)
        self.assertEqual(rule_trades(rows, swapped), [RuleTrade(5, Decimal("11.75"))])

    def test_a_bollinger_rule_buys_with_the_rules_of_other_indicators(self) -> None:
        # The close falls on the third and the fifth candle, and RSI is under 30 from the fourth.
        rows = closing_at(10, 10, 8, 8, 7, 12, 12)
        strategy = RuleStrategy(
            (Rule(RSI, 7, IS_BELOW, Decimal(30)), BandRule(2, Decimal("0.5"), IS_BELOW, LOWER_BAND)),
            (SELL_RULE, BandRule(2, Decimal("0.5"), IS_ABOVE, UPPER_BAND)),
        )
        sold_by = "Bollinger(2, 0.5): close is above upper band"
        self.assertEqual(
            self.rsi_trades([50, 50, 50, 20, 20, 20, 20], rows, strategy),
            [RuleTrade(5, Decimal("11.75"), 6, Decimal("11.75"), sold_by)],
        )

    def test_bollinger_rules_for_several_candles_are_worked_out_from_the_closes(self) -> None:
        # With the same bands, the close falls under the lower band three times in a row, and
        # later rises over the upper band three times in a row.
        rows = closing_at(10, 10, 9, 8, 7, 7, 8, 9, 10, 10)
        strategy = RuleStrategy(
            (BandRule(2, Decimal("0.5"), CROSSES_BELOW, LOWER_BAND, 3),),
            (BandRule(2, Decimal("0.5"), CROSSES_ABOVE, UPPER_BAND, 3),),
        )
        sold_by = "Bollinger(2, 0.5): close crosses above upper band for 3 candles"
        self.assertEqual(
            rule_trades(rows, strategy), [RuleTrade(5, Decimal("6.75"), 9, Decimal("9.75"), sold_by)])
        # Two closes under the band buy an open sooner, and three are too few for four.
        two = RuleStrategy((BandRule(2, Decimal("0.5"), IS_BELOW, LOWER_BAND, 2),), strategy.sell_rules)
        self.assertEqual(
            rule_trades(rows, two), [RuleTrade(4, Decimal("6.75"), 9, Decimal("9.75"), sold_by)])
        four = RuleStrategy((BandRule(2, Decimal("0.5"), IS_BELOW, LOWER_BAND, 4),), strategy.sell_rules)
        self.assertEqual(rule_trades(rows, four), [])

    def test_the_indicators_are_worked_out_from_the_rows(self) -> None:
        # RSI(2) of these closes is 100 on the third candle, then 25, 16.67, 77.27 and 83.33.
        rows = candles(
            (10, 10, 10, 10), (10, 11, 10, 11), (11, 12, 11, 12), (12, 12, 9, 9), (9, 9, 8, 8),
            (8, 12, 8, 12), (12, 13, 12, 13),
        )
        strategy = RuleStrategy(
            (Rule(RSI, 2, CROSSES_BELOW, Decimal(30)),), (Rule(RSI, 2, CROSSES_ABOVE, Decimal(70)),))
        self.assertEqual(
            rule_trades(rows, strategy),
            [RuleTrade(4, Decimal(9), 6, Decimal(12), "RSI(2) crosses above 70")],
        )

    def test_rows_too_few_for_the_indicators_make_no_trades(self) -> None:
        self.assertEqual(rule_trades([], default_strategy()), [])
        self.assertEqual(rule_trades(candles(*[QUIET] * 7), default_strategy()), [])
        strategy = RuleStrategy((Rule(RSI, 9999, IS_BELOW, Decimal(100)),), (SELL_RULE,))
        self.assertEqual(rule_trades(load_price_rows(), strategy), [])

    def test_rows_too_few_for_the_bands_make_no_trades(self) -> None:
        strategy = RuleStrategy((BAND_BUY_RULE,), (BAND_SELL_RULE,))
        self.assertEqual(rule_trades([], strategy), [])
        self.assertEqual(rule_trades(candles(*[QUIET] * 19), strategy), [])
        # The twentieth candle is the first one with bands, so its close under the lower band
        # has not crossed it. It is under the band all the same.
        rows = closing_at(*[100] * 19, 50, 40)
        self.assertEqual(rule_trades(rows, strategy), [])
        under = RuleStrategy((BandRule(20, Decimal(2), IS_BELOW, LOWER_BAND),), (BAND_SELL_RULE,))
        self.assertEqual(rule_trades(rows, under), [RuleTrade(20, Decimal("39.75"))])
        strategy = RuleStrategy((BandRule(9999, Decimal(2), IS_BELOW, UPPER_BAND),), (BAND_SELL_RULE,))
        self.assertEqual(rule_trades(load_price_rows(), strategy), [])


class ReturnTests(unittest.TestCase):
    def test_a_trade_made_the_change_from_its_buy_price_to_its_sell_price(self) -> None:
        rows = opening_at(100, 100)
        trades = [
            RuleTrade(0, Decimal(100), 1, Decimal(110), "ROI"),
            RuleTrade(0, Decimal(100), 1, Decimal(95), "Stop loss"),
            RuleTrade(0, Decimal("0.5"), 1, Decimal("0.5"), SOLD_BY_RULE),
            RuleTrade(0, Decimal("0.3"), 1, Decimal("0.9"), SOLD_BY_RULE),
        ]
        self.assertEqual(trade_returns(rows, trades), [0.1, -0.05, 0.0, 2.0])

    def test_a_trade_that_is_still_open_is_valued_at_the_last_close(self) -> None:
        rows = candles((100, 101, 99, 100), (100, 130, 100, 125), (125, 126, 119, 120))
        self.assertEqual(trade_returns(rows, [RuleTrade(1, Decimal(100))]), [0.2])
        self.assertEqual(trade_returns(rows, [RuleTrade(2, Decimal(125))]), [-0.04])

    def test_no_trades_have_no_returns(self) -> None:
        self.assertEqual(trade_returns(opening_at(100, 100), []), [])
        self.assertEqual(trade_returns([], []), [])

    def test_trades_compound(self) -> None:
        self.assertEqual(compound_return([]), 0)
        self.assertEqual(compound_return([0.25]), 0.25)
        self.assertAlmostEqual(compound_return([0.1, 0.1]), 0.21)
        self.assertAlmostEqual(compound_return([1.0, -0.5]), 0.0)
        self.assertAlmostEqual(compound_return([0.5, -0.2, 0.1]), 0.32)
        self.assertEqual(compound_return([0.5, -1.0, 3.0]), -1.0)

    def test_buy_and_hold_is_from_the_first_open_to_the_last_close(self) -> None:
        rows = candles((100, 160, 90, 150), (150, 170, 120, 160), (160, 165, 110, 125))
        self.assertEqual(buy_and_hold_return(rows), 0.25)
        self.assertEqual(buy_and_hold_return(rows[:1]), 0.5)
        self.assertEqual(buy_and_hold_return(candles((100, 100, 40, 50))), -0.5)

    def test_buy_and_hold_needs_a_first_open_above_zero(self) -> None:
        self.assertIsNone(buy_and_hold_return([]))
        self.assertIsNone(buy_and_hold_return(candles((0, 5, 0, 5), (5, 6, 4, 5))))

    def test_a_return_is_written_as_a_signed_percentage(self) -> None:
        for fraction, text in (
            (0.05, "+5.00%"), (-0.7613, "-76.13%"), (5.532, "+553.20%"), (139.5307, "+13953.07%"),
            (-1.0, "-100.00%"), (0.00004, "0.00%"), (-0.00004, "0.00%"), (0.0, "0.00%"), (-0.0, "0.00%"),
            (0.0001, "+0.01%"), (-0.0001, "-0.01%"),
        ):
            self.assertEqual(percent_text(fraction), text, fraction)


class RealPriceTests(unittest.TestCase):
    """Strategies tested on four years of daily XRP prices."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_price_rows()
        highs, lows, cls.closes = ([row[column] for row in cls.rows] for column in (2, 3, 4))
        cls.values = {(RSI, period): wilder_rsi(cls.closes, period) for period in (7, 14)}
        cls.values[ADX, 14] = adx_components(highs, lows, cls.closes, 14)[0]
        # The bands as the chart draws them, by their period and their multiplier.
        cls.bands = {}
        for period, multiplier in ((20, Decimal(2)), (10, Decimal("1.5"))):
            _, upper, lower = Indicators(price_data=cls.rows).calculate_bollinger(period, float(multiplier))
            cls.bands[period, multiplier] = {UPPER_BAND: upper, LOWER_BAND: lower}

    def compared(self, rule: AnyRule, index: int) -> Optional[Tuple[float, float]]:
        """What the rule compares on a candle: a value, and the level that it is held against.

        A Bollinger rule holds the close against the band of that candle. None on a candle
        that has no value yet.
        """
        if isinstance(rule, BandRule):
            band = self.bands[rule.period, rule.multiplier][rule.band][index]
            return None if band is None else (self.closes[index], band)
        value = self.values[rule.indicator, rule.period][index]
        return None if value is None else (value, float(rule.level))

    def beyond(self, rule: AnyRule, index: int) -> Optional[bool]:
        """Whether a candle left what the rule compares on the side of the level that the rule names.

        None on a candle that has no value yet.
        """
        now = self.compared(rule, index)
        if now is None:
            return None
        value, level = now
        return value > level if rule.condition in (IS_ABOVE, CROSSES_ABOVE) else value < level

    def met(self, rule: AnyRule, index: int) -> bool:
        """Whether the candle met the rule, worked out from its candles and the one before them."""
        first = index - rule.candles + 1
        if first < 0 or not all(self.beyond(rule, at) for at in range(first, index + 1)):
            return False
        if rule.condition in (IS_ABOVE, IS_BELOW):
            return True
        # A crossing came from a candle with a value on the level or on the other side of it.
        return first > 0 and self.beyond(rule, first - 1) is False

    def check_trades(self, strategy: RuleStrategy) -> List[RuleTrade]:
        """Test the strategy and check each trade against the candles around it."""
        rows = self.rows
        last = len(rows) - 1
        candle_numbers = range(len(rows))
        buys = [all(self.met(rule, index) for rule in strategy.buy_rules) for index in candle_numbers]
        sells = [[rule for rule in strategy.sell_rules if self.met(rule, index)] for index in candle_numbers]
        roi_percent, stop_loss_percent = strategy.roi_percent, strategy.stop_loss_percent
        trades = rule_trades(rows, strategy)
        waiting_from = 0
        for number, trade in enumerate(trades):
            where = (strategy, number)
            # No candle since the last sale met the buy rules until the one before the buy.
            self.assertGreater(trade.buy_index, waiting_from, where)
            self.assertNotIn(True, buys[waiting_from:trade.buy_index - 1], where)
            self.assertTrue(buys[trade.buy_index - 1], where)
            self.assertEqual(trade.buy_price, Decimal(repr(rows[trade.buy_index][1])), where)
            target = None if roi_percent is None else trade.buy_price * (1 + roi_percent / 100)
            stop = None if stop_loss_percent is None else trade.buy_price * (1 - stop_loss_percent / 100)
            take = math.inf if target is None else float(target)
            cut = -math.inf if stop is None else float(stop)
            if trade.sell_index is None:
                # Only the last trade can be left open.
                self.assertEqual(number, len(trades) - 1, strategy)
                self.assertEqual((trade.sell_price, trade.sold_by), (None, None), strategy)
                held_to = last + 1
            else:
                self.assertGreaterEqual(trade.sell_index, trade.buy_index, where)
                held_to = trade.sell_index
            # Until the sale no candle reached the stop or the target, and no candle met a sell
            # rule in time to sell at an earlier open.
            for row in rows[trade.buy_index:held_to]:
                self.assertTrue(row[3] > cut and row[2] < take, where)
            self.assertEqual(sells[trade.buy_index:min(held_to, last) - 1], [[]] * max(
                0, min(held_to, last) - 1 - trade.buy_index), where)
            if trade.sell_index is None:
                waiting_from = last
                continue
            open_, high, low = rows[trade.sell_index][1:4]
            met = sells[trade.sell_index - 1] if trade.sell_index > trade.buy_index else []
            if met:
                expected = (Decimal(repr(open_)), rule_text(met[0]))
            elif open_ <= cut:
                expected = (Decimal(repr(open_)), "Stop loss")
            elif open_ >= take:
                expected = (Decimal(repr(open_)), "ROI")
            elif low <= cut:
                expected = (stop, "Stop loss")
            else:
                self.assertGreaterEqual(high, take, where)
                expected = (target, "ROI")
            self.assertEqual((trade.sell_price, trade.sold_by), expected, where)
            waiting_from = trade.sell_index
        self.assertNotIn(True, buys[waiting_from:last], strategy)
        return trades

    def test_every_trade_follows_the_rules(self) -> None:
        rsi_14_buy = Rule(RSI, 14, CROSSES_BELOW, Decimal(30))
        rsi_14_sell = Rule(RSI, 14, CROSSES_ABOVE, Decimal(70))
        calm = Rule(ADX, 14, IS_BELOW, Decimal(25))
        trending = Rule(ADX, 14, CROSSES_ABOVE, Decimal(25))
        dip = Rule(RSI, 7, IS_BELOW, Decimal(30))
        under = BandRule(10, Decimal("1.5"), IS_BELOW, LOWER_BAND)
        over = BandRule(10, Decimal("1.5"), IS_ABOVE, UPPER_BAND)
        for strategy, count in (
            (default_strategy(), None),
            (RuleStrategy((rsi_14_buy,), (rsi_14_sell,)), None),
            (RuleStrategy((BUY_RULE,), (SELL_RULE,), Decimal(10), Decimal(5)), None),
            (RuleStrategy((BUY_RULE,), (), Decimal(20), Decimal(10)), None),
            (RuleStrategy((BUY_RULE,), (), Decimal(3), None), None),
            (RuleStrategy((BUY_RULE,), (), None, Decimal("1.5")), None),
            (RuleStrategy((dip, calm), (SELL_RULE, trending)), None),
            (RuleStrategy((dip,), (trending, rsi_14_sell), Decimal(50), Decimal(20)), None),
            (RuleStrategy((dip, calm), (Rule(RSI, 7, IS_ABOVE, Decimal(50)),), Decimal(1), Decimal(1)), None),
            (RuleStrategy((Rule(RSI, 7, IS_ABOVE, Decimal(100)),), (SELL_RULE,)), 0),
            (RuleStrategy((BAND_BUY_RULE,), (BAND_SELL_RULE,)), 17),
            (RuleStrategy((BAND_BUY_RULE,), (BAND_SELL_RULE,), Decimal(10), Decimal(5)), None),
            (RuleStrategy((BAND_BUY_RULE,), (), Decimal(20), Decimal(10)), None),
            (RuleStrategy((under,), (over,)), None),
            (RuleStrategy((dip, under), (SELL_RULE, over)), None),
            (RuleStrategy((under, calm), (trending, over), Decimal(25), None), None),
            # Bought on a close over the upper band and sold on one under the lower band.
            (RuleStrategy((BAND_SELL_RULE,), (BAND_BUY_RULE,)), None),
        ):
            trades = self.check_trades(strategy)
            if count is not None:
                self.assertEqual(len(trades), count, strategy)

    def test_every_trade_follows_rules_for_several_candles(self) -> None:
        def rsi(condition: str, level: int, count: int) -> Rule:
            return Rule(RSI, 7, condition, Decimal(level), count)

        def adx(condition: str, count: int) -> Rule:
            return Rule(ADX, 14, condition, Decimal(25), count)

        def band(condition: str, name: str, count: int) -> BandRule:
            return BandRule(20, Decimal(2), condition, name, count)

        def narrow(condition: str, name: str, count: int) -> BandRule:
            return BandRule(10, Decimal("1.5"), condition, name, count)

        under, over = narrow(IS_BELOW, LOWER_BAND, 2), narrow(IS_ABOVE, UPPER_BAND, 2)
        for strategy, count in (
            (RuleStrategy((rsi(CROSSES_BELOW, 30, 2),), (rsi(CROSSES_ABOVE, 70, 2),)), 11),
            (RuleStrategy((rsi(CROSSES_BELOW, 30, 3),), (rsi(CROSSES_ABOVE, 70, 3),)), 8),
            (RuleStrategy((rsi(CROSSES_BELOW, 30, 3),), (SELL_RULE,)), None),
            (RuleStrategy((rsi(CROSSES_BELOW, 30, 5),), (rsi(CROSSES_ABOVE, 70, 5),)), None),
            (RuleStrategy((rsi(IS_BELOW, 30, 2),), (rsi(IS_ABOVE, 70, 2),), Decimal(10), Decimal(5)), None),
            (RuleStrategy((rsi(IS_BELOW, 30, 4),), (rsi(IS_ABOVE, 70, 3),)), None),
            (RuleStrategy((band(CROSSES_BELOW, LOWER_BAND, 2),), (band(CROSSES_ABOVE, UPPER_BAND, 2),)), 11),
            (RuleStrategy((band(CROSSES_BELOW, LOWER_BAND, 3),), (band(CROSSES_ABOVE, UPPER_BAND, 3),)), 7),
            (RuleStrategy((band(IS_BELOW, LOWER_BAND, 2),), (band(IS_ABOVE, UPPER_BAND, 2),)), None),
            (RuleStrategy((under,), (narrow(IS_ABOVE, UPPER_BAND, 3),)), None),
            (RuleStrategy(
                (narrow(CROSSES_BELOW, LOWER_BAND, 3),), (narrow(CROSSES_ABOVE, UPPER_BAND, 2),)), None),
            (RuleStrategy(
                (rsi(IS_BELOW, 30, 2), adx(IS_BELOW, 5)), (rsi(CROSSES_ABOVE, 70, 2), adx(CROSSES_ABOVE, 3)),
            ), None),
            (RuleStrategy((under, adx(IS_BELOW, 3)), (adx(CROSSES_ABOVE, 2), over), Decimal(25), None), None),
            # The file has fewer candles than the buy rule asks for.
            (RuleStrategy((rsi(IS_BELOW, 100, 9999),), (SELL_RULE,)), 0),
        ):
            trades = self.check_trades(strategy)
            if count is not None:
                self.assertEqual(len(trades), count, strategy)

    def test_a_rule_for_one_more_candle_is_true_one_candle_later(self) -> None:
        # It is true there when that candle leaves the indicator beyond the level too.
        sides = {CROSSES_ABOVE: IS_ABOVE, IS_ABOVE: IS_ABOVE, CROSSES_BELOW: IS_BELOW, IS_BELOW: IS_BELOW}
        for key, level in (((RSI, 7), 30), ((RSI, 14), 70), ((ADX, 14), 25)):
            values = self.values[key]
            for condition, side in sides.items():
                beyond = condition_signals(values, side, level)
                signals = condition_signals(values, condition, level)
                for count in range(2, 9):
                    earlier, signals = signals, condition_signals(values, condition, level, count)
                    after = [False] + [was and now for was, now in zip(earlier, beyond[1:])]
                    self.assertEqual(signals, after, (key, condition, count))
                    self.assertIn(True, signals, (key, condition, count))


if __name__ == "__main__":
    unittest.main()
