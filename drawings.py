"""Geometry and layout for the drawing tools used in draw mode.

Drawings are stored in chart units, (candle position, price), so they stay put when the
chart is zoomed, scrolled, or resized. Clipping, hit tests, and the toolbox layout work in
canvas coordinates. A bounds tuple is (left, top, right, bottom).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence, Tuple

Bounds = Tuple[float, float, float, float]
Point = Tuple[float, float]

LINE = "line"
SEGMENT = "segment"
BOX = "box"
ELLIPSE = "ellipse"
FILLABLE_KINDS = (BOX, ELLIPSE)

SOLID = "solid"
DASHED = "dashed"
DOTTED = "dotted"
STYLE_DASHES = {SOLID: (), DASHED: (8, 4), DOTTED: (2, 4)}

SEGMENT_CIRCLE_RADIUS = 4
HIT_TOLERANCE = 6

# Solid fills use a stipple so the candles underneath still show through.
FILL_STIPPLE = "gray50"

BUTTON_WIDTH = 80
SWATCH_WIDTH = 24
BUTTON_HEIGHT = 22
BUTTON_GAP = 6
ROW_GAP = 6
TOOLBOX_PADDING = 8
TOOLBOX_MARGIN = 12


@dataclass(frozen=True)
class Drawing:
    id: int
    kind: str
    style: str
    color: str
    filled: bool
    start: Point
    end: Point

    def translated(self, index_delta: float, price_delta: float) -> Drawing:
        return replace(
            self,
            start=(self.start[0] + index_delta, self.start[1] + price_delta),
            end=(self.end[0] + index_delta, self.end[1] + price_delta),
        )


def fill_applicable(tool: Optional[str]) -> bool:
    return tool in FILLABLE_KINDS


def clip_line(p1: Point, p2: Point, bounds: Bounds) -> Optional[Tuple[float, float, float, float]]:
    """Return the part of the infinite line through p1 and p2 that lies inside bounds.

    Uses the Liang-Barsky algorithm. Returns None for a degenerate line or one that misses
    the bounds.
    """
    x1, y1 = p1
    dx = p2[0] - x1
    dy = p2[1] - y1
    if dx == 0 and dy == 0:
        return None
    left, top, right, bottom = bounds
    t_min = -math.inf
    t_max = math.inf
    for p, q in ((-dx, x1 - left), (dx, right - x1), (-dy, y1 - top), (dy, bottom - y1)):
        if p == 0:
            if q < 0:
                return None
            continue
        ratio = q / p
        if p < 0:
            t_min = max(t_min, ratio)
        else:
            t_max = min(t_max, ratio)
    if t_min > t_max:
        return None
    return (x1 + t_min * dx, y1 + t_min * dy, x1 + t_max * dx, y1 + t_max * dy)


def distance_to_segment(x: float, y: float, p1: Point, p2: Point) -> float:
    x1, y1 = p1
    dx = p2[0] - x1
    dy = p2[1] - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_sq))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def hit_test(kind: str, p1: Point, p2: Point, x: float, y: float,
             tolerance: float = HIT_TOLERANCE) -> bool:
    """Whether canvas point (x, y) is on or inside a drawing with anchors p1 and p2."""
    if kind == LINE:
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if length == 0:
            return False
        cross = (p2[0] - p1[0]) * (p1[1] - y) - (p1[0] - x) * (p2[1] - p1[1])
        return abs(cross) / length <= tolerance
    if kind == SEGMENT:
        return distance_to_segment(x, y, p1, p2) <= tolerance
    left, right = sorted((p1[0], p2[0]))
    top, bottom = sorted((p1[1], p2[1]))
    if kind == BOX:
        return left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    radius_x = (right - left) / 2 + tolerance
    radius_y = (bottom - top) / 2 + tolerance
    return ((x - center_x) / radius_x) ** 2 + ((y - center_y) / radius_y) ** 2 <= 1


ToolKey = Tuple[str, Any]


@dataclass(frozen=True)
class ToolButton:
    key: ToolKey
    text: str
    bounds: Bounds

    def contains(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.bounds
        return left <= x <= right and top <= y <= bottom


@dataclass(frozen=True)
class Toolbox:
    bounds: Bounds
    buttons: Tuple[ToolButton, ...]

    def contains(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.bounds
        return left <= x <= right and top <= y <= bottom

    def button_at(self, x: float, y: float) -> Optional[ToolButton]:
        for button in self.buttons:
            if button.contains(x, y):
                return button
        return None


# Rows from top to bottom. Each entry is ((action, value), label).
# Rows above the colour row. Colour swatches are added by toolbox_rows().
TOOLBOX_ROWS: Tuple[Tuple[Tuple[ToolKey, str], ...], ...] = (
    (
        (("tool", LINE), "Line"),
        (("tool", SEGMENT), "Segment"),
        (("tool", BOX), "Box"),
        (("tool", ELLIPSE), "Ellipse"),
    ),
    (
        (("style", SOLID), "Solid"),
        (("style", DASHED), "Dashed"),
        (("style", DOTTED), "Dotted"),
    ),
    (
        (("fill", True), "Solid"),
        (("fill", False), "Hollow"),
    ),
    (
        (("undo", None), "Undo"),
        (("delete", None), "Delete"),
        (("clear", None), "Clear"),
    ),
)
COLOR_ROW_INDEX = 3


def toolbox_rows(colors: Sequence[str]) -> Tuple[Tuple[Tuple[ToolKey, str], ...], ...]:
    """The toolbox rows, with one row of colour swatches after the fill row."""
    swatches = tuple((("color", name), "") for name in colors)
    return TOOLBOX_ROWS[:COLOR_ROW_INDEX] + (swatches,) + TOOLBOX_ROWS[COLOR_ROW_INDEX:]


def button_width(key: ToolKey) -> int:
    return SWATCH_WIDTH if key[0] == "color" else BUTTON_WIDTH


def toolbox_layout(view: Bounds, colors: Sequence[str]) -> Toolbox:
    """Place the toolbox in the bottom-right corner of the view, rows centred on each other."""
    rows = toolbox_rows(colors)
    row_widths = [
        sum(button_width(key) for key, _ in row) + (len(row) - 1) * BUTTON_GAP for row in rows
    ]
    content_width = max(row_widths)
    width = content_width + 2 * TOOLBOX_PADDING
    height = (len(rows) * BUTTON_HEIGHT + (len(rows) - 1) * ROW_GAP
              + 2 * TOOLBOX_PADDING)
    right = view[2] - TOOLBOX_MARGIN
    bottom = view[3] - TOOLBOX_MARGIN
    left = max(right - width, view[0])
    top = max(bottom - height, view[1])
    buttons = []
    for row_index, row in enumerate(rows):
        row_left = left + TOOLBOX_PADDING + (content_width - row_widths[row_index]) / 2
        row_top = top + TOOLBOX_PADDING + row_index * (BUTTON_HEIGHT + ROW_GAP)
        button_left = row_left
        for key, text in row:
            width_of_button = button_width(key)
            buttons.append(ToolButton(
                key, text,
                (button_left, row_top, button_left + width_of_button, row_top + BUTTON_HEIGHT),
            ))
            button_left += width_of_button + BUTTON_GAP
    return Toolbox((left, top, right, bottom), tuple(buttons))

