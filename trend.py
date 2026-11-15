"""Trend identification by combining rule-based strategies.

Each strategy votes UP, DOWN or SIDEWAYS for every candle using only that candle and
earlier ones. The consensus is the label with the most votes, provided at least two
strategies back it and no other label ties it. Otherwise the label is MIXED. The
number of votes behind the label is kept as a measure of conviction.

``rsi_adx_states`` is a separate hybrid labeler (ADX for strength, RSI for direction)
and is not part of the consensus. ``layered_trend_states`` is a second, separate labeler:
an ADX gate with hysteresis decides whether a trend exists, and the 7/30 SMA order
gives its direction. Optionally, on-balance volume must agree with that direction.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from indicators import ADX_PERIOD, adx_components, on_balance_volume, parse_setting_fields
from levels import LevelSettings, swing_pivots

UP = "UP"
DOWN = "DOWN"
SIDEWAYS = "SIDEWAYS"
MIXED = "MIXED"

# Efficiency ratio: net move over the window divided by the total path length (0 to 1).
EFFICIENCY_PERIOD = 10
EFFICIENCY_THRESHOLD = 0.3

# Swing points are confirmed by this many candles on each side, matching the S-R default.
PIVOT_BARS = LevelSettings().pivot_bars

# Moving-average stack periods, counted in candles.
MA_FAST = 20
MA_SLOW = 50

# ADX level at or above which the market counts as trending (period is ADX_PERIOD from indicators).
ADX_THRESHOLD = 25
# RSI (Wilder) period, and the midline that separates bullish from bearish momentum.
RSI_PERIOD = 14
RSI_MIDLINE = 50.0

# Layered labeler: the ADX gate switches on at ADX_THRESHOLD and off below ADX_EXIT_THRESHOLD,
# so a reading that hovers near one level does not flip the trend on and off.
ADX_EXIT_THRESHOLD = 20
# Direction comes from the fast SMA relative to the slow SMA, in candles.
SMA_DIRECTION_FAST = 7
SMA_DIRECTION_SLOW = 30
# With volume included, on-balance volume must sit on the same side of its own SMA as the
# trend direction; this is the number of candles in that SMA.
OBV_SMA_PERIOD = 20

Votes = Sequence[Optional[str]]


@dataclass(frozen=True)
class Consensus:
    label: str
    agreement: int
    votes: Tuple[str, ...]

    @property
    def unanimous(self) -> bool:
        return self.agreement == len(self.votes)


def efficiency_ratio_states(
    closes: Sequence[float], period: int = EFFICIENCY_PERIOD, threshold: float = EFFICIENCY_THRESHOLD,
) -> List[Optional[str]]:
    """Trend from the efficiency ratio: UP or DOWN when the move is clean enough, else SIDEWAYS."""
    states: List[Optional[str]] = [None] * len(closes)
    path = 0.0
    for i in range(1, len(closes)):
        path += abs(closes[i] - closes[i - 1])
        if i > period:
            path -= abs(closes[i - period] - closes[i - period - 1])
        if i < period:
            continue
        change = closes[i] - closes[i - period]
        efficiency = abs(change) / path if path > 0 else 0.0
        if change == 0 or efficiency < threshold:
            states[i] = SIDEWAYS
        else:
            states[i] = UP if change > 0 else DOWN
    return states


def swing_structure_states(
    highs: Sequence[float], lows: Sequence[float], bars: int = PIVOT_BARS,
) -> List[Optional[str]]:
    """Dow-style structure from the last two confirmed swing highs and swing lows.

    Higher highs with higher lows is UP, lower highs with lower lows is DOWN, and
    anything else is SIDEWAYS. A swing only counts once its ``bars`` confirming
    candles have closed, so the result never looks ahead.
    """
    swing_highs, swing_lows = swing_pivots(highs, lows, bars)
    states: List[Optional[str]] = [None] * len(highs)
    confirmed_highs: List[float] = []
    confirmed_lows: List[float] = []
    next_high = next_low = 0
    for i in range(len(highs)):
        while next_high < len(swing_highs) and swing_highs[next_high].index + bars <= i:
            confirmed_highs.append(swing_highs[next_high].price)
            next_high += 1
        while next_low < len(swing_lows) and swing_lows[next_low].index + bars <= i:
            confirmed_lows.append(swing_lows[next_low].price)
            next_low += 1
        if len(confirmed_highs) < 2 or len(confirmed_lows) < 2:
            continue
        higher_high = confirmed_highs[-1] > confirmed_highs[-2]
        higher_low = confirmed_lows[-1] > confirmed_lows[-2]
        lower_high = confirmed_highs[-1] < confirmed_highs[-2]
        lower_low = confirmed_lows[-1] < confirmed_lows[-2]
        if higher_high and higher_low:
            states[i] = UP
        elif lower_high and lower_low:
            states[i] = DOWN
        else:
            states[i] = SIDEWAYS
    return states


def _simple_moving_average(values: Sequence[float], period: int) -> List[Optional[float]]:
    averages: List[Optional[float]] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            averages[i] = total / period
    return averages


def moving_average_stack_states(
    closes: Sequence[float], fast: int = MA_FAST, slow: int = MA_SLOW,
) -> List[Optional[str]]:
    """UP when close > fast MA > slow MA, DOWN for the reverse order, otherwise SIDEWAYS."""
    fast_averages = _simple_moving_average(closes, fast)
    slow_averages = _simple_moving_average(closes, slow)
    states: List[Optional[str]] = []
    for close, fast_value, slow_value in zip(closes, fast_averages, slow_averages):
        if fast_value is None or slow_value is None:
            states.append(None)
        elif close > fast_value > slow_value:
            states.append(UP)
        elif close < fast_value < slow_value:
            states.append(DOWN)
        else:
            states.append(SIDEWAYS)
    return states


def adx_states(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
    period: int = ADX_PERIOD, threshold: float = ADX_THRESHOLD,
) -> List[Optional[str]]:
    """Trend from Wilder's ADX and directional indicators.

    ADX below ``threshold`` is SIDEWAYS. Otherwise the side with the stronger
    directional indicator (+DI or -DI) gives UP or DOWN. The first value appears
    after about two periods of candles.
    """
    adx_values, plus_values, minus_values = adx_components(highs, lows, closes, period)
    states: List[Optional[str]] = [None] * len(closes)
    for i, adx in enumerate(adx_values):
        if adx is None:
            continue
        if adx < threshold or plus_values[i] == minus_values[i]:
            states[i] = SIDEWAYS
        else:
            states[i] = UP if plus_values[i] > minus_values[i] else DOWN
    return states


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    # With no gains or losses the ratio is undefined; the midline is the neutral value.
    if avg_gain == 0 and avg_loss == 0:
        return RSI_MIDLINE
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def wilder_rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    """Wilder's RSI for every candle. The first value appears after ``period`` close-to-close changes."""
    count = len(closes)
    rsi: List[Optional[float]] = [None] * count
    if count <= period:
        return rsi
    gains = [0.0] * count
    losses = [0.0] * count
    for i in range(1, count):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    rsi[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, count):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi[i] = _rsi_value(avg_gain, avg_loss)
    return rsi


