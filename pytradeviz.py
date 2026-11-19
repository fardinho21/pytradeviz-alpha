from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
import copy
import csv
import itertools
import os
import platform
import dataclasses
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Set, Tuple
from candle import Candle
from cursors import MOVE_CURSOR, POINTING_HAND, closed_hand_candidates, first_supported_cursor
import datetime as datetime
import math
from indicators import (
    BOLLINGER_MULTIPLIER, BOLLINGER_PERIOD, BOLLINGER_SETTING_FIELDS, INDICATOR_SETTING_FIELDS,
    CLOSE_COLUMN, Indicators, SMA_PERIODS, HIGH_COLUMN, LOW_COLUMN, WILLIAMS_R_CANVAS_OFFSET,
    band_intersects,
    default_indicator_settings, rsi_crosses_level, validate_bollinger_settings,
    validate_indicator_settings,
)
from breakout import (
    ATR_REJECTION, HORIZONS, REJECTION_RULES, BreakoutStudy, Odds,
)
from levels_help import LEVELS_HELP
from indicators_help import (
    BOLLINGER_DETAILED_HELP, INDICATOR_DETAILED_HELP, INDICATOR_HELP, TREND_DETAILED_HELP,
)
from sr_popups import SRPopup, popup_bounds
from drawings import (
    BOX, DASHED, DOTTED, FIB, FILL_STIPPLE, LINE, SEGMENT, SEGMENT_CIRCLE_RADIUS, SOLID,
    TOOLBOX_FADE_STIPPLE,
    STYLE_DASHES, Drawing, Point, ToolKey, Toolbox, clip_line, complementary_color, fib_level_ys, fill_applicable,
    hit_test, toolbox_layout,
)
from levels import (
    SUPPORT, WINDOW_LOOKBACKS, LevelFinder, LevelSettings, Segment, merge_crowded_segments,
)
from labeled_selections import (
    EXPORT_DIRECTORY, MOVING_AVERAGE_FIELDS, Selections, export_path, merge_selections,
    read_selections, write_selections,
)
from data_window import data_window_days, range_difference, row_ordinal, window_index_range
from paginated_price_data import PaginatedPriceData
from strategies import (
    Trade, is_price_text, is_roi_text, is_stop_loss_text, positional_levels, positional_trades,
    price_text, stop_price_text, target_price_text,
)
from timeframes import (
    DAILY, TIMEFRAMES, candle_ids, candle_last_rows, shows_day_labels, timeframe_rows,
)
from trend import (
    DOWN, SIDEWAYS, TREND_SETTING_FIELDS, UP, default_trend_settings, layered_trend_details,
    validate_trend_settings,
)

DATA_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Series that the indicator canvas can show. The first is shown when a file is opened.
INDICATOR_MODES: Tuple[str, ...] = ("RSI", "ADX", "STOSC", "W%R")
INDICATOR_TITLES: Dict[str, str] = {
    "RSI": "Relative Strength Index (RSI)",
    "ADX": "Avg. Directional Index (ADX)",
    "STOSC": "Stochastic Oscillator (STOSC)",
    "W%R": "Williams %R (W%R)",
}
# Tags of everything drawn on the indicator canvas, so a redraw can clear all of it.
INDICATOR_SERIES_TAGS: Tuple[str, ...] = ("rsi", "adx", "stoch", "willr", "indicator_level")


def format_setting_value(value: float) -> str:
    """Show whole numbers without a trailing .0 in the settings windows."""
    return str(int(value)) if float(value).is_integer() else str(value)
# Size and spacing of the RSI/ADX/STOSC/W%R toggle boxes at the top left of the indicator canvas.
INDICATOR_TOGGLE_MARGIN = 4
# Toggle boxes are at least this wide, and widen to fit their label.
INDICATOR_TOGGLE_MIN_WIDTH = 40
INDICATOR_TOGGLE_PADDING = 6
INDICATOR_TOGGLE_HEIGHT = 18
INDICATOR_TOGGLE_GAP = 4
# The Info box sits at the right edge of the same row and opens the indicator help window.
INDICATOR_INFO_LABEL = "Info"
INDICATOR_INFO_WIDTH = 44
# The TREND box sits at the bottom left of the price chart and uses the same box size as the toggles.
TREND_TOGGLE_LABEL = "TREND"
# How strong the trend shading is: 0 is invisible and 1 is the full gain or loss colour.
TREND_SHADE_STRENGTH = 0.15


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


def default_trend_applied() -> Dict[str, Any]:
    """Trend shading starts off, with the labeler's default settings and volume left out."""
    return {"enabled": False, "include_volume": False, **default_trend_settings()}


