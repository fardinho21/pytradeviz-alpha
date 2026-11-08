
from __future__ import annotations

import tkinter as tk
from typing import List, Sequence, Tuple


class Candle:
    candle_width: int = 5
    cents_per_pixle: float = 0

    def __init__(
        self, open: float, high: float, low: float, close: float, date: float,
        dppx: float = 0, price_origin: float = 1000, tags: Tuple[str, ...] = (),
    ) -> None:
        self.open=open
        self.high=high
        self.low=low
        self.close=close
        self.color="grey"
        self.body="hollow"
        self.date=date
        self.cents_per_pixle=dppx
        self.tags = tags

        self.render_open=price_origin-(open)/dppx
        self.render_high=price_origin-(high)/dppx
        self.render_low=price_origin-(low)/dppx
        self.render_close=price_origin-(close)/dppx

        if open < close:
            self.color="green"
            self.body="solid"
        elif close < open:
            self.color="red"

        
    def get_body(self) -> str:
        return self.body
    def set_body(self, body: str) -> None:
        self.body=body

    def get_color(self) -> str:
        return self.color
    def set_color(self, color: str) -> None:
        self.color=color

    def get_ohlc(self) -> List[float]:
        return [self.open, self.high, self.low,  self.close]    
    def set_ohlc(self, ohlc_ary: Sequence[float]) -> None:
        self.open=ohlc_ary[0]
        self.high=ohlc_ary[1]
        self.low=ohlc_ary[2]
        self.close=ohlc_ary[3]

    """
    Draw the candle on a tkinter canvas
    """
    def draw_candle(self, tk_canvas: tk.Canvas) -> None:
        self.draw_high_low(tk_canvas)
        self.draw_open_close(tk_canvas, True)
        pass

    """
    Draw the high and low as a line
    """
    def draw_high_low(self, tk_canvas: tk.Canvas) -> None:
        tk_canvas.create_line(self.date, self.render_high, self.date, self.render_low, fill=self.color, width=3, tags=self.tags)
        pass

    """
    Draw open and close as a line 
    """
    def draw_open_close(self, tk_canvas: tk.Canvas, candle: bool = False) -> None:
        if candle:
            tk_canvas.create_rectangle(self.date - self.candle_width, self.render_open, self.date + self.candle_width, self.render_close, fill=self.color, tags=self.tags)
        else:
            tk_canvas.create_line(self.date, self.render_open, self.date, self.render_close, fill=self.color, width=3, tags=self.tags)

        pass