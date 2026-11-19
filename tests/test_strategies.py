from __future__ import annotations

import csv
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Sequence

from strategies import (
    Trade, is_price_text, is_roi_text, is_stop_loss_text, parse_number, positional_levels,
    positional_trades, price_text, stop_price, stop_price_text, target_price, target_price_text,
)

# Text that is a number, or the start of one, for a price and so for an ROI as well.
UNSIGNED_TEXT = ("", "7", "007", "12.", ".5", "0.25", ".", "65432.12345")
# Text that no box takes. float() and Decimal() would read several of these as numbers.
NOT_NUMBER_TEXT = (
    "a", "1a", "1.2.3", "1e5", "1e-5", " 1", "1 ", "1\n", "1,5", "$1", "5%", "inf", "nan",
    "1_000", "１２", "١٢", "−5", "--1", "1-", "-+1", "- 1",
)
SIGNED_TEXT = ("-", "+", "-1", "+1", "-.5")

# An order to buy at 100, with a target of 110 and a stop of 95.
ENTRY, TARGET, STOP = positional_levels("100", "10", "5")


def candles(*prices: Sequence[float]) -> List[List[Any]]:
    """Price rows for (open, high, low, close) candles, one for each day from 2024-01-01."""
    return [[["2024", "01", f"{day:02d}"], *ohlc, {}] for day, ohlc in enumerate(prices, start=1)]


