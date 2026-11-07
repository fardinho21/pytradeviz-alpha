import tkinter as tk
from tkinter import messagebox, ttk
import csv
from candle import Candle
import datetime as datetime
import math
from indicators import Indicators

class PyTradeViz:

    window_geo="1020x750"
    window_min_width=1020
    window_min_height=750

    canvas_width=900
    canvas_height=500
    canvas_color_bg="white"
    price_limit=3000
    price_data= None
    price_data_object=None
    chart_grid_space_x = 15000 
    #TODO: calculate the chart_grid_space_y inside the init function
    #the value will be equal to the highest p
    chart_grid_space_y = 1000
    base_chart_height = 1000
    chart_grid_divider_v = 30
    chart_grid_divider_h = 20 #20px/price_level
    chart_padding_x = 60
    chart_layout_info = {}
    incrementer=0
    min_zoom_level = 0.5
    max_zoom_level = 4.0
    zoom_step = 1.1
    min_candle_height_scale = 1.0
    max_candle_height_scale = 2.5

    def __init__(self, tk, ttk, price_data_object=None, data_source=None):

        self.price_data_object=price_data_object
        self.price_data=price_data_object["price_data"]
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

        # set up scrollbars
        self.initialize_scrollbars(ttk, tk)

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

    def initialize_window(self, tk):
        self.window = tk.Tk()
        self.window.configure(bg="black")
        self.window.title("PyTradeViz - Alpha")
        self.window.geometry(self.window_geo)
        self.window.minsize(self.window_min_width, self.window_min_height)
        self.window.resizable(True, True)

    def initialize_charts(self, price_data=None):

        for i in range(0, self.chart_grid_space_x, self.chart_grid_divider_v):
            #render vertical lines
            self.canvas_date.create_line(i, 0, i, 50, dash=(5, 5))
            self.canvas.create_line(i, 0, i, self.chart_grid_space_y, dash=(5, 5))
            self.canvas_indicators.create_line(i, 0, i, 100, dash=(5, 5))

        
        self.incrementer = (
            (self.price_upper - self.price_lower)
            * self.chart_grid_divider_h / self.chart_grid_space_y
        )
        price_level = self.price_upper

        for i in range(0, self.chart_grid_space_y, self.chart_grid_divider_h):
            #render horizontal lines 
            self.canvas.create_line(
                0, i, self.chart_grid_space_x, i, dash=(5, 5),
                tags=("horizontal_grid",)
            )
            self.canvas_price.create_line(0, i, 100, i, dash=(5, 5))
            #render price levels
            plrender="{:.2f}".format(price_level)
            self.canvas_price.create_text(
                50, i, text=plrender, anchor="n" if i == 0 else "center",
                tags=("price_label",)
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
        
    def initialize_canvases(self, tk):
        self.canvas= tk.Canvas(self.frame_canvas, width=self.canvas_width, height=self.canvas_height)
        self.canvas_price= tk.Canvas(self.frame_canvas_price, width=100, height=500)
        self.canvas_date = tk.Canvas(self.frame_canvas_date, width=self.canvas_width, height=50)
        self.canvas_indicators= tk.Canvas(self.frame_canvas_indicators, width=self.canvas_width, height=100)

    def initialize_scrollbars(self, ttk, tk):
        self.scrollbar_horizontal = ttk.Scrollbar(
            self.window, orient=tk.HORIZONTAL, command=self.scroll_xview
        )
        self.scrollbar_vertical = ttk.Scrollbar(
            self.window, orient=tk.VERTICAL, command=self.scroll_yview
        )
        self.load_more_button = ttk.Button(
            self.window, text="+3 months →", command=self.load_more_data
        )
        if self.data_source is None or not self.data_source.has_more:
            self.load_more_button.state(["disabled"])

    def initialize_frames(self, ttk):
        self.frame_canvas = ttk.Frame(self.window, width=self.canvas_width, height=self.canvas_height)
        self.frame_canvas_indicators = ttk.Frame(self.window, width=self.canvas_width, height=100)
        self.frame_canvas_price = ttk.Frame(self.window, width=100, height=500)
        self.frame_canvas_date = ttk.Frame(self.window, width=self.canvas_width, height=50)

    def configure_all_canvas(self):
        self.canvas.configure(background=self.canvas_color_bg)
        self.canvas_price.configure(background=self.canvas_color_bg)
        self.canvas_date.configure(background=self.canvas_color_bg)
        self.canvas_indicators.configure(background=self.canvas_color_bg)
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

    def update_scroll_regions(self):
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

    def configure_grid_layout(self):
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
        self.load_more_button.grid(row=3, column=1, columnspan=2, sticky="e")
        self.scrollbar_vertical.grid(row=0, column=2, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_price.grid(row=0, column=0, sticky="nsew")
        self.canvas_date.grid(row=0, column=0, sticky="ew")
        self.canvas_indicators.grid(row=0, column=0, sticky="ew")

    def render_candles(self, start=0, tags=()):
        price_per_pixel = (self.price_upper - self.price_lower) / self.base_chart_height
        for i in range(start, len(self.price_data)):
            pd=self.price_data[i]
            c=Candle(
                pd[1], pd[2], pd[3], pd[4],
                self.chart_padding_x + i*self.chart_grid_divider_v,
                price_per_pixel, self.price_upper / price_per_pixel,
                tags=("candle",) + tags
            )
            c.draw_candle(self.canvas)

    def render_indicators(self, start=0, tags=()):
        self.indicators_object.render_RSI(
            self.canvas_indicators, self.chart_grid_divider_v, self.chart_padding_x,
            start=start, tags=("rsi",) + tags
        )
        pass

    def calculate_grid_space_x(self, price_data_object):
        num_of_candles = len(price_data_object["price_data"])
        rendered_width = (
            max(0, num_of_candles - 1) * self.chart_grid_divider_v
            + 2 * self.chart_padding_x
        )
        self.chart_grid_space_x = max(self.canvas_width, rendered_width)

    def calculate_price_range(self, new_rows=None):
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

    def calculate_(self):
        pass

    def render_dates(self, start=0, tags=()):
        y = self.price_data[start - 1][0][0] if start else ""
        m = self.price_data[start - 1][0][1] if start else ""
        for i in range(start, len(self.price_data)):

            iy = self.price_data[i][0][0]
            im = self.price_data[i][0][1]
            id = self.price_data[i][0][2]
            
            if im != str(m) or iy != str(y):
                m = im
                m_name = datetime.datetime.strptime(str(m), "%m").strftime("%b")

                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 10, text=m_name, tags=tags)
            if iy != str(y):
                y = iy
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text="Y"+str(iy)[2:], tags=tags)
            else:
                self.canvas_date.create_text(self.chart_padding_x + i*self.chart_grid_divider_v, 30, text=str(id), tags=tags)
        pass

    def get_window(self):
        return self.window

    def load_more_data(self):
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
        for i in range(
            start_grid * self.chart_grid_divider_v,
            new_base_width, self.chart_grid_divider_v
        ):
            self.canvas.create_line(
                i, 0, i, self.base_chart_height, dash=(5, 5), tags=("new_page",)
            )
            self.canvas_date.create_line(
                i, 0, i, 50, dash=(5, 5), tags=("new_page",)
            )
            self.canvas_indicators.create_line(
                i, 0, i, 100, dash=(5, 5), tags=("new_page",)
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
        
    def get_canvas(self):
        return self.canvas
        pass

    def scroll_xview(self, *args):
        self.canvas.xview(*args)

    def scroll_yview(self, *args):
        self.canvas.yview(*args)

    def sync_horizontal_scroll(self, first, last):
        self.scrollbar_horizontal.set(first, last)
        self.canvas_date.xview_moveto(first)
        self.canvas_indicators.xview_moveto(first)

    def sync_vertical_scroll(self, first, last):
        self.scrollbar_vertical.set(first, last)
        self.canvas_price.yview_moveto(first)

    def scroll_start(self, event):
        if event.widget is self.canvas:
            self.canvas.scan_mark(event.x, event.y)
        elif event.widget is self.canvas_price:
            self.canvas.scan_mark(0, event.y)
        else:
            self.canvas.scan_mark(event.x, 0)

    def scroll_move(self, event):
        if event.widget is self.canvas:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
        elif event.widget is self.canvas_price:
            self.canvas.scan_dragto(0, event.y, gain=1)
        else:
            self.canvas.scan_dragto(event.x, 0, gain=1)

    def event_bindings(self):
        self.canvas.bind("<ButtonPress-1>", self.scroll_start)
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

    def resize_chart(self, event):
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

    def wheel_scale_factor(self, event):
        if hasattr(event, "delta") and event.delta:
            return self.zoom_step if event.delta > 0 else 1 / self.zoom_step
        if hasattr(event, "num") and event.num in (4, 5):
            return self.zoom_step if event.num == 4 else 1 / self.zoom_step
        return None

    def scale_candle_height(self, event):
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
        return "break"

    def zoom_chart(self, event):
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
        return "break"