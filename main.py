import tkinter as tk
from tkinter import ttk
from pytradeviz import PyTradeViz
from pricedataprepper import PriceDataPrepper

pdp = PriceDataPrepper("./data/data.csv", reverse=True)
price_data_object = pdp.get_price_data_object()

ptz = PyTradeViz(tk, ttk, price_data_object)
ptz.get_window().mainloop()
