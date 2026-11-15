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
loaded; the ticker is omitted when the file names none. The `data/XRP_4_year_ohlc_no_vol.csv`
sample and `data/AMZN_10_year_OHLC.csv` are examples. Opening a file shows its oldest year of data. Use the
**>** button at the bottom right to append the next three calendar months. The
**>>>** button beside it loads all remaining data and jumps the view to the newest
candle. Both buttons are disabled when all data has been loaded. Missing dates do
not create synthetic candles.

Only one year of data is drawn at a time on the Daily tab, four years on the 2W tab, and
six years on the 1M, 2M, 3M, and 6M tabs. The window is centred on the middle of the visible chart and
spans half of its length on either side, so candles, dates, and active indicators outside
it are not drawn. Scrolling back into that range redraws
them. Drawings (lines, levels, Fibonacci retracements, and labeled selections) keep
their position even when they are outside the window. All data stays in memory, so
the window only affects drawing, not loading. The vertical price scale still uses all loaded data.

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
ROI, select-and-export, or support/resistance mode.
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
The button beside `{</>}`, labelled `S-R`, toggles support/resistance mode, which shows a
"support/resistance mode" label. Click a candle to highlight it and show four popups
beside the cursor, one per window: 1M, 2M, 3M, and 6M. Clicking a popup draws the
support and resistance levels for that window, ending at the candle, as orange solid
lines. A popup with too little data to draw any level has a dashed outline, a red tint,
and does not respond to clicks. Clicking another candle shows new popups and keeps the
levels already drawn. Clicking empty space, dragging, zooming, or resizing dismisses the
popups. Escape clears the levels and leaves the mode. Dragging still scrolls the chart in
this mode.
The pencil button beside the light/dark mode toggle enters draw mode, which shows a
"draw mode" label and opens a toolbox in the bottom-right corner of the chart. The toolbox
has four rows of options. The first row selects the feature to draw: Line, Segment, Box,
Ellipse, or Fib. Only one can be on at a time, and clicking the active feature turns it off. A
Line spans the full width of the chart. A Segment has a hollow circle at each end. A Fib
(Fibonacci retracement) is drawn by dragging from the start point to the end point. A
dotted diagonal joins the two points in the complementary colour of the levels. It draws
horizontal lines at 0, 23.6, 38.2, 50, 61.8, 78.6, and 100% of the move. Each line is solid
across the box spanned by the two anchors and dotted beyond it, out to the edges of the
chart. Each line is labelled with its percentage and price, and the label sits on a
background that stops the dotted extension. The 0% line sits at the end point and the 100%
line at the start point. The FIB button beside the pencil button
enters draw mode with the Fib feature selected and shows a "fib mode" label. Clicking it
again leaves draw mode. The
second row chooses the style, Solid, Dashed, or Dotted, which is applied to each new
drawing when it is made. The third row chooses Solid or Hollow fill. It only applies to
Box and Ellipse, and is inert (tinted red) for other features. A solid fill is drawn
translucent (a stipple pattern) so candles behind it stay visible. The fourth row is a
row of colour swatches using the indicator colours. The active swatch has a thicker
outline. Colour applies to new drawings only, and existing drawings keep their colour.
The last row has Undo,
Delete (removes the selected drawing), and Clear (removes all drawings). Drag on the chart
with a feature selected to draw. Click a drawing to select it, then drag it to move it. While
a drawing is being drawn or moved, the toolbox fades to a stipple pattern so the candles behind
it stay visible. It returns to solid on release. Hovering over a drawing shows a move cursor. Drawings can only be moved in draw mode, and they stay
fixed when you press Escape, which leaves the mode. Drawings are stored in candle and price
units, so they stay in place when you zoom, scroll, or resize. Opening a new data file clears
them. Drawings, including Fib retracements, are stored per tab. A retracement appears only on
the tab where it was drawn and is not carried over when you switch time frames.
Drawings are not saved to disk.
A row of tabs at the top right of the chart switches the time frame: Daily (the
loaded candles), 2W, 1M, 2M, 3M, and 6M. Weekly tabs group ISO week pairs and monthly
tabs group calendar months, each candle taking the first open, highest high, lowest low,
and last close of its days. Each tab keeps its own drawings, indicator settings, zoom,
candle height, and scroll position, and RSI and the price axis follow the tab's candles.
A tab starts from the indicator settings in use when you first open it. Switching tabs
leaves select, ROI, export, support/resistance, and draw modes. Monthly tabs label the
dates by month and year only. Labeled selections and exports made on a non-daily tab
use that tab's aggregated candles.
The menu bar has five items:

