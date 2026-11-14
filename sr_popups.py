"""Geometry for the window popups shown beside a candle in support/resistance mode.

Coordinates are canvas coordinates. A bounds tuple is (left, top, right, bottom).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

Bounds = Tuple[float, float, float, float]

POPUP_WIDTH = 44
POPUP_HEIGHT = 20
POPUP_GAP = 4
POPUP_OFFSET = 12


@dataclass(frozen=True)
class SRPopup:
    label: str
    enabled: bool
    bounds: Bounds

    def contains(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.bounds
        return left <= x <= right and top <= y <= bottom


def popup_bounds(anchor_x: float, anchor_y: float, count: int, view: Bounds) -> List[Bounds]:
    """Stack ``count`` popups below and right of the cursor, kept inside ``view``.

    The stack flips to the left of the cursor near the right edge, and to above it near
    the bottom edge.
    """
    left, top, right, bottom = view
    stack_height = count * POPUP_HEIGHT + (count - 1) * POPUP_GAP
    x0 = anchor_x + POPUP_OFFSET
    if x0 + POPUP_WIDTH > right:
        x0 = anchor_x - POPUP_OFFSET - POPUP_WIDTH
    x0 = min(max(x0, left), right - POPUP_WIDTH)
    y0 = anchor_y + POPUP_OFFSET
    if y0 + stack_height > bottom:
        y0 = anchor_y - POPUP_OFFSET - stack_height
    y0 = min(max(y0, top), bottom - stack_height)
    boxes: List[Bounds] = []
    for i in range(count):
        box_top = y0 + i * (POPUP_HEIGHT + POPUP_GAP)
        boxes.append((x0, box_top, x0 + POPUP_WIDTH, box_top + POPUP_HEIGHT))
    return boxes
