import tkinter as tk
from tkinter import ttk
from tkinter.tix import COLUMN
from turtle import width

class PyTradeViz():

    canvas_width=900
    canvas_height=500
    canvas_color_bg="white"
    price_limit=3000
    date_range=(0,0)

    def __init__(self, tk, ttk):

        #styles
        # self.style = ttk.Style()
        # self.style.configure('fbg.TFrame', background="red")

        #set up window and frames
        self.window = self.initialize_window()
        self.frame_canvas = ttk.Frame(self.window, width=self.canvas_width, height=self.canvas_height)
        self.frame_canvas_price = ttk.Frame(self.window, width=100, height=500)
        self.frame_canvas_date = ttk.Frame(self.window, width=self.canvas_width, height=50)

        # set up canvas
        self.canvas= tk.Canvas(self.frame_canvas, width=self.canvas_width, height=self.canvas_height)
        self.canvas_price= tk.Canvas(self.frame_canvas_price, width=100, height=500)
        self.canvas_date = tk.Canvas(self.frame_canvas_date, width=self.canvas_width, height=50)

        # configure
        self.canvas.configure(background=self.canvas_color_bg)
        self.canvas_price.configure(background=self.canvas_color_bg)
        self.canvas_date.configure(background=self.canvas_color_bg)
        self.canvas.configure(scrollregion=(0,0,3000,3000))
        self.canvas_price.configure(scrollregion=(0,0,100,3000))
        self.canvas_date.configure(scrollregion=(0,0,3000,50))

        #layout manage
        self.frame_canvas.grid()
        self.frame_canvas_price.grid(row=0, column=1, sticky="ns")
        self.frame_canvas_date.grid(row=1, sticky="ew")
        self.canvas.grid(row=0, column=0, sticky="nse")
        self.canvas_price.grid(row=0, column=0, sticky="nsew")
        self.canvas_date.grid(row=0, column=0, sticky="ew")
        # self.frame_canvas.grid_rowconfigure(0,weight=1)
        # self.frame_canvas.grid_columnconfigure(0,weight=2)


        #render chart and price on canvas
        for i in range(0, 3075, 75):
            #vertical
            self.canvas_date.create_line(i, 0, i, 50, dash=(5, 5))
            self.canvas_date.create_text(i, 25, text="date")
            self.canvas.create_line(i, 0, i, 3000, dash=(5, 5))
        for i in range(0, 3025, 25):
            #horizontal
            self.canvas_price.create_text(50, i, text=str(self.price_limit-i))
            self.canvas_price.create_line(0, i, 100, i, dash=(5, 5))
            self.canvas.create_line(0, i, 3000, i, dash=(5, 5))


        #event bind scrolling to mouse dragging
        self.canvas.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas.bind("<B1-Motion>", self.scroll_move)
        self.canvas_price.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_price.bind("<B1-Motion>", self.scroll_move)
        self.canvas_date.bind("<ButtonPress-1>", self.scroll_start)
        self.canvas_date.bind("<B1-Motion>", self.scroll_move)


        pass

    def initialize_window(self):       
        self.window = tk.Tk()
        self.window.configure(bg="black")
        self.window.title("PyTradeViz - Alpha")
        self.window.geometry("1000x750")
        self.window.resizable(False, False) 

        return self.window

    def get_window(self):
        return self.window
        

    def get_canvas(self):
        return self.canvas
        pass

    def scroll_start(self, event):
        self.canvas_price.scan_mark(0, event.y)
        self.canvas_date.scan_mark(event.x, 0)
        self.canvas.scan_mark(event.x, event.y)

    def scroll_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.canvas_date.scan_dragto(event.x, 0, gain=1)
        self.canvas_price.scan_dragto(0, event.y, gain=1)
