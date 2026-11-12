
from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Tuple

# Simple moving average periods, counted in candles (rows of price data).
SMA_PERIODS: Tuple[int, ...] = (3, 7, 14, 30)

# Bollinger Bands use a fixed window (in candles) and width (in standard deviations).
BOLLINGER_PERIOD = 20
BOLLINGER_MULTIPLIER = 2

# Indices of the price fields in each row: [date, open, high, low, close, indicators].
HIGH_COLUMN = 2
LOW_COLUMN = 3
CLOSE_COLUMN = 4

# RSI levels drawn on the indicator canvas and used for the overbought/oversold flags.
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def band_intersects(low: Optional[float], high: Optional[float], band: Optional[float]) -> Optional[bool]:
    """Return True when the candle's high-low range contains the band value.

    Returns None when the candle or the band has no value yet (warm-up rows).
    """
    if low is None or high is None or band is None:
        return None
    return low <= band <= high


def rsi_crosses_level(previous: Optional[float], current: Optional[float], level: float) -> Optional[bool]:
    """Return True when RSI moves from one side of ``level`` to the other on this candle.

    Returns None when either RSI value is missing, e.g. for the first candle.
    """
    if previous is None or current is None:
        return None
    return (previous - level) * (current - level) < 0


class Indicators:

    price_data: Optional[List[List[Any]]] = None
    _rsi_state: Optional[Dict[str, Any]] = None


    def __init__(
        self,
        tk_canvas: Optional[tk.Canvas] = None,
        price_data: Optional[List[List[Any]]] = None,
    ) -> None:
        self.price_data=price_data
        self._rsi_state = None
        self._sma_cache: Dict[Tuple[int, int], List[Optional[float]]] = {}
        self._bollinger_cache: Dict[Tuple[int, float, int], Tuple[
            List[Optional[float]], List[Optional[float]], List[Optional[float]]]] = {}
        pass

    def set_price_data(self, price_data: List[List[Any]]) -> None:
        self.price_data=price_data
        self._rsi_state = None
        self._sma_cache = {}
        self._bollinger_cache = {}

    def render_RSI(self, tk_indicators_canvas: tk.Canvas, divider_v: float,
                   offset_x: float = 0, start: int = 0,
                   tags: Tuple[str, ...] = (), fill: str = "black") -> None:
        previous = None
        for i in range(start - 1, -1, -1):
            if self.price_data[i][5]["rsi"] is not None:
                previous = (offset_x + divider_v * i, self.price_data[i][5]["rsi"])
                break
        
        for i in range(start, len(self.price_data)):
            row = self.price_data[i]
            pos = offset_x + divider_v*i
            
            if row[5]["rsi"] is not None:
                rsi = row[5]["rsi"]

                if previous is None:
                    tk_indicators_canvas.create_line(offset_x, 100, pos, 100 - rsi, fill=fill, tags=tags)
                else:
                    tk_indicators_canvas.create_line(previous[0], 100 - previous[1], pos, 100 - rsi, fill=fill, tags=tags)

                previous = [pos, rsi]
        pass

    def render_SMA(
        self, tk_canvas: tk.Canvas, period: int,
        x_for_index: Callable[[int], float], y_for_price: Callable[[float], float],
        fill: str = "black", dash: Tuple[int, ...] = (), width: int = 2,
        tags: Tuple[str, ...] = (), column: int = CLOSE_COLUMN,
    ) -> List[int]:
        """Draw the SMA for ``period`` as polylines and return the line item ids.

        ``column`` selects the price field that is averaged.
        """
        return self.render_series(
            tk_canvas, self.calculate_SMA(period, column),
            x_for_index=x_for_index, y_for_price=y_for_price,
            fill=fill, dash=dash, width=width, tags=tags,
        )

    def render_series(
        self, tk_canvas: tk.Canvas, values: List[Optional[float]],
        x_for_index: Callable[[int], float], y_for_price: Callable[[float], float],
        fill: str = "black", dash: Tuple[int, ...] = (), width: int = 2,
        tags: Tuple[str, ...] = (),
    ) -> List[int]:
        """Draw one value per row as polylines and return the line item ids.

        ``x_for_index`` and ``y_for_price`` map a row index and a price to canvas
        coordinates. ``None`` entries (the warm-up rows) break the line.
        """
        options: Dict[str, Any] = {"fill": fill, "width": width, "tags": tags}
        if dash:
            options["dash"] = dash
        items: List[int] = []
        run: List[float] = []
        for i, value in enumerate(values):
            if value is None:
                self._draw_run(tk_canvas, run, options, items)
                run = []
                continue
            run.extend((x_for_index(i), y_for_price(value)))
        self._draw_run(tk_canvas, run, options, items)
        return items

    def render_SMA_markers(
        self, tk_canvas: tk.Canvas, period: int, column: int,
        x_for_index: Callable[[int], float], y_for_price: Callable[[float], float],
        fill: str = "black", size: int = 6, tags: Tuple[str, ...] = (),
        x_range: Optional[Tuple[float, float]] = None,
    ) -> List[int]:
        """Draw an X of ``size`` pixels across at each valid point of the SMA.

        Each X is two diagonal one-pixel strokes. Points whose x falls outside
        ``x_range`` (canvas coordinates) are skipped, so only the visible part
        of the series creates canvas items. Returns the stroke item ids.
        """
        half = size / 2
        items: List[int] = []
        for i, value in enumerate(self.calculate_SMA(period, column)):
            if value is None:
                continue
            x, y = x_for_index(i), y_for_price(value)
            if x_range is not None and not (x_range[0] - half <= x <= x_range[1] + half):
                continue
            for x1, y1, x2, y2 in ((x - half, y - half, x + half, y + half),
                                   (x - half, y + half, x + half, y - half)):
                items.append(tk_canvas.create_line(x1, y1, x2, y2, fill=fill, width=1, tags=tags))
        return items

    @staticmethod
    def _draw_run(tk_canvas: tk.Canvas, run: List[float], options: Dict[str, Any],
                  items: List[int]) -> None:
        if len(run) >= 4:
            items.append(tk_canvas.create_line(*run, **options))

    def render_EMA(self) -> None:
        pass

    def calculate_RSI(self, avg_gain: float, avg_loss: float) -> float:
        # With no gains or losses the ratio is undefined; 50 is the neutral value.
        if avg_gain == 0 and avg_loss == 0:
            return 50
        if avg_loss == 0:
            return 100
        return 100 - (100/ (1 + (avg_gain/avg_loss)))

    def calculate_RSI_full(self, period: int = 7) -> None:
        self._rsi_state = None
        self.calculate_RSI_incremental(period)

    def calculate_RSI_incremental(self, period: int = 7) -> None:
        """Compute Wilder's RSI for rows that do not have a value yet.

        Each bar's gain or loss is its close-to-close change. The first RSI is
        the simple average of the first ``period`` changes and is stored at
        index ``period``. Later bars smooth both averages with
        ``(previous * (period - 1) + current) / period``.
        """
        if len(self.price_data) <= period:
            return
        if self._rsi_state is None:
            avg_gain, avg_loss = self.RSI_step_one(period)
            self._rsi_state = {
                "period": period, "next_index": period + 1,
                "avg_gain": avg_gain, "avg_loss": avg_loss,
            }
        state = self._rsi_state
        if state["period"] != period:
            raise ValueError("RSI period cannot change during incremental calculation")

        for i in range(state["next_index"], len(self.price_data)):
            gain, loss = self._close_change_gain_loss(i)
            state["avg_gain"] = (state["avg_gain"] * (period - 1) + gain) / period
            state["avg_loss"] = (state["avg_loss"] * (period - 1) + loss) / period
            self.price_data[i][5]["rsi"] = self.calculate_RSI(
                state["avg_gain"], state["avg_loss"]
            )
        state["next_index"] = len(self.price_data)

    def _close_change_gain_loss(self, index: int) -> Tuple[float, float]:
        change = self.price_data[index][4] - self.price_data[index - 1][4]
        return max(change, 0.0), max(-change, 0.0)

    def RSI_step_one(self, period: int) -> Tuple[float, float]:
        """Seed the Wilder averages from the first ``period`` changes.

        Stores the first RSI at index ``period`` and returns the average gain
        and average loss used to seed the smoothing.
        """
        gain_sum = 0.0
        loss_sum = 0.0
        for i in range(1, period + 1):
            gain, loss = self._close_change_gain_loss(i)
            gain_sum += gain
            loss_sum += loss

        avg_gain = gain_sum / period
        avg_loss = loss_sum / period
        self.price_data[period][5]["rsi"] = self.calculate_RSI(avg_gain, avg_loss)
        return avg_gain, avg_loss

    def calculate_SMA(self, period: int, column: int = CLOSE_COLUMN) -> List[Optional[float]]:
        """Return the simple moving average of one price field, one entry per row.

        ``column`` is the price field to average (close by default; use
        ``HIGH_COLUMN`` or ``LOW_COLUMN`` for the high and low moving averages).
        The average covers the current row and the ``period - 1`` rows before it,
        so the first ``period - 1`` entries are ``None``. Results are cached per
        period and field, and only rows added since the last call are computed.
        """
        if period < 1:
            raise ValueError("SMA period must be at least 1")
        values = self._sma_cache.setdefault((period, column), [])
        for i in range(len(values), len(self.price_data)):
            if i < period - 1:
                values.append(None)
            else:
                window = self.price_data[i - period + 1:i + 1]
                values.append(sum(row[column] for row in window) / period)
        return values

    def calculate_bollinger(
        self, period: int = BOLLINGER_PERIOD, multiplier: float = BOLLINGER_MULTIPLIER,
        column: int = CLOSE_COLUMN,
    ) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
        """Return the (middle, upper, lower) Bollinger Bands, one entry per row.

        The middle band is the simple moving average of ``column``. The upper and
        lower bands sit ``multiplier`` population standard deviations above and
        below it, using the same window. Warm-up rows are ``None``. Results are
        cached and only rows added since the last call are computed.
        """
        if period < 1:
            raise ValueError("Bollinger period must be at least 1")
        averages = self.calculate_SMA(period, column)
        middle, upper, lower = self._bollinger_cache.setdefault(
            (period, multiplier, column), ([], [], []))
        for i in range(len(middle), len(self.price_data)):
            average = averages[i]
            if average is None:
                middle.append(None)
                upper.append(None)
                lower.append(None)
                continue
            window = [row[column] for row in self.price_data[i - period + 1:i + 1]]
            deviation = math.sqrt(sum((price - average) ** 2 for price in window) / period)
            middle.append(average)
            upper.append(average + multiplier * deviation)
            lower.append(average - multiplier * deviation)
        return middle, upper, lower

    def bollinger_range(
        self, period: int = BOLLINGER_PERIOD, multiplier: float = BOLLINGER_MULTIPLIER,
    ) -> Optional[Tuple[float, float]]:
        """Return the (lowest, highest) band value over all rows, or None if there are none."""
        _, upper, lower = self.calculate_bollinger(period, multiplier)
        values = [value for value in upper + lower if value is not None]
        if not values:
            return None
        return min(values), max(values)

    def calculate_EMA(self, period: int = 7) -> None:
        pass