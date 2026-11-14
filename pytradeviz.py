from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
import csv
import itertools
import os
import platform
from types import ModuleType
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple
from candle import Candle
import datetime as datetime
import math
from indicators import (
    Indicators, SMA_PERIODS, HIGH_COLUMN, LOW_COLUMN, RSI_OVERBOUGHT, RSI_OVERSOLD,
    band_intersects, rsi_crosses_level,
)
from breakout import (
    ATR_REJECTION, HORIZONS, REJECTION_RULES, BreakoutStudy, Odds,
)
from levels_help import LEVELS_HELP
from levels import (
    RESISTANCE, SUPPORT, WINDOW_LOOKBACKS, LevelFinder, LevelSettings, Segment,
)
from labeled_selections import (
    EXPORT_DIRECTORY, MOVING_AVERAGE_FIELDS, Selections, export_path, merge_selections,
    read_selections, write_selections,
)
from paginated_price_data import PaginatedPriceData

DATA_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def odds_text(odds: Optional[Odds]) -> str:
    """Short breakout odds, such as ``38% n=24``, or ``n=4 (too few)`` below the sample minimum."""
    if odds is None:
        return "n/a"
    if not odds.reliable:
        return f"n={odds.samples} (too few)"
    return f"{odds.probability:.0%} n={odds.samples}"


