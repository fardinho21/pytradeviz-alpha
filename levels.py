"""Support and resistance levels built from confirmed swing pivots.

Pure Python with no Tk dependency. Price rows use the viewer's layout
(``[[year, month, day], open, high, low, close, indicators]``) and must be in
ascending date order.

Causality: a pivot at bar ``i`` only becomes known once ``pivot_bars`` later bars
have closed, so the levels reported for bar ``t`` never use data after ``t``.
"""
from __future__ import annotations

import calendar
import datetime as dt
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from indicators import CLOSE_COLUMN, HIGH_COLUMN, LOW_COLUMN

SUPPORT = "support"
RESISTANCE = "resistance"
MAX_LEVELS_PER_SIDE = 2

# Lookback for each window label, as (months, days) measured back from the latest candle.
WINDOW_LOOKBACKS: Dict[str, Tuple[int, int]] = {
    "2W": (0, 14),
    "1M": (1, 0),
    "2M": (2, 0),
    "3M": (3, 0),
    "6M": (6, 0),
}


@dataclass(frozen=True)
class LevelSettings:
    pivot_bars: int = 2
    width_pct: float = 1.0
    min_touches: int = 2


@dataclass(frozen=True)
class Level:
    price: float
    touches: int
    kind: str


@dataclass(frozen=True)
class Segment:
    """A level drawn from candle ``start`` to candle ``end`` inclusive, at a fixed price."""
    start: int
    end: int
    price: float
    kind: str


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float