def load_price_rows() -> List[List[Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "XRP_4_year_ohlc_no_vol.csv"
    with path.open(newline="") as file:
        rows = list(csv.reader(file))[1:]
    return [[row[0].split("-"), *(float(value) for value in row[1:5]), {}] for row in rows]


class NumberTextTests(unittest.TestCase):
    def test_price_text_is_digits_with_at_most_one_decimal_point(self) -> None:
        for text in UNSIGNED_TEXT:
            self.assertTrue(is_price_text(text), repr(text))
        for text in NOT_NUMBER_TEXT:
            self.assertFalse(is_price_text(text), repr(text))

    def test_price_text_has_no_sign(self) -> None:
        for text in SIGNED_TEXT:
            self.assertFalse(is_price_text(text), repr(text))

    def test_roi_text_may_start_with_a_sign(self) -> None:
        for text in UNSIGNED_TEXT + ("-", "+", "-5", "+5", "-.", "-0.75", "+.5"):
            self.assertTrue(is_roi_text(text), repr(text))
        for text in NOT_NUMBER_TEXT:
            self.assertFalse(is_roi_text(text), repr(text))

    def test_stop_loss_text_is_digits_with_at_most_one_decimal_point_and_no_sign(self) -> None:
        for text in UNSIGNED_TEXT:
            self.assertTrue(is_stop_loss_text(text), repr(text))
        for text in NOT_NUMBER_TEXT + SIGNED_TEXT:
            self.assertFalse(is_stop_loss_text(text), repr(text))

    def test_parse_number_reads_finished_numbers(self) -> None:
        for text, number in (("7", "7"), ("007", "7"), ("12.", "12"), (".5", "0.5"),
                             ("-7.25", "-7.25"), ("+3", "3"), ("-.5", "-0.5"), ("0", "0")):
            self.assertEqual(parse_number(text), Decimal(number), repr(text))

    def test_parse_number_is_none_until_the_text_is_a_number(self) -> None:
        for text in ("", ".", "-", "+", "-.", "+.") + NOT_NUMBER_TEXT:
            self.assertIsNone(parse_number(text), repr(text))

    def test_length_does_not_change_the_answer(self) -> None:
        # A pattern that could match these digits in more than one way would take minutes here.
        digits = "9" * 100_000
        for is_number_text in (is_price_text, is_roi_text, is_stop_loss_text):
            self.assertTrue(is_number_text(digits + "." + digits))
            self.assertFalse(is_number_text(digits + "x"))
            self.assertFalse(is_number_text(digits + "." + digits + "."))
        self.assertIsNone(parse_number(digits + "\n"))
        self.assertIsNone(parse_number("." + digits + "x"))


class TargetPriceTests(unittest.TestCase):
    def test_roi_is_applied_as_a_percentage_of_the_entry_price(self) -> None:
        for entry_price, roi_percent, target in (
            ("100", "5", "105"), ("100", "-5", "95"), ("100", "0", "100"),
            ("19.99", "7.5", "21.48925"), ("100", "-100", "0"), ("100", "-150", "-50"),
        ):
            self.assertEqual(target_price(Decimal(entry_price), Decimal(roi_percent)), Decimal(target))

    def test_text_is_the_exact_target_price(self) -> None:
        for entry_price, roi, shown in (
            # Float arithmetic gives 110.00000000000001, 0.10020000000000001 and
            # 195.78074999999998 for the first three.
            ("100", "10", "110"), ("0.1", "0.2", "0.1002"), ("187.35", "4.5", "195.78075"),
            ("19.99", "7.5", "21.48925"), ("65432.1", "2.5", "67067.9025"),
            ("3", "33.333333", "3.99999999"),
        ):
            self.assertEqual(target_price_text(entry_price, roi), shown, (entry_price, roi))

    def test_text_is_empty_until_both_boxes_hold_a_number(self) -> None:
        for entry_price, roi in (("", ""), ("100", ""), ("", "5"), ("100", "-"), ("100", "+"),
                                 ("100", "-."), (".", "5"), ("abc", "5"), ("100", "1e5")):
            self.assertEqual(target_price_text(entry_price, roi), "", (entry_price, roi))

    def test_text_has_no_trailing_zeros_or_exponent(self) -> None:
        for entry_price, roi, shown in (
            ("100.", ".5", "100.5"), ("100.00", "0", "100"), ("007", "1", "7.07"),
            ("1000000", "0", "1000000"), ("5000", "100", "10000"),
            ("0.00001234", "10", "0.000013574"), ("0.0000000123", "10", "0.00000001353"),
            ("1" + "0" * 30, "5", "105" + "0" * 28),
        ):
            self.assertEqual(target_price_text(entry_price, roi), shown, (entry_price, roi))

    def test_signed_roi_moves_the_target_either_way(self) -> None:
        for entry_price, roi, shown in (
            ("100", "+5", "105"), ("100", "-25", "75"), ("100", "-0", "100"),
            ("100", "-100", "0"), ("100", "-150", "-50"),
        ):
            self.assertEqual(target_price_text(entry_price, roi), shown, (entry_price, roi))

    def test_zero_is_shown_without_a_sign_or_decimals(self) -> None:
        for entry_price, roi in (("0", "5"), ("0", "-150"), ("0.00", "-150"), ("100", "-100.0")):
            self.assertEqual(target_price_text(entry_price, roi), "0", (entry_price, roi))

    def test_text_is_empty_when_the_number_is_too_large_to_work_out(self) -> None:
        huge = "9" * 1_000_001
        self.assertEqual(target_price_text(huge, "5"), "")
        self.assertEqual(target_price_text("100", huge), "")
        self.assertEqual(target_price_text("100", "-" + huge), "")


class StopPriceTests(unittest.TestCase):
    def test_stop_loss_is_taken_off_as_a_percentage_of_the_entry_price(self) -> None:
        for entry_price, stop_loss_percent, stop in (
            ("100", "5", "95"), ("100", "0", "100"), ("19.99", "7.5", "18.49075"),
            ("100", "100", "0"), ("100", "150", "-50"),
        ):
            self.assertEqual(stop_price(Decimal(entry_price), Decimal(stop_loss_percent)), Decimal(stop))

    def test_text_is_the_exact_stop_price(self) -> None:
        for entry_price, stop_loss, shown in (
            # Float arithmetic gives 178.91924999999998, 29.753999999999998 and
            # 18.599999999999998 for the first three.
            ("187.35", "4.5", "178.91925"), ("31.32", "5", "29.754"), ("20", "7", "18.6"),
            ("19.99", "7.5", "18.49075"), ("65432.1", "2.5", "63796.2975"),
            ("3", "33.333333", "2.00000001"),
        ):
            self.assertEqual(stop_price_text(entry_price, stop_loss), shown, (entry_price, stop_loss))

    def test_text_is_empty_until_both_boxes_hold_a_number(self) -> None:
        for entry_price, stop_loss in (("", ""), ("100", ""), ("", "5"), ("100", "."), (".", "5"),
                                       ("abc", "5"), ("100", "1e5")):
            self.assertEqual(stop_price_text(entry_price, stop_loss), "", (entry_price, stop_loss))

    def test_text_has_no_trailing_zeros_or_exponent(self) -> None:
        for entry_price, stop_loss, shown in (
            ("100.", ".5", "99.5"), ("100.00", "0", "100"), ("007", "1", "6.93"),
            ("5000", "50", "2500"), ("0.00001234", "10", "0.000011106"),
            ("1" + "0" * 30, "5", "95" + "0" * 28),
        ):
            self.assertEqual(stop_price_text(entry_price, stop_loss), shown, (entry_price, stop_loss))

    def test_a_stop_loss_of_100_or_more_takes_the_price_to_zero_or_below(self) -> None:
        for entry_price, stop_loss, shown in (
            ("100", "100", "0"), ("100", "100.0", "0"), ("0", "5", "0"), ("0.00", "150", "0"),
            ("100", "150", "-50"),
        ):
            self.assertEqual(stop_price_text(entry_price, stop_loss), shown, (entry_price, stop_loss))

    def test_text_is_empty_when_the_number_is_too_large_to_work_out(self) -> None:
        huge = "9" * 1_000_001
        self.assertEqual(stop_price_text(huge, "5"), "")
        self.assertEqual(stop_price_text("100", huge), "")


class PriceTextTests(unittest.TestCase):
    def test_price_is_written_in_plain_digits(self) -> None:
        for price, shown in (
            ("95.00", "95"), ("110.0", "110"), ("0.5000", "0.5"), ("1E+3", "1000"),
            ("1.2E-7", "0.00000012"), ("-50.0", "-50"), ("0", "0"), ("-0", "0"), ("0E+5", "0"),
            ("0.000", "0"),
        ):
            self.assertEqual(price_text(Decimal(price)), shown, price)


class PositionalLevelsTests(unittest.TestCase):
    def test_levels_are_the_entry_target_and_stop_prices(self) -> None:
        for boxes, levels in (
            (("100", "10", "5"), ("100", "110", "95")),
            (("0.5", "+20", "10."), ("0.5", "0.6", "0.45")),
            (("19.99", "7.5", "7.5"), ("19.99", "21.48925", "18.49075")),
            ((".5", "1000", "99.9"), ("0.5", "5.5", "0.0005")),
        ):
            self.assertEqual(positional_levels(*boxes), tuple(Decimal(level) for level in levels), boxes)

    def test_each_box_must_hold_a_number_that_can_be_tested(self) -> None:
        entry_price = "Entry price must be a number greater than 0."
        roi = "ROI must be a number greater than 0."
        stop_loss = "Stop loss must be a number greater than 0 and less than 100."
        for boxes, message in (
            (("", "10", "5"), entry_price), ((".", "10", "5"), entry_price),
            (("0", "10", "5"), entry_price), (("0.00", "10", "5"), entry_price),
            (("100", "", "5"), roi), (("100", "-", "5"), roi), (("100", "0", "5"), roi),
            (("100", "-5", "5"), roi), (("100", "-0.0", "5"), roi),
            (("100", "10", ""), stop_loss), (("100", "10", "."), stop_loss),
            (("100", "10", "0"), stop_loss), (("100", "10", "100"), stop_loss),
            (("100", "10", "100.0"), stop_loss), (("100", "10", "150"), stop_loss),
        ):
            with self.assertRaises(ValueError, msg=boxes) as raised:
                positional_levels(*boxes)
            self.assertEqual(str(raised.exception), message, boxes)

    def test_the_first_box_at_fault_is_the_one_named(self) -> None:
        for boxes, message in (
            (("", "", ""), "Entry price must be a number greater than 0."),
            (("100", "", ""), "ROI must be a number greater than 0."),
            (("100", "-5", "100"), "ROI must be a number greater than 0."),
        ):
            with self.assertRaises(ValueError, msg=boxes) as raised:
                positional_levels(*boxes)
            self.assertEqual(str(raised.exception), message, boxes)

    def test_numbers_too_large_to_work_out_cannot_be_tested(self) -> None:
        huge = "9" * 1_000_001
        for boxes in ((huge, "10", "5"), ("100", huge, "5")):
            with self.assertRaises(ValueError) as raised:
                positional_levels(*boxes)
            self.assertEqual(str(raised.exception), "Entry price and ROI are too large to test.")


class PositionalTradesTests(unittest.TestCase):
    def trades(self, *prices: Sequence[float]) -> List[Trade]:
        return positional_trades(candles(*prices), ENTRY, TARGET, STOP)

    def test_nothing_is_bought_until_a_candle_holds_the_entry_price(self) -> None:
        self.assertEqual(self.trades(), [])
        self.assertEqual(self.trades((120, 125, 100.01, 110), (110, 112, 101, 105)), [])
        self.assertEqual(self.trades((90, 99.99, 85, 95), (95, 97, 92, 96)), [])
        # The price went from below 100 to above it between two candles, and neither holds 100.
        self.assertEqual(self.trades((90, 99, 85, 95), (101, 120, 101, 110)), [])

    def test_the_first_candle_that_holds_the_entry_price_buys(self) -> None:
        # The low and the high of a candle are part of it.
        self.assertEqual(self.trades((105, 108, 100, 104)), [Trade(0, ENTRY)])
        self.assertEqual(self.trades((98, 100, 96, 97)), [Trade(0, ENTRY)])
        self.assertEqual(
            self.trades((120, 125, 101, 110), (99, 104, 98, 103), (100, 101, 99, 100)),
            [Trade(1, ENTRY)],
        )

    def test_a_later_candle_that_reaches_the_target_sells_at_the_target_price(self) -> None:
        self.assertEqual(
            self.trades((99, 101, 98, 100), (101, 109.99, 100, 109), (109, 110, 108, 109.5)),
            [Trade(0, ENTRY, 2, TARGET)],
        )

    def test_a_later_candle_that_reaches_the_stop_sells_at_the_stop_price(self) -> None:
        self.assertEqual(
            self.trades((99, 101, 98, 100), (98, 99, 95.01, 96), (96, 97, 95, 96)),
            [Trade(0, ENTRY, 2, STOP)],
        )

    def test_the_candle_that_buys_does_not_sell(self) -> None:
        # The first candle reaches the target and the stop as well as the entry price.
        self.assertEqual(self.trades((100, 120, 90, 105)), [Trade(0, ENTRY)])
        self.assertEqual(self.trades((100, 120, 90, 105), (105, 106, 99, 100)), [Trade(0, ENTRY)])
        self.assertEqual(
            self.trades((100, 120, 90, 105), (105, 106, 99, 100), (100, 111, 99, 110)),
            [Trade(0, ENTRY, 2, TARGET)],
        )

    def test_a_candle_that_reaches_both_prices_sells_at_the_stop(self) -> None:
        bought = (99, 101, 98, 100)
        self.assertEqual(self.trades(bought, (100, 112, 94, 105)), [Trade(0, ENTRY, 1, STOP)])
        self.assertEqual(self.trades(bought, (109.99, 112, 94, 105)), [Trade(0, ENTRY, 1, STOP)])
        # It reached the target first when it opened there.
        self.assertEqual(self.trades(bought, (110, 112, 94, 105)), [Trade(0, ENTRY, 1, TARGET)])
        self.assertEqual(self.trades(bought, (111, 112, 94, 105)), [Trade(0, ENTRY, 1, TARGET)])

    def test_the_candle_that_sells_does_not_buy_again(self) -> None:
        # The second candle holds the entry price too, and the third buys there instead.
        self.assertEqual(
            self.trades((99, 101, 98, 100), (100, 111, 99, 105), (100, 101, 99, 100)),
            [Trade(0, ENTRY, 1, TARGET), Trade(2, ENTRY)],
        )

    def test_trades_follow_one_another_to_the_last_candle(self) -> None:
        self.assertEqual(
            self.trades(
                (99, 101, 98, 100), (100, 110, 99, 109), (109, 112, 105, 106),
                (106, 107, 100, 101), (101, 102, 94, 95), (95, 96, 90, 91),
                (91, 100, 90, 99), (99, 105, 96, 104),
            ),
            [Trade(0, ENTRY, 1, TARGET), Trade(3, ENTRY, 4, STOP), Trade(6, ENTRY)],
        )

    def test_a_candle_that_opens_beyond_a_price_still_sells_at_that_price(self) -> None:
        bought = (99, 101, 98, 100)
        self.assertEqual(self.trades(bought, (90, 92, 88, 91)), [Trade(0, ENTRY, 1, STOP)])
        self.assertEqual(self.trades(bought, (115, 118, 114, 116)), [Trade(0, ENTRY, 1, TARGET)])

    def test_prices_are_compared_with_the_exact_target_and_stop(self) -> None:
        # In float arithmetic the target of 100 at 10 is 110.00000000000001, which a high of
        # 110 does not reach, and the stop of 20 at 7 is 18.599999999999998, which a low of
        # 18.6 does not reach.
        rows = candles((99, 101, 98, 100), (101, 110.0, 100, 109))
        self.assertEqual(positional_trades(rows, ENTRY, TARGET, STOP), [Trade(0, ENTRY, 1, TARGET)])
        entry_price, target, stop = positional_levels("20", "10", "7")
        rows = candles((20, 20.5, 19.5, 20), (19.5, 19.8, 18.6, 19))
        self.assertEqual(
            positional_trades(rows, entry_price, target, stop), [Trade(0, entry_price, 1, stop)])

    def test_trades_carry_the_exact_prices(self) -> None:
        entry_price, target, stop = positional_levels("19.99", "7.5", "7.5")
        rows = candles((20, 20.5, 19.5, 20), (20, 22, 19.5, 21), (20, 20.1, 19.9, 20), (19, 19.5, 18, 18.2))
        trades = positional_trades(rows, entry_price, target, stop)
        self.assertEqual(
            [(trade.buy_price, trade.sell_price) for trade in trades],
            [(Decimal("19.99"), Decimal("21.48925")), (Decimal("19.99"), Decimal("18.49075"))],
        )


class RealPriceTests(unittest.TestCase):
    """Orders tested on four years of daily XRP prices."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_price_rows()

    def check_trades(self, boxes: Sequence[str]) -> List[Trade]:
        """Test the order in ``boxes`` and check each trade against the rows around it."""
        rows = self.rows
        entry_price, target, stop = positional_levels(*boxes)
        entry, take, cut = float(entry_price), float(target), float(stop)
        trades = positional_trades(rows, entry_price, target, stop)
        waiting_from = 0
        for number, trade in enumerate(trades):
            # No candle before the buy could have bought, and the buy candle could.
            for row in rows[waiting_from:trade.buy_index]:
                self.assertFalse(row[3] <= entry <= row[2], (boxes, number))
            buy_row = rows[trade.buy_index]
            self.assertTrue(buy_row[3] <= entry <= buy_row[2], (boxes, number))
            self.assertEqual(trade.buy_price, entry_price, (boxes, number))
            if trade.sell_index is None:
                # Only the last trade can be left open.
                self.assertEqual(number, len(trades) - 1, boxes)
                self.assertIsNone(trade.sell_price, boxes)
                held = rows[trade.buy_index + 1:]
                waiting_from = len(rows)
            else:
                self.assertGreater(trade.sell_index, trade.buy_index, (boxes, number))
                held = rows[trade.buy_index + 1:trade.sell_index]
                sell_row = rows[trade.sell_index]
                if trade.sell_price == stop:
                    self.assertLessEqual(sell_row[3], cut, (boxes, number))
                else:
                    self.assertEqual(trade.sell_price, target, (boxes, number))
                    self.assertGreaterEqual(sell_row[2], take, (boxes, number))
                waiting_from = trade.sell_index + 1
            # No candle between the buy and the sale reached the target or the stop.
            for row in held:
                self.assertTrue(row[3] > cut and row[2] < take, (boxes, number))
        for row in rows[waiting_from:]:
            self.assertFalse(row[3] <= entry <= row[2], boxes)
        return trades

    def test_every_trade_follows_the_rules(self) -> None:
        for boxes, count in (
            (("0.5", "10", "5"), 30), (("0.5", "20", "10"), 23), (("0.6", "25", "10"), 18),
            (("1", "10", "5"), 21), (("0.3", "50", "20"), 10), (("0.5", "1000", "50"), 4),
            (("0.25", "3", "1.5"), None), (("1.9", "0.5", "0.5"), None), (("5", "10", "5"), 0),
        ):
            trades = self.check_trades(boxes)
            if count is not None:
                self.assertEqual(len(trades), count, boxes)

    def test_a_wide_order_makes_few_long_trades(self) -> None:
        rows = self.rows
        trades = self.check_trades(("0.5", "1000", "50"))
        self.assertEqual(
            [(trade.buy_index, trade.sell_index) for trade in trades],
            [(0, 102), (140, 467), (934, 964), (1002, None)],
        )
        self.assertEqual(
            [("-".join(rows[trade.buy_index][0]),
              None if trade.sell_index is None else "-".join(rows[trade.sell_index][0]))
             for trade in trades],
            [("2018-05-04", "2018-08-14"), ("2018-09-21", "2019-08-14"),
             ("2020-11-23", "2020-12-23"), ("2021-01-30", None)],
        )
        # The price never reached the target of 5.5, so every sale was at the stop of 0.25.
        self.assertEqual({trade.sell_price for trade in trades[:-1]}, {Decimal("0.25")})

    def test_an_entry_price_outside_the_prices_makes_no_trades(self) -> None:
        self.assertEqual(self.check_trades(("5", "10", "5")), [])
        self.assertEqual(self.check_trades(("0.05", "10", "5")), [])


if __name__ == "__main__":
    unittest.main()