@dataclasses.dataclass
class ChartTabState:
    """What a time-frame tab remembers while another tab is shown."""
    drawings: Tuple[Drawing, ...] = ()
    draw_history: Tuple[Tuple[Drawing, ...], ...] = ()
    sma_applied: Dict[int, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    bollinger_applied: Dict[str, Any] = dataclasses.field(default_factory=dict)
    trend_applied: Dict[str, Any] = dataclasses.field(default_factory=default_trend_applied)
    levels_applied: Dict[str, Any] = dataclasses.field(default_factory=dict)
    indicator_settings: Dict[str, Dict[str, Any]] = dataclasses.field(
        default_factory=default_indicator_settings)
    zoom_level: float = 1.0
    candle_height_scale: float = 1.0
    # Left and top scroll positions as fractions of the scroll region. None means centered.
    xview: float = 0.0
    yview: Optional[float] = None


class PyTradeViz:
    # Candle indexes whose items are shown, as (first, last) inclusive. See apply_data_window.
    _applied_window: Tuple[int, int] = (0, -1)
    _ordinals_cache: Optional[Tuple[Any, List[int]]] = None

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
        "gain": "#1a7f37", "loss": "#cf222e", "sr_unavailable": "#f4c7c3",
    }
    dark_theme: Dict[str, str] = {
        "canvas": "black", "ink": "white", "grid": "#4a4a4a",
        "crosshair": "#f4a261", "crosshair_text": "black",
        "selection": "#e0894f", "highlight": "#f4a261",
        "gain": "#3fb950", "loss": "#ff7b72", "sr_unavailable": "#4d2a2a",
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
        "1M": "Blue", "2M": "Orange", "3M": "Green", "6M": "Violet",
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
    min_price_label_gap: float = 14.0 #px between visible price labels
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
    load_all_button: ttk.Button
    load_frame: ttk.Frame
    dark_mode_button: ttk.Button
    theme_button_frame: ttk.Frame
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
    # Candles that trades of a strategy test were made on. They are highlighted like the
    # selection for as long as the results of the test are open.
    trade_indices: Set[int]
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
    # Support/resistance mode: click a candle to pick a window, then its levels are drawn.
    sr_mode: bool = False
    sr_button: ttk.Button
    sr_color_name: str = "Orange"
    sr_window_labels: Tuple[str, ...] = ("1M", "2M", "3M", "6M")
    # Candle the popups belong to, the popups, and the (candle, window) being drawn.
    _sr_popup_index: Optional[int] = None
    _sr_popups: Tuple[SRPopup, ...] = ()
    _sr_levels: Optional[Tuple[int, str]] = None
    _sr_items: Tuple[int, ...] = ()
    _sr_popup_items: Tuple[int, ...] = ()
    # Draw mode. Drawings are stored in chart units so they stay put when the chart moves.
    draw_mode: bool = False
    draw_button: ttk.Button
    draw_icon: Any
    draw_color_name: str = "Blue"
    draw_tool: Optional[str] = None
    draw_style: str = SOLID
    draw_filled: bool = False
    drawings: Tuple[Drawing, ...] = ()
    _draw_history: Tuple[Tuple[Drawing, ...], ...] = ()
    _draw_next_id: int = 1
    _draw_selected: Optional[int] = None
    _draw_gesture: Optional[Dict[str, Any]] = None
    _toolbox: Optional[Toolbox] = None
    # Where the user dragged the toolbox, as its (left, top) from the top-left of the view.
    # None is the default bottom-right corner. Kept for the session, across tabs and files.
    _toolbox_position: Optional[Point] = None
    # Cursor shown while a canvas is dragged to scroll the chart: the closed fist where Tk has
    # one, resolved at start-up. The canvas showing it is remembered until the button is released.
    drag_cursor: str = MOVE_CURSOR
    _drag_cursor_widget: Optional[tk.Canvas] = None
    # The series drawn on the indicator canvas, one of INDICATOR_MODES.
    indicator_mode: str = "RSI"
    # Toggle box bounds in indicator canvas coordinates, keyed by mode.
    _indicator_toggle_boxes: Dict[str, Tuple[float, float, float, float]] = {}
    # Info box bounds in indicator canvas coordinates, set when the overlay is drawn.
    _indicator_info_box: Optional[Tuple[float, float, float, float]] = None
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
        # Loaded daily rows feed every time-frame tab. On the daily tab the charted rows are this same list.
        self._daily_rows = self.price_data
        self.active_timeframe = DAILY
        self._tab_states: Dict[str, ChartTabState] = {}
        self.selected_indices = set()
        self.trade_indices = set()
        self.labeled_selections = {}
        self.data_source = data_source
        # Parameters for each indicator; each timeframe tab keeps its own copy.
        self.indicator_settings: Dict[str, Dict[str, Any]] = default_indicator_settings()
        self.indicators_object = Indicators()
        self.indicators_object.set_price_data(self.price_data)
        self.indicators_object.calculate_RSI_incremental(self.indicator_settings["RSI"]["period"])
        # Applied simple moving average settings, keyed by period.
        self.sma_applied: Dict[int, Dict[str, Any]] = self.default_sma_applied()
        self._sma_items: List[int] = []
        # Bollinger Bands settings. The period and multiplier are kept per tab, like the indicator settings.
        self.bollinger_applied: Dict[str, Any] = self.default_bollinger_applied()
        self._bollinger_items: List[int] = []
        # Trend shading settings, kept per tab like the others.
        self.trend_applied: Dict[str, Any] = default_trend_applied()
        self._trend_items: List[int] = []
        self._trend_cache: Optional[Tuple[Tuple[Any, ...], List[Tuple[Optional[str], Optional[float]]]]] = None
        # Support and resistance settings. Each window label has its own display settings.
        self.levels_applied: Dict[str, Any] = self.default_levels_applied()
        self._levels_items: List[int] = []
        # Finder, per-window segments and breakout studies, rebuilt when the rows or
        # level settings change. Studies are keyed by (window, horizon, rejection).
        self._levels_cache: Optional[Tuple[
            Tuple[int, LevelSettings], LevelFinder, Dict[str, List[Segment]],
            Dict[Tuple[str, int, str], BreakoutStudy],
        ]] = None
        # Candle index of each daily row for the active tab, and the last daily row of each candle.
        self._timeframe_map_cache: Optional[Tuple[Tuple[str, int], List[int], List[int]]] = None

        self.calculate_grid_space_x(price_data_object)
        self._base_chart_width = self.chart_grid_space_x
        self.calculate_price_range()

        #set up window and frames
        self.initialize_window(tk)
        self.drag_cursor = first_supported_cursor(self.window, closed_hand_candidates())
        self.initialize_menu_bar(tk)

        #set up frames
        self.initialize_frames(ttk)

        # set up canvas
        self.initialize_canvases(tk)
        self.initialize_candle_info(tk)
        self.initialize_trend_toggle(tk)
        self.initialize_no_data_label(tk)
        self.initialize_ticker_label(tk)

        # set up scrollbars
        self.initialize_scrollbars(ttk, tk)
        self.initialize_dark_mode_button(ttk)
        self.initialize_select_mode_button(ttk, tk)
        self.initialize_draw_button(ttk, tk)
        self.initialize_fib_button(ttk)
        self.initialize_timeframe_bar(ttk)
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
        self.update_timeframe_buttons()

        #set price data for indicators_objec 

    def initialize_window(self, tk: ModuleType) -> None:
        self.window = tk.Tk()
        self.window.configure(bg=self.window_color)
        self.window.title("PyTradeViz - Alpha")
        self.window.geometry(self.window_geo)
        self.window.minsize(self.window_min_width, self.window_min_height)
        self.window.resizable(True, True)
        # Every button and drop-down menu made from now on, in this window and in the settings
        # windows, shows the pointing hand. The menubar itself is set in initialize_menu_bar.
        for pattern in ("*Button.cursor", "*TButton.cursor", "*Menu.cursor"):
            self.window.option_add(pattern, POINTING_HAND)

    def initialize_menu_bar(self, tk: ModuleType) -> None:
        self.menu_bar = tk.Menu(self.window, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=self.initialize_file_menu(tk))
        self.menu_bar.add_cascade(label="Indicators", menu=self.initialize_indicators_menu(tk))
        self.menu_bar.add_cascade(label="Strategies", menu=self.initialize_strategies_menu(tk))
        self.menu_bar.add_command(label="Data", command=lambda: self.open_data_window(tk))
        self.menu_bar.add_command(label="Reset", command=lambda: self.open_reset_window(tk))
        self.window.configure(menu=self.menu_bar)
        # Attaching the bar resets its cursor, so the pointing hand is set afterwards. Tk passes
        # it on to the copy of the bar that it draws along the top of the window.
        self.menu_bar.configure(cursor=POINTING_HAND)

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
        self._daily_rows = rows
        self.data_source = data_source
        self.active_timeframe = DAILY
        # Every tab belongs to the loaded data, so the tab memories start over with the file.
        self._tab_states = {}
        state = self.inherited_tab_state()
        self.load_tab_state(state)
        self._tab_states[DAILY] = state
        self.build_chart(rows, state)

    def default_sma_applied(self) -> Dict[int, Dict[str, Any]]:
        return {
            period: {"enabled": False, "hi_lo": False, "style": "Solid",
                     "color": self.sma_default_colors[period]}
            for period in SMA_PERIODS
        }

    def default_bollinger_applied(self) -> Dict[str, Any]:
        return {
            "enabled": False, "style": "Solid", "color": "Green",
            "period": BOLLINGER_PERIOD, "multiplier": BOLLINGER_MULTIPLIER,
        }

    def default_levels_applied(self) -> Dict[str, Any]:
        return {
            "mode": "Causal",
            "settings": LevelSettings(),
            "horizon": HORIZONS[-1],
            "rejection": ATR_REJECTION,
            "windows": {
                label: {
                    "enabled": False,
                    "color": self.levels_default_colors[label],
                }
                for label in WINDOW_LOOKBACKS
            },
        }

    def default_tab_state(self, view: Optional[ChartTabState] = None) -> ChartTabState:
        """A tab with every indicator at its default and nothing drawn.

        The zoom and scroll position of view, if given, are kept.
        """
        state = ChartTabState(
            sma_applied=self.default_sma_applied(),
            bollinger_applied=self.default_bollinger_applied(),
            trend_applied=default_trend_applied(),
            levels_applied=self.default_levels_applied(),
            indicator_settings=default_indicator_settings(),
        )
        if view is not None:
            state.zoom_level = view.zoom_level
            state.candle_height_scale = view.candle_height_scale
            state.xview = view.xview
            state.yview = view.yview
        return state

    def reset_chart_configuration(self) -> None:
        """Put every indicator back to its default and clear drawings on all tabs. The loaded data stays."""
        has_data = bool(self._daily_rows)
        if has_data:
            self.store_tab_state()
        self.reset_interaction_state()
        self.indicator_mode = "RSI"
        for label, state in list(self._tab_states.items()):
            self._tab_states[label] = self.default_tab_state(view=state)
        if has_data:
            state = self._tab_states[self.active_timeframe]
            self.load_tab_state(state)
            self.build_chart(self.price_data, state)
        else:
            self.load_tab_state(self.default_tab_state())

    def inherited_tab_state(self) -> ChartTabState:
        """Starting state for a tab: copies of the current indicator settings and a default view."""
        return ChartTabState(
            sma_applied=copy.deepcopy(self.sma_applied),
            bollinger_applied=copy.deepcopy(self.bollinger_applied),
            trend_applied=copy.deepcopy(self.trend_applied),
            levels_applied=copy.deepcopy(self.levels_applied),
            indicator_settings=copy.deepcopy(self.indicator_settings),
        )

    def capture_tab_state(self) -> ChartTabState:
        return ChartTabState(
            drawings=self.drawings,
            draw_history=self._draw_history,
            sma_applied=self.sma_applied,
            bollinger_applied=self.bollinger_applied,
            trend_applied=self.trend_applied,
            levels_applied=self.levels_applied,
            indicator_settings=self.indicator_settings,
            zoom_level=self.zoom_level,
            candle_height_scale=self.candle_height_scale,
            xview=self.canvas.xview()[0],
            yview=self.canvas.yview()[0],
        )

    def store_tab_state(self) -> None:
        self._tab_states[self.active_timeframe] = self.capture_tab_state()

    def load_tab_state(self, state: ChartTabState) -> None:
        """Make the state's drawings and indicator settings the live ones."""
        self.drawings = state.drawings
        self._draw_history = state.draw_history
        self.sma_applied = state.sma_applied
        self.bollinger_applied = state.bollinger_applied
        self.trend_applied = state.trend_applied
        self.levels_applied = state.levels_applied
        self.indicator_settings = state.indicator_settings

    def select_timeframe(self, label: str) -> None:
        if label == self.active_timeframe or label not in TIMEFRAMES or not self._daily_rows:
            return
        self.store_tab_state()
        self.reset_interaction_state()
        self.active_timeframe = label
        state = self._tab_states.get(label)
        if state is None:
            state = self.inherited_tab_state()
            self._tab_states[label] = state
        self.load_tab_state(state)
        self.build_chart(timeframe_rows(self._daily_rows, label), state)

    def build_chart(
        self, rows: List[List[Any]], state: ChartTabState, keep_left: Optional[float] = None
    ) -> None:
        """Draw rows as the chart, then restore the zoom and scroll position saved in state.

        keep_left is an absolute horizontal position at the current zoom, used when rows are
        appended so the view does not jump.
        """
        for canvas in (self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators):
            canvas.delete("all")
        self._sma_items = []
        self._bollinger_items = []
        self._trend_items = []
        self._trend_cache = None
        self._levels_items = []
        self._levels_cache = None
        self._timeframe_map_cache = None
        self._applied_window = (0, -1)

        self.price_data_object = {"price_data": rows}
        self.price_data = rows
        self.indicators_object.set_price_data(rows)
        self.indicators_object.calculate_RSI_full(self.indicator_settings["RSI"]["period"])

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
        self.apply_view_zoom(state.zoom_level, state.candle_height_scale)
        self.update_scroll_regions()
        if keep_left is None:
            self.canvas.xview_moveto(state.xview)
        else:
            self.canvas.xview_moveto(keep_left / self.chart_grid_space_x)
        if state.yview is None:
            self.center_vertical_view()
        else:
            self.canvas.yview_moveto(state.yview)
        self.update_load_more_button()
        self.update_no_data_label()
        self.update_ticker_label()
        self.update_timeframe_buttons()
        self.draw_overlays()

    def apply_view_zoom(self, zoom_level: float, candle_height_scale: float) -> None:
        """Apply a saved zoom and candle height to a chart that was just built and fitted.

        The factors match what zoom_chart and scale_candle_height apply to the canvases.
        """
        x_factor = zoom_level
        y_factor = zoom_level * candle_height_scale
        if x_factor != 1 or y_factor != 1:
            self.canvas.scale("all", 0, 0, x_factor, y_factor)
            self.canvas_price.scale("all", 0, 0, 1, y_factor)
            self.canvas_date.scale("all", 0, 0, x_factor, 1)
            self.canvas_indicators.scale("all", 0, 0, x_factor, 1)
            self.chart_grid_space_x *= x_factor
            self.chart_grid_space_y *= y_factor
            self._scale_x *= x_factor
            self._scale_y *= y_factor
        self.zoom_level = zoom_level
        self.candle_height_scale = candle_height_scale

    def initialize_timeframe_bar(self, ttk: ModuleType) -> None:
        # Its own grid row above the chart, right-aligned so the tabs sit at the top right.
        self.timeframe_bar = ttk.Frame(self.window)
        self.timeframe_buttons: Dict[str, Any] = {}
        for column, label in enumerate(TIMEFRAMES):
            button = ttk.Button(
                self.timeframe_bar, text=label, width=0,
                command=lambda label=label: self.select_timeframe(label),
            )
            button.grid(row=0, column=column, sticky="nse", padx=(4, 0) if column else 0)
            self.timeframe_buttons[label] = button
        self.update_timeframe_buttons()

    def update_timeframe_buttons(self) -> None:
        has_data = bool(self._daily_rows)
        for label, button in self.timeframe_buttons.items():
            button.state(["pressed" if label == self.active_timeframe else "!pressed"])
            button.state(["!disabled" if has_data else "disabled"])

    def reset_interaction_state(self) -> None:
        self.selection_mode = self.roi_mode = self.export_mode = self.sr_mode = False
        self.draw_mode = False
        self.clear_draw_state()
        self.clear_sr_state()
        self.selected_indices = set()
        self.trade_indices = set()
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
        has_more = self.data_source is not None and self.data_source.has_more
        self.set_load_buttons_enabled(has_more)

    def set_load_buttons_enabled(self, enabled: bool) -> None:
        state = "!disabled" if enabled else "disabled"
        for button in (self.load_more_button, self.load_all_button):
            button.state([state])

    def open_reset_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Reset")
        tk.Label(
            window, justify="left", wraplength=360, text=(
                "Reset every indicator to its default settings and clear all drawings "
                "on every timeframe. The loaded data is kept."
            ),
        ).pack(fill="x", padx=12, pady=(12, 0))
        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(
            buttons, text="Confirm", width=8,
            command=lambda: self.confirm_reset(window),
        ).pack(side="left")
        tk.Button(buttons, text="Cancel", width=8, command=window.destroy).pack(side="left", padx=(8, 0))

    def confirm_reset(self, window: Any) -> None:
        window.destroy()
        self.reset_chart_configuration()

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

    def initialize_strategies_menu(self, tk: ModuleType) -> Any:
        strategies_menu = tk.Menu(self.menu_bar, tearoff=0)
        strategies_menu.add_command(
            label="Positional", command=lambda: self.open_positional_window(tk),
        )
        # Indicator based strategies are not built yet, so this item does nothing.
        strategies_menu.add_command(label="Indicator Based")
        return strategies_menu

    def open_positional_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Positional Strategy")
        self.build_positional_content(tk, window)

    def build_positional_content(self, tk: ModuleType, window: Any) -> None:
        entry_price, roi, target, stop_loss, stop = (tk.StringVar(window) for _ in range(5))

        def show_prices(*_: Any) -> None:
            target.set(target_price_text(entry_price.get(), roi.get()))
            stop.set(stop_price_text(entry_price.get(), stop_loss.get()))

        # The target and stop prices follow every change to the other three boxes. The trace
        # command belongs to the window, so closing the window releases the variables.
        # Variable.trace_add would keep them alive until the program exits.
        show = window.register(show_prices)
        for variable in (entry_price, roi, stop_loss):
            window.tk.call("trace", "add", "variable", str(variable), "write", show)

        # The two rows describe the order. The entry price, ROI and stop loss boxes refuse any
        # edit that would leave something other than a number, and the target and stop prices
        # cannot be edited.
        order = tk.Frame(window)
        order.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(order, text="Entry price").grid(row=0, column=0, sticky="w")
        entry_price_box = tk.Entry(
            order, textvariable=entry_price, width=14,
            validate="key", validatecommand=(window.register(is_price_text), "%P"),
        )
        entry_price_box.grid(row=0, column=1, padx=(6, 16))
        tk.Label(order, text="ROI (%)").grid(row=0, column=2, sticky="w")
        tk.Entry(
            order, textvariable=roi, width=8,
            validate="key", validatecommand=(window.register(is_roi_text), "%P"),
        ).grid(row=0, column=3, padx=(6, 16))
        tk.Label(order, text="Target price").grid(row=0, column=4, sticky="w")
        tk.Entry(order, textvariable=target, width=14, state="readonly").grid(
            row=0, column=5, padx=(6, 0))
        # The stop loss is under the ROI, and the stop price under the target price.
        tk.Label(order, text="Stop loss (%)").grid(row=1, column=2, sticky="w", pady=(8, 0))
        tk.Entry(
            order, textvariable=stop_loss, width=8,
            validate="key", validatecommand=(window.register(is_stop_loss_text), "%P"),
        ).grid(row=1, column=3, padx=(6, 16), pady=(8, 0))
        tk.Label(order, text="Stop price").grid(row=1, column=4, sticky="w", pady=(8, 0))
        tk.Entry(order, textvariable=stop, width=14, state="readonly").grid(
            row=1, column=5, padx=(6, 0), pady=(8, 0))
        entry_price_box.focus_set()

        def reset() -> None:
            # Emptying the three boxes empties the target and stop prices as well.
            for variable in (entry_price, roi, stop_loss):
                variable.set("")
            # The boxes are gone when this runs because the window is closing.
            if entry_price_box.winfo_exists():
                entry_price_box.focus_set()

        testing = False

        def test() -> None:
            # Showing the results runs the event loop until their window appears, and a second
            # click on Test in that time must not start another test.
            nonlocal testing
            if testing:
                return
            testing = True
            try:
                self.run_positional_test(
                    tk, window, entry_price.get(), roi.get(), stop_loss.get(), reset)
            finally:
                testing = False

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Test", width=8, command=test).pack(side="left")
        tk.Button(buttons, text="Cancel", width=8, command=window.destroy).pack(side="left", padx=(8, 0))

    def run_positional_test(
        self, tk: ModuleType, window: Any, entry_price_text: str, roi_text: str,
        stop_loss_text: str, reset: Callable[[], None],
    ) -> None:
        """Test the order typed in the Positional window on the loaded daily candles, then list its trades.

        ``reset`` empties the boxes of the window. It is called when the list is closed.
        """
        if not self._daily_rows:
            messagebox.showerror("Unable to test", "No price data is loaded.", parent=window)
            return
        try:
            entry_price, target, stop = positional_levels(entry_price_text, roi_text, stop_loss_text)
        except ValueError as error:
            messagebox.showerror("Invalid setting", str(error), parent=window)
            return
        trades = positional_trades(self._daily_rows, entry_price, target, stop)
        self.open_positional_results_window(tk, window, trades, reset)

    def open_positional_results_window(
        self, tk: ModuleType, parent: Any, trades: List[Trade], reset: Callable[[], None],
    ) -> None:
        """List the trades of a positional test and highlight their candles until the list is closed."""
        window = self.open_modal_window(tk, "Positional Strategy Results", parent=parent)
        rows = self._daily_rows

        def date(index: int) -> str:
            return "-".join(rows[index][0])

        tested = f"{len(rows)} daily candles tested, from {date(0)} to {date(-1)}."
        if trades:
            summary = f"{len(trades)} trade{'' if len(trades) == 1 else 's'}. {tested}"
            hint = "Select a trade to show it on the chart."
        else:
            summary = f"No trades. {tested}"
            hint = "No candle reached the entry price."
        tk.Label(window, text=f"{summary}\n{hint}", justify="left", anchor="w").pack(
            fill="x", padx=12, pady=(12, 0))

        listing = tk.Frame(window)
        listing.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        columns = ("Entry date", "Entry price", "Sell date", "Sell price")
        tree = ttk.Treeview(listing, columns=columns, show="headings", height=12, selectmode="browse")
        for column in columns:
            tree.heading(column, text=column, anchor="w")
            tree.column(column, width=130, anchor="w")
        scrollbar = tk.Scrollbar(listing, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        for number, trade in enumerate(trades):
            sold = trade.sell_index is not None
            tree.insert("", "end", iid=str(number), values=(
                date(trade.buy_index), price_text(trade.buy_price),
                date(trade.sell_index) if sold else "Still open",
                price_text(trade.sell_price) if sold else "",
            ))
        tk.Button(window, text="Close", width=8, command=window.destroy).pack(pady=12)

        # The candles of the active tab that hold the days each trade was bought and sold on.
        ids, _ = self.timeframe_map()
        candles = [
            (ids[trade.buy_index], None if trade.sell_index is None else ids[trade.sell_index])
            for trade in trades
        ]

        def show_selected(_event: Any) -> None:
            for item in tree.selection():
                buy, sell = candles[int(item)]
                self.show_trade_on_chart(
                    buy, sell, float(trades[int(item)].buy_price), (parent, window))

        def close(event: Any) -> None:
            if event.widget is not window:
                return
            # The chart is gone before this window when the whole program is closing.
            if self.canvas.winfo_exists():
                self.set_trade_highlights(set())
            reset()
            self.return_grab(event, window, parent)

        tree.bind("<<TreeviewSelect>>", show_selected)
        window.bind("<Destroy>", close)
        # Only the trades are highlighted while the list is open, so a selection made on the
        # chart is dropped first.
        self._roi_span = None
        self.roi_header = None
        self.roi_results = None
        self.set_selection(set(), None)
        self.set_trade_highlights(
            {index for pair in candles for index in pair if index is not None})
        if trades:
            # The first trade is shown beside this window, which needs its full size for that.
            window.update_idletasks()
            tree.selection_set("0")
            tree.focus("0")
            tree.focus_set()

    def set_trade_highlights(self, indices: Set[int]) -> None:
        changed = self.trade_indices ^ indices
        self.trade_indices = set(indices)
        self.restyle_candles(changed)

    def show_trade_on_chart(
        self, buy: int, sell: Optional[int], entry_price: float, windows: Sequence[Any],
    ) -> None:
        """Scroll the chart to the candles that a trade was bought and sold on.

        The two are centred in the part of the chart that ``windows`` leave uncovered, when
        both fit there. Candles too far apart for that leave the buy candle centred at the
        entry price, and candles too tall for the chart stay side by side at the entry price.
        """
        left, right = self.uncovered_chart_span(windows)
        height = self.canvas.winfo_height()
        x = self.candle_x(buy)
        y = self.price_to_y(entry_price)
        if sell is not None:
            sell_x = self.candle_x(sell)
            candle_width = self.chart_grid_divider_v * self._scale_x
            if sell_x - x + candle_width <= right - left:
                x = (x + sell_x) / 2
                rows = (self.price_data[buy], self.price_data[sell])
                top = self.price_to_y(max(row[2] for row in rows))
                bottom = self.price_to_y(min(row[3] for row in rows))
                if bottom - top <= height:
                    y = (top + bottom) / 2
        # The scroll commands of the chart redraw its overlays for the new view.
        self.canvas.xview_moveto((x - (left + right) / 2) / self.chart_grid_space_x)
        self.canvas.yview_moveto((y - height / 2) / self.chart_grid_space_y)

    def uncovered_chart_span(self, windows: Sequence[Any]) -> Tuple[float, float]:
        """The left and right x, in the chart view, of its widest part that none of ``windows`` lies over.

        It is the whole view when they leave no room for a candle.
        """
        left, top = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        covered = sorted(
            (window.winfo_rootx() - left, window.winfo_rootx() - left + window.winfo_width())
            for window in windows
            if window.winfo_rooty() < top + height and window.winfo_rooty() + window.winfo_height() > top
        )
        # Each gap runs from the furthest right edge so far to the left edge of the next window.
        gaps = []
        start = 0
        for first, last in covered + [(width, width)]:
            gaps.append((start, min(first, width)))
            start = max(start, last)
        gap_left, gap_right = max(gaps, key=lambda gap: gap[1] - gap[0])
        if gap_right - gap_left < self.chart_grid_divider_v * self._scale_x:
            return 0, width
        return gap_left, gap_right

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
        middle, upper, lower = self.indicators_object.calculate_bollinger(*self.bollinger_parameters())
        record["bollinger_middle"] = middle[index]
        record["bollinger_upper"] = upper[index]
        record["bollinger_lower"] = lower[index]
        previous_rsi = self.price_data[index - 1][5]["rsi"] if index > 0 else None
        record["top_bol_intersect"] = band_intersects(low, high, upper[index])
        record["btm_bol_intersect"] = band_intersects(low, high, lower[index])
        rsi_settings = self.indicator_settings["RSI"]
        record["rsi_os"] = rsi_crosses_level(previous_rsi, record["rsi"], rsi_settings["oversold"])
        record["rsi_ob"] = rsi_crosses_level(previous_rsi, record["rsi"], rsi_settings["overbought"])
        return record

    def initialize_indicators_menu(self, tk: ModuleType) -> Any:
        indicators_menu = tk.Menu(self.menu_bar, tearoff=0)
        moving_averages_menu = tk.Menu(indicators_menu, tearoff=0)
        for name in ("Exponential", "Simple"):
            moving_averages_menu.add_command(
                label=name, command=lambda name=name: self.open_moving_average_window(tk, name),
            )
        indicators_menu.add_cascade(label="Moving Averages", menu=moving_averages_menu)
        for mode in INDICATOR_MODES:
            indicators_menu.add_command(
                label=INDICATOR_TITLES[mode],
                command=lambda mode=mode: self.open_indicator_settings_window(tk, mode),
            )
        indicators_menu.add_command(
            label="Bollinger", command=lambda: self.open_bollinger_window(tk),
        )
        indicators_menu.add_command(
            label="Trend Identification", command=lambda: self.open_trend_window(tk),
        )
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

    def bollinger_parameters(self) -> Tuple[int, float]:
        return self.bollinger_applied["period"], self.bollinger_applied["multiplier"]

    def build_bollinger_content(self, tk: ModuleType, window: Any) -> None:
        # Edits are staged in these variables and only applied by the Apply button.
        applied = self.bollinger_applied
        staged: Dict[str, Any] = {
            "enabled": tk.BooleanVar(window, value=applied["enabled"]),
            "style": tk.StringVar(window, value=applied["style"]),
            "color": tk.StringVar(window, value=applied["color"]),
        }
        bands = tk.LabelFrame(window, text="Bands", padx=10, pady=6)
        bands.pack(fill="x", padx=12, pady=(12, 0))
        defaults = {"period": BOLLINGER_PERIOD, "multiplier": BOLLINGER_MULTIPLIER}
        for row, (key, label, _kind, _low, _high) in enumerate(BOLLINGER_SETTING_FIELDS):
            staged[key] = tk.StringVar(window, value=format_setting_value(applied[key]))
            tk.Label(bands, text=label).grid(row=row, column=0, sticky="w", pady=2)
            tk.Entry(bands, textvariable=staged[key], width=10).grid(
                row=row, column=1, sticky="w", padx=(12, 12), pady=2)
            tk.Label(bands, text=f"Default: {format_setting_value(defaults[key])}", fg="gray").grid(
                row=row, column=2, sticky="w", pady=2)

        display = tk.LabelFrame(window, text="Display", padx=10, pady=6)
        display.pack(fill="x", padx=12, pady=(12, 0))
        tk.Checkbutton(display, text="Show", variable=staged["enabled"]).grid(
            row=0, column=0, sticky="w")
        tk.Label(display, text="Style:").grid(row=1, column=0, sticky="w")
        for column, style in enumerate(self.sma_line_styles, start=1):
            tk.Radiobutton(display, text=style, value=style, variable=staged["style"]).grid(
                row=1, column=column, sticky="w")
        tk.Label(display, text="Color:").grid(row=2, column=0, sticky="w")
        for column, color in enumerate(self.sma_colors, start=1):
            tk.Radiobutton(display, text=color, value=color, variable=staged["color"]).grid(
                row=2, column=column, sticky="w")

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Close", width=8, command=window.destroy).pack(side="right")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_bollinger(window, staged),
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons, text="Help", width=8,
            command=lambda: self.show_help_window(
                tk, "Bollinger Bands Help", BOLLINGER_DETAILED_HELP, window),
        ).pack(side="left")

    def apply_bollinger(self, window: Any, staged: Dict[str, Any]) -> None:
        # Nothing changes unless the period and multiplier are valid, so Show and the style stay as they were.
        try:
            values = validate_bollinger_settings({key: staged[key].get() for key in ("period", "multiplier")})
        except ValueError as error:
            messagebox.showerror("Invalid setting", str(error), parent=window)
            return
        self.bollinger_applied = {
            "enabled": staged["enabled"].get(),
            "style": staged["style"].get(),
            "color": staged["color"].get(),
            **values,
        }
        # Showing the bands can widen the price scale, so the chart is rescaled to fit.
        old_upper, old_lower = self.price_upper, self.price_lower
        self.calculate_price_range()
        self.rescale_price_scale(old_upper, old_lower)
        self.draw_overlays()

    def open_indicator_settings_window(self, tk: ModuleType, mode: str) -> None:
        window = self.open_modal_window(tk, INDICATOR_TITLES[mode])
        self.build_indicator_settings_content(tk, window, mode)

    def build_indicator_settings_content(self, tk: ModuleType, window: Any, mode: str) -> None:
        # Entries are staged as text and only applied by the Apply button, which validates them first.
        applied = self.indicator_settings[mode]
        defaults = default_indicator_settings()[mode]
        staged: Dict[str, Any] = {}
        group = tk.LabelFrame(window, text=f"{INDICATOR_TITLES[mode]} settings", padx=10, pady=6)
        group.pack(fill="x", padx=12, pady=(12, 0))
        for row, (key, label, _kind, _low, _high) in enumerate(INDICATOR_SETTING_FIELDS[mode]):
            staged[key] = tk.StringVar(window, value=format_setting_value(applied[key]))
            tk.Label(group, text=label).grid(row=row, column=0, sticky="w", pady=2)
            tk.Entry(group, textvariable=staged[key], width=10).grid(
                row=row, column=1, sticky="w", padx=(12, 12), pady=2)
            tk.Label(group, text=f"Default: {format_setting_value(defaults[key])}", fg="gray").grid(
                row=row, column=2, sticky="w", pady=2)

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Cancel", width=8, command=window.destroy).pack(side="left")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_indicator_settings_from_window(window, mode, staged),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text="Help", width=8,
            command=lambda: self.show_help_window(
                tk, f"{INDICATOR_TITLES[mode]} Help", INDICATOR_DETAILED_HELP[mode], window),
        ).pack(side="left", padx=(8, 0))

    def apply_indicator_settings_from_window(self, window: Any, mode: str, staged: Dict[str, Any]) -> None:
        try:
            values = validate_indicator_settings(mode, {key: var.get() for key, var in staged.items()})
        except ValueError as error:
            messagebox.showerror("Invalid setting", str(error), parent=window)
            return
        self.apply_indicator_settings(mode, values)

    def apply_indicator_settings(self, mode: str, values: Dict[str, Any]) -> None:
        previous = self.indicator_settings[mode]
        self.indicator_settings[mode] = values
        # RSI is stored on each candle, so a new period means recomputing every candle.
        if mode == "RSI" and values["period"] != previous["period"] and self.indicators_object.price_data:
            self.indicators_object.calculate_RSI_full(values["period"])
        # Applying a setting shows its indicator on the canvas.
        self.indicator_mode = mode
        self.redraw_indicator_canvas()
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
                }
                for label, variables in staged["windows"].items()
            },
        }
        self.dismiss_sr_popups()
        for label, status in staged["status"].items():
            status.set(self.levels_status_text(label))
        self.draw_overlays()

    def levels_status_text(self, label: str) -> str:
        if not self._daily_rows:
            return "No price data loaded"
        finder, _, _ = self.levels_for_chart()
        last = len(self._daily_rows) - 1
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
        """Levels come from the daily rows on every tab, so they do not depend on the tab shown."""
        settings = self.levels_applied["settings"]
        key = (len(self._daily_rows or []), settings)
        if self._levels_cache is None or self._levels_cache[0] != key:
            self._levels_cache = (key, LevelFinder(self._daily_rows or [], settings), {}, {})
        return self._levels_cache[1], self._levels_cache[2], self._levels_cache[3]

    def breakout_study(self, label: str) -> BreakoutStudy:
        """Breakout odds for one window under the current horizon and rejection rule."""
        finder, _, studies = self.levels_for_chart()
        horizon = self.levels_applied["horizon"]
        rejection = self.levels_applied["rejection"]
        key = (label, horizon, rejection)
        if key not in studies:
            studies[key] = BreakoutStudy(self._daily_rows or [], finder, label, horizon, rejection)
        return studies[key]

    def timeframe_map(self) -> Tuple[List[int], List[int]]:
        """For the active tab: the candle of each daily row, and the last daily row of each candle."""
        key = (self.active_timeframe, len(self._daily_rows or []))
        if self._timeframe_map_cache is None or self._timeframe_map_cache[0] != key:
            ids = candle_ids(self._daily_rows or [], self.active_timeframe)
            self._timeframe_map_cache = (key, ids, candle_last_rows(ids))
        return self._timeframe_map_cache[1], self._timeframe_map_cache[2]

    def daily_index_for_candle(self, index: int) -> int:
        """The daily row a candle of the active tab is judged by: the last one it contains.

        Levels shown on a candle use only daily rows up to the candle's close.
        """
        _, last_rows = self.timeframe_map()
        return last_rows[min(max(index, 0), len(last_rows) - 1)]

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
        self.show_help_window(tk, "Support and Resistance Help", LEVELS_HELP, parent)

    def open_indicator_help(self, tk: ModuleType, parent: Any) -> None:
        self.show_help_window(tk, "Indicator Help", INDICATOR_HELP, parent)

    def show_help_window(
        self, tk: ModuleType, title: str,
        sections: Tuple[Tuple[str, Tuple[str, ...]], ...], parent: Any,
    ) -> None:
        help_window = self.open_modal_window(tk, title, parent=parent)
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
        for heading, paragraphs in sections:
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

        self.draw_indicator_levels()
        
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
        # The two load buttons share one grid cell, so ">>>" sits beside ">".
        self.load_frame = ttk.Frame(self.window)
        self.load_more_button = ttk.Button(
            self.load_frame, text=">", width=1, command=self.load_more_data
        )
        self.load_all_button = ttk.Button(
            self.load_frame, text=">|", width=3, command=self.load_all_data
        )
        self.load_frame.grid_rowconfigure(0, weight=1)
        self.load_more_button.grid(row=0, column=0, sticky="nsew")
        self.load_all_button.grid(row=0, column=1, sticky="nsew")
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
        self.window.grid_rowconfigure(1, weight=1)
        self.frame_canvas.grid_columnconfigure(0, weight=1)
        self.frame_canvas.grid_rowconfigure(0, weight=1)
        self.frame_canvas_price.grid_columnconfigure(0, weight=1)
        self.frame_canvas_price.grid_rowconfigure(0, weight=1)
        self.frame_canvas_date.grid_columnconfigure(0, weight=1)
        self.frame_canvas_indicators.grid_columnconfigure(0, weight=1)

        self.timeframe_bar.grid(row=0, column=0, columnspan=3, sticky="e", pady=(2, 0))
        self.frame_canvas.grid(row=1, column=0, sticky="nsew")
        self.frame_canvas_price.grid(row=1, column=1, sticky="nsew")
        self.frame_canvas_date.grid(row=2, column=0, sticky="ew")
        self.frame_canvas_indicators.grid(row=3, column=0, sticky="ew")
        self.bottom_bar.grid(row=4, column=0, sticky="ew")
        self.mode_button_frame.pack(side="right")
        self.scrollbar_horizontal.pack(side="left", fill="x", expand=True)
        self.load_frame.grid(row=3, column=1, sticky="nsw")
        self.theme_button_frame.grid(row=2, column=1, sticky="nsw")
        self.scrollbar_vertical.grid(row=1, column=2, sticky="ns")
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
        self.hide_outside_window("candle", start)

    def render_indicators(self, start: int = 0, tags: Tuple[str, ...] = ()) -> None:
        self.render_indicator_series(start, tags)
        self.hide_outside_window("ind", start)

    def render_indicator_series(self, start: int = 0, tags: Tuple[str, ...] = ()) -> None:
        ink = self.get_theme()["ink"]
        settings = self.indicator_settings
        if self.indicator_mode == "ADX":
            self.indicators_object.render_ADX(
                self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
                start=start, tags=("adx", "ink") + tags, fill=ink,
                period=settings["ADX"]["period"],
            )
            return
        if self.indicator_mode == "STOSC":
            self.indicators_object.render_STOCH(
                self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
                start=start, tags=("stoch", "ink") + tags, fill=ink,
                k_period=settings["STOSC"]["k_period"], d_period=settings["STOSC"]["d_period"],
            )
            return
        if self.indicator_mode == "W%R":
            self.indicators_object.render_WILLR(
                self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
                start=start, tags=("willr", "ink") + tags, fill=ink,
                period=settings["W%R"]["period"],
            )
            return
        self.indicators_object.render_RSI(
            self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
            start=start, tags=("rsi", "ink") + tags, fill=ink
        )

    def draw_indicator_levels(self) -> None:
        """Draw the reference lines for the active series on the indicator canvas."""
        canvas = self.canvas_indicators
        canvas.delete("indicator_level")
        width = self.chart_grid_space_x
        settings = self.indicator_settings[self.indicator_mode]
        # Values are plotted as 100 - value, so a level sits at 100 - level on the canvas.
        # Williams %R is shifted by WILLIAMS_R_CANVAS_OFFSET before plotting, so its levels are too.
        if self.indicator_mode == "ADX":
            y = 100 - settings["trend_level"]
            canvas.create_line(0, y, width, y, fill="gray", width=2, dash=(4, 4),
                               tags=("indicator_level",))
            return
        offset = WILLIAMS_R_CANVAS_OFFSET if self.indicator_mode == "W%R" else 0
        overbought, oversold = settings["overbought"], settings["oversold"]
        y_overbought = 100 - (overbought + offset)
        y_oversold = 100 - (oversold + offset)
        canvas.create_line(0, y_overbought, width, y_overbought, fill="orange",
                           width=2, tags=("indicator_level",))
        canvas.create_line(0, y_oversold, width, y_oversold, fill="blue",
                           width=2, tags=("indicator_level",))

    def redraw_indicator_canvas(self) -> None:
        for tag in INDICATOR_SERIES_TAGS:
            self.canvas_indicators.delete(tag)
        if self.indicators_object.price_data:
            self.render_indicators()
        self.draw_indicator_levels()

    def select_indicator_mode(self, mode: str) -> None:
        if mode == self.indicator_mode:
            return
        self.indicator_mode = mode
        self.redraw_indicator_canvas()
        self.draw_overlays()

    def indicator_toggle_at(self, event: tk.Event) -> Optional[str]:
        x = self.canvas_indicators.canvasx(event.x)
        for mode, (x1, y1, x2, y2) in self._indicator_toggle_boxes.items():
            if x1 <= x <= x2 and y1 <= event.y <= y2:
                return mode
        return None

    def on_indicators_press(self, event: tk.Event) -> None:
        # Start the scroll gesture first so a drag that begins on a button still scrolls cleanly.
        self.scroll_start(event)
        if self.indicator_info_at(event):
            self.open_indicator_help(tk, self.window)
            return
        mode = self.indicator_toggle_at(event)
        if mode is not None:
            self.select_indicator_mode(mode)

    def indicator_info_at(self, event: tk.Event) -> bool:
        if self._indicator_info_box is None:
            return False
        x1, y1, x2, y2 = self._indicator_info_box
        x = self.canvas_indicators.canvasx(event.x)
        return x1 <= x <= x2 and y1 <= event.y <= y2

    def draw_indicator_info_button(self) -> None:
        canvas = self.canvas_indicators
        canvas.delete("indicator_info")
        theme = self.get_theme()
        # The right edge of the visible part of the canvas, so the box stays pinned while scrolling.
        visible_width = canvas.winfo_width() or self.canvas_width
        x2 = canvas.canvasx(visible_width) - INDICATOR_TOGGLE_MARGIN
        x1 = x2 - INDICATOR_INFO_WIDTH
        top = INDICATOR_TOGGLE_MARGIN
        y2 = top + INDICATOR_TOGGLE_HEIGHT
        self._indicator_info_box = (x1, top, x2, y2)
        canvas.create_rectangle(
            x1, top, x2, y2, fill=theme["canvas"], outline=theme["ink"],
            tags=("indicator_info",)
        )
        canvas.create_text(
            (x1 + x2) / 2, (top + y2) / 2, text=INDICATOR_INFO_LABEL,
            fill=theme["ink"], tags=("indicator_info",)
        )

    def draw_indicator_toggles(self) -> None:
        canvas = self.canvas_indicators
        canvas.delete("indicator_toggle")
        theme = self.get_theme()
        left = canvas.canvasx(0) + INDICATOR_TOGGLE_MARGIN
        top = INDICATOR_TOGGLE_MARGIN
        self._indicator_toggle_boxes = {}
        font = tkfont.Font(root=self.window, name="TkDefaultFont", exists=True)
        x1 = left
        for mode in INDICATOR_MODES:
            width = max(INDICATOR_TOGGLE_MIN_WIDTH, font.measure(mode) + 2 * INDICATOR_TOGGLE_PADDING)
            x2 = x1 + width
            y2 = top + INDICATOR_TOGGLE_HEIGHT
            self._indicator_toggle_boxes[mode] = (x1, top, x2, y2)
            active = mode == self.indicator_mode
            canvas.create_rectangle(
                x1, top, x2, y2, fill=theme["ink"] if active else theme["canvas"],
                outline=theme["ink"], tags=("indicator_toggle",)
            )
            canvas.create_text(
                (x1 + x2) / 2, (top + y2) / 2, text=mode,
                fill=theme["canvas"] if active else theme["ink"], tags=("indicator_toggle",)
            )
            x1 = x2 + INDICATOR_TOGGLE_GAP

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
            band_range = self.indicators_object.bollinger_range(*self.bollinger_parameters())
            if band_range is not None:
                scale_lowest = min(scale_lowest, band_range[0])
                scale_highest = max(scale_highest, band_range[1])
        margin = max((scale_highest - scale_lowest) * 0.05, abs(scale_highest) * 0.01, 0.01)
        self.price_upper = max(1.60, scale_highest + margin)
        self.price_lower = min(0, scale_lowest - margin)

    def thin_price_labels(self) -> None:
        """Show every Nth price label so that visible labels keep a readable pixel gap."""
        gap = self.chart_grid_divider_h * self.chart_grid_space_y / self.base_chart_height
        step = max(1, math.ceil(self.min_price_label_gap / gap))
        for index, item in enumerate(self.canvas_price.find_withtag("price_label")):
            self.canvas_price.itemconfigure(item, state="normal" if index % step == 0 else "hidden")

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
        show_days = shows_day_labels(self.active_timeframe)
        y = self.price_data[start - 1][0][0] if start else ""
        m = self.price_data[start - 1][0][1] if start else ""
        for i in range(start, len(self.price_data)):

            iy = self.price_data[i][0][0]
            im = self.price_data[i][0][1]
            id = self.price_data[i][0][2]
            
            if im != str(m) or iy != str(y):
                m = im
                m_name = datetime.datetime.strptime(str(m), "%m").strftime("%b")[:2]

                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 10, text=m_name, fill=ink, tags=("ink", f"date_{i}") + tags)
            if iy != str(y):
                y = iy
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text="Y"+str(iy)[2:], fill=ink, tags=("ink", f"date_{i}") + tags)
            elif show_days:
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text=str(id), fill=ink, tags=("ink", f"date_{i}") + tags)
        self.hide_outside_window("date", start)

    def get_window(self) -> tk.Tk:
        return self.window

    def get_theme(self) -> Dict[str, str]:
        return self.dark_theme if self.dark_mode else self.light_theme

    def initialize_dark_mode_button(self, ttk: ModuleType) -> None:
        # Shares a grid cell with the draw button so the two sit side by side.
        self.theme_button_frame = ttk.Frame(self.window)
        self.dark_mode_button = ttk.Button(
            self.theme_button_frame, text="☀" if self.dark_mode else "☾", width=1,
            command=self.toggle_dark_mode,
        )
        self.dark_mode_button.grid(row=0, column=0, sticky="nsw")

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
        self.sr_button = ttk.Button(
            self.mode_button_frame, text="S-R", width=0, command=self.toggle_sr_mode,
        )
        self.sr_button.grid(row=0, column=3, sticky="nsw", padx=(4, 0))

    def make_candle_group_icon(self, tk: ModuleType, ink: str) -> Any:
        icon = tk.PhotoImage(master=self.window, width=18, height=18)
        # (center x, wick top, wick bottom, body top, body bottom)
        for cx, wick_top, wick_bottom, body_top, body_bottom in (
            (4, 2, 16, 6, 12), (9, 1, 17, 4, 10), (14, 4, 14, 7, 13)
        ):
            icon.put(ink, to=(cx, wick_top, cx + 1, wick_bottom + 1))
            icon.put(ink, to=(cx - 1, body_top, cx + 2, body_bottom + 1))
        return icon

    def make_pencil_icon(self, tk: ModuleType, ink: str) -> Any:
        icon = tk.PhotoImage(master=self.window, width=18, height=18)
        for x in range(18):
            for y in range(18):
                diagonal = x + y
                if 4 <= x <= 14 and abs(diagonal - 17) <= 1:
                    # Barrel, running from the tip up to the eraser.
                    pixel = True
                elif 1 <= x <= 3 and abs(diagonal - 17) <= x - 1:
                    # Sharpened tip.
                    pixel = True
                elif x >= 15 and abs(diagonal - 17) <= 1:
                    # Eraser end.
                    pixel = True
                else:
                    pixel = False
                if pixel:
                    icon.put(ink, to=(x, y, x + 1, y + 1))
        return icon

    def initialize_draw_button(self, ttk: ModuleType, tk: ModuleType) -> None:
        # Black in both themes, matching the other button icons.
        self.draw_icon = self.make_pencil_icon(tk, self.light_theme["ink"])
        self.draw_button = ttk.Button(
            self.theme_button_frame, image=self.draw_icon, command=self.toggle_draw_mode,
        )
        self.draw_button.grid(row=0, column=1, sticky="nsw", padx=(4, 0))

    def initialize_fib_button(self, ttk: ModuleType) -> None:
        # Enters draw mode with the Fib tool selected. Sits right of the draw button.
        self.fib_button = ttk.Button(
            self.theme_button_frame, text="FIB", width=3, command=self.toggle_fib_mode,
        )
        self.fib_button.grid(row=0, column=2, sticky="nsw", padx=(2, 0))

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
            self.roi_mode = self.export_mode = self.sr_mode = self.draw_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_roi_mode(self) -> None:
        self.roi_mode = not self.roi_mode
        if self.roi_mode:
            self.selection_mode = self.export_mode = self.sr_mode = self.draw_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_export_mode(self) -> None:
        self.export_mode = not self.export_mode
        if self.export_mode:
            self.selection_mode = self.roi_mode = self.sr_mode = self.draw_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_sr_mode(self) -> None:
        self.sr_mode = not self.sr_mode
        if self.sr_mode:
            self.selection_mode = self.roi_mode = self.export_mode = self.draw_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_draw_mode(self) -> None:
        self.draw_mode = not self.draw_mode
        if self.draw_mode:
            self.selection_mode = self.roi_mode = self.export_mode = self.sr_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def toggle_fib_mode(self) -> None:
        """The FIB button is draw mode with the Fib tool. Pressing it again turns draw mode off."""
        if self.draw_mode and self.draw_tool == FIB:
            self.draw_mode = False
        else:
            self.draw_tool = FIB
            self.draw_mode = True
            self.selection_mode = self.roi_mode = self.export_mode = self.sr_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def exit_modes(self) -> None:
        if not self.gesture_active():
            return
        self.selection_mode = self.roi_mode = self.export_mode = self.sr_mode = False
        self.draw_mode = False
        self.clear_gesture_state()
        self.update_mode_widgets()

    def gesture_active(self) -> bool:
        return (self.selection_mode or self.roi_mode or self.export_mode or self.sr_mode
                or self.draw_mode)

    def box_gesture_active(self) -> bool:
        """Modes where a drag draws a box instead of scrolling the chart."""
        return self.selection_mode or self.roi_mode or self.export_mode

    def clear_gesture_state(self) -> None:
        self._box_origin = None
        self._roi_span = None
        self.roi_header = None
        self.roi_results = None
        self.clear_draw_state()
        self.clear_sr_state()
        self.set_selection(set(), None)

    def clear_draw_state(self) -> None:
        self._draw_gesture = None
        self._draw_selected = None

    def clear_sr_state(self) -> None:
        self._sr_popup_index = None
        self._sr_popups = ()
        self._sr_levels = None

    def update_mode_widgets(self) -> None:
        if self.gesture_active():
            if self.roi_mode:
                text = "ROI mode enabled"
            elif self.export_mode:
                text = "select and export mode"
            elif self.sr_mode:
                text = "support/resistance mode"
            elif self.draw_mode and self.draw_tool == FIB:
                text = "fib mode"
            elif self.draw_mode:
                text = "draw mode"
            else:
                text = "select mode enabled"
            self.select_mode_label.configure(text=text)
            self.place_mode_label()
        else:
            self.select_mode_label.place_forget()
        self.select_button.state(["pressed" if self.selection_mode else "!pressed"])
        self.roi_button.state(["pressed" if self.roi_mode else "!pressed"])
        self.export_button.state(["pressed" if self.export_mode else "!pressed"])
        self.sr_button.state(["pressed" if self.sr_mode else "!pressed"])
        self.draw_button.state(["pressed" if self.draw_mode else "!pressed"])
        self.fib_button.state(
            ["pressed" if self.draw_mode and self.draw_tool == FIB else "!pressed"])
        if not self.draw_mode:
            self.canvas.configure(cursor="")
        self.draw_drawings()
        self.draw_toolbox()

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
        self.load_pages(pages=1)

    def load_all_data(self) -> None:
        """Load every remaining window and show the newest candles."""
        self.load_pages(pages=None, to_end=True)

    def load_pages(self, pages: Optional[int], to_end: bool = False) -> None:
        """Load the next ``pages`` windows, or all remaining windows when pages is None."""
        if self.data_source is None or not self.data_source.has_more:
            return

        new_rows: List[List[Any]] = []
        error: Optional[Exception] = None
        exhausted = False
        loaded = 0
        try:
            while self.data_source.has_more and (pages is None or loaded < pages):
                page = self.data_source.load_next()
                if not page:
                    exhausted = True
                    break
                new_rows.extend(page)
                loaded += 1
        except (csv.Error, OSError, ValueError) as exc:
            error = exc

        if new_rows:
            self.append_loaded_rows(new_rows, to_end)
        if exhausted:
            self.set_load_buttons_enabled(False)
        else:
            self.update_load_more_button()
        if error is not None:
            messagebox.showerror("Unable to load price data", str(error), parent=self.window)

    def append_loaded_rows(self, new_rows: List[List[Any]], to_end: bool = False) -> None:
        if self.active_timeframe != DAILY:
            self.extend_active_timeframe(new_rows)
            if to_end:
                self.canvas.xview_moveto(1.0)
                self.draw_overlays()
            return

        old_count = len(self.price_data)
        old_width = self.chart_grid_space_x
        old_base_width = self._base_chart_width
        old_left = self.canvas.xview()[0] * old_width
        old_top = self.canvas.yview()[0] * self.chart_grid_space_y
        old_upper, old_lower = self.price_upper, self.price_lower

        self._daily_rows.extend(new_rows)
        self.update_ticker_label()
        self.indicators_object.calculate_RSI_incremental(self.indicator_settings["RSI"]["period"])
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
        if to_end:
            self.canvas.xview_moveto(1.0)
        else:
            self.canvas.xview_moveto(old_left / self.chart_grid_space_x)
        self.canvas.yview_moveto(
            max(0, (old_top * ratio + shift) / self.chart_grid_space_y)
        )
        self.draw_overlays()

    def extend_active_timeframe(self, new_rows: List[List[Any]]) -> None:
        """Append daily rows while a derived tab is shown, then rebuild that tab at the same view."""
        self.store_tab_state()
        keep_left = self.canvas.xview()[0] * self.chart_grid_space_x
        self._daily_rows.extend(new_rows)
        self.build_chart(
            timeframe_rows(self._daily_rows, self.active_timeframe),
            self._tab_states[self.active_timeframe], keep_left=keep_left,
        )

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
        if self.draw_mode and event.widget is self.canvas and self.start_draw_gesture(event):
            return
        if self.box_gesture_active():
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
        if self.box_gesture_active():
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
        if self.draw_mode and self.continue_draw_gesture(event):
            return
        if self._sr_popups and self.moved_past_click_threshold(event):
            # Popups are placed in canvas coordinates, so a drag would leave them behind.
            self.dismiss_sr_popups()
        self.show_drag_cursor(event.widget)
        if event.widget is self.canvas:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
        elif event.widget is self.canvas_price:
            self.canvas.scan_dragto(0, event.y, gain=1)
        else:
            self.canvas.scan_dragto(event.x, 0, gain=1)
        self.draw_crosshair()

    def show_drag_cursor(self, widget: tk.Canvas) -> None:
        """Show the closed fist on the canvas being dragged, until end_canvas_drag."""
        if self._drag_cursor_widget is None:
            widget.configure(cursor=self.drag_cursor)
            self._drag_cursor_widget = widget

    def end_canvas_drag(self, event: tk.Event) -> None:
        """Put the cursor back after a drag, to whatever suits the point now under the pointer."""
        widget = self._drag_cursor_widget
        if widget is None:
            return
        self._drag_cursor_widget = None
        if event.widget is widget:
            self.update_hover_cursor(event)
        else:
            widget.configure(cursor="")

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
        if self.draw_mode:
            self.finish_draw_gesture(event)
            return
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
        if self.sr_mode:
            self.select_support_resistance(event)
            return
        if self._press_position is None:
            return
        press_x, press_y = self._press_position
        if abs(event.x - press_x) + abs(event.y - press_y) > self.click_drag_threshold:
            return
        chart_x = self.canvas.canvasx(event.x)
        chart_y = self.canvas.canvasy(event.y)
        index = self.candle_index_at(chart_x, chart_y)
        self.set_selection({index} if index is not None else set(), None)
        if index is not None:
            self.show_candle_info(index)

    def moved_past_click_threshold(self, event: tk.Event) -> bool:
        if self._press_position is None:
            return True
        press_x, press_y = self._press_position
        return abs(event.x - press_x) + abs(event.y - press_y) > self.click_drag_threshold

    def select_support_resistance(self, event: tk.Event) -> None:
        if self.moved_past_click_threshold(event):
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        popup = self.sr_popup_at(x, y)
        if popup is not None:
            if popup.enabled:
                self.choose_sr_window(popup.label)
            return
        index = self.candle_index_at(x, y)
        if index is None:
            self.dismiss_sr_popups()
        else:
            self.show_sr_popups(index, x, y)

    def show_sr_popups(self, index: int, x: float, y: float) -> None:
        finder = self.levels_for_chart()[0]
        daily = self.daily_index_for_candle(index)
        boxes = popup_bounds(x, y, len(self.sr_window_labels), self.canvas_view_bounds())
        self._sr_popups = tuple(
            SRPopup(label, bool(finder.levels_at(daily, label)), box)
            for label, box in zip(self.sr_window_labels, boxes)
        )
        self._sr_popup_index = index
        self.set_selection({index}, None)

    def choose_sr_window(self, label: str) -> None:
        if self._sr_popup_index is None:
            return
        self._sr_levels = (self._sr_popup_index, label)
        self._sr_popups = ()
        self._sr_popup_index = None
        self.draw_overlays()

    def dismiss_sr_popups(self) -> None:
        if not self._sr_popups:
            return
        self._sr_popups = ()
        self._sr_popup_index = None
        # The highlight stays on the candle the drawn levels end on, if there is one.
        self.set_selection({self._sr_levels[0]} if self._sr_levels else set(), None)

    def sr_popup_at(self, x: float, y: float) -> Optional[SRPopup]:
        for popup in self._sr_popups:
            if popup.contains(x, y):
                return popup
        return None

    def canvas_view_bounds(self) -> Tuple[float, float, float, float]:
        canvas = self.canvas
        return (canvas.canvasx(0), canvas.canvasy(0),
                canvas.canvasx(canvas.winfo_width()), canvas.canvasy(canvas.winfo_height()))

    def track_crosshair(self, event: tk.Event) -> None:
        self.crosshair_root = (event.x_root, event.y_root)
        self.update_hover_cursor(event)
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
                if self.trend_applied["enabled"]:
                    state, adx = self.trend_details()[index]
                    if state is not None:
                        self.draw_crosshair_label(
                            self.canvas, chart_x, self.canvas.canvasy(0) + 24,
                            f"{state}  ADX {adx:.1f}", "n", line_color, text_color,
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
        highlighted = index in self.selected_indices or index in self.trade_indices
        if highlighted:
            color = self.highlight_color(color)
        if self.canvas.type(item) == "rectangle":
            # Highlighted bodies are always solid so the highlight fills them in dark mode too.
            Candle.style_body(self.canvas, item, self.dark_mode and not highlighted, color)
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

    def candle_x(self, index: float) -> float:
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
                index_range=self._applied_window,
            ))
            if settings["hi_lo"]:
                # Markers are only created for the visible part of the chart inside the data window.
                x_range = self.drawable_x_range()
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
        series = zip(("middle", "upper", "lower"),
                     self.indicators_object.calculate_bollinger(*self.bollinger_parameters()))
        for name, values in series:
            self._bollinger_items.extend(self.indicators_object.render_series(
                self.canvas, values,
                x_for_index=self.candle_x, y_for_price=self.price_to_y,
                fill=self.sma_colors[settings["color"]],
                dash=self.sma_line_styles[settings["style"]],
                width=self.sma_line_widths[settings["style"]],
                tags=("bollinger", f"bollinger_{name}"),
                index_range=self._applied_window,
            ))

    def trend_volumes(self) -> Optional[List[float]]:
        """Volume for each candle, or None when the loaded data has no volume."""
        if not self.price_data or "volume" not in self.price_data[0][5]:
            return None
        return [row[5]["volume"] for row in self.price_data]

    def trend_details(self) -> List[Tuple[Optional[str], Optional[float]]]:
        """Trend state and ADX for every candle. Recomputed only when the data or settings change."""
        settings = self.trend_applied
        volumes = self.trend_volumes() if settings["include_volume"] else None
        key = (id(self.price_data), len(self.price_data), settings["adx_enter"], settings["adx_exit"],
               settings["sma_fast"], settings["sma_slow"], volumes is not None)
        if self._trend_cache is None or self._trend_cache[0] != key:
            rows = self.price_data
            details = layered_trend_details(
                [row[HIGH_COLUMN] for row in rows],
                [row[LOW_COLUMN] for row in rows],
                [row[CLOSE_COLUMN] for row in rows],
                settings["adx_enter"], settings["adx_exit"],
                settings["sma_fast"], settings["sma_slow"],
                volumes,
            )
            self._trend_cache = (key, details)
        return self._trend_cache[1]

    def draw_trend_shading(self) -> None:
        for item in self._trend_items:
            self.canvas.delete(item)
        self._trend_items = []
        if not self.trend_applied["enabled"] or not self.price_data:
            return
        theme = self.get_theme()
        colors = {
            UP: self.blend_colors(theme["canvas"], theme["gain"], TREND_SHADE_STRENGTH),
            DOWN: self.blend_colors(theme["canvas"], theme["loss"], TREND_SHADE_STRENGTH),
            SIDEWAYS: self.blend_colors(theme["canvas"], theme["grid"], TREND_SHADE_STRENGTH),
        }
        top = self.price_to_y(self.price_upper)
        bottom = self.price_to_y(self.price_lower)
        half_width = self.chart_grid_divider_v * self._scale_x / 2
        # Consecutive candles with the same state share one rectangle.
        runs: List[List[Any]] = []
        details = self.trend_details()
        first, last = self._applied_window
        for index in range(max(first, 0), min(last, len(details) - 1) + 1):
            state, _adx = details[index]
            if state is None:
                continue
            if runs and runs[-1][2] == state and runs[-1][1] == index - 1:
                runs[-1][1] = index
            else:
                runs.append([index, index, state])
        for first, last, state in runs:
            self._trend_items.append(self.canvas.create_rectangle(
                self.candle_x(first) - half_width, top,
                self.candle_x(last) + half_width, bottom,
                fill=colors[state], outline="", tags=("trend",),
            ))
        # The shading goes beneath the candles, grid and other overlays.
        if self._trend_items:
            self.canvas.tag_lower("trend")

    def initialize_trend_toggle(self, tk: ModuleType) -> None:
        # A widget rather than a canvas item: it is placed in window coordinates,
        # so it stays fixed on screen while the chart scrolls.
        self.trend_toggle_label = tk.Label(
            self.frame_canvas, text=TREND_TOGGLE_LABEL, relief="solid", bd=1,
            padx=INDICATOR_TOGGLE_PADDING, cursor=POINTING_HAND,
        )
        self.trend_toggle_label.bind("<Button-1>", lambda _event: self.toggle_trend())
        self.trend_toggle_label.place_forget()

    def draw_trend_toggle(self) -> None:
        label = self.trend_toggle_label
        if not self.price_data:
            label.place_forget()
            return
        theme = self.get_theme()
        active = self.trend_applied["enabled"]
        label.configure(
            bg=theme["ink"] if active else theme["canvas"],
            fg=theme["canvas"] if active else theme["ink"],
        )
        label.place(
            in_=self.canvas, relx=0.0, rely=1.0, anchor="sw",
            x=INDICATOR_TOGGLE_MARGIN, y=-INDICATOR_TOGGLE_MARGIN,
        )

    def toggle_trend(self) -> None:
        self.trend_applied = {**self.trend_applied, "enabled": not self.trend_applied["enabled"]}
        self.draw_overlays()

    def open_trend_window(self, tk: ModuleType) -> None:
        window = self.open_modal_window(tk, "Trend Identification")
        self.build_trend_content(tk, window)

    def build_trend_content(self, tk: ModuleType, window: Any) -> None:
        # Edits are staged in these variables and only applied by the Apply button.
        applied = self.trend_applied
        defaults = default_trend_settings()
        has_volume = self.trend_volumes() is not None
        staged: Dict[str, Any] = {
            "enabled": tk.BooleanVar(window, value=applied["enabled"]),
            "include_volume": tk.BooleanVar(window, value=applied["include_volume"]),
        }
        display = tk.LabelFrame(window, text="Display", padx=10, pady=6)
        display.pack(fill="x", padx=12, pady=(12, 0))
        tk.Checkbutton(display, text="Show trend shading", variable=staged["enabled"]).grid(
            row=0, column=0, sticky="w")
        tk.Checkbutton(
            display, text="Include volume", variable=staged["include_volume"],
            state="normal" if has_volume else "disabled",
        ).grid(row=1, column=0, sticky="w")
        if not has_volume:
            tk.Label(display, text="The loaded data has no volume column.", fg="gray").grid(
                row=1, column=1, sticky="w", padx=(12, 0))
        settings = tk.LabelFrame(window, text="Trend settings", padx=10, pady=6)
        settings.pack(fill="x", padx=12, pady=(12, 0))
        for row, (key, label, _kind, _low, _high) in enumerate(TREND_SETTING_FIELDS):
            staged[key] = tk.StringVar(window, value=format_setting_value(applied[key]))
            tk.Label(settings, text=label).grid(row=row, column=0, sticky="w", pady=2)
            tk.Entry(settings, textvariable=staged[key], width=10).grid(
                row=row, column=1, sticky="w", padx=(12, 12), pady=2)
            tk.Label(settings, text=f"Default: {format_setting_value(defaults[key])}", fg="gray").grid(
                row=row, column=2, sticky="w", pady=2)

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        tk.Button(buttons, text="Cancel", width=8, command=window.destroy).pack(side="left")
        tk.Button(
            buttons, text="Apply", width=8,
            command=lambda: self.apply_trend(window, staged),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text="Help", width=8,
            command=lambda: self.show_help_window(
                tk, "Trend Identification Help", TREND_DETAILED_HELP, window),
        ).pack(side="left", padx=(8, 0))

    def apply_trend(self, window: Any, staged: Dict[str, Any]) -> None:
        # Nothing changes unless every setting is valid, so the shading stays as it was.
        try:
            values = validate_trend_settings({field[0]: staged[field[0]].get() for field in TREND_SETTING_FIELDS})
        except ValueError as error:
            messagebox.showerror("Invalid setting", str(error), parent=window)
            return
        self.trend_applied = {
            "enabled": staged["enabled"].get(),
            # Volume can only be used when the loaded data has it.
            "include_volume": staged["include_volume"].get() and self.trend_volumes() is not None,
            **values,
        }
        self.draw_overlays()

    def draw_levels(self) -> None:
        for item in self._levels_items:
            self.canvas.delete(item)
        self._levels_items = []
        if not self.price_data:
            return
        finder, segment_cache, _ = self.levels_for_chart()
        candle_of_row, _ = self.timeframe_map()
        last_daily = len(self._daily_rows) - 1
        static = self.levels_applied["mode"] == "Static"
        first_visible, last_visible = self.visible_candle_range()
        occupied_label_boxes: List[Tuple[int, int, int, int]] = []
        for label, settings in self.levels_applied["windows"].items():
            if not settings["enabled"]:
                continue
            study = self.breakout_study(label)
            if static:
                # Static levels have no qualification candle of their own, so they are
                # priced as of the latest daily row.
                daily_spans = [Segment(0, last_daily, level.price, level.kind,
                                       last_daily, level.touches)
                               for level in finder.static_levels(label)]
            else:
                if label not in segment_cache:
                    segment_cache[label] = finder.segments(label)
                daily_spans = segment_cache[label]
            # Daily spans are moved onto this tab's candles, then crowded ones are averaged.
            spans = [Segment(candle_of_row[span.start], candle_of_row[span.end], span.price,
                             span.kind, span.origin, span.touches) for span in daily_spans]
            spans = merge_crowded_segments(spans, self.price_to_y)
            color = self.sma_colors[settings["color"]]
            for span in spans:
                start, end, price, kind, origin, touches = (
                    span.start, span.end, span.price, span.kind, span.origin, span.touches)
                self.draw_level_line(start, end, price, kind, color, label)
                distance = study.rejection_distance(origin, price)
                if distance is not None:
                    self.draw_rejection_line(start, end, price, kind, distance, color, label)
                # One odds label per level, where its drawing ends on screen. A level that
                # runs past the right edge is labelled at that edge.
                if start <= last_visible and end >= first_visible:
                    odds = study.odds_at(origin, price, kind, touches)
                    self.draw_level_odds(min(end, last_visible), price, color, label,
                                         odds_text(odds), occupied_label_boxes)
        # Level lines sit above the candles so a body never hides a level.
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

    def draw_level_line(self, start: int, end: int, price: float, kind: str, color: str,
                        label: str) -> None:
        item = self.level_line_item(start, end, price, kind, color,
                                    tags=("levels", f"levels_{label}", f"level_{kind}"))
        if item is not None:
            self._levels_items.append(item)

    def draw_rejection_line(self, start: int, end: int, price: float, kind: str,
                            distance: float, color: str, label: str) -> None:
        # The rejection distance is above a support and below a resistance.
        rejection_price = price + distance if kind == SUPPORT else price - distance
        item = self.horizontal_level_item(
            start, end, rejection_price, color, STYLE_DASHES[DOTTED],
            tags=("levels", f"levels_{label}", "level_rejection"))
        if item is not None:
            self._levels_items.append(item)

    def level_line_item(self, start: int, end: int, price: float, kind: str, color: str,
                        tags: Tuple[str, ...]) -> Optional[int]:
        """Solid line for support and dashed line for resistance, from candle start to end."""
        dash = STYLE_DASHES[SOLID] if kind == SUPPORT else STYLE_DASHES[DASHED]
        return self.horizontal_level_item(start, end, price, color, dash, tags)

    def horizontal_level_item(self, start: int, end: int, price: float, color: str,
                              dash: Tuple[int, ...], tags: Tuple[str, ...]) -> Optional[int]:
        """A straight line at ``price`` from candle start to end, clipped to the view.

        Returns None when the line lies outside the view or the data window.
        """
        left, right = self.drawable_x_range()
        x0 = max(self.candle_x(start), left)
        x1 = min(self.candle_x(end), right)
        if x0 > x1:
            return None
        y = self.price_to_y(price)
        cap = "round" if dash == STYLE_DASHES[DOTTED] else "butt"
        return self.canvas.create_line(
            x0, y, x1, y, fill=color, width=2, dash=dash, capstyle=cap, tags=tags)

    def visible_x_range(self) -> Tuple[float, float]:
        """Return the left and right canvas x coordinates of the visible area."""
        return self.canvas.canvasx(0), self.canvas.canvasx(self.canvas.winfo_width())

    def visible_candle_range(self) -> Tuple[int, int]:
        """Return the first and last candle indexes that fall inside the visible canvas and data window."""
        left, right = self.visible_x_range()
        first = math.floor((left / self._scale_x - self.chart_padding_x)
                           / self.chart_grid_divider_v)
        last = math.floor((right / self._scale_x - self.chart_padding_x)
                          / self.chart_grid_divider_v)
        last_index = len(self.price_data or []) - 1
        window_first, window_last = self._applied_window
        return max(0, first, window_first), min(last_index, last, window_last)

    def drawable_x_range(self) -> Tuple[float, float]:
        """The visible x range, limited to the candles inside the data window.

        When the window is empty the range is inverted, so nothing passes a left-to-right check.
        """
        left, right = self.visible_x_range()
        first, last = self._applied_window
        if first > last:
            return left, left - 1
        half = self.chart_grid_divider_v * self._scale_x / 2
        return max(left, self.candle_x(first) - half), min(right, self.candle_x(last) + half)

    def data_window_range(self) -> Tuple[int, int]:
        """Candle indexes within half the active tab's data window either side of the chart view centre."""
        rows = self.price_data or []
        key = (id(rows), len(rows),
               rows[0][0] if rows else None, rows[-1][0] if rows else None)
        if self._ordinals_cache is None or self._ordinals_cache[0] != key:
            self._ordinals_cache = (key, [row_ordinal(row) for row in rows])
        left, right = self.visible_x_range()
        centre = ((left + right) / 2 / self._scale_x - self.chart_padding_x) / self.chart_grid_divider_v
        return window_index_range(self._ordinals_cache[1], centre, data_window_days(self.active_timeframe))

    def window_canvas(self, kind: str) -> tk.Canvas:
        return {"candle": self.canvas, "date": self.canvas_date, "ind": self.canvas_indicators}[kind]

    def window_range_for(self, kind: str, window: Tuple[int, int]) -> Tuple[int, int]:
        """The candle indexes of ``kind`` items that show for ``window``.

        An indicator segment joins the previous candle to its own, so both ends must be
        inside the window. That keeps the segment from overhanging the edge.
        """
        first, last = window
        return (first + 1, last) if kind == "ind" else (first, last)

    def hide_outside_window(self, kind: str, start: int) -> None:
        """Hide items of ``kind`` created for candles from ``start`` on, when outside the applied window."""
        first, last = self.window_range_for(kind, self._applied_window)
        canvas = self.window_canvas(kind)
        for i in range(start, len(self.price_data)):
            if not first <= i <= last:
                canvas.itemconfigure(f"{kind}_{i}", state="hidden")

    def apply_data_window(self) -> None:
        """Show the items inside the data window and hide those outside it.

        Only the candles that change state are touched. Overlays read the new window
        in the same redraw.
        """
        old = self._applied_window
        new = self.data_window_range()
        self._applied_window = new
        for kind in ("candle", "date", "ind"):
            old_range = self.window_range_for(kind, old)
            new_range = self.window_range_for(kind, new)
            for i in range_difference(new_range, old_range):
                self.window_canvas(kind).itemconfigure(f"{kind}_{i}", state="normal")
            for i in range_difference(old_range, new_range):
                self.window_canvas(kind).itemconfigure(f"{kind}_{i}", state="hidden")

    def draw_overlays(self) -> None:
        self.apply_data_window()
        self.thin_price_labels()
        self.draw_trend_shading()
        self.draw_selection_box()
        self.draw_moving_averages()
        self.draw_bollinger()
        self.draw_levels()
        self.draw_support_resistance()
        self.draw_drawings()
        self.draw_toolbox()
        self.draw_indicator_toggles()
        self.draw_indicator_info_button()
        self.draw_trend_toggle()
        self.draw_crosshair()

    def refresh_drawing_layer(self) -> None:
        self.draw_drawings()
        self.draw_toolbox()

    def drawing_points(self, drawing: Drawing) -> Tuple[Point, Point]:
        return (
            (self.candle_x(drawing.start[0]), self.price_to_y(drawing.start[1])),
            (self.candle_x(drawing.end[0]), self.price_to_y(drawing.end[1])),
        )

    def chart_point(self, x: float, y: float) -> Point:
        """Convert a canvas point to (candle position, price)."""
        index = (x / self._scale_x - self.chart_padding_x) / self.chart_grid_divider_v
        return index, self.price_at(y)

    def make_drawing(self, drawing_id: int, start: Point, end: Point) -> Drawing:
        """Build a drawing with the current tool and style from two canvas points."""
        kind = self.draw_tool or LINE
        return Drawing(
            drawing_id, kind, self.draw_style, self.sma_colors[self.draw_color_name],
            self.draw_filled and fill_applicable(kind),
            self.chart_point(*start), self.chart_point(*end),
        )

    def drawing_at(self, x: float, y: float) -> Optional[Drawing]:
        # The most recently drawn feature is on top, so it is hit first.
        for drawing in reversed(self.drawings):
            p1, p2 = self.drawing_points(drawing)
            if hit_test(drawing.kind, p1, p2, x, y):
                return drawing
        return None

    def draw_drawings(self) -> None:
        self.canvas.delete("drawing")
        for drawing in self.drawings:
            self.render_drawing(drawing, selected=drawing.id == self._draw_selected)
        gesture = self._draw_gesture
        if gesture is not None and gesture["kind"] == "draw" and gesture["moved"]:
            preview = self.make_drawing(0, gesture["start"], gesture["end"])
            self.render_drawing(preview, selected=False)

    def render_drawing(self, drawing: Drawing, selected: bool) -> None:
        (x1, y1), (x2, y2) = self.drawing_points(drawing)
        color = drawing.color
        width = 4 if selected else 2
        dash = STYLE_DASHES[drawing.style]
        cap = "round" if drawing.style == DOTTED else "butt"
        tags = ("drawing", f"drawing_{drawing.id}")
        if drawing.kind == FIB:
            self.render_fib(drawing, (x1, y1), (x2, y2), width, dash, cap, tags)
        elif drawing.kind == LINE:
            clipped = clip_line((x1, y1), (x2, y2), self.canvas_view_bounds())
            if clipped is None:
                return
            self.canvas.create_line(
                *clipped, fill=color, width=width, dash=dash, capstyle=cap, tags=tags)
        elif drawing.kind == SEGMENT:
            self.canvas.create_line(
                x1, y1, x2, y2, fill=color, width=width, dash=dash, capstyle=cap, tags=tags)
            # Hollow circles at both ends, filled with the canvas colour so the line does not show through.
            background = self.get_theme()["canvas"]
            radius = SEGMENT_CIRCLE_RADIUS
            for x, y in ((x1, y1), (x2, y2)):
                self.canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    outline=color, fill=background, width=2, tags=tags)
        else:
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            fill = color if drawing.filled else ""
            stipple = FILL_STIPPLE if drawing.filled else ""
            create = self.canvas.create_rectangle if drawing.kind == BOX else self.canvas.create_oval
            create(left, top, right, bottom, outline=color, fill=fill, stipple=stipple,
                   width=width, dash=dash, tags=tags)

    def render_fib(
        self, drawing: Drawing, p1: Point, p2: Point, width: int, dash: Tuple[int, ...],
        cap: str, tags: Tuple[str, ...],
    ) -> None:
        """A retracement, drawn in three parts.

        A dotted diagonal joins the two anchors in the complementary colour. Each level is a
        line in the drawing's style across the box spanned by the anchors, and a dotted line
        beyond each side of the box out to the edges of the view. Each label gives the level's
        percentage and its price, which is interpolated from the two anchor prices in the same
        way as the line's position.
        """
        view_left, _, view_right, _ = self.canvas_view_bounds()
        left, right = sorted((p1[0], p2[0]))
        background = self.get_theme()["canvas"]
        self.canvas.create_line(
            *p1, *p2, fill=complementary_color(drawing.color), width=width,
            dash=STYLE_DASHES[DOTTED], capstyle="round", tags=tags)
        start_price, end_price = drawing.start[1], drawing.end[1]
        for ratio, level_y in fib_level_ys(p1, p2):
            self.canvas.create_line(
                left, level_y, right, level_y, fill=drawing.color, width=width,
                dash=dash, capstyle=cap, tags=tags)
            if left > view_left:
                self.canvas.create_line(
                    view_left, level_y, left, level_y, fill=drawing.color, width=width,
                    dash=STYLE_DASHES[DOTTED], capstyle="round", tags=tags)
            if right < view_right:
                self.canvas.create_line(
                    right, level_y, view_right, level_y, fill=drawing.color, width=width,
                    dash=STYLE_DASHES[DOTTED], capstyle="round", tags=tags)
            price = end_price - ratio * (end_price - start_price)
            label = self.canvas.create_text(
                right + 4, level_y, anchor="w", fill=drawing.color, tags=tags,
                text=f"{ratio * 100:.1f}%  {price:.2f}")
            # The label sits on the dotted extension, so it is backed by the canvas colour.
            x1, y1, x2, y2 = self.canvas.bbox(label)
            self.canvas.create_rectangle(
                x1 - 2, y1, x2 + 2, y2, fill=background, outline="", tags=tags)
            self.canvas.tag_raise(label)

    def draw_toolbox(self) -> None:
        self.canvas.delete("toolbox")
        self._toolbox = None
        if not self.draw_mode:
            return
        theme = self.get_theme()
        view = self.canvas_view_bounds()
        toolbox = toolbox_layout(view, tuple(self.sma_colors), self._toolbox_position)
        self._toolbox = toolbox
        if self._toolbox_position is not None:
            # Keep the clamped position, so a toolbox pushed in by a smaller window stays put.
            self._toolbox_position = (toolbox.bounds[0] - view[0], toolbox.bounds[1] - view[1])
        # Stippled while a feature or the toolbox itself is being dragged, so candles behind it show through.
        stipple = TOOLBOX_FADE_STIPPLE if self.toolbox_faded() else ""
        left, top, right, bottom = toolbox.bounds
        self.create_toolbox_box(
            left, top, right, bottom, fill=theme["canvas"], outline=theme["ink"], stipple=stipple)
        for button in toolbox.buttons:
            enabled = self.toolbox_enabled(button.key)
            active = enabled and self.toolbox_active(button.key)
            if not enabled:
                fill, text_fill = theme["sr_unavailable"], theme["ink"]
            elif active:
                fill, text_fill = theme["ink"], theme["canvas"]
            else:
                fill, text_fill = theme["canvas"], theme["ink"]
            b_left, b_top, b_right, b_bottom = button.bounds
            if button.key[0] == "color":
                # A swatch shows its colour; the active one gets a heavier outline.
                self.create_toolbox_box(
                    b_left, b_top, b_right, b_bottom,
                    fill=self.sma_colors[button.key[1]], outline=theme["ink"],
                    width=3 if active else 1, stipple=stipple)
                continue
            self.create_toolbox_box(
                b_left, b_top, b_right, b_bottom, fill=fill, outline=theme["ink"], stipple=stipple)
            self.canvas.create_text(
                (b_left + b_right) / 2, (b_top + b_bottom) / 2, text=button.text,
                fill=text_fill, stipple=stipple, tags=("toolbox",))

    def toolbox_faded(self) -> bool:
        gesture = self._draw_gesture
        return (gesture is not None and gesture["moved"]
                and gesture["kind"] in ("draw", "move", "toolbox_move"))

    def create_toolbox_box(
        self, left: float, top: float, right: float, bottom: float, fill: str, outline: str,
        width: int = 1, stipple: str = "",
    ) -> None:
        """Draw a toolbox box. Tk cannot stipple an outline, so a faded box draws its outline as stippled lines."""
        if not stipple:
            self.canvas.create_rectangle(
                left, top, right, bottom, fill=fill, outline=outline, width=width,
                tags=("toolbox",))
            return
        self.canvas.create_rectangle(
            left, top, right, bottom, fill=fill, stipple=stipple, outline="", tags=("toolbox",))
        corners = (left, top, right, top, right, bottom, left, bottom, left, top)
        self.canvas.create_line(
            *corners, fill=outline, width=width, stipple=stipple, tags=("toolbox",))

    def toolbox_enabled(self, key: ToolKey) -> bool:
        # The fill row only applies to box and ellipse.
        return key[0] != "fill" or fill_applicable(self.draw_tool)

    def toolbox_active(self, key: ToolKey) -> bool:
        action, value = key
        if action == "tool":
            return self.draw_tool == value
        if action == "style":
            return self.draw_style == value
        if action == "fill":
            return self.draw_filled == value
        if action == "color":
            return self.draw_color_name == value
        return False

    def activate_draw_button(self, key: ToolKey) -> None:
        action, value = key
        if action == "tool":
            # Clicking the active feature turns it off.
            self.draw_tool = None if self.draw_tool == value else value
        elif action == "style":
            self.draw_style = value
        elif action == "color":
            self.draw_color_name = value
        elif action == "fill" and self.toolbox_enabled(key):
            self.draw_filled = value
        elif action == "undo":
            self.undo_drawing()
        elif action == "delete":
            self.delete_selected_drawing()
        elif action == "clear":
            self.clear_drawings()
        self.refresh_drawing_layer()

    def commit_drawings(self, drawings: Tuple[Drawing, ...]) -> None:
        self._draw_history += (self.drawings,)
        self.drawings = drawings
        self.refresh_drawing_layer()

    def undo_drawing(self) -> None:
        if not self._draw_history:
            return
        self.drawings = self._draw_history[-1]
        self._draw_history = self._draw_history[:-1]
        if self._draw_selected not in {drawing.id for drawing in self.drawings}:
            self._draw_selected = None
        self.refresh_drawing_layer()

    def delete_selected_drawing(self) -> None:
        if self._draw_selected is None:
            return
        remaining = tuple(d for d in self.drawings if d.id != self._draw_selected)
        self._draw_selected = None
        if len(remaining) != len(self.drawings):
            self.commit_drawings(remaining)

    def clear_drawings(self) -> None:
        if not self.drawings:
            return
        self._draw_selected = None
        self.commit_drawings(())

    def update_hover_cursor(self, event: tk.Event) -> None:
        """Set the cursor of the canvas under the pointer for what lies beneath it.

        A pointing hand marks a button, the move cursor marks something that can be dragged
        into place, and everything else gets the arrow.
        """
        widget = event.widget
        if widget is self.canvas:
            cursor = self.chart_hover_cursor(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        elif widget is self.canvas_indicators:
            clickable = self.indicator_info_at(event) or self.indicator_toggle_at(event) is not None
            cursor = POINTING_HAND if clickable else ""
        else:
            cursor = ""
        if str(widget.cget("cursor")) != cursor:
            widget.configure(cursor=cursor)

    def chart_hover_cursor(self, x: float, y: float) -> str:
        """The cursor for canvas point (x, y) on the price chart in the active mode."""
        if self.draw_mode:
            if self._toolbox is not None and self._toolbox.contains(x, y):
                button = self._toolbox.button_at(x, y)
                if button is None:
                    # An empty spot on the toolbox can be dragged to move it.
                    return MOVE_CURSOR
                return POINTING_HAND if self.toolbox_enabled(button.key) else ""
            return MOVE_CURSOR if self.drawing_at(x, y) is not None else ""
        if self.sr_mode:
            popup = self.sr_popup_at(x, y)
            return POINTING_HAND if popup is not None and popup.enabled else ""
        return ""

    def start_draw_gesture(self, event: tk.Event) -> bool:
        """Start a toolbox press or drag, a move, or a new drawing. Returns False to scroll instead."""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if self._toolbox is not None and self._toolbox.contains(x, y):
            button = self._toolbox.button_at(x, y)
            if button is None:
                # Pressing an empty spot on the toolbox starts dragging the toolbox itself.
                view_left, view_top, _, _ = self.canvas_view_bounds()
                left, top, _, _ = self._toolbox.bounds
                self._draw_gesture = {
                    "kind": "toolbox_move", "moved": False,
                    "origin": (left - view_left, top - view_top),
                    "start": (x, y), "end": (x, y),
                }
                return True
            self._draw_gesture = {
                "kind": "toolbox", "moved": False, "key": button.key,
                "start": (x, y), "end": (x, y),
            }
            return True
        hit = self.drawing_at(x, y)
        if hit is not None:
            self._draw_gesture = {
                "kind": "move", "moved": False, "drawing": hit, "before": self.drawings,
                "start": (x, y), "end": (x, y),
            }
            return True
        if self.draw_tool is not None:
            self._draw_gesture = {
                "kind": "draw", "moved": False, "before": self.drawings,
                "start": (x, y), "end": (x, y),
            }
            return True
        return False

    def continue_draw_gesture(self, event: tk.Event) -> bool:
        gesture = self._draw_gesture
        if gesture is None:
            return False
        if gesture["kind"] == "toolbox":
            return True
        if self.moved_past_click_threshold(event):
            gesture["moved"] = True
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        gesture["end"] = (x, y)
        if gesture["kind"] == "toolbox_move":
            if gesture["moved"]:
                # Offset from where the toolbox was when the press began, so the grip point
                # under the cursor stays the same for the whole drag.
                origin_x, origin_y = gesture["origin"]
                start_x, start_y = gesture["start"]
                self._toolbox_position = (origin_x + x - start_x, origin_y + y - start_y)
            self.draw_toolbox()
            return True
        if gesture["kind"] == "move" and gesture["moved"]:
            # Move from the drawing's position when the gesture started, not from its last step.
            start_index, start_price = self.chart_point(*gesture["start"])
            end_index, end_price = self.chart_point(x, y)
            moved = gesture["drawing"].translated(end_index - start_index, end_price - start_price)
            self.drawings = tuple(
                moved if d.id == moved.id else d for d in gesture["before"])
        self.refresh_drawing_layer()
        return True

    def finish_draw_gesture(self, event: tk.Event) -> None:
        gesture = self._draw_gesture
        self._draw_gesture = None
        if gesture is None:
            # A plain click on empty chart in draw mode clears the selection.
            if not self.moved_past_click_threshold(event):
                self._draw_selected = None
                self.refresh_drawing_layer()
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        kind = gesture["kind"]
        if kind == "toolbox":
            # Only a press and release on the same button activates it.
            button = self._toolbox.button_at(x, y) if self._toolbox is not None else None
            if button is not None and button.key == gesture["key"]:
                self.activate_draw_button(button.key)
            return
        if kind == "toolbox_move":
            # The toolbox already sits where the drag left it; this redraws it solid.
            self.refresh_drawing_layer()
            return
        if kind == "move":
            if gesture["moved"]:
                self._draw_history += (gesture["before"],)
            self._draw_selected = gesture["drawing"].id
        elif kind == "draw":
            self._draw_selected = None
            if gesture["moved"]:
                new_drawing = self.make_drawing(self._draw_next_id, gesture["start"], (x, y))
                self._draw_next_id += 1
                self.commit_drawings(gesture["before"] + (new_drawing,))
                return
        self.refresh_drawing_layer()

    def draw_support_resistance(self) -> None:
        for item in self._sr_items + self._sr_popup_items:
            self.canvas.delete(item)
        self._sr_items = ()
        self._sr_popup_items = ()
        if self._sr_levels is not None and self.price_data:
            index, label = self._sr_levels
            finder = self.levels_for_chart()[0]
            candle_of_row, _ = self.timeframe_map()
            daily = self.daily_index_for_candle(index)
            start = candle_of_row[finder.window_first(daily, label)]
            color = self.sma_colors[self.sr_color_name]
            items = []
            for level in finder.levels_at(daily, label):
                item = self.level_line_item(
                    start, index, level.price, level.kind, color,
                    tags=("sr_levels", f"sr_levels_{label}"))
                if item is not None:
                    items.append(item)
            self._sr_items = tuple(items)
            if items:
                self.canvas.tag_raise("sr_levels")
        if self._sr_popups:
            theme = self.get_theme()
            items = []
            for popup in self._sr_popups:
                left, top, right, bottom = popup.bounds
                # Unavailable windows get a dashed outline and a red tint, and do not respond to clicks.
                if popup.enabled:
                    box = self.canvas.create_rectangle(
                        left, top, right, bottom, fill=theme["canvas"], outline=theme["ink"],
                        tags=("sr_popup",))
                else:
                    box = self.canvas.create_rectangle(
                        left, top, right, bottom, fill=theme["sr_unavailable"],
                        outline=theme["ink"], dash=(3, 2), tags=("sr_popup",))
                text = self.canvas.create_text(
                    (left + right) / 2, (top + bottom) / 2, text=popup.label,
                    fill=theme["ink"], tags=("sr_popup",))
                items.extend((box, text))
            self._sr_popup_items = tuple(items)
            self.canvas.tag_raise("sr_popup")

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
        self.canvas_indicators.bind("<ButtonPress-1>", self.on_indicators_press)
        self.canvas_indicators.bind("<B1-Motion>", self.scroll_move)
        self.canvas_indicators.bind("<Control-MouseWheel>", self.zoom_chart)
        self.canvas_indicators.bind("<Control-Button-4>", self.zoom_chart)
        self.canvas_indicators.bind("<Control-Button-5>", self.zoom_chart)
        for canvas in (
            self.canvas, self.canvas_price, self.canvas_date, self.canvas_indicators
        ):
            # Added after select_candle on the chart canvas, so the drag ends after the click is handled.
            canvas.bind("<ButtonRelease-1>", self.end_canvas_drag, add="+")
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

        self.dismiss_sr_popups()
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
        self.dismiss_sr_popups()

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

        self.dismiss_sr_popups()
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