- **File**: *Open Data File* loads a CSV file as described above, replacing any
  data already shown. *Close Data File* clears the candles, RSI, price labels,
  dates, and all labeled selections. *About* shows the program name, version, and Python version. *Exit* closes the
  program.
- **Indicators**: *Moving Averages* → *Simple* opens the simple moving average
  settings, and *Moving Averages* → *Exponential* opens an empty window for now.
  *Bollinger* opens the Bollinger Bands window directly. *Trend Identification* opens the
  trend settings described below. *Support and Resistance*
  opens the level settings described below. The next four items open a settings window for
  one indicator each: *Relative Strength Index (RSI)*, *Avg. Directional Index (ADX)*,
  *Stochastic Oscillator (STOSC)*, and *Williams %R (W%R)*.
- **RSI/ADX/STOSC/W%R canvas**: the strip under the chart shows RSI, ADX, the stochastic
  oscillator or Williams %R. Click the `RSI`, `ADX`, `STOSC` or `W%R` box at its top left to switch; the active box is filled. RSI is drawn
  with its 70 (orange) and 30 (blue) lines. ADX uses Wilder's 14-candle period and is
  drawn with a gray dashed line at 25, the level above which the market is treated as trending.
  STOSC uses %K 14 and %D 3, with the 80 (orange) and 20 (blue) levels; %D is the dashed magenta line.
  W%R uses a 14-candle period, with the -20 (orange) and -80 (blue) levels. It is plotted with 100 added, so 0 is at the top of the canvas and -100 at the bottom.
  Each indicator's settings window has *Cancel*, *Apply*, and *Help* buttons. The settings are
  the period(s) and levels listed above, and each shows its default. *Apply* validates the values,
  shows that indicator on the canvas, and keeps the window open. *Help* explains the indicator and
  what each setting changes. Settings are kept per timeframe tab. Changing the RSI period
  recalculates the RSI for every candle on that tab.
  The `Info` box at the top right of the same canvas opens a window that explains RSI, ADX,
  the stochastic oscillator, Williams %R and how they are used together.
- **Strategies**: a placeholder that does nothing yet.
- **Data**: lists the labeled selections with their candle counts. *Export to JSON*
  and *Export to XML* write all selections to `data/labeled_data/selections_YYYYmmdd_HHMMSS.json`
  or `.xml`. *Add To Existing...* opens a file dialog in `data/labeled_data` and
  merges the current selections into the chosen export, overwriting that file.
  *Clear* removes all labeled selections after you confirm. *Close* closes the window.
- **Reset**: after you confirm, every indicator returns to its default settings (RSI, ADX,
  STOSC, W%R, moving averages, Bollinger Bands, trend shading and support and resistance),
  all drawings are cleared, and RSI is shown on the canvas. This applies to every timeframe
  tab. The loaded data, zoom level, labeled selections and scroll position are kept.
  *Cancel* closes the confirmation without changes.

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
- `rsi_ob` / `rsi_os`: `true` when RSI moves from one side of the overbought or oversold
  level (70 and 30 by default, set in the RSI settings) to the other on this candle, in either
  direction. Labels saved before a change keep the flags they were saved with.

In the Simple window each moving average has its own *Show* checkbox, line
*Style* (Dotted, Dashed, or Solid), and *Color* (Red, Blue, Orange, Green, or
Violet). The 3-, 7-, 14-, and 30-candle averages use closing prices and are
counted in candles (rows of data), not calendar days. Changes apply when
**Apply** is pressed. Lines are drawn over the candles and follow zooming,
scrolling, dark mode, and loading more data.