def rsi_adx_states(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
    rsi_period: int = RSI_PERIOD, adx_period: int = ADX_PERIOD, threshold: float = ADX_THRESHOLD,
) -> List[Optional[str]]:
    """Hybrid trend: ADX decides whether a trend exists, RSI decides its direction.

    ADX below ``threshold`` is SIDEWAYS. Otherwise RSI above the midline is UP and
    RSI below it is DOWN. RSI exactly on the midline is SIDEWAYS.
    """
    adx_values, _, _ = adx_components(highs, lows, closes, adx_period)
    rsi = wilder_rsi(closes, rsi_period)
    states: List[Optional[str]] = [None] * len(closes)
    for i, (adx, momentum) in enumerate(zip(adx_values, rsi)):
        if adx is None or momentum is None:
            continue
        if adx < threshold or momentum == RSI_MIDLINE:
            states[i] = SIDEWAYS
        else:
            states[i] = UP if momentum > RSI_MIDLINE else DOWN
    return states


def adx_gate_states(
    adx_values: Sequence[Optional[float]],
    enter: float = ADX_THRESHOLD, exit_level: float = ADX_EXIT_THRESHOLD,
) -> List[Optional[bool]]:
    """Whether a trend is on: True once ADX reaches ``enter``, False again below ``exit_level``."""
    gate: List[Optional[bool]] = []
    on = False
    for adx in adx_values:
        if adx is None:
            gate.append(None)
            continue
        if not on and adx >= enter:
            on = True
        elif on and adx < exit_level:
            on = False
        gate.append(on)
    return gate


def sma_direction_states(
    closes: Sequence[float], fast: int = SMA_DIRECTION_FAST, slow: int = SMA_DIRECTION_SLOW,
) -> List[Optional[str]]:
    """UP when the fast SMA is above the slow SMA, DOWN when below, SIDEWAYS when equal."""
    fast_averages = _simple_moving_average(closes, fast)
    slow_averages = _simple_moving_average(closes, slow)
    states: List[Optional[str]] = []
    for fast_value, slow_value in zip(fast_averages, slow_averages):
        if fast_value is None or slow_value is None:
            states.append(None)
        elif fast_value > slow_value:
            states.append(UP)
        elif fast_value < slow_value:
            states.append(DOWN)
        else:
            states.append(SIDEWAYS)
    return states


