import tkinter as tk
from tkinter import ttk
from candle import Candle
from pytradeviz import PyTradeViz
from pricedataprepper import PriceDataPrepper

#Data Prepper
pdp = PriceDataPrepper("./data/data.csv")
price_data = pdp.get_price_data_object()["price_data"]


for e in price_data:
    print(e)
    input()

print(pdp)

#Visualizer 
# ptz = PyTradeViz(tk, ttk)



input()

#runs the Tkinter event loop that listents for input events 
#window.mainloop() 
