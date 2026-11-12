import tkinter as tk
from tkinter import ttk
from pytradeviz import PyTradeViz

ptz = PyTradeViz(tk, ttk, {"price_data": []})
ptz.get_window().mainloop()
