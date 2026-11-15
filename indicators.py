
from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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
RSI_DEFAULT_PERIOD = 7

# ADX smoothing period, and the level above which the market counts as trending.
ADX_PERIOD = 14
ADX_TREND_LEVEL = 25
# Colour of the %D line; %K uses the theme ink colour like the other series.
STOCH_D_COLOR = "#e040fb"

# Stochastic oscillator: %K looks back STOCH_K_PERIOD candles, %D is a moving average of %K.
STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
STOCH_OVERBOUGHT = 80
STOCH_OVERSOLD = 20

# Williams %R looks back WILLIAMS_R_PERIOD candles and runs from -100 (close at the low) to 0 (at the high).
WILLIAMS_R_PERIOD = 14
WILLIAMS_R_OVERBOUGHT = -20
WILLIAMS_R_OVERSOLD = -80
# Added to %R so it fits the 0-100 canvas scale: -100 plots at the bottom and 0 at the top.
WILLIAMS_R_CANVAS_OFFSET = 100

# Editable parameters per indicator: (key, label, kind, low, high). Kind is "int" or "float";
# a None bound is open. Levels are on the indicator's own scale (Williams %R uses -100 to 0).
INDICATOR_SETTING_FIELDS: Dict[str, Tuple[Tuple[str, str, str, Optional[float], Optional[float]], ...]] = {
    "RSI": (
        ("period", "Period (candles)", "int", 2, None),
        ("overbought", "Overbought level", "float", 0, 100),
        ("oversold", "Oversold level", "float", 0, 100),
    ),
    "ADX": (
        ("period", "Period (candles)", "int", 2, None),
        ("trend_level", "Trend level", "float", 0, 100),
    ),
    "STOSC": (
        ("k_period", "%K period (candles)", "int", 2, None),
        ("d_period", "%D period (candles)", "int", 1, None),
        ("overbought", "Overbought level", "float", 0, 100),
        ("oversold", "Oversold level", "float", 0, 100),
    ),
    "W%R": (
        ("period", "Period (candles)", "int", 2, None),
        ("overbought", "Overbought level", "float", -100, 0),
        ("oversold", "Oversold level", "float", -100, 0),
    ),
}


# Bollinger Bands settings, kept with the band display style. The defaults are the module constants.
BOLLINGER_SETTING_FIELDS: Tuple[Tuple[str, str, str, Optional[float], Optional[float]], ...] = (
    ("period", "Period (candles)", "int", 2, None),
    ("multiplier", "Std. dev. multiplier", "float", 0.1, 10),
)


def default_indicator_settings() -> Dict[str, Dict[str, Any]]:
    """The settings every new chart starts with, keyed by indicator mode."""
    return {
        "RSI": {"period": RSI_DEFAULT_PERIOD, "overbought": RSI_OVERBOUGHT, "oversold": RSI_OVERSOLD},
        "ADX": {"period": ADX_PERIOD, "trend_level": ADX_TREND_LEVEL},
        "STOSC": {"k_period": STOCH_K_PERIOD, "d_period": STOCH_D_PERIOD,
                  "overbought": STOCH_OVERBOUGHT, "oversold": STOCH_OVERSOLD},
        "W%R": {"period": WILLIAMS_R_PERIOD, "overbought": WILLIAMS_R_OVERBOUGHT,
                "oversold": WILLIAMS_R_OVERSOLD},
    }


def parse_setting_fields(
    fields: Tuple[Tuple[str, str, str, Optional[float], Optional[float]], ...], raw: Dict[str, str],
) -> Dict[str, Any]:
    """Parse the typed text for each field, checking type and range.

    Raises ValueError with a message the user can read when a value is missing,
    not a number, or out of range.
    """
    values: Dict[str, Any] = {}
    for key, label, kind, low, high in fields:
        text = raw[key].strip()
        try:
            value: float = int(text) if kind == "int" else float(text)
        except ValueError:
            noun = "a whole number" if kind == "int" else "a number"
            raise ValueError(f"{label} must be {noun}.")
        if not math.isfinite(value):
            raise ValueError(f"{label} must be {'a whole number' if kind == 'int' else 'a number'}.")
        if (low is not None and value < low) or (high is not None and value > high):
            raise ValueError(f"{label} must be between {low if low is not None else 'any'} and "
                             f"{high if high is not None else 'any'}.")
        values[key] = value
    return values


