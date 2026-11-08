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
to zoom. Click a candle to show its date and open, high, low, and close values
in the top-right corner of the chart. Hold Shift and use the mouse wheel over
the chart or its axes to adjust candle height and the price scale independently
from 1.0× to 2.5×. The ☾/☀ button in the bottom-right corner, above the load button, toggles
dark mode, which hollows out the candles and inverts the chart colors.
Moving the cursor over the chart shows a crosshair: a solid vertical line with
the date at the top and a solid horizontal line with the price at the right
edge. Its colors follow the theme (black in light mode, soft orange in dark mode).
The candle-group button at the very bottom right toggles selection mode, which
shows a "select mode enabled" label. Drag across the chart to box-select the
candles it touches; the selected candles are highlighted and the top-right box
shows the average open, high, low, and close of the selection. Clicking a single
candle selects only that candle, and clicking empty space clears the selection.
Drag-panning is disabled while selection mode is on; the scrollbars and Ctrl
zoom still work. Turning selection mode off clears the selection.
The window can be resized or maximized.

Run the tests with `python3 -m unittest discover -s tests -v`. Tk integration
tests require a graphical display.
