"""Chronological, calendar-based pagination of price CSV files.

The header row is located by name: a record that names a date column (``date``
or ``datetime``) and ``open``, ``high``, ``low`` and ``close``, matched without
regard to case. Other columns are ignored. Records may be in ascending or
descending order and must not repeat a timestamp. Dates may be written as
``YYYY-MM-DD``, ``YYYY-MM-DD HH:MM[:SS]`` (with a space or ``T`` separator) or
``YYYY/MM/DD``. OHLC values may carry a leading ``$``. When no header names the
columns, the file is read by position instead: the first ``skip_lines`` records
are skipped, the date is in column 1 and OHLC values are in columns 3 through 6. Timestamps and record offsets, including those of
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
from typing import Any, Dict, List, Optional, Tuple, Union

DATE_COLUMN_NAMES = ("date", "datetime")
DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
)
OHLC_COLUMN_NAMES = ("open", "high", "low", "close")
# Positional layout used when no header record names the columns.
POSITIONAL_COLUMNS: Dict[str, int] = {"date": 1, "open": 3, "high": 4, "low": 5, "close": 6}
HEADER_SEARCH_RECORDS = 10


def _named_columns(row: List[str]) -> Optional[Dict[str, int]]:
    """Return the column index of each required field, or None if the row lacks any."""
    positions: Dict[str, int] = {}
    for index, name in enumerate(row):
        positions.setdefault(name.strip().lower(), index)
    date_name = next((name for name in DATE_COLUMN_NAMES if name in positions), None)
    if date_name is None or any(name not in positions for name in OHLC_COLUMN_NAMES):
        return None
    columns = {"date": positions[date_name]}
    columns.update({name: positions[name] for name in OHLC_COLUMN_NAMES})
    return columns


def _add_months(anchor: datetime, months: int) -> Optional[datetime]:
    """Return an anchored calendar boundary, or None beyond datetime's range."""
    year, month = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
    if year > datetime.max.year:
        return None
    month += 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def _parse_date(row: List[str], line: int, column: int = 1) -> datetime:
    if len(row) <= column:
        raise ValueError(f"CSV record ending on line {line}: missing date")
    value = row[column].strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(f"CSV record ending on line {line}: invalid date {row[column]!r}")


def _parse_price(text: str) -> float:
    """Convert an OHLC field to float, accepting a leading dollar sign."""
    return float(text.strip().replace("$", ""))


class PaginatedPriceData:
    """Page oldest-first, with an initial year followed by three-month windows.

    All boundaries are exclusive and calculated from the oldest timestamp,
    avoiding drift after short months. Empty windows are skipped by load_next.
    Duplicate timestamps and malformed CSV dates raise ValueError during
    indexing. Malformed OHLC values raise ValueError
    when their page is loaded; filesystem errors propagate unchanged.
    """

    def __init__(
        self, file_path: Union[str, os.PathLike], skip_lines: int = 2,
        require_named_columns: bool = False,
    ) -> None:
        if isinstance(skip_lines, bool) or not isinstance(skip_lines, int) or skip_lines < 0:
            raise ValueError("skip_lines must be a non-negative integer")
        self._file_path = file_path
        records: List[Tuple[datetime, int, int]] = []
        with open(file_path, encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(iter(file.readline, ""), strict=True)
            try:
                columns = self._find_named_header(reader)
                if columns is None:
                    if require_named_columns:
                        raise ValueError(
                            "CSV header must name a date column (date or datetime) "
                            "and open, high, low and close columns"
                        )
                    file.seek(0)
                    reader = csv.reader(iter(file.readline, ""), strict=True)
                    for _ in range(skip_lines):
                        if next(reader, None) is None:
                            raise ValueError(
                                f"CSV must contain {skip_lines} header records to skip"
                            )
                    columns = POSITIONAL_COLUMNS
                self._date_column = columns["date"]
                self._ohlc_columns = tuple(columns[name] for name in OHLC_COLUMN_NAMES)
                while True:
                    offset = file.tell()
                    row = next(reader, None)
                    if row is None:
                        break
                    line = reader.line_num
                    date = _parse_date(row, line, self._date_column)
                    records.append((date, offset, line))
            except csv.Error as exc:
                raise ValueError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc

        if not records:
            raise ValueError("CSV contains no price records")
        records.sort(key=lambda record: record[0])
        for earlier, later in zip(records, records[1:]):
            if earlier[0] == later[0]:
                raise ValueError(
                    f"CSV record ending on line {later[2]}: duplicate date "
                    f"{later[0].strftime('%Y-%m-%d %H:%M:%S')}"
                )
        self._records = records
        self._dates = [record[0] for record in self._records]
        self._cursor = 0
        self._interval = 0
        self._started = False

    @staticmethod
    def _find_named_header(reader: Any) -> Optional[Dict[str, int]]:
        """Read the leading records and return the columns of the first one that names them."""
        for _ in range(HEADER_SEARCH_RECORDS):
            row = next(reader, None)
            if row is None:
                return None
            columns = _named_columns(row)
            if columns is not None:
                return columns
        return None

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
                if _parse_date(row, line, self._date_column) != date:
                    raise ValueError(f"CSV timestamp changed at indexed line {line}")
                if len(row) <= max(self._ohlc_columns):
                    raise ValueError(f"CSV record ending on line {line}: missing OHLC values")
                try:
                    prices = [_parse_price(row[column]) for column in self._ohlc_columns]
                    if not all(isfinite(value) for value in prices):
                        raise ValueError("non-finite price")
                except ValueError as exc:
                    raise ValueError(f"CSV record ending on line {line}: invalid OHLC values") from exc
                page.append([
                    [f"{date.year:04d}", f"{date.month:02d}", f"{date.day:02d}"],
                    *prices,
                    {"rsi": None, "ema": None, "sma": None},
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
