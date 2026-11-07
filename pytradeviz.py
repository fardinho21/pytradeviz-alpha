import tkinter as tk
from tkinter import ttk
from candle import Candle
import datetime as datetime
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
    chart_grid_divider_v = 30
    chart_grid_divider_h = 20 #20px/price_level
    chart_layout_info = {}
    incrementer=0

    indicators_object = Indicators()

    def __init__(self, tk, ttk, price_data_object=None):

        self.price_data_object=price_data_object
        self.price_data=price_data_object["price_data"]
        self.indicators_object.set_price_data(self.price_data)
        self.indicators_object.calculate_RSI_full()

        self.calculate_grid_space_x(price_data_object)

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

        
        upperlimit=1.60
        self.incrementer=upperlimit*(self.chart_grid_divider_h/self.chart_grid_space_y)
        price_level=upperlimit

        for i in range(0, self.chart_grid_space_y, self.chart_grid_divider_h):
            #render horizontal lines 
            self.canvas.create_line(0, i, self.chart_grid_space_x, i, dash=(5, 5))
            self.canvas_price.create_line(0, i, 100, i, dash=(5, 5))
            #render price levels
            plrender="{:.2f}".format(price_level)
            self.canvas_price.create_text(50, i, text=plrender)
            price_level-=self.incrementer

            self.canvas_indicators.create_line(0, 70, self.chart_grid_space_x, 70, fill="orange", width=2)
            self.canvas_indicators.create_line(0, 30, self.chart_grid_space_x, 30, fill="blue", width=2)

        print(len(self.price_data))
        
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
        self.scrollbar_vertical.grid(row=0, column=2, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_price.grid(row=0, column=0, sticky="nsew")
        self.canvas_date.grid(row=0, column=0, sticky="ew")
        self.canvas_indicators.grid(row=0, column=0, sticky="ew")

    def render_candles(self):
        for i in range(0, len(self.price_data)):
            pd=self.price_data[i]
            c=Candle(pd[1], pd[2], pd[3], pd[4], i*self.chart_grid_divider_v, self.incrementer/self.chart_grid_divider_h)
            c.draw_candle(self.canvas)

    def render_indicators(self):
        self.indicators_object.render_RSI(self.canvas_indicators, self.chart_grid_divider_v)
        pass

    def calculate_grid_space_x(self, price_data_object):
        num_of_candles = len(price_data_object["price_data"])
        rendered_width = (
            num_of_candles * self.chart_grid_divider_v + Candle.candle_width
        )
        self.chart_grid_space_x = max(self.canvas_width, rendered_width)

    def calculate_(self):
        pass

    def render_dates(self):
        y=""
        m=""
        for i in range(0, len(self.price_data) - 1):

            iy = self.price_data[i][0][0]
            im = self.price_data[i][0][1]
            id = self.price_data[i][0][2]
            
            if im != str(m):
                m = im
                m_name = datetime.datetime.strptime(str(m), "%m").strftime("%b")

                self.canvas_date.create_text(i*self.chart_grid_divider_v, 10, text=m_name)
            if iy != str(y):
                y = iy
                self.canvas_date.create_text(i*self.chart_grid_divider_v, 30, text="Y"+str(iy)[2:])
            else:
                self.canvas_date.create_text(i*self.chart_grid_divider_v, 30, text=str(id))
        pass

    def get_window(self):
        return self.window
        
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
        self.canvas_price.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_price.bind("<B1-Motion>", self.scroll_move)
        self.canvas_date.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_date.bind("<B1-Motion>", self.scroll_move)
        self.canvas_indicators.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_indicators.bind("<B1-Motion>", self.scroll_move)

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
        self.chart_grid_space_x *= scale_x
        self.chart_grid_space_y *= scale_y

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

        self.canvas.xview_moveto(horizontal_position)
        self.canvas.yview_moveto(vertical_position)