from __future__ import annotations

import math
import unittest
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest import mock

from indicators import adx_components
from strategy_rules import (
    ADX, BUY, CONDITIONS, CROSSES_ABOVE, CROSSES_BELOW, DEFAULT_RULES, INDICATORS, IS_ABOVE,
    IS_BELOW, RSI, SELL, Rule, RuleStrategy, RuleTrade, buy_and_hold_return, compound_return,
    condition_signals, default_strategy, indicator_values, is_period_text, next_default_rule,
    percent_text, rule_strategy, rule_text, rule_trades, trade_returns,
)
from test_strategies import NOT_NUMBER_TEXT, candles, load_price_rows
from trend import wilder_rsi

# The rows of the window as it opens: buy on RSI(7) falling below 30, sell on it rising above 70.
BUY_ROW = ("RSI", "7", "crosses below", "30")
SELL_ROW = ("RSI", "7", "crosses above", "70")
BUY_RULE = Rule(RSI, 7, CROSSES_BELOW, Decimal(30))
SELL_RULE = Rule(RSI, 7, CROSSES_ABOVE, Decimal(70))
SOLD_BY_RULE = "RSI(7) crosses above 70"

# A candle that opens at 100 and reaches neither a stop 5% under it nor a target 10% over it.
QUIET = (100, 101, 99, 100)


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


class DefaultRuleTests(unittest.TestCase):
    def test_the_first_strategy_buys_on_oversold_rsi_and_sells_on_overbought_rsi(self) -> None:
        self.assertEqual(default_strategy(), RuleStrategy((BUY_RULE,), (SELL_RULE,), None, None))

    def test_every_side_and_indicator_has_a_rule_that_can_be_tested(self) -> None:
        self.assertEqual(set(DEFAULT_RULES), {(side, name) for side in (BUY, SELL) for name in INDICATORS})
        for (side, name), rule in DEFAULT_RULES.items():
            row = (rule.indicator, str(rule.period), rule.condition, str(rule.level))
            self.assertEqual(rule.indicator, name)
            self.assertEqual(rule_strategy([row], [row], "", "").buy_rules, (rule,), (side, name))

    def test_adx_buys_without_a_trend_and_sells_when_one_starts(self) -> None:
        self.assertEqual(DEFAULT_RULES[BUY, ADX], Rule(ADX, 14, IS_BELOW, Decimal(25)))
        self.assertEqual(DEFAULT_RULES[SELL, ADX], Rule(ADX, 14, CROSSES_ABOVE, Decimal(25)))

    def test_a_new_row_is_for_the_first_indicator_the_side_does_not_use(self) -> None:
        self.assertEqual(next_default_rule(BUY, []), BUY_RULE)
        self.assertEqual(next_default_rule(BUY, [RSI]), DEFAULT_RULES[BUY, ADX])
        self.assertEqual(next_default_rule(SELL, [RSI, RSI]), DEFAULT_RULES[SELL, ADX])
        self.assertEqual(next_default_rule(SELL, [ADX]), SELL_RULE)

    def test_a_new_row_is_for_rsi_when_the_side_uses_every_indicator(self) -> None:
        self.assertEqual(next_default_rule(BUY, [RSI, ADX]), BUY_RULE)
        self.assertEqual(next_default_rule(SELL, [ADX, RSI, ADX]), SELL_RULE)


class RuleStrategyTests(unittest.TestCase):
    def assert_refused(self, message: str, *boxes: Any) -> None:
        with self.assertRaises(ValueError, msg=boxes) as raised:
            rule_strategy(*boxes)
        self.assertEqual(str(raised.exception), message, boxes)

    def test_the_rows_as_the_window_opens_are_the_first_strategy(self) -> None:
        self.assertEqual(rule_strategy([BUY_ROW], [SELL_ROW], "", ""), default_strategy())

    def test_every_row_is_one_rule_in_the_order_of_the_rows(self) -> None:
        strategy = rule_strategy(
            [BUY_ROW, ("ADX", "14", "is below", "25")],
            [SELL_ROW, ("ADX", "20", "crosses above", "22.5"), ("RSI", "14", "is above", "80")],
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
            rule = rule_strategy([("RSI", period, "is below", "30")], [SELL_ROW], "", "").buy_rules[0]
            self.assertEqual(rule.period, int(period))
        for period in ("", "0", "1", "10000", "7.0", "7.", "-7", "+7", " 7", "seven"):
            self.assert_refused(
                "Buy rule 1: Period must be a whole number from 2 to 9999.",
                [("RSI", period, "is below", "30")], [SELL_ROW], "", "")

    def test_a_level_is_a_number_from_0_to_100(self) -> None:
        for level in ("0", "0.0", "100", "100.00", "29.5", ".5"):
            rule = rule_strategy([BUY_ROW], [("ADX", "14", "is above", level)], "", "").sell_rules[0]
            self.assertEqual(rule.level, Decimal(level))
        for level in ("", ".", "-1", "-0.01", "100.01", "101", "1e1", "thirty"):
            self.assert_refused(
                "Sell rule 1: Level must be a number from 0 to 100.",
                [BUY_ROW], [("ADX", "14", "is above", level)], "", "")

    def test_the_indicator_and_the_condition_are_ones_the_window_offers(self) -> None:
        for indicator in INDICATORS:
            for condition in CONDITIONS:
                rule = rule_strategy([(indicator, "7", condition, "50")], [SELL_ROW], "", "").buy_rules[0]
                self.assertEqual((rule.indicator, rule.condition), (indicator, condition))
        self.assert_refused(
            "Buy rule 1: The indicator must be RSI or ADX.",
            [("MACD", "7", "is below", "30")], [SELL_ROW], "", "")
        self.assert_refused(
            "Buy rule 1: The condition must be crosses above, crosses below, is above or is below.",
            [("RSI", "7", "equals", "30")], [SELL_ROW], "", "")

    def test_the_row_at_fault_is_named_by_its_side_and_number(self) -> None:
        bad = ("RSI", "7", "is above", "")
        self.assert_refused(
            "Buy rule 2: Level must be a number from 0 to 100.", [BUY_ROW, bad], [SELL_ROW], "", "")
        self.assert_refused(
            "Sell rule 3: Level must be a number from 0 to 100.",
            [BUY_ROW], [SELL_ROW, SELL_ROW, bad], "", "")
        # The buy rules are read first, and a row is read from left to right.
        self.assert_refused(
            "Buy rule 1: Period must be a whole number from 2 to 9999.",
            [("RSI", "", "is above", "")], [bad], "", "")

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
        highs, lows, closes = ([row[column] for row in cls.rows] for column in (2, 3, 4))
        cls.values = {(RSI, period): wilder_rsi(closes, period) for period in (7, 14)}
        cls.values[ADX, 14] = adx_components(highs, lows, closes, 14)[0]

    def met(self, rule: Rule, index: int) -> bool:
        """Whether the candle met the rule, worked out from the indicator on it and the one before."""
        values = self.values[rule.indicator, rule.period]
        now, before, level = values[index], values[index - 1] if index else None, float(rule.level)
        if now is None:
            return False
        if rule.condition == IS_ABOVE:
            return now > level
        if rule.condition == IS_BELOW:
            return now < level
        if before is None:
            return False
        return before <= level < now if rule.condition == CROSSES_ABOVE else before >= level > now

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
        ):
            trades = self.check_trades(strategy)
            if count is not None:
                self.assertEqual(len(trades), count, strategy)


if __name__ == "__main__":
    unittest.main()