def obv_direction_states(
    closes: Sequence[float], volumes: Sequence[float], period: int = OBV_SMA_PERIOD,
) -> List[Optional[str]]:
    """Volume's view of direction: UP when on-balance volume is above its own SMA, DOWN when below.

    SIDEWAYS when they are equal. None until the SMA has enough candles.
    """
    obv = on_balance_volume(closes, volumes)
    averages = _simple_moving_average(obv, period)
    states: List[Optional[str]] = []
    for value, average in zip(obv, averages):
        if average is None:
            states.append(None)
        elif value > average:
            states.append(UP)
        elif value < average:
            states.append(DOWN)
        else:
            states.append(SIDEWAYS)
    return states


# Settings the user can change in the Trend Identification window: (key, label, kind, low, high).
TREND_SETTING_FIELDS: Tuple[Tuple[str, str, str, Optional[float], Optional[float]], ...] = (
    ("adx_enter", "ADX entry level", "float", 0, 100),
    ("adx_exit", "ADX exit level", "float", 0, 100),
    ("sma_fast", "Fast SMA period (candles)", "int", 2, None),
    ("sma_slow", "Slow SMA period (candles)", "int", 3, None),
)


def default_trend_settings() -> Dict[str, float]:
    """The layered labeler's settings, using the module constants as defaults."""
    return {
        "adx_enter": ADX_THRESHOLD, "adx_exit": ADX_EXIT_THRESHOLD,
        "sma_fast": SMA_DIRECTION_FAST, "sma_slow": SMA_DIRECTION_SLOW,
    }


def validate_trend_settings(raw: Dict[str, str]) -> Dict[str, Any]:
    """Parse and check the text typed into the Trend Identification window.

    Raises ValueError with a message the user can read when a value is missing, not a
    number, out of range, when the exit level is above the entry level, or when the fast
    SMA is not shorter than the slow SMA.
    """
    values = parse_setting_fields(TREND_SETTING_FIELDS, raw)
    if values["adx_exit"] > values["adx_enter"]:
        raise ValueError("ADX exit level must not be above the entry level.")
    if values["sma_fast"] >= values["sma_slow"]:
        raise ValueError("Fast SMA period must be shorter than the slow SMA period.")
    return values


def layered_trend_details(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
    enter: float = ADX_THRESHOLD, exit_level: float = ADX_EXIT_THRESHOLD,
    fast: int = SMA_DIRECTION_FAST, slow: int = SMA_DIRECTION_SLOW,
    volumes: Optional[Sequence[float]] = None,
) -> List[Tuple[Optional[str], Optional[float]]]:
    """Layered trend for every candle, as (state, ADX) pairs.

    The ADX gate decides whether a trend exists, and the fast/slow SMA order gives its
    direction. While the gate is off the state is SIDEWAYS. A state is None until both
    layers have warmed up. The ADX value is returned so it can be shown next to the state.

    With ``volumes``, an UP or DOWN state is kept only when on-balance volume agrees with
    it (see ``obv_direction_states``). Otherwise the candle is SIDEWAYS: the trend is not
    confirmed by volume.
    """
    adx_values, _, _ = adx_components(highs, lows, closes, ADX_PERIOD)
    gate = adx_gate_states(adx_values, enter, exit_level)
    direction = sma_direction_states(closes, fast, slow)
    confirmation = None if volumes is None else obv_direction_states(closes, volumes)
    details: List[Tuple[Optional[str], Optional[float]]] = []
    for index, (adx, trending, side) in enumerate(zip(adx_values, gate, direction)):
        if trending is None or side is None:
            state = None
        elif not trending:
            state = SIDEWAYS
        else:
            state = side
        if confirmation is not None and state in (UP, DOWN):
            volume_side = confirmation[index]
            if volume_side is None:
                state = None
            elif volume_side != state:
                state = SIDEWAYS
        details.append((state, adx))
    return details


def layered_trend_states(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
    enter: float = ADX_THRESHOLD, exit_level: float = ADX_EXIT_THRESHOLD,
    fast: int = SMA_DIRECTION_FAST, slow: int = SMA_DIRECTION_SLOW,
    volumes: Optional[Sequence[float]] = None,
) -> List[Optional[str]]:
    """The state of each candle from ``layered_trend_details``."""
    return [state for state, _adx in layered_trend_details(
        highs, lows, closes, enter, exit_level, fast, slow, volumes)]


def consensus(votes: Votes) -> Optional[Consensus]:
    """Combine one vote per strategy. Returns None while any strategy is still warming up."""
    if any(vote is None for vote in votes):
        return None
    ballots = tuple(vote for vote in votes if vote is not None)
    ranked = Counter(ballots).most_common()
    label, count = ranked[0]
    tied = len(ranked) > 1 and ranked[1][1] == count
    if count >= 2 and not tied:
        return Consensus(label, count, ballots)
    return Consensus(MIXED, count, ballots)


def trend_series(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
) -> List[Optional[Consensus]]:
    """Consensus trend for every candle, from the four strategies."""
    votes_per_candle = zip(
        efficiency_ratio_states(closes),
        swing_structure_states(highs, lows),
        moving_average_stack_states(closes),
        adx_states(highs, lows, closes),
    )
    return [consensus(votes) for votes in votes_per_candle]
