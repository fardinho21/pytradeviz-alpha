# PyTradeViz

Run the visualizer from the repository root with:

```sh
python3 main.py
```

The application starts with no data loaded. The chart is empty and a
"No price data is loaded" message is shown. Use **File → Open Data File** to
choose a CSV file of OHLC data. The file must have a header row (the first
record that names the columns) with a `date` or `datetime` column and `open`,
`high`, `low`, and `close` columns, matched case-insensitively in any order.
Other columns are ignored. Dates may be written as `YYYY-MM-DD`,
`YYYY-MM-DD HH:MM[:SS]` (with a space or `T` between date and time), or
`YYYY/MM/DD`. Rows may be in either oldest-first or newest-first order, but
each timestamp must be unique. OHLC values may have a leading `$`. Ambiguous
formats such as `MM/DD/YYYY` are not accepted. The asset ticker is the first
value of a `symbol` column, or else a lone line above the header that is not a
URL. The top-left corner shows that ticker and the close of the last candle
loaded; the ticker is omitted when the file names none. The `data/data.csv`
sample (CryptoDataDownload format) and `data/AMZN_10_year_OHLC.csv` are
examples. Opening a file shows its oldest year of data. Use the
**+3 months →** button at the bottom right to append the next three calendar
months; the button is disabled when all data has been loaded. Missing dates do
not create synthetic candles.

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
selected candles. Each candle stores its open, high, low, close, RSI, the
3-, 7-, 14-, and 30-candle simple moving averages, and the Bollinger middle, upper,
and lower bands. Labeled selections are kept in
memory until *Close Data File* or the program exits. Opening a new data file
keeps them.
The menu bar has four menus:

- **File**: *Open Data File* loads a CSV file as described above, replacing any
  data already shown. *Close Data File* clears the candles, RSI, price labels,
  dates, and all labeled selections. *About* shows the program name, version, and Python version. *Exit* closes the
  program.
- **Indicators**: *Moving Averages* → *Simple* opens the simple moving average
  settings, and *Moving Averages* → *Exponential* opens an empty window for now.
  *Bollinger* → *Bollinger Bands* opens the Bollinger settings. *Support and Resistance*
  opens the level settings described below. *RSI* is a placeholder.
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
attribute names cannot start with a digit. The Bollinger values are stored as
`bollinger_middle`, `bollinger_upper`, and `bollinger_lower`.

Each candle also has four flags, written as `true`, `false`, or `null` (JSON) and
`true`, `false`, or an empty attribute (XML). `null` means the flag cannot be
determined yet, for example during the Bollinger warm-up or on the first candle for RSI:
- `top_bol_intersect` / `btm_bol_intersect`: `true` when the candle's high-low range
  contains the top or bottom Bollinger band value (`low <= band <= high`).
- `rsi_ob` / `rsi_os`: `true` when RSI moves from one side of 70 (overbought) or 30
  (oversold) to the other on this candle, in either direction.

In the Simple window each moving average has its own *Show* checkbox, line
*Style* (Dotted, Dashed, or Solid), and *Color* (Red, Blue, Orange, Green, or
Violet). The 3-, 7-, 14-, and 30-candle averages use closing prices and are
counted in candles (rows of data), not calendar days. Changes apply when
**Apply** is pressed. Lines are drawn over the candles and follow zooming,
scrolling, dark mode, and loading more data.

Each average also has a *Show Hi-Low MA* checkbox, which is drawn only while
*Show* is checked. It adds two averages of the same period, one of the highs
and one of the lows, drawn as 6-pixel Xs with 1-pixel lines in the average's color.

The Bollinger Bands use a fixed 20-candle window and 2 standard deviations of
the closing prices. The middle band is the 20-candle average, and the upper and
lower bands sit 2 standard deviations above and below it. The window has a *Show*
checkbox, a line *Style* and a *Color* chosen the same way as the averages, and
**Apply**. The three bands are drawn as lines only, with no shading. While the
bands are shown, the price scale grows to include them and shrinks back when they
are hidden.

The Support and Resistance window draws horizontal price levels found from pivots
(local highs and lows) in five look-back windows: 2 weeks, 1 month, 2 months,
3 months, and 6 months, counted back from the latest candle in calendar time.
Each window has its own *Show* checkbox, *Color*, and *Style*. The window
defaults are Red (2W), Blue (1M), Orange (2M), Green (3M), and Violet (6M),
and all five start hidden. The styles are:

- *Triangles*: a marker on each visible candle the level spans, a solid upward
  triangle for support and a hollow downward triangle for resistance.
- *Lines*: a solid straight line for support and a solid zigzag line for resistance.
- *Wavy*: a dashed straight line for support and a solid wavy line for resistance.

Lines are drawn only across the visible part of the level's span. A level is a cluster of pivot prices within a width
of the price, and it needs at least *Min touches* pivots. Each window
shows at most 2 support levels (below the close) and 2 resistance levels (above the
close) on any candle, the nearest to the close.

- *Causal* mode draws each level from the first candle it qualifies, using only
  the pivots confirmed by that candle, until price closes beyond the level's zone
  (its width on either side) or its pivots leave the window. A pivot is confirmed
  only after *Pivot bars* later candles have closed, so a level never uses future
  candles.
- *Static* mode draws the levels present at the latest candle across the full
  chart.

Detection settings: *Pivot bars* (default 2) is how many candles on each side a
pivot must be higher or lower than. *Cluster width* (default 1.0%) is the percent
of price within which pivot prices merge. *Min touches* (default 2) is the
pivot count a level needs. Changes apply when **Apply** is pressed. Each window
shows its latest support and resistance count, or "No pivots in this window".
Dates are stored by day, so windows are measured in days, and on daily data the
2-week window often has few or no pivots.
The **Help** button in this window opens an in-app guide to these settings and the
breakout odds, with the same rules described here.

Breakout odds: the status line for each window adds, for each shown level, the
historical chance that price breaks through it before it is rejected, in the form
`S 99.12 38% n=24` (price, percent, and sample count). Two switches choose the rule:

- *Horizon* (5 or 10 candles, default 10): how far ahead an outcome must be decided.
- *Rejection* (1 ATR or 2%, default 1 ATR): how far price must move away from the
  level to count as a rejection. 1 ATR uses the 14-candle average true range at the
  level's first candle; 2% uses 2% of the level's price.

A level is a breakout when a candle closes beyond its zone, and a rejection when
price moves the rejection distance away from it. Whichever happens first decides
the outcome, and a breakout wins if both happen on the same candle. Levels with
neither within the horizon are left out. The percent is breakouts divided by
breakouts plus rejections among levels in the same window with the same touch count
(capped at 4) and distance from the close (under 1, 1 to 3, or 3 ATR and over), counting
only levels whose outcome was already known when this level first qualified. A
bucket with fewer than 10 outcomes shows `n=… (too few)` instead of a percent.
Chart labels sit at the visible end of each level and are skipped where they would
overlap another label; the status line always lists every shown level.

These are historical frequencies, not forecasts. Levels in the same window overlap,
so their outcomes are not independent, and the odds for recent levels are based
on less data.

The window can be resized or maximized.

Run the tests with `python3 -m unittest discover -s tests -v`. Tk integration
tests require a graphical display.
