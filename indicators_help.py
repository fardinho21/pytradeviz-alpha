"""Help text for the indicator windows: the canvas Info box and the per-indicator Help buttons.

Each section is a (heading, paragraphs) pair in the same format as levels_help.py.
Pure Python with no Tk dependency, so the wording can be checked without a display.
"""
from typing import Dict, Tuple

HelpSection = Tuple[str, Tuple[str, ...]]

RSI_HELP: HelpSection = ("RSI (Relative Strength Index)", (
    "RSI is a momentum oscillator. It compares the size of recent gains with recent "
    "losses and scales the result from 0 to 100. By default this chart uses a 7-candle RSI.",
    "• Above 70 (orange line): overbought. Recent buying has been strong.\n"
    "• Below 30 (blue line): oversold. Recent selling has been strong.\n"
    "• Around 50: neutral momentum. Readings above 50 favour buyers; below 50 favour sellers.",
    "How it is used: watch for RSI leaving the overbought or oversold zone, and for "
    "divergence, where price makes a new high or low but RSI does not.",
    "RSI describes momentum, not trend strength. A strong trend can keep RSI above 70 "
    "or below 30 for a long time, so these zones are not reversal signals on their own.",
))

ADX_HELP: HelpSection = ("ADX (Average Directional Index)", (
    "ADX measures how strong a trend is, on a scale from 0 to 100. It does not show "
    "direction: a high ADX can belong to an uptrend or a downtrend.",
    "By default the chart uses Wilder's 14-candle period. The gray dashed line at 25 is the "
    "level above which the market is treated as trending. Below 25 it is treated as sideways "
    "or weak. Values below about 20 usually mean no clear trend.",
    "How it is used: a rising ADX means the trend is strengthening. A falling ADX means "
    "it is weakening or the market is moving sideways.",
    "ADX is smoothed, so it reacts slowly. The first value appears after about 27 candles.",
))

STOSC_HELP: HelpSection = ("STOSC (Stochastic Oscillator)", (
    "The stochastic oscillator compares the close with the high-low range of the last "
    "14 candles. It scales the result from 0 to 100: near 100 means the close is near "
    "the top of that range, near 0 means it is near the bottom.",
    "%K (solid line) is the raw reading. %D (dashed magenta line) is the 3-candle "
    "average of %K, so it moves more slowly.",
    "• Above 80 (orange line): overbought. Closes are near the top of the recent range.\n"
    "• Below 20 (blue line): oversold. Closes are near the bottom of the recent range.",
    "How it is used: a %K crossing below %D while above 80 can warn that a rally is "
    "fading. A %K crossing above %D while below 20 can warn that a decline is "
    "weakening. Divergence also helps: a new price low with a higher stochastic low "
    "can mean selling pressure is easing.",
    "Like RSI, the stochastic measures momentum, not trend strength. In a strong trend "
    "it can stay above 80 or below 20 for a long time.",
))

WILLR_HELP: HelpSection = ("W%R (Williams %R)", (
    "Williams %R measures where the close sits within the high-low range of the last "
    "14 candles. It runs from -100 to 0: near 0 means the close is near the top of that "
    "range, near -100 means it is near the bottom. It is the stochastic idea, inverted.",
    "Default setup: 14 candles, no smoothing. The chart adds 100 to the value so it "
    "fits the same canvas as the other indicators: the top of the canvas is 0 and the "
    "bottom is -100. If the high and low are equal over the window, the value is -50.",
    "• Above -20 (orange line): overbought. Closes are near the top of the recent range.\n"
    "• Below -80 (blue line): oversold. Closes are near the bottom of the recent range.",
    "How it is used: a move back below -20 after a stay above it can warn that buying is "
    "fading. A move back above -80 after a stay below it can warn that selling is easing. "
    "Divergence against price is also useful.",
    "Williams %R is a momentum measure, not trend strength, and it reacts quickly. In a "
    "strong trend it can stay near 0 or -100 for a long time, so check ADX before relying "
    "on it.",
))

TOGETHER_HELP: HelpSection = ("Using them together", (
    "ADX answers whether a trend exists. RSI, the stochastic and Williams %R show the "
    "momentum behind price moves.",
    "Example: if ADX is falling toward 20 while RSI is near 30 and price keeps "
    "making lower lows, the downtrend may be losing strength.",
    "These indicators give context, not buy or sell signals. Confirm them against price "
    "action and your own risk rules.",
))

# The Info box on the indicator canvas.
INDICATOR_HELP: Tuple[HelpSection, ...] = (RSI_HELP, ADX_HELP, STOSC_HELP, WILLR_HELP, TOGETHER_HELP)

