
from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple

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
        pass

    def set_price_data(self, price_data: List[List[Any]]) -> None:
        self.price_data=price_data
        self._rsi_state = None

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

    def render_SMA(self) -> None:
        pass

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

    def calculate_SMA(self, period: int = 7) -> None:
        pass

    def calculate_EMA(self, period: int = 7) -> None:
        pass