"""Calendar-based resampling of daily candles into the chart tab time frames."""

from __future__ import annotations

import datetime
from typing import Callable, Dict, Hashable, List, Sequence, Tuple

DAILY = "Daily"
TIMEFRAMES: Tuple[str, ...] = (DAILY, "2W", "1M", "2M", "3M", "6M")

Row = list


def _date(row: Row) -> datetime.date:
    year, month, day = (int(part) for part in row[0])
    return datetime.date(year, month, day)


def _week_key(row: Row) -> Hashable:
    iso_year, iso_week, _ = _date(row).isocalendar()
    return iso_year, (iso_week - 1) // 2


def _month_key(months: int) -> Callable[[Row], Hashable]:
    def key(row: Row) -> Hashable:
        day = _date(row)
        return day.year, (day.month - 1) // months

    return key


BUCKET_KEYS: Dict[str, Callable[[Row], Hashable]] = {
    "2W": _week_key,
    "1M": _month_key(1),
    "2M": _month_key(2),
    "3M": _month_key(3),
    "6M": _month_key(6),
}


def shows_day_labels(label: str) -> bool:
    """Daily and 2W candles are narrow enough to label each day; monthly tabs are not."""
    return label in (DAILY, "2W")


def resample(rows: Sequence[Row], label: str) -> List[Row]:
    """Aggregate chronological daily rows into the candles of one time frame.

    Each bucket keeps the first open, highest high, lowest low, last close and the
    date of its first day. Daily returns the rows unchanged.
    """
    if label == DAILY:
        return rows if isinstance(rows, list) else list(rows)
    key_for = BUCKET_KEYS[label]
    buckets: Dict[Hashable, List[Row]] = {}
    for row in rows:
        buckets.setdefault(key_for(row), []).append(row)
    candles: List[Row] = []
    for bucket in buckets.values():
        candles.append([
            list(bucket[0][0]),
            bucket[0][1],
            max(row[2] for row in bucket),
            min(row[3] for row in bucket),
            bucket[-1][4],
            {"rsi": None, "ema": None, "sma": None},
        ])
    return candles


def timeframe_rows(daily_rows: Sequence[Row], label: str) -> List[Row]:
    """Return the candles to chart for a tab, given the loaded daily rows."""
    return resample(daily_rows, label)
