import tkinter as tk
from tkinter import ttk
from candle import Candle
from pytradeviz import PyTradeViz
from pricedataprepper import PriceDataPrepper

#Data Prepper
pdp = PriceDataPrepper("./data/data.csv")

print(pdp)

#Visualizer 
# ptz = PyTradeViz(tk, ttk)



input()

#runs the Tkinter event loop that listents for input events 
#window.mainloop() 