def shift_months(day: dt.date, months: int) -> dt.date:
    """Move ``day`` back by ``months`` calendar months, clamping to the end of short months."""
    month_index = day.year * 12 + (day.month - 1) - months
    year, month = divmod(month_index, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def window_start(end: dt.date, label: str) -> dt.date:
    months, days = WINDOW_LOOKBACKS[label]
    return shift_months(end, months) - dt.timedelta(days=days)


def find_pivots(highs: Sequence[float], lows: Sequence[float], bars: int) -> List[Pivot]:
    """Swing highs and lows, each confirmed by ``bars`` candles on both sides.

    A swing high is strictly above the candles before it and at least as high as
    the candles after it (the mirror rule applies to swing lows). Pivots are
    returned in index order.
    """
    pivots: List[Pivot] = []
    for i in range(bars, len(highs) - bars):
        before_high = highs[i - bars:i]
        after_high = highs[i + 1:i + bars + 1]
        if highs[i] > max(before_high) and highs[i] >= max(after_high):
            pivots.append(Pivot(i, highs[i]))
        before_low = lows[i - bars:i]
        after_low = lows[i + 1:i + bars + 1]
        if lows[i] < min(before_low) and lows[i] <= min(after_low):
            pivots.append(Pivot(i, lows[i]))
    return pivots


def cluster_prices(prices: Sequence[float], width: float) -> List[Tuple[float, int]]:
    """Group sorted prices into (mean price, count) clusters.

    A price joins the current cluster when it is within ``width`` (a fraction of
    price) of the cluster's most recent price.
    """
    groups: List[List[float]] = []
    for price in sorted(prices):
        if groups and price - groups[-1][-1] <= width * groups[-1][-1]:
            groups[-1].append(price)
        else:
            groups.append([price])
    return [(sum(group) / len(group), len(group)) for group in groups]


def candidate_levels(prices: Sequence[float], close: float, settings: LevelSettings) -> List[Level]:
    """Every cluster with enough touches, classed as support or resistance against ``close``."""
    levels: List[Level] = []
    for price, touches in cluster_prices(prices, settings.width_pct / 100):
        if touches < settings.min_touches or price == close:
            continue
        levels.append(Level(price, touches, SUPPORT if price < close else RESISTANCE))
    return levels


def nearest_per_side(levels: Sequence[Level], close: float) -> List[Level]:
    """Keep the nearest ``MAX_LEVELS_PER_SIDE`` supports below and resistances above ``close``."""
    supports = sorted((l for l in levels if l.kind == SUPPORT), key=lambda l: close - l.price)
    resistances = sorted(
        (l for l in levels if l.kind == RESISTANCE), key=lambda l: l.price - close,
    )
    return supports[:MAX_LEVELS_PER_SIDE] + resistances[:MAX_LEVELS_PER_SIDE]


@dataclass
class _Track:
    start: int
    end: int
    price: float
    kind: str


class LevelFinder:
    """Precomputes pivots once so levels can be queried for any candle cheaply."""

    def __init__(self, rows: Sequence[List[Any]], settings: LevelSettings) -> None:
        self.settings = settings
        self.count = len(rows)
        self._dates = [dt.date(*(int(part) for part in row[0])) for row in rows]
        self._closes = [float(row[CLOSE_COLUMN]) for row in rows]
        self._pivots = find_pivots(
            [float(row[HIGH_COLUMN]) for row in rows],
            [float(row[LOW_COLUMN]) for row in rows],
            settings.pivot_bars,
        )
        self._pivot_indices = [pivot.index for pivot in self._pivots]

    def pivot_count(self, index: int, label: str) -> int:
        """Number of confirmed pivots inside the window that ends at candle ``index``."""
        first, last = self._pivot_range(index, label)
        return last - first

    def candidates_at(self, index: int, label: str) -> List[Level]:
        """All qualifying levels known after candle ``index`` closes, before the per-side cap."""
        if not 0 <= index < self.count:
            return []
        first, last = self._pivot_range(index, label)
        prices = [pivot.price for pivot in self._pivots[first:last]]
        return candidate_levels(prices, self._closes[index], self.settings)

    def levels_at(self, index: int, label: str) -> List[Level]:
        """Levels to show at candle ``index``: the nearest two per side, using only past data."""
        if not 0 <= index < self.count:
            return []
        return nearest_per_side(self.candidates_at(index, label), self._closes[index])

    def static_levels(self, label: str) -> List[Level]:
        """Levels as of the latest candle, for drawing across the whole chart."""
        return self.levels_at(self.count - 1, label)

    def segments(self, label: str) -> List[Segment]:
        """Where each level is shown, candle by candle.

        A level's life runs from the candle it first qualifies until price closes
        beyond its zone or its pivots age out of the window. Within that life it
        is drawn on every candle where it is one of the nearest two on its side,
        so a level does not flicker off and back on as price moves.
        """
        tracks = self._tracks(label)
        shown: List[set] = [set() for _ in range(self.count)]
        for index in range(self.count):
            close = self._closes[index]
            alive = [
                (position, track) for position, track in enumerate(tracks)
                if track.start <= index <= track.end
            ]
            for kind in (SUPPORT, RESISTANCE):
                ranked = sorted(
                    (item for item in alive if item[1].kind == kind),
                    key=lambda item: abs(close - item[1].price),
                )
                shown[index].update(position for position, _ in ranked[:MAX_LEVELS_PER_SIDE])

        segments: List[Segment] = []
        for position, track in enumerate(tracks):
            run_start: Optional[int] = None
            for index in range(track.start, track.end + 1):
                if position in shown[index]:
                    if run_start is None:
                        run_start = index
                    continue
                if run_start is not None:
                    segments.append(Segment(run_start, index - 1, track.price, track.kind))
                    run_start = None
            if run_start is not None:
                segments.append(Segment(run_start, track.end, track.price, track.kind))
        return sorted(segments, key=lambda segment: (segment.start, segment.price))

    def _tracks(self, label: str) -> List["_Track"]:
        """Follow each candidate level from its first candle until it is broken or lapses."""
        if self.count == 0:
            return []
        tolerance = self.settings.width_pct / 100
        finished: List[_Track] = []
        active: List[_Track] = []
        for index in range(self.count):
            close = self._closes[index]
            unmatched = self.candidates_at(index, label)
            survivors: List[_Track] = []
            for track in active:
                if _is_broken(track, close, tolerance):
                    track.end = index - 1
                    finished.append(track)
                    continue
                match = _closest_match(track, unmatched, tolerance)
                if match is None:
                    track.end = index - 1
                    finished.append(track)
                else:
                    unmatched.remove(match)
                    survivors.append(track)
            for level in unmatched:
                survivors.append(_Track(index, index, level.price, level.kind))
            active = survivors
        for track in active:
            track.end = self.count - 1
            finished.append(track)
        return finished

    def _pivot_range(self, index: int, label: str) -> Tuple[int, int]:
        """Slice bounds of confirmed pivots (index <= ``index - pivot_bars``) in the window."""
        start_index = bisect_left(self._dates, window_start(self._dates[index], label))
        first = bisect_left(self._pivot_indices, start_index)
        last = bisect_right(self._pivot_indices, index - self.settings.pivot_bars)
        return first, max(first, last)


def _is_broken(track: _Track, close: float, tolerance: float) -> bool:
    """A level is a zone ``tolerance`` wide, so breaking it takes a close beyond the zone."""
    band = tolerance * track.price
    if track.kind == SUPPORT:
        return close < track.price - band
    return close > track.price + band


def _closest_match(track: _Track, levels: List[Level], tolerance: float) -> Level | None:
    best: Level | None = None
    best_distance = tolerance * track.price
    for level in levels:
        distance = abs(level.price - track.price)
        if level.kind == track.kind and distance <= best_distance:
            best, best_distance = level, distance
    return best
