"""Index math for the data window that limits which loaded candles are drawn.

The window is centred on the candle under the middle of the chart view. Its span depends on
the timeframe tab: one year on the daily tab, four years on 2W, and six years on the monthly
tabs. Candles outside it stay loaded and keep their drawings, but are not rendered.
"""

from bisect import bisect_left, bisect_right
import datetime
from typing import Any, List, Sequence, Tuple

DATA_WINDOW_DAYS = 365
# Total calendar span of the data window for each timeframe tab. Tabs not listed use DATA_WINDOW_DAYS.
TIMEFRAME_WINDOW_DAYS = {
    "2W": 4 * 365,
    "1M": 6 * 365,
    "2M": 6 * 365,
    "3M": 6 * 365,
    "6M": 6 * 365,
}


def data_window_days(timeframe: str) -> int:
    """Total calendar span of the data window for a timeframe tab."""
    return TIMEFRAME_WINDOW_DAYS.get(timeframe, DATA_WINDOW_DAYS)


def row_ordinal(row: List[Any]) -> int:
    """Proleptic Gregorian ordinal of a price row's [year, month, day] strings."""
    year, month, day = (int(part) for part in row[0])
    return datetime.date(year, month, day).toordinal()


def window_index_range(
    ordinals: Sequence[int], centre_index: float, days: float = DATA_WINDOW_DAYS,
) -> Tuple[int, int]:
    """Inclusive (first, last) candle indexes within half of ``days`` either side of the centre.

    ``ordinals`` must be ascending. ``centre_index`` is clamped to the data, so the centre
    candle is always inside the window. An empty list gives (0, -1), an empty range.
    """
    if not ordinals:
        return 0, -1
    index = min(max(round(centre_index), 0), len(ordinals) - 1)
    centre = ordinals[index]
    half = days / 2
    first = bisect_left(ordinals, centre - half)
    last = bisect_right(ordinals, centre + half) - 1
    return first, last


def range_difference(first: Tuple[int, int], second: Tuple[int, int]) -> List[int]:
    """Indexes in the inclusive range ``first`` that are not in the range ``second``."""
    second_first, second_last = second
    return [index for index in range(first[0], first[1] + 1)
            if not second_first <= index <= second_last]
