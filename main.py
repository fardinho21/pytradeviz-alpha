import tkinter as tk
from tkinter import ttk
from pytradeviz import PyTradeViz
from paginated_price_data import PaginatedPriceData

source = PaginatedPriceData("./data/data.csv")
price_data_object = {"price_data": source.load_initial()}

ptz = PyTradeViz(tk, ttk, price_data_object, data_source=source)
ptz.get_window().mainloop()