# Bollinger Bands are drawn on the price chart and configured from Indicators > Bollinger.
BOLLINGER_HELP: HelpSection = ("Bollinger Bands", (
    "Bollinger Bands show how far the closing price moves away from its recent average. The "
    "middle band is the simple moving average of the closes over the period. The upper and "
    "lower bands sit the standard deviation multiplier above and below it, using the same window.",
    "The bands widen when prices are volatile and narrow when they are quiet. Most closes "
    "usually fall between the bands.",
    "A touch happens when a candle's high-low range reaches a band. Repeated touches of the "
    "lower band during a downtrend can mean the downtrend is weakening. This is stronger when "
    "RSI is oversold and ADX is low, around 20, because a low ADX means there is little trend "
    "strength left. A touch on its own is not a buy or sell signal.",
))

BOLLINGER_SETTINGS_HELP: HelpSection = ("Settings", (
    "Period (default 20, minimum 2): the number of candles in the average and in the standard "
    "deviation window. A shorter period makes the bands follow price closely and react faster. "
    "A longer period gives smoother, slower bands.",
    "Std. dev. multiplier (default 2, from 0.1 to 10): the distance of the upper and lower bands "
    "from the middle band, in standard deviations. A higher value widens the bands and a lower "
    "value tightens them. It does not move the middle band.",
    "Show, Style and Color only change how the bands are drawn. They do not change the values.",
    "When the bands are shown, changing the period or multiplier rescales the price axis so the "
    "bands fit. Labeled exports store the band values and the touch flags as they were when each "
    "label was saved. Labels saved before a change keep their old values.",
))

BOLLINGER_DETAILED_HELP: Tuple[HelpSection, ...] = (BOLLINGER_HELP, BOLLINGER_SETTINGS_HELP)

# Per-indicator settings help: the settings window's Help button shows the Info text for the
# indicator followed by this section, which explains what each parameter changes on the chart.
SETTINGS_HELP: Dict[str, HelpSection] = {
    "RSI": ("Settings", (
        "Period (default 7, minimum 2): the length of the averaging window. A shorter period "
        "reacts faster and swings between 0 and 100 more often. A longer period, such as 14, "
        "gives a smoother line that moves more slowly.",
        "Changing the period recalculates RSI for every candle on this timeframe. The stored "
        "RSI values, candle info and the overbought and oversold flags in labeled exports all "
        "use the new period. Labels saved before the change keep the values they were saved with.",
        "Overbought level (default 70): moves the orange line. Readings at or above it are "
        "flagged overbought in labeled exports. A lower level flags overbought earlier.",
        "Oversold level (default 30): moves the blue line. Readings at or below it are flagged "
        "oversold in labeled exports. A higher level flags oversold earlier.",
        "The overbought level must be above the oversold level. Levels run from 0 to 100.",
    )),
    "ADX": ("Settings", (
        "Period (default 14, minimum 2): the smoothing length for the directional movement "
        "and ADX values. A shorter period reacts faster but is noisier. A longer period is "
        "steadier but lags more. The first value appears after roughly twice the period.",
        "Trend level (default 25): moves the gray dashed line. It only changes the reference "
        "line; the ADX curve itself is not affected. Readings above the line are read as a "
        "trend, and readings below it as sideways.",
        "Levels run from 0 to 100.",
    )),
    "STOSC": ("Settings", (
        "%K period (default 14, minimum 2): the number of candles in the high-low range that "
        "%K compares the close against. A shorter period gives a more sensitive line that "
        "reaches 80 and 20 more often. A longer period is smoother.",
        "%D period (default 3, minimum 1): the moving average applied to %K. A larger value "
        "gives a smoother %D line that trails %K by more. A value of 1 makes %D equal to %K.",
        "Overbought level (default 80) and oversold level (default 20): move the orange and "
        "blue lines. They do not change the %K or %D values, only the reference lines.",
        "The overbought level must be above the oversold level. Levels run from 0 to 100.",
    )),
    "W%R": ("Settings", (
        "Period (default 14, minimum 2): the number of candles in the high-low range that the "
        "close is compared against. A shorter period reverses quickly and flips between -100 "
        "and 0 more often. A longer period is smoother and slower.",
        "Overbought level (default -20) and oversold level (default -80): move the orange and "
        "blue lines. They do not change the Williams %R values, only the reference lines.",
        "Levels run from -100 to 0. The overbought level must be above the oversold level, "
        "so the default -20 is above -80.",
    )),
}

# The Help window for each indicator's settings: its Info text followed by its settings.
INDICATOR_DETAILED_HELP: Dict[str, Tuple[HelpSection, ...]] = {
    "RSI": (RSI_HELP, SETTINGS_HELP["RSI"]),
    "ADX": (ADX_HELP, SETTINGS_HELP["ADX"]),
    "STOSC": (STOSC_HELP, SETTINGS_HELP["STOSC"]),
    "W%R": (WILLR_HELP, SETTINGS_HELP["W%R"]),
}
