"""Rule based strategies: buy and sell on what indicators show.

A rule compares one indicator with a level, as in "RSI(7) crosses below 30". A strategy has
buy rules and sell rules. It buys when every buy rule is true on one candle, and sells when
any sell rule is true. It can also sell at an ROI or a stop loss, which are percentages of the
price each trade was bought at.

``rule_strategy`` reads a strategy from the text in the Indicator Based window, and
``rule_trades`` tests one on price rows. ``trade_returns``, ``compound_return`` and
``buy_and_hold_return`` work out what was made.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, Overflow
from typing import Any, Dict, List, Optional, Sequence, Tuple

from indicators import (
    ADX_PERIOD, ADX_TREND_LEVEL, RSI_DEFAULT_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD, adx_components,
)
from strategies import Trade, parse_number, price_text, stop_price, target_price
from trend import wilder_rsi

RSI = "RSI"
ADX = "ADX"
INDICATORS = (RSI, ADX)

CROSSES_ABOVE = "crosses above"
CROSSES_BELOW = "crosses below"
IS_ABOVE = "is above"
IS_BELOW = "is below"
CONDITIONS = (CROSSES_ABOVE, CROSSES_BELOW, IS_ABOVE, IS_BELOW)

# The two sides of a strategy.
BUY = "buy"
SELL = "sell"

# What sold a trade that no rule sold.
SOLD_BY_ROI = "ROI"
SOLD_BY_STOP_LOSS = "Stop loss"

# The most rules that one side of the window takes, which keeps the window on the screen.
MAX_RULES = 6

MIN_PERIOD, MAX_PERIOD = 2, 9999
# RSI and ADX both run from 0 to 100.
MIN_LEVEL, MAX_LEVEL = 0, 100

# What a period box accepts while a period is being typed: no more than four digits.
PERIOD_TEXT = re.compile(r"[0-9]{0,4}")


@dataclass(frozen=True)
class Rule:
    """One indicator compared with a level, as in RSI(7) crosses below 30."""
    indicator: str
    period: int
    condition: str
    level: Decimal


@dataclass(frozen=True)
class RuleStrategy:
    """The rules to buy and to sell on, and the ROI and stop loss of each trade when they are set."""
    buy_rules: Tuple[Rule, ...]
    sell_rules: Tuple[Rule, ...] = ()
    roi_percent: Optional[Decimal] = None
    stop_loss_percent: Optional[Decimal] = None


@dataclass(frozen=True)
class RuleTrade(Trade):
    """A trade of a rule based strategy. ``sold_by`` is the rule that sold it, "ROI" or "Stop loss"."""
    sold_by: Optional[str] = None


# The rule a new row holds, for each side and indicator. RSI buys on a fall into its oversold
# range and sells on a rise into its overbought range. ADX buys while there is no trend and
# sells when one starts.
DEFAULT_RULES: Dict[Tuple[str, str], Rule] = {
    (BUY, RSI): Rule(RSI, RSI_DEFAULT_PERIOD, CROSSES_BELOW, Decimal(RSI_OVERSOLD)),
    (SELL, RSI): Rule(RSI, RSI_DEFAULT_PERIOD, CROSSES_ABOVE, Decimal(RSI_OVERBOUGHT)),
    (BUY, ADX): Rule(ADX, ADX_PERIOD, IS_BELOW, Decimal(ADX_TREND_LEVEL)),
    (SELL, ADX): Rule(ADX, ADX_PERIOD, CROSSES_ABOVE, Decimal(ADX_TREND_LEVEL)),
}


def default_strategy() -> RuleStrategy:
    """The strategy the window starts with: buy on RSI falling below 30, sell on it rising above 70."""
    return RuleStrategy((DEFAULT_RULES[BUY, RSI],), (DEFAULT_RULES[SELL, RSI],))


def next_default_rule(side: str, used: Sequence[str]) -> Rule:
    """The rule a row added to ``side`` holds, given the indicators of the rows already there.

    It is for the first indicator the side does not use yet, or for RSI when it uses them all.
    """
    indicator = next((name for name in INDICATORS if name not in used), INDICATORS[0])
    return DEFAULT_RULES[side, indicator]


def rule_text(rule: Rule) -> str:
    """A rule in words, as in "RSI(7) crosses below 30"."""
    return f"{rule.indicator}({rule.period}) {rule.condition} {price_text(rule.level)}"


def is_period_text(text: str) -> bool:
    """True when ``text`` is a period, or would be one with more typing."""
    return PERIOD_TEXT.fullmatch(text) is not None


def parse_rule(indicator: str, period_text: str, condition: str, level_text: str) -> Rule:
    """The rule that one row of the window holds. ValueError says what in the row is not allowed."""
    if indicator not in INDICATORS:
        raise ValueError(f"The indicator must be {' or '.join(INDICATORS)}.")
    period = int(period_text) if period_text and is_period_text(period_text) else None
    if period is None or not MIN_PERIOD <= period <= MAX_PERIOD:
        raise ValueError(f"Period must be a whole number from {MIN_PERIOD} to {MAX_PERIOD}.")
    if condition not in CONDITIONS:
        raise ValueError(f"The condition must be {', '.join(CONDITIONS[:-1])} or {CONDITIONS[-1]}.")
    level = parse_number(level_text)
    if level is None or not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError(f"Level must be a number from {MIN_LEVEL} to {MAX_LEVEL}.")
    return Rule(indicator, period, condition, level)


def parse_rules(side: str, rows: Sequence[Sequence[str]]) -> Tuple[Rule, ...]:
    """The rules in the rows of one side. ValueError names the row that does not hold one."""
    rules = []
    for number, row in enumerate(rows, start=1):
        try:
            rules.append(parse_rule(*row))
        except ValueError as error:
            raise ValueError(f"{side.capitalize()} rule {number}: {error}") from error
    return tuple(rules)


def rule_strategy(
    buy_rows: Sequence[Sequence[str]], sell_rows: Sequence[Sequence[str]],
    roi_text: str, stop_loss_text: str,
) -> RuleStrategy:
    """The strategy typed in the Indicator Based window.

    A row is the indicator, the period text, the condition and the level text of one rule. The
    ROI and the stop loss are left empty to sell on the rules alone. ValueError says which row
    or box does not allow a test.
    """
    buy_rules = parse_rules(BUY, buy_rows)
    sell_rules = parse_rules(SELL, sell_rows)
    if not buy_rules:
        raise ValueError("A strategy needs at least one buy rule.")
    roi_percent = parse_number(roi_text)
    if roi_text and (roi_percent is None or roi_percent <= 0):
        raise ValueError("ROI must be empty or a number greater than 0.")
    stop_loss_percent = parse_number(stop_loss_text)
    if stop_loss_text and (stop_loss_percent is None or not 0 < stop_loss_percent < 100):
        raise ValueError("Stop loss must be empty or a number greater than 0 and less than 100.")
    if not sell_rules and roi_percent is None and stop_loss_percent is None:
        raise ValueError("A strategy needs a sell rule, an ROI or a stop loss to sell on.")
    if roi_percent is not None:
        try:
            # The target of the highest price a row can hold. Lower prices have lower targets.
            target_price(Decimal(sys.float_info.max), roi_percent)
        except Overflow as error:
            # Only a number about a million digits long is too large to work out.
            raise ValueError("ROI is too large to test.") from error
    return RuleStrategy(buy_rules, sell_rules, roi_percent, stop_loss_percent)


def indicator_values(rows: Sequence[Sequence[Any]], indicator: str, period: int) -> List[Optional[float]]:
    """The indicator on every row. It is None on the first rows, which have too few before them."""
    closes = [row[4] for row in rows]
    if indicator == RSI:
        return wilder_rsi(closes, period)
    adx, _, _ = adx_components([row[2] for row in rows], [row[3] for row in rows], closes, period)
    return adx


def condition_signals(values: Sequence[Optional[float]], condition: str, level: float) -> List[bool]:
    """Whether a condition is true on each candle, for the values of an indicator on every candle.

    "is above" and "is below" are true on every candle that leaves the indicator beyond the
    level. The crossings are true only on the candle that takes it there, from the level or
    from the other side of it. A candle with no value is never true, and neither is a crossing
    on the first candle that has one.
    """
    signals = [False] * len(values)
    previous: Optional[float] = None
    for index, value in enumerate(values):
        if value is not None:
            if condition == IS_ABOVE:
                signals[index] = value > level
            elif condition == IS_BELOW:
                signals[index] = value < level
            elif previous is not None:
                if condition == CROSSES_ABOVE:
                    signals[index] = previous <= level < value
                else:
                    signals[index] = previous >= level > value
        previous = value
    return signals


def rule_signals(rows: Sequence[Sequence[Any]], rules: Sequence[Rule]) -> List[List[bool]]:
    """For each rule, whether it is true on each row."""
    # Rules that share an indicator and a period share its values.
    values: Dict[Tuple[str, int], List[Optional[float]]] = {}
    signals = []
    for rule in rules:
        key = (rule.indicator, rule.period)
        if key not in values:
            values[key] = indicator_values(rows, *key)
        signals.append(condition_signals(values[key], rule.condition, float(rule.level)))
    return signals


def exit_prices(
    buy_price: Decimal, strategy: RuleStrategy,
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """The target and stop prices of a trade bought at ``buy_price``. One that is not set is None."""
    roi_percent, stop_loss_percent = strategy.roi_percent, strategy.stop_loss_percent
    return (
        None if roi_percent is None else target_price(buy_price, roi_percent),
        None if stop_loss_percent is None else stop_price(buy_price, stop_loss_percent),
    )


def stop_or_target_sale(
    open_: float, high: float, low: float, target: Optional[Decimal], stop: Optional[Decimal],
) -> Optional[Tuple[Decimal, str]]:
    """The price a candle sells a position at for its stop or its target, and which of them it was.

    None when the candle reaches neither. A price that is not set is None and is never reached.
    """
    # The prices in the rows are floats, so each level is rounded to one float to compare with.
    # A candle that opened beyond a level could only be sold at its open.
    if stop is not None and open_ <= float(stop):
        return Decimal(repr(open_)), SOLD_BY_STOP_LOSS
    if target is not None and open_ >= float(target):
        return Decimal(repr(open_)), SOLD_BY_ROI
    if stop is not None and low <= float(stop):
        return stop, SOLD_BY_STOP_LOSS
    if target is not None and high >= float(target):
        return target, SOLD_BY_ROI
    return None


def rule_trades(rows: Sequence[Sequence[Any]], strategy: RuleStrategy) -> List[RuleTrade]:
    """The trades the strategy makes over ``rows``, taken one candle at a time from first to last.

    A row is ``[date, open, high, low, close, ...]``. The rules are read when a candle closes
    and acted on when the next one opens, so no trade uses a price from before its rules were
    true:

    - With nothing held, a candle where every buy rule is true buys at the next open.
    - With a position held, a candle where any sell rule is true sells at the next open.
    - A position is also sold by a candle that reaches its stop price or its target price. It
      is sold at that price, or at the open when the candle opened beyond it. A candle that
      reaches both sells at the stop, because the order they were reached in is not known.
      The candle the position was bought on can reach them too, as it was bought at the open.

    One position is held at a time. A candle that sells does not buy at that same open, but
    the buy rules are read again at its close. Rules that are true on the last candle are not
    acted on, because no candle follows it. A strategy with no buy rules never buys.
    """
    if not strategy.buy_rules:
        return []
    count = len(strategy.buy_rules)
    signals = rule_signals(rows, strategy.buy_rules + strategy.sell_rules)
    buy_signals, sell_signals = signals[:count], signals[count:]
    trades: List[RuleTrade] = []
    bought: Optional[int] = None
    buy_price = Decimal(0)
    target: Optional[Decimal] = None
    stop: Optional[Decimal] = None
    for index, row in enumerate(rows):
        open_, high, low = row[1], row[2], row[3]
        before = index - 1
        sale: Optional[Tuple[Decimal, str]] = None
        if bought is None:
            # Nothing can be bought at a price of zero, and no return worked out from one.
            if index == 0 or open_ <= 0 or not all(signal[before] for signal in buy_signals):
                continue
            bought, buy_price = index, Decimal(repr(open_))
            target, stop = exit_prices(buy_price, strategy)
        else:
            # The first sell rule that was true is the one named as selling the trade.
            for rule, signal in zip(strategy.sell_rules, sell_signals):
                if signal[before]:
                    sale = Decimal(repr(open_)), rule_text(rule)
                    break
        if sale is None:
            sale = stop_or_target_sale(open_, high, low, target, stop)
        if sale is not None:
            trades.append(RuleTrade(bought, buy_price, index, *sale))
            bought = None
    if bought is not None:
        trades.append(RuleTrade(bought, buy_price))
    return trades


def trade_returns(rows: Sequence[Sequence[Any]], trades: Sequence[Trade]) -> List[float]:
    """What each trade made as a fraction of the price it was bought at: 0.05 is a gain of 5%.

    A trade that is still open is valued at the close of the last row.
    """
    returns = []
    for trade in trades:
        sell_price = trade.sell_price
        if sell_price is None:
            sell_price = Decimal(repr(rows[-1][4]))
        returns.append(float(sell_price / trade.buy_price - 1))
    return returns


def compound_return(returns: Sequence[float]) -> float:
    """What the trades made together, when each put in everything the one before it left."""
    return math.prod(1 + made for made in returns) - 1


def buy_and_hold_return(rows: Sequence[Sequence[Any]]) -> Optional[float]:
    """What buying at the first open and holding to the last close made, as a fraction.

    None when there are no rows, or the first open is not above zero.
    """
    if not rows or rows[0][1] <= 0:
        return None
    return rows[-1][4] / rows[0][1] - 1


def percent_text(fraction: float) -> str:
    """A return as a percentage with a sign and two decimals: 0.05 is "+5.00%"."""
    text = f"{fraction * 100:+.2f}"
    # A return that rounds to zero has no sign.
    return f"{text[1:] if float(text) == 0 else text}%"
