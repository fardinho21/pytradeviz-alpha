from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import csv
from types import ModuleType
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple
from candle import Candle
import datetime as datetime
import math
from indicators import Indicators


class PriceDataSource(Protocol):
    @property
    def has_more(self) -> bool: ...

    def load_next(self) -> List[List[Any]]: ...


class PyTradeViz:

    window_geo: str = "1020x750"
    window_min_width: int = 1020
    window_min_height: int = 750

    canvas_width: int = 900
    canvas_height: int = 500
    window_color: str = "black"
    light_theme: Dict[str, str] = {
        "canvas": "white", "ink": "black", "grid": "black",
        "crosshair": "black", "crosshair_text": "white",
        "selection": "#8c8c8c", "highlight": "#ffffff",
    }
    dark_theme: Dict[str, str] = {
        "canvas": "black", "ink": "white", "grid": "#4a4a4a",
        "crosshair": "#f4a261", "crosshair_text": "black",
        "selection": "#e0894f", "highlight": "#f4a261",
    }
    dark_mode: bool = False
    crosshair_root: Optional[Tuple[int, int]] = None
    price_limit: int = 3000
    price_data: Optional[List[List[Any]]] = None
    price_data_object: Optional[Dict[str, Any]] = None
    chart_grid_space_x: float = 15000 
    #TODO: calculate the chart_grid_space_y inside the init function
    #the value will be equal to the highest p
    chart_grid_space_y: float = 1000
    base_chart_height: int = 1000
    chart_grid_divider_v: int = 30
    chart_grid_divider_h: int = 20 #20px/price_level
    chart_padding_x: int = 60
    chart_layout_info: Dict[str, Any] = {}
    incrementer: float = 0
    min_zoom_level: float = 0.5
    max_zoom_level: float = 4.0
    zoom_step: float = 1.1
    min_candle_height_scale: float = 1.0
    max_candle_height_scale: float = 2.5

    window: tk.Tk
    canvas: tk.Canvas
    canvas_price: tk.Canvas
    canvas_date: tk.Canvas
    canvas_indicators: tk.Canvas
    frame_canvas: ttk.Frame
    frame_canvas_indicators: ttk.Frame
    frame_canvas_price: ttk.Frame
    frame_canvas_date: ttk.Frame
    scrollbar_horizontal: ttk.Scrollbar
    scrollbar_vertical: ttk.Scrollbar
    load_more_button: ttk.Button
    dark_mode_button: ttk.Button
    data_source: Optional[PriceDataSource]
    indicators_object: Indicators
    zoom_level: float
    candle_height_scale: float
    _scale_x: float
    _scale_y: float
    _base_chart_width: float
    _last_canvas_width: int
    _last_canvas_height: int
    price_upper: float
    price_lower: float
    _data_lowest: float
    _data_highest: float
    candle_info_label: tk.Label
    _press_position: Optional[Tuple[int, int]] = None
    click_drag_threshold: int = 5
    selection_mode: bool = False
    selected_indices: Set[int]
    # Box as (left x, right x, top price, bottom price). x is unscaled so the
    # box follows the candles through zoom and resize.
    _selection_box: Optional[Tuple[float, float, float, float]] = None
    _box_origin: Optional[Tuple[float, float]] = None
    _box_current: Optional[Tuple[float, float]] = None
    select_mode_label: tk.Label
    select_button: ttk.Button
    select_icon: Any
    select_label_y: int = 0

    def __init__(
        self, tk: ModuleType, ttk: ModuleType,
        price_data_object: Optional[Dict[str, Any]] = None,
        data_source: Optional[PriceDataSource] = None,
    ) -> None:

        self.price_data_object=price_data_object
        self.price_data=price_data_object["price_data"]
        self.selected_indices = set()
        self.data_source = data_source
        self.indicators_object = Indicators()
        self.indicators_object.set_price_data(self.price_data)
        self.indicators_object.calculate_RSI_incremental()

        self.calculate_grid_space_x(price_data_object)
        self._base_chart_width = self.chart_grid_space_x
        self.calculate_price_range()

        #set up window and frames
        self.initialize_window(tk)

        #set up frames
        self.initialize_frames(ttk)

        # set up canvas
        self.initialize_canvases(tk)
        self.initialize_candle_info(tk)

        # set up scrollbars
        self.initialize_scrollbars(ttk, tk)
        self.initialize_dark_mode_button(ttk)
        self.initialize_select_mode_button(ttk, tk)
        self.initialize_select_mode_label(tk)
        # configure
        self.configure_all_canvas()

        #layout manage
        self.configure_grid_layout()

        #render chart and price on canvas
        self.initialize_charts(self.price_data)

        #render candles
        self.render_candles()

        #render dates
        self.render_dates()

        self.render_indicators()

        self._last_canvas_width = self.canvas_width
        self._last_canvas_height = self.canvas_height
        self.zoom_level = 1.0
        self.candle_height_scale = 1.0
        self._scale_x = 1.0
        self._scale_y = 1.0

        #event bind scrolling to mouse dragging
        self.event_bindings()

        #set price data for indicators_objec 

    def initialize_window(self, tk: ModuleType) -> None:
        self.window = tk.Tk()
        self.window.configure(bg=self.window_color)
        self.window.title("PyTradeViz - Alpha")
        self.window.geometry(self.window_geo)
        self.window.minsize(self.window_min_width, self.window_min_height)
        self.window.resizable(True, True)

    def initialize_charts(self, price_data: Optional[List[List[Any]]] = None) -> None:

        ink = self.get_theme()["ink"]
        grid = self.get_theme()["grid"]
        for i in range(0, self.chart_grid_space_x, self.chart_grid_divider_v):
            #render vertical lines
            self.canvas_date.create_line(i, 0, i, 50, dash=(5, 5), fill=grid, tags=("grid",))
            self.canvas.create_line(i, 0, i, self.chart_grid_space_y, dash=(5, 5), fill=grid, tags=("grid",))
            self.canvas_indicators.create_line(i, 0, i, 100, dash=(5, 5), fill=grid, tags=("grid",))

        
        self.incrementer = (
            (self.price_upper - self.price_lower)
            * self.chart_grid_divider_h / self.chart_grid_space_y
        )
        price_level = self.price_upper

        for i in range(0, self.chart_grid_space_y, self.chart_grid_divider_h):
            #render horizontal lines 
            self.canvas.create_line(
                0, i, self.chart_grid_space_x, i, dash=(5, 5), fill=grid,
                tags=("horizontal_grid", "grid")
            )
            self.canvas_price.create_line(0, i, 100, i, dash=(5, 5), fill=grid, tags=("grid",))
            #render price levels
            plrender="{:.2f}".format(price_level)
            self.canvas_price.create_text(
                50, i, text=plrender, anchor="n" if i == 0 else "center",
                fill=ink, tags=("price_label", "ink")
            )
            price_level-=self.incrementer

        self.canvas_indicators.create_line(
            0, 70, self.chart_grid_space_x, 70, fill="orange", width=2,
            tags=("indicator_level",)
        )
        self.canvas_indicators.create_line(
            0, 30, self.chart_grid_space_x, 30, fill="blue", width=2,
            tags=("indicator_level",)
        )
        
    def initialize_canvases(self, tk: ModuleType) -> None:
        self.canvas= tk.Canvas(self.frame_canvas, width=self.canvas_width, height=self.canvas_height)
        self.canvas_price= tk.Canvas(self.frame_canvas_price, width=100, height=500)
        self.canvas_date = tk.Canvas(self.frame_canvas_date, width=self.canvas_width, height=50)
        self.canvas_indicators= tk.Canvas(self.frame_canvas_indicators, width=self.canvas_width, height=100)

    def initialize_scrollbars(self, ttk: ModuleType, tk: ModuleType) -> None:
        self.scrollbar_horizontal = ttk.Scrollbar(
            self.window, orient=tk.HORIZONTAL, command=self.scroll_xview
        )
        self.scrollbar_vertical = ttk.Scrollbar(
            self.window, orient=tk.VERTICAL, command=self.scroll_yview
        )
        self.load_more_button = ttk.Button(
            self.window, text=">", width=1, command=self.load_more_data
        )
        if self.data_source is None or not self.data_source.has_more:
            self.load_more_button.state(["disabled"])

    def initialize_frames(self, ttk: ModuleType) -> None:
        self.frame_canvas = ttk.Frame(self.window, width=self.canvas_width, height=self.canvas_height)
        self.frame_canvas_indicators = ttk.Frame(self.window, width=self.canvas_width, height=100)
        self.frame_canvas_price = ttk.Frame(self.window, width=100, height=500)
        self.frame_canvas_date = ttk.Frame(self.window, width=self.canvas_width, height=50)

    def configure_all_canvas(self) -> None:
        self.canvas.configure(background=self.get_theme()["canvas"])
        self.canvas_price.configure(background=self.get_theme()["canvas"])
        self.canvas_date.configure(background=self.get_theme()["canvas"])
        self.canvas_indicators.configure(background=self.get_theme()["canvas"])
        self.canvas.configure(
            scrollregion=(0, 0, self.chart_grid_space_x, self.chart_grid_space_y),
            xscrollcommand=self.sync_horizontal_scroll,
            yscrollcommand=self.sync_vertical_scroll,
        )
        self.canvas_price.configure(scrollregion=(0, 0, 100, self.chart_grid_space_y))
        self.canvas_date.configure(scrollregion=(0, 0, self.chart_grid_space_x, 50))
        self.canvas_indicators.configure(
            scrollregion=(0, 0, self.chart_grid_space_x, 100)
        )

    def update_scroll_regions(self) -> None:
        self.canvas.configure(
            scrollregion=(
                0, 0, self.chart_grid_space_x, self.chart_grid_space_y
            )
        )
        self.canvas_price.configure(
            scrollregion=(0, 0, 100, self.chart_grid_space_y)
        )
        self.canvas_date.configure(
            scrollregion=(0, 0, self.chart_grid_space_x, 50)
        )
        self.canvas_indicators.configure(
            scrollregion=(0, 0, self.chart_grid_space_x, 100)
        )

    def configure_grid_layout(self) -> None:
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)
        self.frame_canvas.grid_columnconfigure(0, weight=1)
        self.frame_canvas.grid_rowconfigure(0, weight=1)
        self.frame_canvas_price.grid_columnconfigure(0, weight=1)
        self.frame_canvas_price.grid_rowconfigure(0, weight=1)
        self.frame_canvas_date.grid_columnconfigure(0, weight=1)
        self.frame_canvas_indicators.grid_columnconfigure(0, weight=1)

        self.frame_canvas.grid(row=0, column=0, sticky="nsew")
        self.frame_canvas_price.grid(row=0, column=1, sticky="ns")
        self.frame_canvas_date.grid(row=1, column=0, sticky="ew")
        self.frame_canvas_indicators.grid(row=2, column=0, sticky="ew")
        self.scrollbar_horizontal.grid(row=3, column=0, sticky="ew")
        self.load_more_button.grid(row=2, column=1, sticky="nsw")
        self.select_button.grid(row=3, column=1, sticky="nsw")
        self.dark_mode_button.grid(row=1, column=1, sticky="nsw")
        self.scrollbar_vertical.grid(row=0, column=2, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_price.grid(row=0, column=0, sticky="nsew")
        self.canvas_date.grid(row=0, column=0, sticky="ew")
        self.canvas_indicators.grid(row=0, column=0, sticky="ew")

    def render_candles(self, start: int = 0, tags: Tuple[str, ...] = ()) -> None:
        price_per_pixel = (self.price_upper - self.price_lower) / self.base_chart_height
        for i in range(start, len(self.price_data)):
            pd=self.price_data[i]
            c=Candle(
                pd[1], pd[2], pd[3], pd[4],
                self.chart_padding_x + i*self.chart_grid_divider_v,
                price_per_pixel, self.price_upper / price_per_pixel,
                tags=("candle", f"candle_{i}") + tags
            )
            c.draw_candle(self.canvas, hollow=self.dark_mode)

    def render_indicators(self, start: int = 0, tags: Tuple[str, ...] = ()) -> None:
        self.indicators_object.render_RSI(
            self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
            start=start, tags=("rsi", "ink") + tags, fill=self.get_theme()["ink"]
        )
        pass

    def calculate_grid_space_x(self, price_data_object: Dict[str, Any]) -> None:
        num_of_candles = len(price_data_object["price_data"])
        rendered_width = (
            max(0, num_of_candles - 1) * self.chart_grid_divider_v
            + 2 * self.chart_padding_x
        )
        self.chart_grid_space_x = max(self.canvas_width, rendered_width)

    def calculate_price_range(self, new_rows: Optional[List[List[Any]]] = None) -> None:
        rows = self.price_data if new_rows is None else new_rows
        prices = [price for row in rows for price in row[1:5]]
        lowest = min(prices)
        highest = max(prices)
        if new_rows is not None:
            lowest = min(lowest, self._data_lowest)
            highest = max(highest, self._data_highest)
        self._data_lowest = lowest
        self._data_highest = highest
        margin = max((highest - lowest) * 0.05, abs(highest) * 0.01, 0.01)
        self.price_upper = max(1.60, highest + margin)
        self.price_lower = min(0, lowest - margin)

    def calculate_(self) -> None:
        pass

    def render_dates(self, start: int = 0, tags: Tuple[str, ...] = ()) -> None:
        ink = self.get_theme()["ink"]
        y = self.price_data[start - 1][0][0] if start else ""
        m = self.price_data[start - 1][0][1] if start else ""
        for i in range(start, len(self.price_data)):

            iy = self.price_data[i][0][0]
            im = self.price_data[i][0][1]
            id = self.price_data[i][0][2]
            
            if im != str(m) or iy != str(y):
                m = im
                m_name = datetime.datetime.strptime(str(m), "%m").strftime("%b")

                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 10, text=m_name, fill=ink, tags=("ink",) + tags)
            if iy != str(y):
                y = iy
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text="Y"+str(iy)[2:], fill=ink, tags=("ink",) + tags)
            else:
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text=str(id), fill=ink, tags=("ink",) + tags)
        pass

    def get_window(self) -> tk.Tk:
        return self.window

    def get_theme(self) -> Dict[str, str]:
        return self.dark_theme if self.dark_mode else self.light_theme

    def initialize_dark_mode_button(self, ttk: ModuleType) -> None:
        self.dark_mode_button = ttk.Button(
            self.window, text="☀" if self.dark_mode else "☾", width=1,
            command=self.toggle_dark_mode,
        )

    def initialize_select_mode_button(self, ttk: ModuleType, tk: ModuleType) -> None:
        # Black in both themes, matching the other button icons.
        self.select_icon = self.make_candle_group_icon(tk, self.light_theme["ink"])
        self.select_button = ttk.Button(
            self.window, image=self.select_icon,
            command=self.toggle_selection_mode,
        )

    def make_candle_group_icon(self, tk: ModuleType, ink: str) -> Any:
        icon = tk.PhotoImage(master=self.window, width=18, height=18)
        # (center x, wick top, wick bottom, body top, body bottom)
        for cx, wick_top, wick_bottom, body_top, body_bottom in (
            (4, 2, 16, 6, 12), (9, 1, 17, 4, 10), (14, 4, 14, 7, 13)
        ):
            icon.put(ink, to=(cx, wick_top, cx + 1, wick_bottom + 1))
            icon.put(ink, to=(cx - 1, body_top, cx + 2, body_bottom + 1))
        return icon

    def initialize_select_mode_label(self, tk: ModuleType) -> None:
        theme = self.get_theme()
        self.select_mode_label = tk.Label(
            self.frame_canvas, text="select mode enabled", justify="left",
            anchor="w", bg=theme["canvas"], fg=theme["ink"], relief="solid",
            bd=1, padx=6, pady=4,
        )
        self.select_mode_label.place_forget()
        # Sit just below the OHLC box, which always has the same height.
        self.candle_info_label.configure(text="x\nO: 0\nH: 0\nL: 0\nC: 0")
        self.candle_info_label.update_idletasks()
        self.select_label_y = 8 + self.candle_info_label.winfo_reqheight() + 8

    def toggle_selection_mode(self) -> None:
        self.selection_mode = not self.selection_mode
        if self.selection_mode:
            self.select_mode_label.place(
                relx=1.0, x=-8, y=self.select_label_y, anchor="ne"
            )
            self.select_mode_label.lift()
            self.select_button.state(["pressed"])
        else:
            self.select_mode_label.place_forget()
            self.select_button.state(["!pressed"])
            self._box_origin = None
            if self.selected_indices or self._selection_box is not None:
                self.set_selection(set(), None)

    def toggle_dark_mode(self) -> None:
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self) -> None:
        theme = self.get_theme()
        for canvas in (
            self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators
        ):
            canvas.configure(background=theme["canvas"])
            canvas.itemconfigure("ink", fill=theme["ink"])
            canvas.itemconfigure("grid", fill=theme["grid"])
        self.restyle_candles()
        self.candle_info_label.configure(bg=theme["canvas"], fg=theme["ink"])
        self.select_mode_label.configure(bg=theme["canvas"], fg=theme["ink"])
        self.dark_mode_button.configure(text="☀" if self.dark_mode else "☾")
        self.draw_overlays()

    def load_more_data(self) -> None:
        if self.data_source is None or not self.data_source.has_more:
            return

        old_count = len(self.price_data)
        try:
            new_rows = self.data_source.load_next()
        except (csv.Error, OSError, ValueError) as error:
            messagebox.showerror("Unable to load price data", str(error), parent=self.window)
            return
        if not new_rows:
            self.load_more_button.state(["disabled"])
            return

        old_width = self.chart_grid_space_x
        old_base_width = self._base_chart_width
        old_left = self.canvas.xview()[0] * old_width
        old_top = self.canvas.yview()[0] * self.chart_grid_space_y
        old_upper, old_lower = self.price_upper, self.price_lower

        self.price_data.extend(new_rows)
        self.indicators_object.calculate_RSI_incremental()
        self.calculate_price_range(new_rows)
        self.price_upper = max(old_upper, self.price_upper)
        self.price_lower = min(old_lower, self.price_lower)
        old_span = old_upper - old_lower
        new_span = self.price_upper - self.price_lower
        ratio = old_span / new_span
        shift = self.chart_grid_space_y * (self.price_upper - old_upper) / new_span
        if ratio != 1 or shift != 0:
            self.canvas.scale("candle", 0, 0, 1, ratio)
            self.canvas.move("candle", 0, shift)
            labels = self.canvas_price.find_withtag("price_label")
            for index, item in enumerate(labels):
                level = self.price_upper - (
                    index * new_span * self.chart_grid_divider_h / self.base_chart_height
                )
                self.canvas_price.itemconfigure(item, text="{:.2f}".format(level))

        self.calculate_grid_space_x(self.price_data_object)
        new_base_width = self.chart_grid_space_x
        self._base_chart_width = new_base_width
        self.chart_grid_space_x *= self._scale_x
        start_grid = math.ceil(old_base_width / self.chart_grid_divider_v)
        grid = self.get_theme()["grid"]
        for i in range(
            start_grid * self.chart_grid_divider_v,
            new_base_width, self.chart_grid_divider_v
        ):
            self.canvas.create_line(
                i, 0, i, self.base_chart_height, dash=(5, 5), fill=grid,
                tags=("new_page", "grid")
            )
            self.canvas_date.create_line(
                i, 0, i, 50, dash=(5, 5), fill=grid, tags=("new_page", "grid")
            )
            self.canvas_indicators.create_line(
                i, 0, i, 100, dash=(5, 5), fill=grid, tags=("new_page", "grid")
            )

        self.render_candles(old_count, tags=("new_page",))
        self.render_dates(old_count, tags=("new_page",))
        indicator_start = old_count if old_count >= 7 else 6
        self.render_indicators(indicator_start, tags=("new_page",))
        for canvas, sx, sy in (
            (self.canvas, self._scale_x, self._scale_y),
            (self.canvas_date, self._scale_x, 1),
            (self.canvas_indicators, self._scale_x, 1),
        ):
            canvas.scale("new_page", 0, 0, sx, sy)
            canvas.dtag("new_page", "new_page")
        for canvas, tag in (
            (self.canvas, "horizontal_grid"),
            (self.canvas_indicators, "indicator_level"),
        ):
            for item in canvas.find_withtag(tag):
                x1, y1, _, y2 = canvas.coords(item)
                canvas.coords(item, x1, y1, self.chart_grid_space_x, y2)

        self.update_scroll_regions()
        self.canvas.xview_moveto(old_left / self.chart_grid_space_x)
        self.canvas.yview_moveto(
            max(0, (old_top * ratio + shift) / self.chart_grid_space_y)
        )
        if not self.data_source.has_more:
            self.load_more_button.state(["disabled"])
        self.draw_overlays()
        
    def get_canvas(self) -> tk.Canvas:
        return self.canvas
        pass

    def scroll_xview(self, *args: str) -> None:
        self.canvas.xview(*args)

    def scroll_yview(self, *args: str) -> None:
        self.canvas.yview(*args)

    def sync_horizontal_scroll(self, first: float, last: float) -> None:
        self.scrollbar_horizontal.set(first, last)
        self.canvas_date.xview_moveto(first)
        self.canvas_indicators.xview_moveto(first)
        self.draw_overlays()

    def sync_vertical_scroll(self, first: float, last: float) -> None:
        self.scrollbar_vertical.set(first, last)
        self.canvas_price.yview_moveto(first)
        self.draw_overlays()

    def scroll_start(self, event: tk.Event) -> None:
        self._press_position = (event.x, event.y)
        if self.selection_mode:
            if event.widget is self.canvas:
                self._box_origin = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
                self._box_current = self._box_origin
            return
        if event.widget is self.canvas:
            self.canvas.scan_mark(event.x, event.y)
        elif event.widget is self.canvas_price:
            self.canvas.scan_mark(0, event.y)
        else:
            self.canvas.scan_mark(event.x, 0)

    def scroll_move(self, event: tk.Event) -> None:
        self.crosshair_root = (event.x_root, event.y_root)
        if self.selection_mode:
            if self._box_origin is not None:
                self._box_current = (
                    self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
                )
                self._selection_box = self.box_from_canvas(
                    self._box_origin, self._box_current
                )
                self.draw_overlays()
            return
        if event.widget is self.canvas:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
        elif event.widget is self.canvas_price:
            self.canvas.scan_dragto(0, event.y, gain=1)
        else:
            self.canvas.scan_dragto(event.x, 0, gain=1)
        self.draw_crosshair()

    def initialize_candle_info(self, tk: ModuleType) -> None:
        self.candle_info_label = tk.Label(
            self.frame_canvas, justify="left", anchor="w",
            bg=self.get_theme()["canvas"], fg=self.get_theme()["ink"],
            relief="solid", bd=1, padx=6, pady=4,
        )
        self.candle_info_label.place_forget()

    def candle_index_at(self, x: float, y: float, tolerance: int = 4) -> Optional[int]:
        for item in self.canvas.find_overlapping(
            x - tolerance, y - tolerance, x + tolerance, y + tolerance
        ):
            for tag in self.canvas.gettags(item):
                if tag.startswith("candle_"):
                    return int(tag[len("candle_"):])
        return None

    def show_candle_info(self, index: int) -> None:
        date, open_, high, low, close = self.price_data[index][:5]
        self.candle_info_label.config(
            text=f"{'-'.join(date)}\nO: {open_}\nH: {high}\nL: {low}\nC: {close}"
        )
        self.candle_info_label.place(relx=1.0, x=-8, y=8, anchor="ne")
        self.candle_info_label.lift()

    def select_candle(self, event: tk.Event) -> None:
        if self.selection_mode:
            self.finish_box_select(event)
            return
        if self._press_position is None:
            return
        press_x, press_y = self._press_position
        if abs(event.x - press_x) + abs(event.y - press_y) > self.click_drag_threshold:
            return
        index = self.candle_index_at(
            self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        )
        if index is not None:
            self.show_candle_info(index)

    def track_crosshair(self, event: tk.Event) -> None:
        self.crosshair_root = (event.x_root, event.y_root)
        self.draw_crosshair()

    def hide_crosshair(self, _event: tk.Event) -> None:
        self.crosshair_root = None
        self.clear_crosshair()

    def clear_crosshair(self) -> None:
        for canvas in (
            self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators
        ):
            canvas.delete("crosshair")

    def cursor_in_x_range(self, canvas: tk.Canvas, root_x: int) -> bool:
        return 0 <= root_x - canvas.winfo_rootx() < canvas.winfo_width()

    def cursor_in_y_range(self, canvas: tk.Canvas, root_y: int) -> bool:
        return 0 <= root_y - canvas.winfo_rooty() < canvas.winfo_height()

    def date_index_at(self, chart_x: float) -> Optional[int]:
        base_x = chart_x / self._scale_x
        index = round((base_x - self.chart_padding_x) / self.chart_grid_divider_v)
        return index if 0 <= index < len(self.price_data) else None

    def price_at(self, chart_y: float) -> float:
        span = self.price_upper - self.price_lower
        return self.price_upper - chart_y * span / self.chart_grid_space_y

    def draw_crosshair_label(
        self, canvas: tk.Canvas, x: float, y: float, text: str, anchor: str,
        fill: str, text_fill: str,
    ) -> None:
        label = canvas.create_text(
            x, y, text=text, anchor=anchor, fill=text_fill, tags=("crosshair",)
        )
        x1, y1, x2, y2 = canvas.bbox(label)
        box = canvas.create_rectangle(
            x1 - 3, y1 - 2, x2 + 3, y2 + 2, fill=fill, outline=fill,
            tags=("crosshair",),
        )
        canvas.tag_raise(label, box)

    def draw_crosshair(self) -> None:
        if self.crosshair_root is None or not self.price_data:
            return
        self.clear_crosshair()

        theme = self.get_theme()
        line_color, text_color = theme["crosshair"], theme["crosshair_text"]
        root_x, root_y = self.crosshair_root
        show_vertical = self.cursor_in_x_range(self.canvas, root_x)
        show_horizontal = self.cursor_in_y_range(self.canvas, root_y)
        if not show_vertical and not show_horizontal:
            return

        chart_x = self.canvas.canvasx(root_x - self.canvas.winfo_rootx())
        chart_y = self.canvas.canvasy(root_y - self.canvas.winfo_rooty())

        if show_vertical:
            for canvas in (self.canvas, self.canvas_date, self.canvas_indicators):
                x = canvas.canvasx(root_x - canvas.winfo_rootx())
                canvas.create_line(
                    x, canvas.canvasy(0), x, canvas.canvasy(canvas.winfo_height()),
                    fill=line_color, width=1, tags=("crosshair",),
                )
        if show_horizontal:
            self.canvas.create_line(
                self.canvas.canvasx(0), chart_y,
                self.canvas.canvasx(self.canvas.winfo_width()), chart_y,
                fill=line_color, width=1, tags=("crosshair",),
            )
            price_y = self.canvas_price.canvasy(
                root_y - self.canvas_price.winfo_rooty()
            )
            self.canvas_price.create_line(
                self.canvas_price.canvasx(0), price_y,
                self.canvas_price.canvasx(self.canvas_price.winfo_width()), price_y,
                fill=line_color, width=1, tags=("crosshair",),
            )
            self.draw_crosshair_label(
                self.canvas_price,
                self.canvas_price.canvasx(self.canvas_price.winfo_width()) - 2,
                price_y, f"{self.price_at(chart_y):.2f}", "e",
                line_color, text_color,
            )

        if show_vertical:
            index = self.date_index_at(chart_x)
            if index is not None:
                date = "-".join(self.price_data[index][0])
                self.draw_crosshair_label(
                    self.canvas, chart_x, self.canvas.canvasy(0) + 4,
                    date, "n", line_color, text_color,
                )

    def blend_colors(self, first: str, second: str, amount: float) -> str:
        first_rgb = [c >> 8 for c in self.window.winfo_rgb(first)]
        second_rgb = [c >> 8 for c in self.window.winfo_rgb(second)]
        mixed = [round(a * (1 - amount) + b * amount) for a, b in zip(first_rgb, second_rgb)]
        return "#%02x%02x%02x" % tuple(mixed)

    def highlight_color(self, base: str) -> str:
        return self.blend_colors(base, self.get_theme()["highlight"], 0.5)

    def candle_index_of(self, item: int) -> Optional[int]:
        for tag in self.canvas.gettags(item):
            if tag.startswith("candle_"):
                return int(tag[len("candle_"):])
        return None

    def style_candle_item(self, item: int, index: int) -> None:
        _, open_, _, _, close = self.price_data[index][:5]
        color = Candle.color_for(open_, close)
        if index in self.selected_indices:
            color = self.highlight_color(color)
        if self.canvas.type(item) == "rectangle":
            Candle.style_body(self.canvas, item, self.dark_mode, color)
        else:
            self.canvas.itemconfigure(item, fill=color)

    def restyle_candles(self, indices: Optional[Set[int]] = None) -> None:
        for item in self.canvas.find_withtag("candle"):
            index = self.candle_index_of(item)
            if index is None or (indices is not None and index not in indices):
                continue
            self.style_candle_item(item, index)

    def price_to_y(self, price: float) -> float:
        span = self.price_upper - self.price_lower
        return (self.price_upper - price) * self.chart_grid_space_y / span

    def box_from_canvas(
        self, first: Tuple[float, float], second: Tuple[float, float]
    ) -> Tuple[float, float, float, float]:
        x1, x2 = sorted((first[0], second[0]))
        y1, y2 = sorted((first[1], second[1]))
        return (x1 / self._scale_x, x2 / self._scale_x,
                self.price_at(y1), self.price_at(y2))

    def clear_selection_box(self) -> None:
        self.canvas.delete("selection")

    def draw_selection_box(self) -> None:
        if self._selection_box is None:
            return
        self.clear_selection_box()
        left, right, top, bottom = self._selection_box
        color = self.get_theme()["selection"]
        self.canvas.create_rectangle(
            left * self._scale_x, self.price_to_y(top),
            right * self._scale_x, self.price_to_y(bottom),
            fill=color, stipple="gray50", outline=color, dash=(4, 4), width=1,
            tags=("selection",),
        )
        # Keep the tint under the candles so their highlight colors stay visible.
        if self.canvas.find_withtag("candle"):
            self.canvas.tag_lower("selection", "candle")

    def draw_overlays(self) -> None:
        self.draw_selection_box()
        self.draw_crosshair()

    def candle_indices_in(self, x1: float, y1: float, x2: float, y2: float) -> Set[int]:
        indices: Set[int] = set()
        for item in self.canvas.find_overlapping(x1, y1, x2, y2):
            index = self.candle_index_of(item)
            if index is not None:
                indices.add(index)
        return indices

    def finish_box_select(self, event: tk.Event) -> None:
        origin = self._box_origin
        self._box_origin = None
        if origin is None or self._press_position is None:
            return
        press_x, press_y = self._press_position
        if abs(event.x - press_x) + abs(event.y - press_y) <= self.click_drag_threshold:
            index = self.candle_index_at(*origin)
            self.set_selection({index} if index is not None else set(), None)
            return
        current = self._box_current or origin
        x1, x2 = sorted((origin[0], current[0]))
        y1, y2 = sorted((origin[1], current[1]))
        self.set_selection(
            self.candle_indices_in(x1, y1, x2, y2),
            self.box_from_canvas(origin, current),
        )

    def set_selection(self, indices: Set[int], box: Optional[Tuple[float, float, float, float]]) -> None:
        changed = self.selected_indices ^ indices
        self.selected_indices = set(indices)
        self._selection_box = box
        self.restyle_candles(changed)
        self.clear_selection_box()
        self.draw_overlays()
        if self.selected_indices:
            self.show_selection_summary()
        else:
            self.candle_info_label.place_forget()

    def show_selection_summary(self) -> None:
        indices = sorted(self.selected_indices)
        rows = [self.price_data[i] for i in indices]
        count = len(rows)
        averages = [round(sum(row[k] for row in rows) / count, 4) for k in (1, 2, 3, 4)]
        first_date = "-".join(rows[0][0])
        if count == 1:
            header = first_date
        else:
            header = f"{first_date} to {'-'.join(rows[-1][0])} ({count} candles)"
        open_, high, low, close = averages
        self.candle_info_label.config(
            text=f"{header}\nO_avg: {open_}\nH_avg: {high}\nL_avg: {low}\nC_avg: {close}"
        )
        self.candle_info_label.place(relx=1.0, x=-8, y=8, anchor="ne")
        self.candle_info_label.lift()

    def event_bindings(self) -> None:
        self.canvas.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas.bind("<ButtonRelease-1>", self.select_candle)
        self.canvas.bind("<B1-Motion>", self.scroll_move)
        self.canvas.bind("<Configure>", self.resize_chart)
        self.canvas.bind("<Control-MouseWheel>", self.zoom_chart)
        self.canvas.bind("<Control-Button-4>", self.zoom_chart)
        self.canvas.bind("<Control-Button-5>", self.zoom_chart)
        self.canvas_price.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_price.bind("<B1-Motion>", self.scroll_move)
        self.canvas_price.bind("<Control-MouseWheel>", self.zoom_chart)
        self.canvas_price.bind("<Control-Button-4>", self.zoom_chart)
        self.canvas_price.bind("<Control-Button-5>", self.zoom_chart)
        self.canvas_date.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_date.bind("<B1-Motion>", self.scroll_move)
        self.canvas_date.bind("<Control-MouseWheel>", self.zoom_chart)
        self.canvas_date.bind("<Control-Button-4>", self.zoom_chart)
        self.canvas_date.bind("<Control-Button-5>", self.zoom_chart)
        self.canvas_indicators.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_indicators.bind("<B1-Motion>", self.scroll_move)
        self.canvas_indicators.bind("<Control-MouseWheel>", self.zoom_chart)
        self.canvas_indicators.bind("<Control-Button-4>", self.zoom_chart)
        self.canvas_indicators.bind("<Control-Button-5>", self.zoom_chart)
        for canvas in (
            self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators
        ):
            canvas.bind("<Shift-MouseWheel>", self.scale_candle_height)
            canvas.bind("<Shift-Button-4>", self.scale_candle_height)
            canvas.bind("<Shift-Button-5>", self.scale_candle_height)
            canvas.bind("<Motion>", self.track_crosshair)
            canvas.bind("<Leave>", self.hide_crosshair)

    def resize_chart(self, event: tk.Event) -> None:
        width = event.width
        height = event.height
        if width <= 1 or height <= 1:
            return

        scale_x = width / self._last_canvas_width
        scale_y = height / self._last_canvas_height
        if scale_x == 1 and scale_y == 1:
            return

        horizontal_position = self.canvas.xview()[0]
        vertical_position = self.canvas.yview()[0]

        self.canvas.scale("all", 0, 0, scale_x, scale_y)
        self.canvas_price.scale("all", 0, 0, 1, scale_y)
        self.canvas_date.scale("all", 0, 0, scale_x, 1)
        self.canvas_indicators.scale("all", 0, 0, scale_x, 1)

        self._last_canvas_width = width
        self._last_canvas_height = height
        self._scale_x *= scale_x
        self._scale_y *= scale_y
        self.chart_grid_space_x *= scale_x
        self.chart_grid_space_y *= scale_y

        self.update_scroll_regions()

        self.canvas.xview_moveto(horizontal_position)
        self.canvas.yview_moveto(vertical_position)
        self.draw_overlays()

    def wheel_scale_factor(self, event: tk.Event) -> Optional[float]:
        if hasattr(event, "delta") and event.delta:
            return self.zoom_step if event.delta > 0 else 1 / self.zoom_step
        if hasattr(event, "num") and event.num in (4, 5):
            return self.zoom_step if event.num == 4 else 1 / self.zoom_step
        return None

    def scale_candle_height(self, event: tk.Event) -> str:
        factor = self.wheel_scale_factor(event)
        if factor is None:
            return "break"

        new_scale = max(
            self.min_candle_height_scale,
            min(self.max_candle_height_scale, self.candle_height_scale * factor),
        )
        factor = new_scale / self.candle_height_scale
        if factor == 1:
            return "break"

        if event.widget is self.canvas:
            anchor_y = self.canvas.canvasy(event.y)
        elif event.widget is self.canvas_price:
            anchor_y = self.canvas_price.canvasy(event.y)
        else:
            anchor_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)

        old_top = self.canvas.yview()[0] * self.chart_grid_space_y
        new_top = anchor_y * factor - (anchor_y - old_top)

        self.canvas.scale("all", 0, 0, 1, factor)
        self.canvas_price.scale("all", 0, 0, 1, factor)
        self.chart_grid_space_y *= factor
        self._scale_y *= factor
        self.candle_height_scale = new_scale
        self.update_scroll_regions()
        self.canvas.yview_moveto(max(0, new_top / self.chart_grid_space_y))
        self.draw_overlays()
        return "break"

    def zoom_chart(self, event: tk.Event) -> str:
        zoom_factor = self.wheel_scale_factor(event)
        if zoom_factor is None:
            return "break"

        next_zoom_level = self.zoom_level * zoom_factor
        if next_zoom_level < self.min_zoom_level:
            zoom_factor = self.min_zoom_level / self.zoom_level
            next_zoom_level = self.min_zoom_level
        elif next_zoom_level > self.max_zoom_level:
            zoom_factor = self.max_zoom_level / self.zoom_level
            next_zoom_level = self.max_zoom_level

        if zoom_factor == 1:
            return "break"

        anchor_x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        anchor_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)

        if event.widget is self.canvas:
            anchor_x = self.canvas.canvasx(event.x)
            anchor_y = self.canvas.canvasy(event.y)
        elif event.widget is self.canvas_price:
            anchor_y = self.canvas_price.canvasy(event.y)
        elif event.widget is self.canvas_date:
            anchor_x = self.canvas_date.canvasx(event.x)
        elif event.widget is self.canvas_indicators:
            anchor_x = self.canvas_indicators.canvasx(event.x)

        old_left = self.canvas.xview()[0] * self.chart_grid_space_x
        old_top = self.canvas.yview()[0] * self.chart_grid_space_y
        new_left = anchor_x * zoom_factor - (anchor_x - old_left)
        new_top = anchor_y * zoom_factor - (anchor_y - old_top)

        self.canvas.scale("all", 0, 0, zoom_factor, zoom_factor)
        self.canvas_price.scale("all", 0, 0, 1, zoom_factor)
        self.canvas_date.scale("all", 0, 0, zoom_factor, 1)
        self.canvas_indicators.scale("all", 0, 0, zoom_factor, 1)

        self.chart_grid_space_x *= zoom_factor
        self.chart_grid_space_y *= zoom_factor
        self._scale_x *= zoom_factor
        self._scale_y *= zoom_factor
        self.zoom_level = next_zoom_level
        self.update_scroll_regions()
        self.canvas.xview_moveto(max(0, new_left / self.chart_grid_space_x))
        self.canvas.yview_moveto(max(0, new_top / self.chart_grid_space_y))
        self.draw_overlays()
        return "break"