class PriceDataSource(Protocol):
    @property
    def has_more(self) -> bool: ...

    @property
    def ticker(self) -> Optional[str]: ...

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
        "gain": "#1a7f37", "loss": "#cf222e",
    }
    dark_theme: Dict[str, str] = {
        "canvas": "black", "ink": "white", "grid": "#4a4a4a",
        "crosshair": "#f4a261", "crosshair_text": "black",
        "selection": "#e0894f", "highlight": "#f4a261",
        "gain": "#3fb950", "loss": "#ff7b72",
    }
    # Simple moving average line styles and colors, keyed by the radio button labels.
    sma_line_styles: Dict[str, Tuple[int, ...]] = {
        "Dotted": (3, 3), "Dashed": (6, 4), "Solid": (),
    }
    sma_line_widths: Dict[str, int] = {
        "Dotted": 3, "Dashed": 2, "Solid": 2,
    }
    sma_colors: Dict[str, str] = {
        "Red": "#e53935", "Blue": "#1e88e5", "Orange": "#fb8c00",
        "Green": "#43a047", "Violet": "#8e24aa",
    }
    sma_default_colors: Dict[int, str] = {3: "Red", 7: "Blue", 14: "Orange", 30: "Violet"}
    levels_default_colors: Dict[str, str] = {
        "2W": "Red", "1M": "Blue", "2M": "Orange", "3M": "Green", "6M": "Violet",
    }
    # Half the width and height of a level marker triangle, in pixels.
    levels_marker_radius: int = 5
    levels_styles: Tuple[str, ...] = ("Triangles", "Lines", "Wavy")
    levels_default_style: str = "Triangles"
    # Zigzag and wave geometry for resistance levels, in canvas pixels.
    levels_zigzag_step: float = 6.0
    levels_zigzag_amplitude: float = 3.0
    levels_wave_period: float = 16.0
    levels_wave_amplitude: float = 3.0
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
    bottom_bar: ttk.Frame
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
    ticker_label: tk.Label
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
    mode_button_frame: ttk.Frame
    roi_button: ttk.Button
    roi_mode: bool = False
    export_mode: bool = False
    export_button: ttk.Button
    # Labels map to candle records, in the order the selections were saved.
    labeled_selections: Selections
    export_directory: str = EXPORT_DIRECTORY
    # Column of the last ROI drag as (left x, right x), unscaled like the box.
    _roi_span: Optional[Tuple[float, float]] = None
    # Each ROI row pairs an entry price field with an exit price field.
    # Column indices match the rows in price_data: open, high, low, close.
    roi_price_fields: Tuple[Tuple[str, str, int], ...] = (
        ("open", "O", 1), ("high", "H", 2), ("low", "L", 3), ("close", "C", 4),
    )
    roi_panel: tk.Frame
    roi_header_label: tk.Label
    roi_row_labels: List[Tuple[tk.Label, tk.Label]]
    roi_header: Optional[str] = None
    # (pairing label, percentage) per entry/exit pairing, sorted from highest
    # ROI to lowest. A percentage of None means the entry price was zero.
    roi_results: Optional[List[Tuple[str, Optional[float]]]] = None

    def __init__(
        self, tk: ModuleType, ttk: ModuleType,
        price_data_object: Optional[Dict[str, Any]] = None,
        data_source: Optional[PriceDataSource] = None,
    ) -> None:

        self.price_data_object=price_data_object
        self.price_data=price_data_object["price_data"]
        self.selected_indices = set()
        self.labeled_selections = {}
        self.data_source = data_source
        self.indicators_object = Indicators()
        self.indicators_object.set_price_data(self.price_data)
        self.indicators_object.calculate_RSI_incremental()
        # Applied simple moving average settings, keyed by period.
        self.sma_applied: Dict[int, Dict[str, Any]] = {
            period: {"enabled": False, "hi_lo": False, "style": "Solid",
                     "color": self.sma_default_colors[period]}
            for period in SMA_PERIODS
        }
        self._sma_items: List[int] = []
        # Bollinger Bands settings. The period and width are fixed in the indicator module.
        self.bollinger_applied: Dict[str, Any] = {"enabled": False, "style": "Solid", "color": "Green"}
        self._bollinger_items: List[int] = []
        # Support and resistance settings. Each window label has its own display settings.
        self.levels_applied: Dict[str, Any] = {
            "mode": "Causal",
            "settings": LevelSettings(),
            "horizon": HORIZONS[-1],
            "rejection": ATR_REJECTION,
            "windows": {
                label: {
                    "enabled": False,
                    "color": self.levels_default_colors[label],
                    "style": self.levels_default_style,
                }
                for label in WINDOW_LOOKBACKS
            },
        }
        self._levels_items: List[int] = []
        # Finder, per-window segments and breakout studies, rebuilt when the rows or
        # level settings change. Studies are keyed by (window, horizon, rejection).
        self._levels_cache: Optional[Tuple[
            Tuple[int, LevelSettings], LevelFinder, Dict[str, List[Segment]],
            Dict[Tuple[str, int, str], BreakoutStudy],
        ]] = None

        self.calculate_grid_space_x(price_data_object)
        self._base_chart_width = self.chart_grid_space_x
        self.calculate_price_range()

        #set up window and frames
        self.initialize_window(tk)
        self.initialize_menu_bar(tk)

        #set up frames
        self.initialize_frames(ttk)

        # set up canvas
        self.initialize_canvases(tk)
        self.initialize_candle_info(tk)
        self.initialize_no_data_label(tk)
        self.initialize_ticker_label(tk)

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
        self.center_vertical_view()
        self.update_no_data_label()
        self.update_ticker_label()

        #set price data for indicators_objec 

    def initialize_window(self, tk: ModuleType) -> None:
        self.window = tk.Tk()
        self.window.configure(bg=self.window_color)
        self.window.title("PyTradeViz - Alpha")
        self.window.geometry(self.window_geo)
        self.window.minsize(self.window_min_width, self.window_min_height)
        self.window.resizable(True, True)

    def initialize_menu_bar(self, tk: ModuleType) -> None:
        self.menu_bar = tk.Menu(self.window, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=self.initialize_file_menu(tk))
        self.menu_bar.add_cascade(label="Indicators", menu=self.initialize_indicators_menu(tk))
        self.menu_bar.add_command(label="Strategies", command=self.open_strategies)
        self.menu_bar.add_command(label="Data", command=lambda: self.open_data_window(tk))
        self.window.configure(menu=self.menu_bar)

    def initialize_file_menu(self, tk: ModuleType) -> Any:
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(label="Open Data File", command=self.open_data_file)
        file_menu.add_command(label="Close Data File", command=self.close_data_file)
        file_menu.add_command(label="About", command=lambda: self.open_about_window(tk))
        file_menu.add_command(label="Exit", command=self.window.destroy)
        return file_menu

    def open_data_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window, title="Open Data File", initialdir=DATA_DIRECTORY,
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            source = PaginatedPriceData(path, require_named_columns=True)
            rows = source.load_initial()
        except (csv.Error, OSError, ValueError) as error:
            messagebox.showerror("Unable to open price data", str(error), parent=self.window)
            return
        self.replace_price_data(rows, source)

    def close_data_file(self) -> None:
        self.labeled_selections.clear()
        self.replace_price_data([], None)

    def replace_price_data(
        self, rows: List[List[Any]], data_source: Optional[PriceDataSource]
    ) -> None:
        """Show rows from the first candle, replacing what was on the chart. Empty rows clear it."""
        self.reset_interaction_state()
        for canvas in (self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators):
            canvas.delete("all")
        self._sma_items = []
        self._bollinger_items = []
        self._levels_items = []
        self._levels_cache = None

        self.price_data_object = {"price_data": rows}
        self.price_data = rows
        self.data_source = data_source
        self.indicators_object.set_price_data(rows)
        self.indicators_object.calculate_RSI_incremental()

        # Build at base size as startup does, then fit the chart to the current window.
        self.zoom_level = 1.0
        self.candle_height_scale = 1.0
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._last_canvas_width = self.canvas_width
        self._last_canvas_height = self.canvas_height
        self.chart_grid_space_y = self.base_chart_height
        self.calculate_grid_space_x(self.price_data_object)
        self._base_chart_width = self.chart_grid_space_x
        self.calculate_price_range()

        self.initialize_charts(rows)
        self.render_candles()
        self.render_dates()
        self.render_indicators()
        self.fit_chart_to_canvas(self.canvas.winfo_width(), self.canvas.winfo_height())
        self.update_scroll_regions()
        self.canvas.xview_moveto(0)
        self.center_vertical_view()
        self.update_load_more_button()
        self.update_no_data_label()
        self.update_ticker_label()
        self.draw_overlays()

    def reset_interaction_state(self) -> None:
        self.selection_mode = self.roi_mode = self.export_mode = False
        self.selected_indices = set()
        self._selection_box = None
        self._box_origin = None
        self._box_current = None
        self._roi_span = None
        self._press_position = None
        self.roi_header = None
        self.roi_results = None
        self.crosshair_root = None
        self.update_mode_widgets()
        self.candle_info_label.place_forget()
        self.roi_panel.place_forget()

    def initialize_no_data_label(self, tk: ModuleType) -> None:
        theme = self.get_theme()
        self.no_data_label = tk.Label(
            self.frame_canvas, text="No price data is loaded",
            bg=theme["canvas"], fg=theme["ink"], padx=24, pady=12, relief="solid", bd=1,
        )

    def update_no_data_label(self) -> None:
        if self.price_data:
            self.no_data_label.place_forget()
        else:
            self.no_data_label.place(relx=0.5, rely=0.5, anchor="center")
            self.no_data_label.lift()

    def initialize_ticker_label(self, tk: ModuleType) -> None:
        theme = self.get_theme()
        self.ticker_label = tk.Label(
            self.frame_canvas, bg=theme["canvas"], fg=theme["ink"], padx=8, pady=4,
        )

    def update_ticker_label(self) -> None:
        """Show the ticker and the close of the last candle loaded, at the top left."""
        if not self.price_data:
            self.ticker_label.place_forget()
            return
        ticker = self.data_source.ticker if self.data_source is not None else None
        parts = [ticker] if ticker else []
        parts.append(f"{self.price_data[-1][4]:.8g}")
        self.ticker_label.configure(text="  ".join(parts))
        self.ticker_label.place(x=0, y=0, anchor="nw")
        self.ticker_label.lift()

    def update_load_more_button(self) -> None:
        if self.data_source is None or not self.data_source.has_more:
            self.load_more_button.state(["disabled"])
        else:
            self.load_more_button.state(["!disabled"])

    def open_about_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "About PyTradeViz")
        about_text = (
            "PyTradeViz - Alpha\n"
            "Version: alpha 0.0.1\n"
            "Python: {}\n\n"
            "Candlestick chart viewer for CryptoDataDownload price data."
        ).format(platform.python_version())
        tk.Label(window, text=about_text, justify="left", padx=16, pady=12).pack()
        tk.Button(window, text="OK", width=8, command=window.destroy).pack(pady=(0, 12))

    def open_strategies(self) -> None:
        # Placeholder until strategies are implemented.
        pass

    def open_data_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Data")
        listing = tk.Frame(window)
        listing.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        self.fill_data_listing(tk, listing)
        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Close", width=12, command=window.destroy).pack(side="right")
        tk.Button(
            buttons, text="Clear", width=12,
            command=lambda: self.clear_labeled_selections(tk, window, listing),
        ).pack(side="left", padx=(0, 24))
        tk.Button(
            buttons, text="Add To Existing...", width=16,
            command=lambda: self.add_to_existing(window),
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons, text="Export to XML", width=14,
            command=lambda: self.export_labeled_selections(window, "xml"),
        ).pack(side="left")
        tk.Button(
            buttons, text="Export to JSON", width=14,
            command=lambda: self.export_labeled_selections(window, "json"),
        ).pack(side="left", padx=(8, 0))

    def fill_data_listing(self, tk: ModuleType, listing: Any) -> None:
        for child in listing.winfo_children():
            child.destroy()
        if self.labeled_selections:
            list_box = tk.Listbox(listing, width=48, height=12)
            list_box.pack(fill="both", expand=True)
            for label, records in self.labeled_selections.items():
                list_box.insert("end", f"{label}: {len(records)} candles")
        else:
            tk.Label(listing, text="No labeled selections yet.").pack(anchor="w")

    def clear_labeled_selections(self, tk: ModuleType, window: Any, listing: Any) -> None:
        if not self.labeled_selections:
            return
        if not messagebox.askyesno(
            "Clear selections", "Remove all labeled selections? This cannot be undone.", parent=window,
        ):
            return
        self.labeled_selections.clear()
        self.fill_data_listing(tk, listing)

    def export_labeled_selections(self, window: Any, extension: str) -> None:
        if not self.labeled_selections:
            messagebox.showinfo("Export", "There are no labeled selections to export.", parent=window)
            return
        path = export_path(self.export_directory, extension, datetime.datetime.now())
        try:
            write_selections(path, self.labeled_selections)
        except OSError as error:
            messagebox.showerror("Unable to export", str(error), parent=window)
            return
        messagebox.showinfo("Export complete", f"Saved to {path}", parent=window)

    def add_to_existing(self, window: Any) -> None:
        if not self.labeled_selections:
            messagebox.showinfo("Add To Existing", "There are no labeled selections to add.", parent=window)
            return
        path = filedialog.askopenfilename(
            parent=window, title="Add selections to an export",
            initialdir=self.export_directory,
            filetypes=[("Labeled selections", "*.json *.xml"), ("JSON", "*.json"), ("XML", "*.xml")],
        )
        if not path:
            return
        try:
            merged = merge_selections(read_selections(path), self.labeled_selections)
            write_selections(path, merged)
        except (OSError, ValueError) as error:
            messagebox.showerror("Unable to add selections", str(error), parent=window)
            return
        count = sum(len(records) for records in self.labeled_selections.values())
        messagebox.showinfo(
            "Selections added", f"Added {count} candles to {os.path.basename(path)}", parent=window,
        )

    def open_label_window(self, indices: Set[int]) -> None:
        window = self.open_modal_window(tk, "Label selection")
        tk.Label(
            window, text=f"Enter a label for the {len(indices)} selected candle(s):",
        ).pack(anchor="w", padx=12, pady=(12, 4))
        entry = tk.Entry(window, width=40)
        entry.pack(fill="x", padx=12)
        entry.focus_set()

        def save(_event: Any = None) -> None:
            label = entry.get().strip()
            if not label:
                messagebox.showwarning("Label required", "Enter a label for the selection.", parent=window)
                entry.focus_set()
                return
            self.save_labeled_selection(label, indices)
            window.destroy()

        def cancel(_event: Any = None) -> None:
            self.set_selection(set(), None)
            window.destroy()

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Cancel", width=8, command=cancel).pack(side="right")
        tk.Button(buttons, text="Save", width=8, command=save).pack(side="right", padx=(0, 8))
        window.bind("<Return>", save)
        window.bind("<Escape>", cancel)
        window.protocol("WM_DELETE_WINDOW", cancel)

    def save_labeled_selection(self, label: str, indices: Set[int]) -> None:
        records = [self.labeled_candle_record(index) for index in sorted(indices)]
        self.labeled_selections.setdefault(label, []).extend(records)
        self.set_selection(set(), None)

    def labeled_candle_record(self, index: int) -> Dict[str, Any]:
        _, open_, high, low, close, indicators = self.price_data[index][:6]
        record: Dict[str, Any] = {
            "open": open_, "high": high, "low": low, "close": close,
            "rsi": indicators["rsi"],
        }
        for period, field in MOVING_AVERAGE_FIELDS.items():
            record[field] = self.indicators_object.calculate_SMA(period)[index]
        middle, upper, lower = self.indicators_object.calculate_bollinger()
        record["bollinger_middle"] = middle[index]
        record["bollinger_upper"] = upper[index]
        record["bollinger_lower"] = lower[index]
        previous_rsi = self.price_data[index - 1][5]["rsi"] if index > 0 else None
        record["top_bol_intersect"] = band_intersects(low, high, upper[index])
        record["btm_bol_intersect"] = band_intersects(low, high, lower[index])
        record["rsi_os"] = rsi_crosses_level(previous_rsi, record["rsi"], RSI_OVERSOLD)
        record["rsi_ob"] = rsi_crosses_level(previous_rsi, record["rsi"], RSI_OVERBOUGHT)
        return record

    def initialize_indicators_menu(self, tk: ModuleType) -> Any:
        indicators_menu = tk.Menu(self.menu_bar, tearoff=0)
        moving_averages_menu = tk.Menu(indicators_menu, tearoff=0)
        for name in ("Exponential", "Simple"):
            moving_averages_menu.add_command(
                label=name, command=lambda name=name: self.open_moving_average_window(tk, name),
            )
        indicators_menu.add_cascade(label="Moving Averages", menu=moving_averages_menu)
        indicators_menu.add_cascade(label="RSI", menu=tk.Menu(indicators_menu, tearoff=0))
        bollinger_menu = tk.Menu(indicators_menu, tearoff=0)
        bollinger_menu.add_command(
            label="Bollinger Bands", command=lambda: self.open_bollinger_window(tk),
        )
        indicators_menu.add_cascade(label="Bollinger", menu=bollinger_menu)
        indicators_menu.add_command(
            label="Support and Resistance", command=lambda: self.open_levels_window(tk),
        )
        return indicators_menu

    def open_moving_average_window(self, tk: ModuleType, name: str) -> None:
        window = self.open_modal_window(tk, name)
        if name == "Simple":
            self.build_simple_moving_average_content(tk, window)

    def open_bollinger_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Bollinger Bands")
        self.build_bollinger_content(tk, window)

    def build_bollinger_content(self, tk: ModuleType, window: Any) -> None:
        # Edits are staged in these variables and only applied by the Apply button.
        applied = self.bollinger_applied
        staged = {
            "enabled": tk.BooleanVar(window, value=applied["enabled"]),
            "style": tk.StringVar(window, value=applied["style"]),
            "color": tk.StringVar(window, value=applied["color"]),
        }
        group = tk.LabelFrame(window, text="Bollinger Bands (20 candles, 2 std. dev.)",
                              padx=10, pady=6)
        group.pack(fill="x", padx=12, pady=(12, 0))
        tk.Checkbutton(group, text="Show", variable=staged["enabled"]).grid(
            row=0, column=0, sticky="w")
        tk.Label(group, text="Style:").grid(row=1, column=0, sticky="w")
        for column, style in enumerate(self.sma_line_styles, start=1):
            tk.Radiobutton(group, text=style, value=style, variable=staged["style"]).grid(
                row=1, column=column, sticky="w")
        tk.Label(group, text="Color:").grid(row=2, column=0, sticky="w")
        for column, color in enumerate(self.sma_colors, start=1):
            tk.Radiobutton(group, text=color, value=color, variable=staged["color"]).grid(
                row=2, column=column, sticky="w")

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Close", width=8, command=window.destroy).pack(side="right")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_bollinger(staged),
        ).pack(side="right", padx=(0, 8))

    def apply_bollinger(self, staged: Dict[str, Any]) -> None:
        self.bollinger_applied = {
            "enabled": staged["enabled"].get(),
            "style": staged["style"].get(),
            "color": staged["color"].get(),
        }
        # Showing the bands can widen the price scale, so the chart is rescaled to fit.
        old_upper, old_lower = self.price_upper, self.price_lower
        self.calculate_price_range()
        self.rescale_price_scale(old_upper, old_lower)
        self.draw_overlays()

    def open_levels_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Support and Resistance")
        self.build_levels_content(tk, window)

    def build_levels_content(self, tk: ModuleType, window: Any) -> None:
        # Edits are staged in these variables and only applied by the Apply button.
        applied = self.levels_applied
        settings = applied["settings"]
        staged: Dict[str, Any] = {
            "mode": tk.StringVar(window, value=applied["mode"]),
            "horizon": tk.StringVar(window, value=str(applied["horizon"])),
            "rejection": tk.StringVar(window, value=applied["rejection"]),
            "settings": {
                "pivot_bars": tk.StringVar(window, value=str(settings.pivot_bars)),
                "width_pct": tk.StringVar(window, value=f"{settings.width_pct:g}"),
                "min_touches": tk.StringVar(window, value=str(settings.min_touches)),
            },
            "windows": {},
            "status": {},
        }
        for label in WINDOW_LOOKBACKS:
            window_applied = applied["windows"][label]
            staged["windows"][label] = {
                "enabled": tk.BooleanVar(window, value=window_applied["enabled"]),
                "color": tk.StringVar(window, value=window_applied["color"]),
                "style": tk.StringVar(window, value=window_applied["style"]),
            }
            staged["status"][label] = tk.StringVar(window, value=self.levels_status_text(label))

        mode_group = tk.LabelFrame(window, text="Mode", padx=10, pady=6)
        mode_group.pack(fill="x", padx=12, pady=(12, 0))
        tk.Radiobutton(
            mode_group, text="Causal (levels as known at each candle)",
            value="Causal", variable=staged["mode"],
        ).grid(row=0, column=0, sticky="w")
        tk.Radiobutton(
            mode_group, text="Static (latest levels across the whole chart)",
            value="Static", variable=staged["mode"],
        ).grid(row=1, column=0, sticky="w")

        detection = tk.LabelFrame(window, text="Detection", padx=10, pady=6)
        detection.pack(fill="x", padx=12, pady=(12, 0))
        detection_rows = (
            ("Pivot bars (candles each side)", "pivot_bars"),
            ("Cluster width (% of price)", "width_pct"),
            ("Min touches", "min_touches"),
        )
        for row, (text, key) in enumerate(detection_rows):
            tk.Label(detection, text=text).grid(row=row, column=0, sticky="w")
            tk.Entry(detection, textvariable=staged["settings"][key], width=8).grid(
                row=row, column=1, sticky="w", padx=(8, 0))

        odds_group = tk.LabelFrame(window, text="Breakout odds", padx=10, pady=6)
        odds_group.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(odds_group, text="Horizon:").grid(row=0, column=0, sticky="w")
        for column, horizon in enumerate(HORIZONS, start=1):
            tk.Radiobutton(odds_group, text=f"{horizon} candles", value=str(horizon),
                           variable=staged["horizon"]).grid(row=0, column=column, sticky="w")
        tk.Label(odds_group, text="Rejection:").grid(row=1, column=0, sticky="w")
        for column, rule in enumerate(REJECTION_RULES, start=1):
            tk.Radiobutton(odds_group, text=rule, value=rule,
                           variable=staged["rejection"]).grid(row=1, column=column, sticky="w")

        for label in WINDOW_LOOKBACKS:
            variables = staged["windows"][label]
            group = tk.LabelFrame(window, text=f"{label} window (max 2 support, 2 resistance)",
                                  padx=10, pady=6)
            group.pack(fill="x", padx=12, pady=(12, 0))
            tk.Checkbutton(group, text="Show", variable=variables["enabled"]).grid(
                row=0, column=0, sticky="w")
            tk.Label(group, textvariable=staged["status"][label]).grid(
                row=0, column=1, columnspan=6, sticky="w", padx=(8, 0))
            tk.Label(group, text="Color:").grid(row=1, column=0, sticky="w")
            for column, color in enumerate(self.sma_colors, start=1):
                tk.Radiobutton(group, text=color, value=color, variable=variables["color"]).grid(
                    row=1, column=column, sticky="w")
            tk.Label(group, text="Style:").grid(row=2, column=0, sticky="w")
            for column, style in enumerate(self.levels_styles, start=1):
                tk.Radiobutton(group, text=style, value=style, variable=variables["style"]).grid(
                    row=2, column=column, sticky="w")

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Help", width=8,
                  command=lambda: self.open_levels_help(tk, window)).pack(side="left")
        tk.Button(buttons, text="Close", width=8, command=window.destroy).pack(side="right")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_levels(window, staged),
        ).pack(side="right", padx=(0, 8))

    def apply_levels(self, window: Any, staged: Dict[str, Any]) -> None:
        values = {key: var.get().strip() for key, var in staged["settings"].items()}
        try:
            pivot_bars = int(values["pivot_bars"])
            width_pct = float(values["width_pct"])
            min_touches = int(values["min_touches"])
        except ValueError:
            messagebox.showerror(
                "Invalid level settings",
                "Pivot bars and min touches must be whole numbers, and width must be a number.",
                parent=window,
            )
            return
        if pivot_bars < 1 or min_touches < 1 or not width_pct > 0:
            messagebox.showerror(
                "Invalid level settings",
                "Pivot bars and min touches must be at least 1, and width must be above 0.",
                parent=window,
            )
            return
        self.levels_applied = {
            "mode": staged["mode"].get(),
            "settings": LevelSettings(pivot_bars, width_pct, min_touches),
            "horizon": int(staged["horizon"].get()),
            "rejection": staged["rejection"].get(),
            "windows": {
                label: {
                    "enabled": variables["enabled"].get(),
                    "color": variables["color"].get(),
                    "style": variables["style"].get(),
                }
                for label, variables in staged["windows"].items()
            },
        }
        for label, status in staged["status"].items():
            status.set(self.levels_status_text(label))
        self.draw_overlays()

    def levels_status_text(self, label: str) -> str:
        if not self.price_data:
            return "No price data loaded"
        finder, _, _ = self.levels_for_chart()
        last = len(self.price_data) - 1
        if finder.pivot_count(last, label) == 0:
            return "No pivots in this window"
        levels = finder.levels_at(last, label)
        supports = sum(1 for level in levels if level.kind == SUPPORT)
        summary = f"Latest: {supports} support, {len(levels) - supports} resistance"
        if not levels:
            return summary
        study = self.breakout_study(label)
        parts = []
        for level in sorted(levels, key=lambda level: level.price):
            odds = study.odds_at(last, level.price, level.kind, level.touches)
            prefix = "S" if level.kind == SUPPORT else "R"
            parts.append(f"{prefix} {level.price:.2f} {odds_text(odds)}")
        return f"{summary}  |  " + "   ".join(parts)

    def levels_for_chart(self) -> Tuple[LevelFinder, Dict[str, List[Segment]],
                                        Dict[Tuple[str, int, str], BreakoutStudy]]:
        settings = self.levels_applied["settings"]
        key = (len(self.price_data or []), settings)
        if self._levels_cache is None or self._levels_cache[0] != key:
            self._levels_cache = (key, LevelFinder(self.price_data or [], settings), {}, {})
        return self._levels_cache[1], self._levels_cache[2], self._levels_cache[3]

    def breakout_study(self, label: str) -> BreakoutStudy:
        """Breakout odds for one window under the current horizon and rejection rule."""
        finder, _, studies = self.levels_for_chart()
        horizon = self.levels_applied["horizon"]
        rejection = self.levels_applied["rejection"]
        key = (label, horizon, rejection)
        if key not in studies:
            studies[key] = BreakoutStudy(self.price_data or [], finder, label, horizon, rejection)
        return studies[key]

    def build_simple_moving_average_content(self, tk: ModuleType, window: Any) -> None:
        # Edits are staged in these variables and only applied by the Apply button.
        staged: Dict[int, Dict[str, Any]] = {}
        for period in SMA_PERIODS:
            applied = self.sma_applied[period]
            staged[period] = {
                "enabled": tk.BooleanVar(window, value=applied["enabled"]),
                "hi_lo": tk.BooleanVar(window, value=applied["hi_lo"]),
                "style": tk.StringVar(window, value=applied["style"]),
                "color": tk.StringVar(window, value=applied["color"]),
            }

        for period in SMA_PERIODS:
            variables = staged[period]
            group = tk.LabelFrame(window, text=f"{period}-candle SMA", padx=10, pady=6)
            group.pack(fill="x", padx=12, pady=(12, 0))
            tk.Checkbutton(group, text="Show", variable=variables["enabled"]).grid(
                row=0, column=0, sticky="w")
            tk.Checkbutton(group, text="Show Hi-Low MA", variable=variables["hi_lo"]).grid(
                row=0, column=1, columnspan=5, sticky="w")
            tk.Label(group, text="Style:").grid(row=1, column=0, sticky="w")
            for column, style in enumerate(self.sma_line_styles, start=1):
                tk.Radiobutton(group, text=style, value=style, variable=variables["style"]).grid(
                    row=1, column=column, sticky="w")
            tk.Label(group, text="Color:").grid(row=2, column=0, sticky="w")
            for column, color in enumerate(self.sma_colors, start=1):
                tk.Radiobutton(group, text=color, value=color, variable=variables["color"]).grid(
                    row=2, column=column, sticky="w")

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Close", width=8, command=window.destroy).pack(side="right")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_simple_moving_averages(staged),
        ).pack(side="right", padx=(0, 8))

    def apply_simple_moving_averages(self, staged: Dict[int, Dict[str, Any]]) -> None:
        for period, variables in staged.items():
            self.sma_applied[period] = {
                "enabled": variables["enabled"].get(),
                "hi_lo": variables["hi_lo"].get(),
                "style": variables["style"].get(),
                "color": variables["color"].get(),
            }
        self.draw_overlays()

    def open_levels_help(self, tk: ModuleType, parent: Any) -> None:
        help_window = self.open_modal_window(tk, "Support and Resistance Help", parent=parent)
        body = tk.Frame(help_window)
        body.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        text = tk.Text(body, wrap="word", width=84, height=30, padx=8, pady=6,
                       relief="flat", cursor="arrow", font="TkDefaultFont")
        scrollbar = tk.Scrollbar(body, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        heading_font = (tkfont.nametofont("TkDefaultFont").cget("family"), 11, "bold")
        text.tag_configure("heading", font=heading_font, spacing1=10, spacing3=2)
        text.tag_configure("body", spacing3=6)
        for heading, paragraphs in LEVELS_HELP:
            text.insert("end", heading + "\n", "heading")
            for paragraph in paragraphs:
                text.insert("end", paragraph + "\n", "body")
        text.configure(state="disabled")
        tk.Button(help_window, text="Close", width=8,
                  command=help_window.destroy).pack(pady=12)
        # Closing help hands the modal grab back to the window that opened it.
        help_window.bind("<Destroy>", lambda event: self.return_grab(event, help_window, parent))

    def return_grab(self, event: Any, help_window: Any, parent: Any) -> None:
        if event.widget is not help_window:
            return
        parent.after_idle(lambda: parent.grab_set() if parent.winfo_exists() else None)

    def open_modal_window(self, tk: ModuleType, title: str, parent: Any = None) -> Any:
        # Selecting a menu item already unposts the menus; this opens the modal dialog.
        parent = self.window if parent is None else parent
        window = tk.Toplevel(parent)
        window.title(title)
        window.transient(parent)
        window.wait_visibility()
        window.grab_set()
        return window

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
            if self.price_data:
                #render price levels
                plrender="{:.2f}".format(price_level)
                self.canvas_price.create_text(
                    50, i, text=plrender, anchor="n" if i == 0 else "center",
                    fill=ink, tags=("price_label", "ink")
                )
            price_level-=self.incrementer

        self.canvas_indicators.create_line(
            0, RSI_OVERBOUGHT, self.chart_grid_space_x, RSI_OVERBOUGHT, fill="orange", width=2,
            tags=("indicator_level",)
        )
        self.canvas_indicators.create_line(
            0, RSI_OVERSOLD, self.chart_grid_space_x, RSI_OVERSOLD, fill="blue", width=2,
            tags=("indicator_level",)
        )
        
    def initialize_canvases(self, tk: ModuleType) -> None:
        self.canvas= tk.Canvas(self.frame_canvas, width=self.canvas_width, height=self.canvas_height)
        self.canvas_price= tk.Canvas(self.frame_canvas_price, width=100, height=500)
        self.canvas_date = tk.Canvas(self.frame_canvas_date, width=self.canvas_width, height=50)
        self.canvas_indicators= tk.Canvas(self.frame_canvas_indicators, width=self.canvas_width, height=100)

    def initialize_scrollbars(self, ttk: ModuleType, tk: ModuleType) -> None:
        self.scrollbar_horizontal = ttk.Scrollbar(
            self.bottom_bar, orient=tk.HORIZONTAL, command=self.scroll_xview
        )
        self.scrollbar_vertical = ttk.Scrollbar(
            self.window, orient=tk.VERTICAL, command=self.scroll_yview
        )
        self.load_more_button = ttk.Button(
            self.window, text=">", width=1, command=self.load_more_data
        )
        self.update_load_more_button()

    def initialize_frames(self, ttk: ModuleType) -> None:
        self.frame_canvas = ttk.Frame(self.window, width=self.canvas_width, height=self.canvas_height)
        self.frame_canvas_indicators = ttk.Frame(self.window, width=self.canvas_width, height=100)
        self.frame_canvas_price = ttk.Frame(self.window, width=100, height=500)
        self.frame_canvas_date = ttk.Frame(self.window, width=self.canvas_width, height=50)
        # Holds the horizontal scrollbar and toolbox so neither widens the price column.
        self.bottom_bar = ttk.Frame(self.window)

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
        self.frame_canvas_price.grid(row=0, column=1, sticky="nsew")
        self.frame_canvas_date.grid(row=1, column=0, sticky="ew")
        self.frame_canvas_indicators.grid(row=2, column=0, sticky="ew")
        self.bottom_bar.grid(row=3, column=0, sticky="ew")
        self.mode_button_frame.pack(side="right")
        self.scrollbar_horizontal.pack(side="left", fill="x", expand=True)
        self.load_more_button.grid(row=2, column=1, sticky="nsw")
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
        if not rows:
            self.price_upper = 1.60
            self.price_lower = 0
            return
        prices = [price for row in rows for price in row[1:5]]
        lowest = min(prices)
        highest = max(prices)
        if new_rows is not None:
            lowest = min(lowest, self._data_lowest)
            highest = max(highest, self._data_highest)
        self._data_lowest = lowest
        self._data_highest = highest
        # The scale also covers the Bollinger Bands while they are shown.
        scale_lowest, scale_highest = lowest, highest
        if self.bollinger_applied["enabled"]:
            band_range = self.indicators_object.bollinger_range()
            if band_range is not None:
                scale_lowest = min(scale_lowest, band_range[0])
                scale_highest = max(scale_highest, band_range[1])
        margin = max((scale_highest - scale_lowest) * 0.05, abs(scale_highest) * 0.01, 0.01)
        self.price_upper = max(1.60, scale_highest + margin)
        self.price_lower = min(0, scale_lowest - margin)

    def rescale_price_scale(self, old_upper: float, old_lower: float) -> Tuple[float, float]:
        """Stretch the candles and price labels from the old range to the current one.

        Returns the vertical scale ratio and the pixel shift that were applied.
        """
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
        return ratio, shift

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
        self.mode_button_frame = ttk.Frame(self.bottom_bar)
        self.select_button = ttk.Button(
            self.mode_button_frame, image=self.select_icon,
            command=self.toggle_selection_mode,
        )
        self.select_button.grid(row=0, column=0, sticky="nsw")
        # width=0 sizes the button to its text; the ttk default minimum is about 9 characters.
        self.roi_button = ttk.Button(
            self.mode_button_frame, text="ROI", width=0, command=self.toggle_roi_mode,
        )
        self.roi_button.grid(row=0, column=1, sticky="nsw", padx=(4, 0))
        self.export_button = ttk.Button(
            self.mode_button_frame, text="{</>}", width=0, command=self.toggle_export_mode,
        )
        self.export_button.grid(row=0, column=2, sticky="nsw", padx=(4, 0))

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
            self.roi_mode = self.export_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_roi_mode(self) -> None:
        self.roi_mode = not self.roi_mode
        if self.roi_mode:
            self.selection_mode = self.export_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_export_mode(self) -> None:
        self.export_mode = not self.export_mode
        if self.export_mode:
            self.selection_mode = self.roi_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def exit_modes(self) -> None:
        if not self.gesture_active():
            return
        self.selection_mode = self.roi_mode = self.export_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def gesture_active(self) -> bool:
        return self.selection_mode or self.roi_mode or self.export_mode

    def clear_gesture_state(self) -> None:
        self._box_origin = None
        self._roi_span = None
        self.roi_header = None
        self.roi_results = None
        self.set_selection(set(), None)

    def update_mode_widgets(self) -> None:
        if self.gesture_active():
            if self.roi_mode:
                text = "ROI mode enabled"
            elif self.export_mode:
                text = "select and export mode"
            else:
                text = "select mode enabled"
            self.select_mode_label.configure(text=text)
            self.place_mode_label()
        else:
            self.select_mode_label.place_forget()
        self.select_button.state(["pressed" if self.selection_mode else "!pressed"])
        self.roi_button.state(["pressed" if self.roi_mode else "!pressed"])
        self.export_button.state(["pressed" if self.export_mode else "!pressed"])

    def place_mode_label(self) -> None:
        # Sit below the ROI panel while it is shown, otherwise below the OHLC box.
        if self.roi_mode and self.roi_results is not None:
            self.roi_panel.update_idletasks()
            y = 8 + self.roi_panel.winfo_reqheight() + 8
        else:
            y = self.select_label_y
        self.select_mode_label.place(relx=1.0, x=-8, y=y, anchor="ne")
        self.select_mode_label.lift()

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
        self.no_data_label.configure(bg=theme["canvas"], fg=theme["ink"])
        self.ticker_label.configure(bg=theme["canvas"], fg=theme["ink"])
        self.render_roi_panel()
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
        self.update_ticker_label()
        self.indicators_object.calculate_RSI_incremental()
        self.calculate_price_range(new_rows)
        self.price_upper = max(old_upper, self.price_upper)
        ratio, shift = self.rescale_price_scale(old_upper, old_lower)

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
        self.render_indicators(old_count, tags=("new_page",))
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

    def center_vertical_view(self) -> None:
        self.window.update_idletasks()
        visible = self.canvas.winfo_height() / self.chart_grid_space_y
        self.canvas.yview_moveto(max(0.0, 0.5 - visible / 2))

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
        if self.gesture_active():
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
        if self.gesture_active():
            if self._box_origin is not None:
                self._box_current = (
                    self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
                )
                if self.roi_mode:
                    self._roi_span = self.span_from_canvas(
                        self._box_origin[0], self._box_current[0]
                    )
                else:
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
        self.roi_panel = tk.Frame(
            self.frame_canvas, relief="solid", bd=1, padx=6, pady=4,
            bg=self.get_theme()["canvas"],
        )
        self.roi_header_label = tk.Label(self.roi_panel, anchor="w")
        self.roi_header_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self.roi_row_labels = []
        for _ in itertools.product(self.roi_price_fields, repeat=2):
            name_label = tk.Label(self.roi_panel, anchor="w")
            value_label = tk.Label(self.roi_panel, anchor="e")
            name_label.grid(row=len(self.roi_row_labels) + 1, column=0, sticky="w")
            value_label.grid(row=len(self.roi_row_labels) + 1, column=1, sticky="e")
            self.roi_row_labels.append((name_label, value_label))
        self.roi_panel.place_forget()
        self.render_roi_panel()

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
        if self.roi_mode:
            self.finish_roi(event)
            return
        if self.export_mode:
            if self.finish_box_select(event) and self.selected_indices:
                self.open_label_window(set(self.selected_indices))
            return
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
        self.set_selection({index} if index is not None else set(), None)
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
        selected = index in self.selected_indices
        if selected:
            color = self.highlight_color(color)
        if self.canvas.type(item) == "rectangle":
            # Selected bodies are always solid so the highlight fills them in dark mode too.
            Candle.style_body(self.canvas, item, self.dark_mode and not selected, color)
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

    def span_from_canvas(self, first_x: float, second_x: float) -> Tuple[float, float]:
        x1, x2 = sorted((first_x, second_x))
        return x1 / self._scale_x, x2 / self._scale_x

    def clear_selection_box(self) -> None:
        self.canvas.delete("selection")

    def draw_selection_region(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.clear_selection_box()
        color = self.get_theme()["selection"]
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=color, stipple="gray50", outline=color, dash=(4, 4), width=1,
            tags=("selection",),
        )
        # Keep the tint under the candles so their highlight colors stay visible.
        if self.canvas.find_withtag("candle"):
            self.canvas.tag_lower("selection", "candle")

    def draw_selection_box(self) -> None:
        if self._roi_span is not None:
            left, right = self._roi_span
            self.draw_selection_region(
                left * self._scale_x, 0, right * self._scale_x, self.chart_grid_space_y
            )
        elif self._selection_box is not None:
            left, right, top, bottom = self._selection_box
            self.draw_selection_region(
                left * self._scale_x, self.price_to_y(top),
                right * self._scale_x, self.price_to_y(bottom),
            )

    def candle_x(self, index: int) -> float:
        return (self.chart_padding_x + index * self.chart_grid_divider_v) * self._scale_x

    def draw_moving_averages(self) -> None:
        for item in self._sma_items:
            self.canvas.delete(item)
        self._sma_items = []
        for period in SMA_PERIODS:
            settings = self.sma_applied[period]
            if not settings["enabled"]:
                continue
            self._sma_items.extend(self.indicators_object.render_SMA(
                self.canvas, period,
                x_for_index=self.candle_x, y_for_price=self.price_to_y,
                fill=self.sma_colors[settings["color"]],
                dash=self.sma_line_styles[settings["style"]],
                width=self.sma_line_widths[settings["style"]],
                tags=("sma", f"sma_{period}"),
            ))
            if settings["hi_lo"]:
                # Markers are only created for the visible part of the chart.
                x_range = (self.canvas.canvasx(0), self.canvas.canvasx(self.canvas.winfo_width()))
                for column in (HIGH_COLUMN, LOW_COLUMN):
                    self._sma_items.extend(self.indicators_object.render_SMA_markers(
                        self.canvas, period, column,
                        x_for_index=self.candle_x, y_for_price=self.price_to_y,
                        fill=self.sma_colors[settings["color"]], size=6,
                        tags=("sma", f"sma_{period}", "sma_hi_lo"), x_range=x_range,
                    ))

    def draw_bollinger(self) -> None:
        for item in self._bollinger_items:
            self.canvas.delete(item)
        self._bollinger_items = []
        settings = self.bollinger_applied
        if not settings["enabled"]:
            return
        series = zip(("middle", "upper", "lower"), self.indicators_object.calculate_bollinger())
        for name, values in series:
            self._bollinger_items.extend(self.indicators_object.render_series(
                self.canvas, values,
                x_for_index=self.candle_x, y_for_price=self.price_to_y,
                fill=self.sma_colors[settings["color"]],
                dash=self.sma_line_styles[settings["style"]],
                width=self.sma_line_widths[settings["style"]],
                tags=("bollinger", f"bollinger_{name}"),
            ))

    def draw_levels(self) -> None:
        for item in self._levels_items:
            self.canvas.delete(item)
        self._levels_items = []
        if not self.price_data:
            return
        finder, segment_cache, _ = self.levels_for_chart()
        last = len(self.price_data) - 1
        static = self.levels_applied["mode"] == "Static"
        first_visible, last_visible = self.visible_candle_range()
        occupied_label_boxes: List[Tuple[int, int, int, int]] = []
        for label, settings in self.levels_applied["windows"].items():
            if not settings["enabled"]:
                continue
            study = self.breakout_study(label)
            if static:
                # Static levels have no qualification candle of their own, so they are
                # priced as of the latest candle.
                spans = [(0, last, level.price, level.kind, last, level.touches)
                         for level in finder.static_levels(label)]
            else:
                if label not in segment_cache:
                    segment_cache[label] = finder.segments(label)
                spans = [(segment.start, segment.end, segment.price, segment.kind,
                          segment.origin, segment.touches)
                         for segment in segment_cache[label]]
            color = self.sma_colors[settings["color"]]
            style = settings["style"]
            for start, end, price, kind, origin, touches in spans:
                if style == "Triangles":
                    # Only candles in view get a marker, so zoomed-out charts stay responsive.
                    for index in range(max(start, first_visible), min(end, last_visible) + 1):
                        self.draw_level_marker(index, price, kind, color, label)
                else:
                    self.draw_level_line(start, end, price, kind, color, label,
                                         wavy=style == "Wavy")
                # One odds label per level, where its drawing ends on screen. A level that
                # runs past the right edge is labelled at that edge.
                if start <= last_visible and end >= first_visible:
                    odds = study.odds_at(origin, price, kind, touches)
                    self.draw_level_odds(min(end, last_visible), price, color, label,
                                         odds_text(odds), occupied_label_boxes)
        # Markers sit above the candles so a body never hides a level.
        if self._levels_items:
            self.canvas.tag_raise("levels")

    def draw_level_odds(self, index: int, price: float, color: str, label: str,
                        text: str, occupied: List[Tuple[int, int, int, int]]) -> None:
        x = self.candle_x(index)
        y = self.price_to_y(price)
        # Anchored to the left of its point so the text stays clear of the price axis.
        item = self.canvas.create_text(
            x - 6, y - 6, text=text, anchor="se", fill=color,
            tags=("levels", f"levels_{label}"))
        # Labels that would land on one already drawn are dropped; the status line keeps them.
        box = self.canvas.bbox(item)
        if any(box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]
               for other in occupied):
            self.canvas.delete(item)
            return
        occupied.append(box)
        self._levels_items.append(item)

    def draw_level_marker(self, index: int, price: float, kind: str, color: str,
                          label: str) -> None:
        x = self.candle_x(index)
        y = self.price_to_y(price)
        r = self.levels_marker_radius
        tags = ("levels", f"levels_{label}")
        if kind == SUPPORT:
            # Solid triangle pointing up.
            points = (x, y - r, x - r, y + r, x + r, y + r)
            item = self.canvas.create_polygon(
                *points, fill=color, outline=color, tags=tags)
        else:
            # Hollow triangle pointing down.
            points = (x - r, y - r, x + r, y - r, x, y + r)
            item = self.canvas.create_polygon(
                *points, fill="", outline=color, width=2, tags=tags)
        self._levels_items.append(item)

    def draw_level_line(self, start: int, end: int, price: float, kind: str, color: str,
                        label: str, wavy: bool) -> None:
        """Draw a level as a line from candle start to candle end, clipped to the view.

        Support is a straight line (solid, or dashed in Wavy style). Resistance is a
        zigzag (solid in Lines style) or a wave (solid in Wavy style).
        """
        left, right = self.visible_x_range()
        x0 = max(self.candle_x(start), left)
        x1 = min(self.candle_x(end), right)
        if x0 > x1:
            return
        y = self.price_to_y(price)
        tags = ("levels", f"levels_{label}")
        if kind == SUPPORT:
            points = [x0, y, x1, y]
            dash = (6, 4) if wavy else ()
        elif wavy:
            points = self.wave_points(x0, x1, y)
            dash = ()
        else:
            points = self.zigzag_points(x0, x1, y)
            dash = ()
        item = self.canvas.create_line(
            *points, fill=color, width=2, dash=dash, joinstyle="round", tags=tags)
        self._levels_items.append(item)

    def zigzag_points(self, x0: float, x1: float, y: float) -> List[float]:
        # Vertices sit on a fixed pixel grid so the zigzag does not shift when scrolling.
        step = self.levels_zigzag_step
        amp = self.levels_zigzag_amplitude
        points = [x0, y]
        for k in range(math.floor(x0 / step) + 1, math.ceil(x1 / step)):
            points.extend((k * step, y - amp if k % 2 else y + amp))
        points.extend((x1, y))
        return points

    def wave_points(self, x0: float, x1: float, y: float) -> List[float]:
        # Samples on a fixed pixel grid so the wave does not shift when scrolling.
        sample = 2.0
        period = self.levels_wave_period
        amp = self.levels_wave_amplitude
        points: List[float] = []
        for k in range(math.floor(x0 / sample), math.ceil(x1 / sample) + 1):
            x = min(max(k * sample, x0), x1)
            points.extend((x, y - amp * math.sin(2 * math.pi * x / period)))
        return points

    def visible_x_range(self) -> Tuple[float, float]:
        """Return the left and right canvas x coordinates of the visible area."""
        return self.canvas.canvasx(0), self.canvas.canvasx(self.canvas.winfo_width())

    def visible_candle_range(self) -> Tuple[int, int]:
        """Return the first and last candle indexes that fall inside the visible canvas."""
        left, right = self.visible_x_range()
        first = math.floor((left / self._scale_x - self.chart_padding_x)
                           / self.chart_grid_divider_v)
        last = math.floor((right / self._scale_x - self.chart_padding_x)
                          / self.chart_grid_divider_v)
        last_index = len(self.price_data or []) - 1
        return max(0, first), min(last_index, last)

    def draw_overlays(self) -> None:
        self.draw_selection_box()
        self.draw_moving_averages()
        self.draw_bollinger()
        self.draw_levels()
        self.draw_crosshair()

    def candle_indices_in(self, x1: float, y1: float, x2: float, y2: float) -> Set[int]:
        indices: Set[int] = set()
        for item in self.canvas.find_overlapping(x1, y1, x2, y2):
            index = self.candle_index_of(item)
            if index is not None:
                indices.add(index)
        return indices

    def finish_box_select(self, event: tk.Event) -> bool:
        """Complete a box or click selection. Returns False if no gesture was in progress."""
        origin = self._box_origin
        self._box_origin = None
        if origin is None or self._press_position is None:
            return False
        press_x, press_y = self._press_position
        if abs(event.x - press_x) + abs(event.y - press_y) <= self.click_drag_threshold:
            index = self.candle_index_at(*origin)
            self.set_selection({index} if index is not None else set(), None)
            return True
        current = self._box_current or origin
        x1, x2 = sorted((origin[0], current[0]))
        y1, y2 = sorted((origin[1], current[1]))
        self.set_selection(
            self.candle_indices_in(x1, y1, x2, y2),
            self.box_from_canvas(origin, current),
        )
        return True

    def finish_roi(self, event: tk.Event) -> None:
        origin = self._box_origin
        self._box_origin = None
        if origin is None or self._press_position is None:
            return
        press_x, press_y = self._press_position
        if abs(event.x - press_x) + abs(event.y - press_y) <= self.click_drag_threshold:
            self.clear_gesture_state()
            return
        release_x = self.canvas.canvasx(event.x)
        entry_index = self.index_at_chart_x(origin[0])
        exit_index = self.index_at_chart_x(release_x)
        entry_row = self.price_data[entry_index]
        exit_row = self.price_data[exit_index]
        self.roi_results = []
        for (_, entry_abbr, entry_col), (_, exit_abbr, exit_col) in itertools.product(
            self.roi_price_fields, repeat=2
        ):
            entry_price, exit_price = entry_row[entry_col], exit_row[exit_col]
            label = f"ent({entry_abbr}):ext({exit_abbr}) -> "
            if entry_price == 0:
                self.roi_results.append((label, None))
            else:
                percent = (exit_price - entry_price) / entry_price * 100
                self.roi_results.append((label, percent))
        # Highest ROI first; rows without a percentage go last.
        self.roi_results.sort(key=lambda result: (result[1] is None, -(result[1] or 0)))
        self.roi_header = (
            f"Entry: {self.date_at(entry_index)}  Exit: {self.date_at(exit_index)}"
        )
        x1, x2 = sorted((origin[0], release_x))
        self._roi_span = self.span_from_canvas(origin[0], release_x)
        self.set_selection(
            self.candle_indices_in(x1, 0, x2, self.chart_grid_space_y), None
        )

    def index_at_chart_x(self, chart_x: float) -> int:
        # Clamped so a drag that starts or ends beyond the data still has a candle.
        base_x = chart_x / self._scale_x
        index = round((base_x - self.chart_padding_x) / self.chart_grid_divider_v)
        return min(max(index, 0), len(self.price_data) - 1)

    def date_at(self, index: int) -> str:
        return "-".join(self.price_data[index][0])

    def set_selection(self, indices: Set[int], box: Optional[Tuple[float, float, float, float]]) -> None:
        changed = self.selected_indices ^ indices
        self.selected_indices = set(indices)
        self._selection_box = box
        self.restyle_candles(changed)
        self.clear_selection_box()
        self.draw_overlays()
        self.refresh_info_label()

    def refresh_info_label(self) -> None:
        if self.roi_mode:
            self.candle_info_label.place_forget()
            if self.roi_results is None:
                self.roi_panel.place_forget()
            else:
                self.render_roi_panel()
                self.roi_panel.place(relx=1.0, x=-8, y=8, anchor="ne")
                self.roi_panel.lift()
            self.place_mode_label()
        elif self.selected_indices:
            self.roi_panel.place_forget()
            self.show_selection_summary()
        else:
            self.roi_panel.place_forget()
            self.candle_info_label.place_forget()

    def render_roi_panel(self) -> None:
        theme = self.get_theme()
        self.roi_panel.configure(bg=theme["canvas"])
        header = "" if self.roi_header is None else self.roi_header
        self.roi_header_label.configure(text=header, bg=theme["canvas"], fg=theme["ink"])
        results = self.roi_results
        for index, (name_label, value_label) in enumerate(self.roi_row_labels):
            name_label.configure(bg=theme["canvas"], fg=theme["ink"])
            if results is None:
                name_text, text, color = "", "", theme["ink"]
            else:
                name_text, percent = results[index]
                if percent is None:
                    text, color = "n/a", theme["ink"]
                else:
                    text = f"{percent:+.2f}%"
                    if percent > 0:
                        color = theme["gain"]
                    elif percent < 0:
                        color = theme["loss"]
                    else:
                        color = theme["ink"]
            name_label.configure(text=name_text)
            value_label.configure(text=text, bg=theme["canvas"], fg=color)

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
        self.window.bind("<Escape>", lambda _event: self.exit_modes())
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
        self.fit_chart_to_canvas(event.width, event.height)

    def fit_chart_to_canvas(self, width: int, height: int) -> None:
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