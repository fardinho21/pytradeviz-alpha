# PyTradeViz

Run the visualizer from the repository root with:

```sh
python3 main.py
```

The application reads `data/data.csv` in CryptoDataDownload CSV format, with
two header lines and newest records first. It initially displays the oldest
year of available data. Use the **+3 months →** button at the bottom right to
append the next three calendar months; the button is disabled when all data
has been loaded. Missing dates do not create synthetic candles.

Drag the chart to pan, use the scrollbars, or hold Ctrl and use the mouse wheel
to zoom. Hold Shift and use the mouse wheel over the chart or its axes to
adjust candle height and the price scale independently from 1.0× to 2.5×.
The window can be resized or maximized.

Run the tests with `python3 -m unittest discover -s tests -v`. Tk integration
tests require a graphical display.
