"""Help text for the Support and Resistance window.

Each section is a (heading, paragraphs) pair. Paragraphs are plain strings; lines
starting with a bullet are shown as separate points. Pure Python with no Tk
dependency, so the wording can be checked without a display.
"""
from typing import Tuple

HelpSection = Tuple[str, Tuple[str, ...]]

LEVELS_HELP: Tuple[HelpSection, ...] = (
    ("Overview", (
        "A support or resistance level is a price where several past swing points "
        "cluster. Support sits below the latest close and resistance above it.",
        "Changes take effect when you press Apply.",
    )),
    ("1. Swing points", (
        "A swing high is a candle whose high is above the highs of the Pivot bars "
        "candles before it and at or above the highs of the Pivot bars candles after "
        "it. A swing low is the mirror image using lows.",
        "A swing point is used only after its confirming candles have closed, so the "
        "levels never look ahead.",
    )),
    ("2. Clustering", (
        "Swing prices are sorted. A price joins the current group when it is within "
        "Cluster width (% of price) of the group's most recent price. Each group becomes "
        "one candidate level at the group's average price, and its touch count is the "
        "number of swing points in it.",
    )),
    ("3. Qualifying levels", (
        "A candidate qualifies when it has at least Min touches swing points. A "
        "qualifying level below the close is support; one above it is resistance.",
    )),
    ("4. Time windows", (
        "Each window (2W, 1M, 2M, 3M, 6M) uses only swing points from its lookback before "
        "the candle being evaluated. 2W is 14 days; 1M to 6M are calendar months.",
        "Short windows react to recent price action. Long windows show older, slower "
        "levels. Windows are independent, so one price can appear in several of them.",
    )),
    ("5. Nearest two per side", (
        "Each window shows at most two supports (the nearest below the close) and two "
        "resistances (the nearest above it). Other qualifying levels are tracked but "
        "not drawn.",
    )),
    ("6. Mode", (
        "Causal: each candle shows the levels known at that candle, so the chart shows "
        "how levels formed, moved, and were broken over time.",
        "Static: shows only the latest levels across the whole chart, with no history. "
        "Use it for a snapshot of current levels.",
    )),
    ("7. Zones and breaks", (
        "Each level is a zone as wide as Cluster width (% of price) on either side of its "
        "price. A level is broken only by a close beyond the zone, so a wick into the zone "
        "does not count.",
        "In Causal mode a level is drawn from the candle it first qualifies until it is "
        "broken or stops qualifying. It is drawn on each candle where it is one of the "
        "nearest two on its side, so it does not flicker on and off.",
    )),
    ("8. Style (per window)", (
        "• Triangles: a solid up-pointing triangle marks each candle where a support is "
        "shown, and a hollow down-pointing triangle marks a resistance.",
        "• Lines: support is a solid straight line; resistance is a solid zigzag.",
        "• Wavy: support is a dashed straight line; resistance is a solid wave.",
        "Markers from different windows can overlap. Later windows are drawn on top. "
        "Lines or Wavy are often easier to read when several windows are shown.",
        "Show turns a window on or off. Color is set per window.",
    )),
    ("9. Detection settings", (
        "• Pivot bars (candles each side): how many candles must confirm a swing point on "
        "each side. Higher values find fewer, more significant swings, but each one is "
        "known only later. Lower values react faster and find more, smaller levels. "
        "Default 2; must be at least 1.",
        "• Cluster width (% of price): how close two swing prices must be to count as one "
        "level. It also sets the width of each level's zone. Wider merges more swings into "
        "fewer, broader levels, and a break needs a larger move. Default 1.0; must be above 0.",
        "• Min touches: the fewest swing points a level needs. Higher values keep only "
        "well-tested levels, so fewer are shown. Default 2; must be at least 1.",
    )),
    ("10. Breakout odds", (
        "• Horizon (5 or 10 candles): how many candles after a level qualifies its outcome "
        "is watched for. Default 10.",
        "• Rejection: the move away from the level that counts as a rejection. 1 ATR uses "
        "the 14-candle average true range at the level's candle. 2% uses 2% of the level's "
        "price.",
        "Each qualifying level is an event. It is a breakout if price closes beyond its "
        "zone first, or a rejection if price moves the rejection distance away first. If a "
        "candle does both, the breakout counts. Events with no decision within the horizon "
        "expire and are not counted.",
        "Probability = breakouts / (breakouts + rejections), over past events in the same "
        "bucket. A bucket groups events by window, support or resistance, touch count (4 or "
        "more share one bucket), and distance from the close (under 1 ATR, 1 to 3 ATR, or "
        "3 ATR and over).",
        "A bucket with fewer than 10 events shows \"too few\" and no probability.",
        "In Causal mode, odds at a candle use only outcomes resolved by that candle. The "
        "status line uses the latest candle. Labels that would overlap are hidden; the status "
        "line still lists every level.",
        "These are historical frequencies, not forecasts. Overlapping levels are not "
        "independent, and past frequencies do not guarantee future results.",
    )),
)