def validate_indicator_settings(mode: str, raw: Dict[str, str]) -> Dict[str, Any]:
    """Parse and check the text typed into an indicator settings window.

    Raises ValueError with a message the user can read when a value is missing,
    not a number, out of range, or when overbought is not above oversold.
    """
    values = parse_setting_fields(INDICATOR_SETTING_FIELDS[mode], raw)
    if "overbought" in values and values["overbought"] <= values["oversold"]:
        raise ValueError("Overbought level must be above oversold level.")
    return values


def validate_bollinger_settings(raw: Dict[str, str]) -> Dict[str, Any]:
    """Parse and check the period and multiplier typed into the Bollinger Bands window."""
    return parse_setting_fields(BOLLINGER_SETTING_FIELDS, raw)


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


def on_balance_volume(closes: Sequence[float], volumes: Sequence[float]) -> List[float]:
    """Running total of volume: added on up closes, taken away on down closes.

    The first candle has no earlier close to compare with, so its volume is not counted.
    """
    total = 0.0
    values: List[float] = []
    for index, (close, volume) in enumerate(zip(closes, volumes)):
        if index > 0:
            if close > closes[index - 1]:
                total += volume
            elif close < closes[index - 1]:
                total -= volume
        values.append(total)
    return values


def adx_components(
    highs: List[float], lows: List[float], closes: List[float], period: int,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Wilder's ADX, +DI and -DI for every candle. ADX is None until its warm-up is over."""
    count = len(closes)
    adx_values: List[Optional[float]] = [None] * count
    plus_values: List[Optional[float]] = [None] * count
    minus_values: List[Optional[float]] = [None] * count
    true_range = [0.0] * count
    plus_move = [0.0] * count
    minus_move = [0.0] * count
    for i in range(1, count):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_move[i] = up if up > down and up > 0 else 0.0
        minus_move[i] = down if down > up and down > 0 else 0.0
        true_range[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    # Wilder smoothing starts from the sum of the first full period of moves.
    smooth_range = sum(true_range[1:period + 1])
    smooth_plus = sum(plus_move[1:period + 1])
    smooth_minus = sum(minus_move[1:period + 1])
    directional_indices: List[float] = []
    adx: Optional[float] = None
    for i in range(period, count):
        if i > period:
            smooth_range = smooth_range - smooth_range / period + true_range[i]
            smooth_plus = smooth_plus - smooth_plus / period + plus_move[i]
            smooth_minus = smooth_minus - smooth_minus / period + minus_move[i]
        plus_di = 100 * smooth_plus / smooth_range if smooth_range > 0 else 0.0
        minus_di = 100 * smooth_minus / smooth_range if smooth_range > 0 else 0.0
        spread = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / spread if spread > 0 else 0.0
        if adx is None:
            directional_indices.append(dx)
            if len(directional_indices) == period:
                adx = sum(directional_indices) / period
        else:
            adx = (adx * (period - 1) + dx) / period
        plus_values[i] = plus_di
        minus_values[i] = minus_di
        adx_values[i] = adx
    return adx_values, plus_values, minus_values


def stochastic_components(
    highs: List[float], lows: List[float], closes: List[float],
    k_period: int, d_period: int,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Fast stochastic %K and %D for every candle. Values are None during warm-up.

    %K places the close within the high-low range of the last k_period candles (0 at the
    low, 100 at the high). %D is the simple average of the last d_period %K values.
    """
    count = len(closes)
    k_values: List[Optional[float]] = [None] * count
    d_values: List[Optional[float]] = [None] * count
    for i in range(k_period - 1, count):
        window_high = max(highs[i - k_period + 1:i + 1])
        window_low = min(lows[i - k_period + 1:i + 1])
        span = window_high - window_low
        # A flat range has no position to measure, so it is treated as the middle.
        k_values[i] = 50.0 if span == 0 else 100 * (closes[i] - window_low) / span
    for i in range(count):
        window = k_values[max(0, i - d_period + 1):i + 1]
        if len(window) == d_period and None not in window:
            d_values[i] = sum(window) / d_period
    return k_values, d_values


def williams_r_values(
    highs: List[float], lows: List[float], closes: List[float], period: int,
) -> List[Optional[float]]:
    """Williams %R for every candle, from -100 to 0. Values are None during warm-up.

    %R = (highest high - close) / (highest high - lowest low) * -100 over the last period candles.
    """
    count = len(closes)
    values: List[Optional[float]] = [None] * count
    for i in range(period - 1, count):
        window_high = max(highs[i - period + 1:i + 1])
        window_low = min(lows[i - period + 1:i + 1])
        span = window_high - window_low
        # A flat range has no position to measure, so it is treated as the middle, as for the stochastic.
        values[i] = -50.0 if span == 0 else -100 * (window_high - closes[i]) / span
    return values


class Indicators:

    price_data: Optional[List[List[Any]]] = None
    _rsi_state: Optional[Dict[str, Any]] = None
    _adx_cache: Optional[Tuple[int, Tuple[Any, ...], List[Optional[float]]]] = None
    _stoch_cache: Optional[Tuple[int, Tuple[Any, ...], Tuple[List[Optional[float]], List[Optional[float]]]]] = None
    _willr_cache: Optional[Tuple[int, Tuple[Any, ...], List[Optional[float]]]] = None


    def __init__(
        self,
        tk_canvas: Optional[tk.Canvas] = None,
        price_data: Optional[List[List[Any]]] = None,
    ) -> None:
        self.price_data=price_data
        self._rsi_state = None
        self._adx_cache = None
        self._stoch_cache = None
        self._willr_cache = None
        self._sma_cache: Dict[Tuple[int, int], List[Optional[float]]] = {}
        self._bollinger_cache: Dict[Tuple[int, float, int], Tuple[
            List[Optional[float]], List[Optional[float]], List[Optional[float]]]] = {}
        pass

    def set_price_data(self, price_data: List[List[Any]]) -> None:
        self.price_data=price_data
        self._rsi_state = None
        self._adx_cache = None
        self._stoch_cache = None
        self._willr_cache = None
        self._sma_cache = {}
        self._bollinger_cache = {}

    def render_RSI(self, tk_indicators_canvas: tk.Canvas, divider_v: float,
                   offset_x: float = 0, start: int = 0,
                   tags: Tuple[str, ...] = (), fill: str = "black") -> None:
        values = [row[5]["rsi"] for row in self.price_data]
        self._draw_scaled_line(tk_indicators_canvas, values, divider_v, offset_x, start, tags, fill)

    def render_ADX(self, tk_indicators_canvas: tk.Canvas, divider_v: float,
                   offset_x: float = 0, start: int = 0,
                   tags: Tuple[str, ...] = (), fill: str = "black",
                   period: int = ADX_PERIOD) -> None:
        values = self.calculate_ADX(period)
        self._draw_scaled_line(tk_indicators_canvas, values, divider_v, offset_x, start, tags, fill)

    def render_STOCH(self, tk_indicators_canvas: tk.Canvas, divider_v: float,
                     offset_x: float = 0, start: int = 0,
                     tags: Tuple[str, ...] = (), fill: str = "black",
                     k_period: int = STOCH_K_PERIOD, d_period: int = STOCH_D_PERIOD) -> None:
        k_values, d_values = self.calculate_stochastic(k_period, d_period)
        self._draw_scaled_line(tk_indicators_canvas, k_values, divider_v, offset_x, start, tags, fill)
        # %D is dashed and kept out of the "ink" tag, so the theme does not recolor it.
        self._draw_scaled_line(tk_indicators_canvas, d_values, divider_v, offset_x, start,
                               ("stoch", "stoch_d"), STOCH_D_COLOR, dash=(4, 4))

    def _draw_scaled_line(self, tk_indicators_canvas: tk.Canvas, values: List[Optional[float]],
                          divider_v: float, offset_x: float, start: int,
                          tags: Tuple[str, ...], fill: str,
                          dash: Tuple[int, ...] = ()) -> None:
        """Draw a 0-100 series on the 100 pixel indicator canvas, skipping missing values."""
        options: Dict[str, Any] = {"dash": dash} if dash else {}
        previous = None
        for i in range(start - 1, -1, -1):
            if values[i] is not None:
                previous = (offset_x + divider_v * i, values[i])
                break

        for i in range(start, len(self.price_data)):
            pos = offset_x + divider_v*i

            if values[i] is not None:
                value = values[i]
                # Each segment ends at candle i, so it can be shown or hidden with that candle.
                segment_tags = tags + (f"ind_{i}",)

                if previous is None:
                    tk_indicators_canvas.create_line(offset_x, 100, pos, 100 - value, fill=fill, tags=segment_tags, **options)
                else:
                    tk_indicators_canvas.create_line(previous[0], 100 - previous[1], pos, 100 - value, fill=fill, tags=segment_tags, **options)

                previous = [pos, value]
        pass

    def calculate_ADX(self, period: int = ADX_PERIOD) -> List[Optional[float]]:
        """Return Wilder's ADX for every row, recomputed only when rows or the period change."""
        if self._adx_cache is not None and self._adx_cache[:2] == (len(self.price_data), (period,)):
            return self._adx_cache[2]
        highs = [row[HIGH_COLUMN] for row in self.price_data]
        lows = [row[LOW_COLUMN] for row in self.price_data]
        closes = [row[CLOSE_COLUMN] for row in self.price_data]
        values, _, _ = adx_components(highs, lows, closes, period)
        self._adx_cache = (len(self.price_data), (period,), values)
        return values

    def calculate_stochastic(
        self, k_period: int = STOCH_K_PERIOD, d_period: int = STOCH_D_PERIOD,
    ) -> Tuple[List[Optional[float]], List[Optional[float]]]:
        """Return (%K, %D) for every row, recomputed only when rows or the periods change."""
        key = (k_period, d_period)
        if self._stoch_cache is not None and self._stoch_cache[:2] == (len(self.price_data), key):
            return self._stoch_cache[2]
        highs = [row[HIGH_COLUMN] for row in self.price_data]
        lows = [row[LOW_COLUMN] for row in self.price_data]
        closes = [row[CLOSE_COLUMN] for row in self.price_data]
        values = stochastic_components(highs, lows, closes, k_period, d_period)
        self._stoch_cache = (len(self.price_data), key, values)
        return values

    def render_WILLR(self, tk_indicators_canvas: tk.Canvas, divider_v: float,
                     offset_x: float = 0, start: int = 0,
                     tags: Tuple[str, ...] = (), fill: str = "black",
                     period: int = WILLIAMS_R_PERIOD) -> None:
        values = [None if v is None else v + WILLIAMS_R_CANVAS_OFFSET
                  for v in self.calculate_williams_r(period)]
        self._draw_scaled_line(tk_indicators_canvas, values, divider_v, offset_x, start, tags, fill)

    def calculate_williams_r(self, period: int = WILLIAMS_R_PERIOD) -> List[Optional[float]]:
        """Return Williams %R for every row, recomputed only when rows or the period change."""
        if self._willr_cache is not None and self._willr_cache[:2] == (len(self.price_data), (period,)):
            return self._willr_cache[2]
        highs = [row[HIGH_COLUMN] for row in self.price_data]
        lows = [row[LOW_COLUMN] for row in self.price_data]
        closes = [row[CLOSE_COLUMN] for row in self.price_data]
        values = williams_r_values(highs, lows, closes, period)
        self._willr_cache = (len(self.price_data), (period,), values)
        return values

    def render_SMA(
        self, tk_canvas: tk.Canvas, period: int,
        x_for_index: Callable[[int], float], y_for_price: Callable[[float], float],
        fill: str = "black", dash: Tuple[int, ...] = (), width: int = 2,
        tags: Tuple[str, ...] = (), column: int = CLOSE_COLUMN,
        index_range: Optional[Tuple[int, int]] = None,
    ) -> List[int]:
        """Draw the SMA for ``period`` as polylines and return the line item ids.

        ``column`` selects the price field that is averaged. ``index_range`` limits the
        line to candles first..last inclusive.
        """
        return self.render_series(
            tk_canvas, self.calculate_SMA(period, column),
            x_for_index=x_for_index, y_for_price=y_for_price,
            fill=fill, dash=dash, width=width, tags=tags, index_range=index_range,
        )

    def render_series(
        self, tk_canvas: tk.Canvas, values: List[Optional[float]],
        x_for_index: Callable[[int], float], y_for_price: Callable[[float], float],
        fill: str = "black", dash: Tuple[int, ...] = (), width: int = 2,
        tags: Tuple[str, ...] = (), index_range: Optional[Tuple[int, int]] = None,
    ) -> List[int]:
        """Draw one value per row as polylines and return the line item ids.

        ``x_for_index`` and ``y_for_price`` map a row index and a price to canvas
        coordinates. ``None`` entries (the warm-up rows) break the line, and so do rows
        outside ``index_range`` (inclusive first and last) when it is given.
        """
        options: Dict[str, Any] = {"fill": fill, "width": width, "tags": tags}
        if dash:
            options["dash"] = dash
        items: List[int] = []
        run: List[float] = []
        for i, value in enumerate(values):
            outside = index_range is not None and not index_range[0] <= i <= index_range[1]
            if value is None or outside:
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

    def calculate_RSI_full(self, period: int = RSI_DEFAULT_PERIOD) -> None:
        """Recompute RSI for every row with a new period, clearing values from any earlier period."""
        for row in self.price_data:
            row[5]["rsi"] = None
        self._rsi_state = None
        self.calculate_RSI_incremental(period)

    def calculate_RSI_incremental(self, period: int = RSI_DEFAULT_PERIOD) -> None:
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