"""The positional strategy: buy at an entry price, then sell at a target price or a stop price.

The entry price, ROI and stop loss boxes take numbers only, so every edit is checked before it
is made. ``is_price_text``, ``is_roi_text`` and ``is_stop_loss_text`` make that check. They have
to accept text that is still on its way to a number, such as "", "." or "-", and
``parse_number`` returns None for those.

The target price is the entry price with the ROI applied as a percentage, and the stop price is
the entry price with the stop loss taken off. An entry price of 100 with an ROI of 5 and a stop
loss of 2 gives a target of 105 and a stop of 98. The typed numbers are kept as decimals, so the
arithmetic is exact to 28 digits: 100 at 10 is 110, where floats would give 110.00000000000001.

``positional_trades`` tests the order on price rows, one candle at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, Overflow
from typing import Any, Callable, List, Optional, Sequence, Tuple

# What a box accepts while a number is being typed: digits, then at most one decimal point with
# more digits after it. Only the ROI may start with a sign, because a price is never negative.
# Each pattern can match a text in only one way, which keeps the check quick for a long paste.
PRICE_TEXT = re.compile(r"[0-9]*(?:\.[0-9]*)?")
ROI_TEXT = re.compile(r"[+-]?[0-9]*(?:\.[0-9]*)?")
# A finished number has at least one digit.
NUMBER_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")


@dataclass(frozen=True)
class Trade:
    """A buy and the sell that closed it. The indexes are the rows they were made on.

    A position that is still open after the last row has no sell.
    """
    buy_index: int
    buy_price: Decimal
    sell_index: Optional[int] = None
    sell_price: Optional[Decimal] = None


def is_price_text(text: str) -> bool:
    """True when ``text`` is a price, or would be one with more typing."""
    return PRICE_TEXT.fullmatch(text) is not None


def is_roi_text(text: str) -> bool:
    """True when ``text`` is an ROI, or would be one with more typing. It may start with a sign."""
    return ROI_TEXT.fullmatch(text) is not None


def is_stop_loss_text(text: str) -> bool:
    """True when ``text`` is a stop loss, or would be one with more typing. It has no sign."""
    return is_price_text(text)


def parse_number(text: str) -> Optional[Decimal]:
    """The number typed in a box, or None while the text is not a number yet (such as "" or "-.")."""
    return Decimal(text) if NUMBER_TEXT.fullmatch(text) else None


def target_price(entry_price: Decimal, roi_percent: Decimal) -> Decimal:
    """The entry price with the ROI applied: 100 at 5 gives 105, and 100 at -5 gives 95."""
    return entry_price * (1 + roi_percent / 100)


def stop_price(entry_price: Decimal, stop_loss_percent: Decimal) -> Decimal:
    """The entry price with the stop loss taken off: 100 at 5 gives 95."""
    return entry_price * (1 - stop_loss_percent / 100)


def price_text(price: Decimal) -> str:
    """A price in plain digits, with no exponent and no trailing zeros."""
    # Zero is written out because it would otherwise keep its sign, as in "-0".
    return format(price.normalize(), "f") if price else "0"


def applied_price_text(
    apply: Callable[[Decimal, Decimal], Decimal], entry_price_text: str, percent_text: str,
) -> str:
    """The entry price with a percentage applied, or "" until both texts are numbers."""
    entry_price = parse_number(entry_price_text)
    percent = parse_number(percent_text)
    if entry_price is None or percent is None:
        return ""
    try:
        return price_text(apply(entry_price, percent))
    except Overflow:
        # Only a number about a million digits long is too large to work out.
        return ""


def target_price_text(entry_price_text: str, roi_text: str) -> str:
    """What the target price box shows for the text in the entry price and ROI boxes.

    It is empty until both hold a number. The price is written in plain digits, with no
    exponent and no trailing zeros.
    """
    return applied_price_text(target_price, entry_price_text, roi_text)


def stop_price_text(entry_price_text: str, stop_loss_text: str) -> str:
    """What the stop price box shows for the text in the entry price and stop loss boxes.

    It is written like the target price, and is empty until both hold a number.
    """
    return applied_price_text(stop_price, entry_price_text, stop_loss_text)


def positional_levels(
    entry_price_text: str, roi_text: str, stop_loss_text: str,
) -> Tuple[Decimal, Decimal, Decimal]:
    """The entry, target and stop prices of the order typed in the three boxes.

    A test needs the stop below the entry price and the target above it. ValueError says
    which box does not allow that.
    """
    entry_price = parse_number(entry_price_text)
    if entry_price is None or entry_price <= 0:
        raise ValueError("Entry price must be a number greater than 0.")
    roi_percent = parse_number(roi_text)
    if roi_percent is None or roi_percent <= 0:
        raise ValueError("ROI must be a number greater than 0.")
    stop_loss_percent = parse_number(stop_loss_text)
    if stop_loss_percent is None or not 0 < stop_loss_percent < 100:
        raise ValueError("Stop loss must be a number greater than 0 and less than 100.")
    try:
        return (
            entry_price,
            target_price(entry_price, roi_percent),
            stop_price(entry_price, stop_loss_percent),
        )
    except Overflow as error:
        raise ValueError("Entry price and ROI are too large to test.") from error


def positional_trades(
    rows: Sequence[Sequence[Any]], entry_price: Decimal, target: Decimal, stop: Decimal,
) -> List[Trade]:
    """The trades the order makes over ``rows``, taken one candle at a time from first to last.

    A row is ``[date, open, high, low, close, ...]``. Each candle does at most one thing:

    - With nothing held, it buys at the entry price when that price is within its low and high.
    - With a position held, it sells at the stop price when its low is at or below the stop, or
      at the target price when its high is at or above the target. A candle that reaches both
      sells at the stop, because the order they were reached in is not known, unless it
      opened at or above the target and so reached that first.

    So a position is sold on a later candle than it was bought on, and the next buy is on a
    later candle than that sale. A sale is always at the stop or target price, even when the
    candle opened beyond it.
    """
    # The prices in the rows are floats, so each level is rounded to one float to compare with.
    # A level worked out in floats could miss a candle that only just reaches it.
    entry, take, cut = float(entry_price), float(target), float(stop)
    trades: List[Trade] = []
    bought: Optional[int] = None
    for index, row in enumerate(rows):
        open_, high, low = row[1], row[2], row[3]
        if bought is None:
            if low <= entry <= high:
                bought = index
            continue
        if low <= cut and open_ < take:
            sell_price = stop
        elif high >= take:
            sell_price = target
        else:
            continue
        trades.append(Trade(bought, entry_price, index, sell_price))
        bought = None
    if bought is not None:
        trades.append(Trade(bought, entry_price))
    return trades
