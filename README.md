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
The candle-group button at the bottom right of the chart, beside the horizontal
scrollbar, toggles selection mode, which
shows a "select mode enabled" label. Drag across the chart to box-select the
candles it touches; the selected candles are highlighted and the top-right box
shows the average open, high, low, and close of the selection. Clicking a single
candle selects only that candle, and clicking empty space clears the selection.
Drag-panning is disabled while selection mode is on; the scrollbars and Ctrl
zoom still work. Turning selection mode off clears the selection. Press Escape to leave select,
ROI, or select-and-export mode.
The ROI button beside the candle-group button toggles ROI mode, which shows a
"ROI mode enabled" label in place of the select-mode label. Click and drag across
the chart, then release: the column between the press and release points is
drawn full height and the candles inside it are highlighted. The top-right panel
lists the entry and exit dates, then the percentage change for every pairing of
entry and exit price (open, high, low, close), in the form
`ent(O):ext(C) -> +1.23%`, sorted from highest ROI to lowest. The entry candle is the one under the press point
and the exit candle is the one under the release point. Gains are green and losses
are red. ROI mode and select mode are mutually exclusive, and turning either on
clears the current selection and ROI result.
The button beside the ROI button, labelled `{</>}`, toggles select-and-export mode,
which shows a "select and export mode" label. It uses the same box-select gesture
as select mode. After you release the mouse, a prompt asks for a label for the
selected candles. Each candle stores its open, high, low, close, RSI, and the
3-, 7-, 14-, and 30-candle simple moving averages. Labeled selections are kept in
memory until the program closes.
The menu bar has four menus:

- **File**: *Open Data File* and *Close Data File* are placeholders for now.
  *About* shows the program name, version, and Python version. *Exit* closes the
  program.
- **Indicators**: *Moving Averages* → *Simple* opens the simple moving average
  settings, and *Moving Averages* → *Exponential* opens an empty window for now.
  *RSI* and *Bollinger* are placeholders.
- **Strategies**: a placeholder that does nothing yet.
- **Data**: lists the labeled selections with their candle counts. *Export to JSON*
  and *Export to XML* write all selections to `data/labeled_data/selections_YYYYmmdd_HHMMSS.json`
  or `.xml`. *Add To Existing...* opens a file dialog in `data/labeled_data` and
  merges the current selections into the chosen export, overwriting that file.
  *Clear* removes all labeled selections after you confirm. *Close* closes the window.

Export files use the layouts in `data/export-format.txt`, with these differences:
the JSON is valid JSON (`{"label": {"label_candle_0": {...}}}`), the XML label is
stored in a `label` attribute on each group element, and the moving-average
attributes are named `sma_3d`, `sma_7d`, `sma_2wk`, and `sma_1mo` because XML
attribute names cannot start with a digit.

In the Simple window each moving average has its own *Show* checkbox, line
*Style* (Dotted, Dashed, or Solid), and *Color* (Red, Blue, Orange, Green, or
Violet). The 3-, 7-, 14-, and 30-candle averages use closing prices and are
counted in candles (rows of data), not calendar days. Changes apply when
**Apply** is pressed. Lines are drawn over the candles and follow zooming,
scrolling, dark mode, and loading more data.

Each average also has a *Show Hi-Low MA* checkbox, which is drawn only while
*Show* is checked. It adds two averages of the same period, one of the highs
and one of the lows, drawn as 6-pixel Xs with 1-pixel lines in the average's color.

The window can be resized or maximized.

Run the tests with `python3 -m unittest discover -s tests -v`. Tk integration
tests require a graphical display.
