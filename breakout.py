"""Empirical breakout odds for support and resistance levels.

Every level that qualifies is an event. The event records what happened next:
price closed through the level first (a breakout), or moved away from it by the
rejection distance first (a rejection). Events that did neither within the
horizon expired. Odds are tallied per bucket of features measured on the
qualification candle, so a level is compared only with levels that looked like it.

Causality: features use candles up to and including the qualification candle.
Outcomes use the candles after it, since they are what the odds estimate. Odds
shown at a candle count only outcomes resolved by that candle. The walk-forward
check tests whether the bucket odds, built from earlier events, beat the overall
base rate on later events.

Pure Python with no Tk dependency.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from indicators import CLOSE_COLUMN, HIGH_COLUMN, LOW_COLUMN
from levels import RESISTANCE, SUPPORT, LevelFinder, is_broken

HORIZONS = (5, 10)
ATR_REJECTION = "1 ATR"
PERCENT_REJECTION = "2%"
REJECTION_RULES = (ATR_REJECTION, PERCENT_REJECTION)
ATR_PERIOD = 14
PERCENT_REJECTION_SHARE = 0.02
MIN_BUCKET_SAMPLES = 10
# Distance from the close to the level, in ATRs, where each bucket starts.
DISTANCE_EDGES = (1.0, 3.0)
# Touch counts at or above this share one bucket.
TOUCH_CAP = 4

BREAKOUT = "breakout"
REJECTION = "rejection"
EXPIRED = "expired"
PENDING = "pending"
RESOLVED = (BREAKOUT, REJECTION)


@dataclass(frozen=True)
class LevelEvent:
    window: str
    origin: int
    kind: str
    price: float
    touches: int
    atr_distance: float
    outcome: str
    resolved_at: Optional[int]


@dataclass(frozen=True)
class Odds:
    breakouts: int
    rejections: int

    @property
    def samples(self) -> int:
        return self.breakouts + self.rejections

    @property
    def reliable(self) -> bool:
        return self.samples >= MIN_BUCKET_SAMPLES

    @property
    def rate(self) -> Optional[float]:
        return self.breakouts / self.samples if self.samples else None

    @property
    def probability(self) -> Optional[float]:
        """Breakout share, or None when there are too few samples to trust it."""
        return self.rate if self.reliable else None


@dataclass(frozen=True)
class WalkForward:
    train_events: int
    test_events: int
    base_brier: float
    model_brier: float

    @property
    def beats_base(self) -> bool:
        return self.model_brier < self.base_brier


def average_true_range(rows: Sequence[List[Any]], period: int = ATR_PERIOD) -> List[Optional[float]]:
    """Simple average of the true range over the last ``period`` candles.

    Entries before the first full period are None.
    """
    true_ranges: List[float] = []
    previous_close: Optional[float] = None
    for row in rows:
        high, low = float(row[HIGH_COLUMN]), float(row[LOW_COLUMN])
        if previous_close is None:
            true_ranges.append(high - low)
        else:
            true_ranges.append(max(high - low, abs(high - previous_close),
                                   abs(low - previous_close)))
        previous_close = float(row[CLOSE_COLUMN])
    atr: List[Optional[float]] = [None] * len(rows)
    for index in range(period - 1, len(rows)):
        atr[index] = sum(true_ranges[index - period + 1:index + 1]) / period
    return atr


def distance_bucket(atr_distance: float) -> int:
    return sum(1 for edge in DISTANCE_EDGES if atr_distance >= edge)


def bucket_key(window: str, kind: str, touches: int, atr_distance: float) -> Tuple[str, str, int, int]:
    return window, kind, min(touches, TOUCH_CAP), distance_bucket(atr_distance)


def tally(events: Iterable[LevelEvent]) -> Dict[Tuple[str, str, int, int], Odds]:
    counts: Dict[Tuple[str, str, int, int], List[int]] = {}
    for event in events:
        if event.outcome not in RESOLVED:
            continue
        key = bucket_key(event.window, event.kind, event.touches, event.atr_distance)
        pair = counts.setdefault(key, [0, 0])
        pair[0 if event.outcome == BREAKOUT else 1] += 1
    return {key: Odds(breakouts, rejections) for key, (breakouts, rejections) in counts.items()}


def timeline(events: Iterable[LevelEvent]) -> Dict[Tuple[str, str, int, int],
                                                   Tuple[List[int], List[int]]]:
    """Per bucket, the candles where outcomes resolved, in order, and running breakout counts.

    ``breakouts[k]`` is the number of breakouts among the first ``k`` resolved events.
    """
    resolved: Dict[Tuple[str, str, int, int], List[Tuple[int, bool]]] = {}
    ordered = sorted((e for e in events if e.outcome in RESOLVED), key=lambda e: e.resolved_at)
    for event in ordered:
        key = bucket_key(event.window, event.kind, event.touches, event.atr_distance)
        resolved.setdefault(key, []).append((event.resolved_at, event.outcome == BREAKOUT))
    table: Dict[Tuple[str, str, int, int], Tuple[List[int], List[int]]] = {}
    for key, pairs in resolved.items():
        running = [0]
        for _, broke in pairs:
            running.append(running[-1] + (1 if broke else 0))
        table[key] = ([candle for candle, _ in pairs], running)
    return table


def resolve_outcome(kind: str, price: float, start: int, horizon: int, rejection: str,
                    atr: float, tolerance: float, highs: Sequence[float],
                    lows: Sequence[float], closes: Sequence[float]) -> Tuple[str, Optional[int]]:
    """Decide what happened first after candle ``start``, reading only candles after it.

    Returns the outcome and the candle that decided it. Within a candle, a close
    through the level counts as a breakout before the rejection distance is
    checked, since the close is the decisive price. ``EXPIRED`` means the full
    horizon was observed without a decision; ``PENDING`` means the data ends first.
    """
    if rejection == ATR_REJECTION:
        threshold = atr
    else:
        threshold = PERCENT_REJECTION_SHARE * price
    last_index = len(closes) - 1
    for index in range(start + 1, min(start + horizon, last_index) + 1):
        if is_broken(kind, price, closes[index], tolerance):
            return BREAKOUT, index
        if kind == SUPPORT and highs[index] >= price + threshold:
            return REJECTION, index
        if kind == RESISTANCE and lows[index] <= price - threshold:
            return REJECTION, index
    if start + horizon <= last_index:
        return EXPIRED, None
    return PENDING, None


class BreakoutStudy:
    """Level events for one window, each labelled with its outcome, plus odds lookups."""

    def __init__(self, rows: Sequence[List[Any]], finder: LevelFinder, label: str,
                 horizon: int, rejection: str) -> None:
        if horizon not in HORIZONS:
            raise ValueError(f"horizon must be one of {HORIZONS}, not {horizon}")
        if rejection not in REJECTION_RULES:
            raise ValueError(f"rejection must be one of {REJECTION_RULES}, not {rejection!r}")
        self.label = label
        self.horizon = horizon
        self.rejection = rejection
        self._closes = [float(row[CLOSE_COLUMN]) for row in rows]
        self._highs = [float(row[HIGH_COLUMN]) for row in rows]
        self._lows = [float(row[LOW_COLUMN]) for row in rows]
        self._atr = average_true_range(rows)
        tolerance = finder.settings.width_pct / 100
        self.events: List[LevelEvent] = []
        for track in finder.tracks(label):
            atr = self._atr[track.start]
            if not atr:
                continue
            outcome, resolved_at = resolve_outcome(
                track.kind, track.price, track.start, self.horizon, self.rejection,
                atr, tolerance, self._highs, self._lows, self._closes)
            self.events.append(LevelEvent(
                window=label,
                origin=track.start,
                kind=track.kind,
                price=track.price,
                touches=track.touches,
                atr_distance=abs(track.price - self._closes[track.start]) / atr,
                outcome=outcome,
                resolved_at=resolved_at,
            ))
        self._timeline = timeline(self.events)

    def odds_at(self, index: int, price: float, kind: str, touches: int) -> Optional[Odds]:
        """Historical odds for a level like this one, as known on candle ``index``.

        Only outcomes resolved by candle ``index`` are counted, so the odds never
        depend on later candles. Returns None when the candle has no ATR yet.
        """
        if not 0 <= index < len(self._closes):
            return None
        atr = self._atr[index]
        if not atr:
            return None
        key = bucket_key(self.label, kind, touches, abs(price - self._closes[index]) / atr)
        times, breakouts = self._timeline.get(key, ([], [0]))
        known = bisect_right(times, index)
        return Odds(breakouts[known], known - breakouts[known])

    def walk_forward(self, split: float = 0.6) -> Optional[WalkForward]:
        """Fit bucket odds on events that resolved before a cutoff, then score later events.

        Scores are Brier scores (lower is better) against the breakout outcome.
        The base prediction is the training breakout share for every test event.
        Returns None when either side has no resolved events.
        """
        cutoff = int(len(self._closes) * split)
        train = [e for e in self.events if e.resolved_at is not None and e.resolved_at < cutoff]
        test = [e for e in self.events if e.origin >= cutoff and e.outcome in RESOLVED]
        train_resolved = [e for e in train if e.outcome in RESOLVED]
        if not train_resolved or not test:
            return None
        train_breakouts = sum(1 for e in train_resolved if e.outcome == BREAKOUT)
        base_rate = train_breakouts / len(train_resolved)
        odds = tally(train_resolved)
        base_total = model_total = 0.0
        for event in test:
            actual = 1.0 if event.outcome == BREAKOUT else 0.0
            key = bucket_key(event.window, event.kind, event.touches, event.atr_distance)
            bucket = odds.get(key, Odds(0, 0))
            predicted = bucket.probability if bucket.probability is not None else base_rate
            base_total += (base_rate - actual) ** 2
            model_total += (predicted - actual) ** 2
        return WalkForward(
            train_events=len(train_resolved),
            test_events=len(test),
            base_brier=base_total / len(test),
            model_brier=model_total / len(test),
        )
