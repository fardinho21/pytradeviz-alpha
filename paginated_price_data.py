"""Chronological, calendar-based pagination of descending price CSV files.

The CSV has two header records by default, configurable with ``skip_lines``,
followed by records in strictly descending timestamp order. Dates use
``YYYY-MM-DD HH:MM:SS`` in column 1 and OHLC values
are in columns 3 through 6. Timestamps and record offsets, including those of
quoted multiline records, are indexed at construction; rows are reread and
OHLC values converted only when a page is requested.

Call ``load_initial()`` once, then ``load_next()`` while ``has_more`` is true.
Rows are compatible with PriceDataPrepper: ``[date_parts, open, high, low,
close, indicators]``. Date parts are zero-padded strings and each indicators
dictionary is independent. A failed page conversion does not advance the
cursor. Input paths may be strings or pathlib.Path objects. An empty data
section raises ValueError.
"""

from __future__ import annotations

import calendar
import csv
import os
from bisect import bisect_left
from datetime import datetime
from math import isfinite
from typing import Any, List, Optional, Tuple, Union


def _add_months(anchor: datetime, months: int) -> Optional[datetime]:
    """Return an anchored calendar boundary, or None beyond datetime's range."""
    year, month = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
    if year > datetime.max.year:
        return None
    month += 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def _parse_date(row: List[str], line: int) -> datetime:
    if len(row) < 2:
        raise ValueError(f"CSV record ending on line {line}: missing date")
    try:
        date = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
        if date.isoformat(sep=" ") != row[1]:
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            f"CSV record ending on line {line}: invalid date {row[1]!r}"
        ) from exc
    return date


class PaginatedPriceData:
    """Page oldest-first, with an initial year followed by three-month windows.

    All boundaries are exclusive and calculated from the oldest timestamp,
    avoiding drift after short months. Empty windows are skipped by load_next.
    Duplicate timestamps, out-of-order timestamps and malformed CSV dates
    raise ValueError during indexing. Malformed OHLC values raise ValueError
    when their page is loaded; filesystem errors propagate unchanged.
    """

    def __init__(
        self, file_path: Union[str, os.PathLike], skip_lines: int = 2
    ) -> None:
        if isinstance(skip_lines, bool) or not isinstance(skip_lines, int) or skip_lines < 0:
            raise ValueError("skip_lines must be a non-negative integer")
        self._file_path = file_path
        records: List[Tuple[datetime, int, int]] = []
        with open(file_path, encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(iter(file.readline, ""), strict=True)
            try:
                for _ in range(skip_lines):
                    if next(reader, None) is None:
                        raise ValueError(
                            f"CSV must contain {skip_lines} header records to skip"
                        )
                previous: Optional[datetime] = None
                while True:
                    offset = file.tell()
                    row = next(reader, None)
                    if row is None:
                        break
                    line = reader.line_num
                    date = _parse_date(row, line)
                    if previous is not None and date >= previous:
                        raise ValueError(
                            f"CSV record ending on line {line}: dates must be strictly descending"
                        )
                    records.append((date, offset, line))
                    previous = date
            except csv.Error as exc:
                raise ValueError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc

        if not records:
            raise ValueError("CSV contains no price records")
        self._records = records[::-1]
        self._dates = [record[0] for record in self._records]
        self._cursor = 0
        self._interval = 0
        self._started = False

    @property
    def has_more(self) -> bool:
        """Whether any records remain, including before the initial load."""
        return self._cursor < len(self._records)

    def _load_until(
        self, boundary: Optional[datetime], interval: int
    ) -> List[List[Any]]:
        end = len(self._records) if boundary is None else bisect_left(self._dates, boundary)
        page: List[List[Any]] = []
        with open(self._file_path, encoding="utf-8-sig", newline="") as file:
            for date, offset, line in self._records[self._cursor:end]:
                file.seek(offset)
                reader = csv.reader(iter(file.readline, ""), strict=True)
                try:
                    row = next(reader, None)
                except csv.Error as exc:
                    raise ValueError(f"Malformed CSV near indexed line {line}: {exc}") from exc
                if row is None:
                    raise ValueError(f"CSV record at indexed line {line} is missing")
                if _parse_date(row, line) != date:
                    raise ValueError(f"CSV timestamp changed at indexed line {line}")
                if len(row) < 7:
                    raise ValueError(f"CSV record ending on line {line}: missing OHLC values")
                try:
                    prices = [float(value) for value in row[3:7]]
                    if not all(isfinite(value) for value in prices):
                        raise ValueError("non-finite price")
                except ValueError as exc:
                    raise ValueError(f"CSV record ending on line {line}: invalid OHLC values") from exc
                page.append([
                    [f"{date.year:04d}", f"{date.month:02d}", f"{date.day:02d}"],
                    *prices,
                    {"rsi": 0, "ema": 0, "sma": 0},
                ])
        self._cursor = end
        self._interval = interval
        return page

    def load_initial(self) -> List[List[Any]]:
        """Load the oldest year's records; calling this more than once is an error."""
        if self._started:
            raise RuntimeError("Initial page has already been loaded")
        page = self._load_until(_add_months(self._dates[0], 12), 0)
        self._started = True
        return page

    def load_next(self) -> List[List[Any]]:
        """Load the next nonempty three-month window, or [] when exhausted."""
        if not self._started:
            raise RuntimeError("Load the initial page first")
        if not self.has_more:
            return []
        anchor = self._dates[0]
        next_date = self._dates[self._cursor]
        months = (next_date.year - anchor.year) * 12 + next_date.month - anchor.month
        interval = max(self._interval + 1, (months - 12) // 3 + 1)
        boundary = _add_months(anchor, 12 + interval * 3)
        while boundary is not None and boundary <= next_date:
            interval += 1
            boundary = _add_months(anchor, 12 + interval * 3)
        return self._load_until(boundary, interval)