Each average also has a *Show Hi-Low MA* checkbox, which is drawn only while
*Show* is checked. It adds two averages of the same period, one of the highs
and one of the lows, drawn as 6-pixel Xs with 1-pixel lines in the average's color.

The Bollinger Bands default to a 20-candle window and 2 standard deviations of
the closing prices. Both can be changed in the Bollinger Bands window, and each
timeframe tab keeps its own values. The middle band is the average over the period, and the upper and
lower bands sit the multiplier's number of standard deviations above and below it. The
window has *Period* and *Std. dev. multiplier* fields (each shows its default), a *Show*
checkbox, a line *Style* and a *Color* chosen the same way as the averages, and
**Close**, **Apply** and **Help** buttons. Apply checks the two numbers first, and
nothing changes if one is invalid. The three bands are drawn as lines only, with no shading. While the
bands are shown, the price scale grows to include them and shrinks back when they
are hidden.

The Trend Identification window turns on a background shading that labels each candle
UP (green), DOWN (red) or SIDEWAYS (gray). A candle is SIDEWAYS while ADX is below the
entry level of 25; once ADX reaches 25 the trend stays on until it falls below 20. While the
trend is on, the 7-candle SMA above the 30-candle SMA means UP, and below means DOWN. The
window has a *Show trend shading* checkbox, the four levels and periods (each shows its
default), and **Cancel**, **Apply** and **Help** buttons. Apply checks the values first and
rejects an exit level above the entry level, or a fast period that is not shorter than the
slow one. The **TREND** box at the bottom left of the price chart switches the shading on and
off, and it is kept for each timeframe tab. Hovering the crosshair over a candle shows its
state and ADX value near the top of the chart. The labels use only past candles, and the
ADX gate always uses the standard 14-candle ADX. The shading is a context aid, not a buy or
sell signal.

The *Include volume* checkbox in the same window is off by default. When it is checked and
applied, a candle keeps its UP or DOWN label only if On-Balance Volume (OBV) agrees: OBV must
be above its 20-candle SMA for UP and below it for DOWN. Otherwise the candle is labelled
SIDEWAYS, meaning the trend is not confirmed by volume. The checkbox is disabled when the
loaded data has no volume. Price files with a `Volume` column (for example the AMZN and
APPL files in `data/`) load volume automatically, and the weekly and monthly tabs sum it per
bucket. On a short backtest this filter increased label flips and did not show a consistent
improvement in the next 10 candles, so treat it as an experiment.

The Support and Resistance window draws horizontal price levels found from pivots
(local highs and lows) in four look-back windows: 1 month, 2 months, 3 months,
and 6 months, counted back from the latest candle in calendar time.
Each window has its own *Show* checkbox and *Color*. The window
defaults are Blue (1M), Orange (2M), Green (3M), and Violet (6M),
and all four start hidden. Support is a solid horizontal line and resistance is a
dashed horizontal line. Each level also has a dotted line of the same color at its
rejection distance (1 ATR or 2% of the level's price, as set under *Breakout odds*),
on the side price would bounce toward.

Levels are always found from the daily data, so every tab (2W, 1M, 2M, 3M, 6M) shows
the same levels, drawn on the candles they cover. Crowded same-side levels that sit
within about one label height (14 px) of each other, and whose candle ranges touch or
are adjacent, are drawn as one level at their touch-weighted average price, so zoomed-out
charts do not stack many lines in one band.

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

- *Horizon* (5 or 10 daily candles, default 10): how far ahead an outcome must be
  decided. It counts daily candles on every tab.
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

Run the tests with `python3 tests/run_tests.py`. It runs each test module in its
own process, several at a time, and prints one line per module. Pass module names
(for example `python3 tests/run_tests.py test_zoom`) to run a subset, or `-j N` to
set the number of workers. Tk integration tests require a graphical display.
`python3 -m unittest discover -s tests -v` still runs everything in one process.
