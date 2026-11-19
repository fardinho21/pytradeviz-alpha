"""Mouse cursors for the chart: a pointing hand over buttons and a closed fist while dragging.

Tk names the pointing hand ``hand2`` on every platform. Only macOS ships a closed hand, so one
is drawn here as a 16 by 16 picture and shipped as an X bitmap (``cursors/closed_hand.xbm``
with its mask), which Tk on X11 loads with its ``@source mask foreground background`` form.
``closed_hand_candidates`` lists the cursors to try for dragging, best first, and
``first_supported_cursor`` picks the first one Tk accepts, so Windows falls back to the
four-way move arrow. The bitmap files are generated from ``CLOSED_HAND_PICTURE`` by
``closed_hand_xbm_texts``; tests/test_cursors.py checks that they still match it.
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any, Callable, Sequence, Tuple

POINTING_HAND = "hand2"
MOVE_CURSOR = "fleur"

CURSOR_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cursors")
CLOSED_HAND_SOURCE = os.path.join(CURSOR_DIRECTORY, "closed_hand.xbm")
CLOSED_HAND_MASK = os.path.join(CURSOR_DIRECTORY, "closed_hand_mask.xbm")

# The fist seen from the back: three knuckles, the thumb tucked in at the left, the wrist below.
# ``#`` is the black outline, ``o`` the white fill and ``.`` is transparent.
CLOSED_HAND_PICTURE: Tuple[str, ...] = (
    "................",
    "................",
    "....###.###.###.",
    "...#ooo#ooo#ooo#",
    "...#ooo#ooo#ooo#",
    ".###ooo#ooo#ooo#",
    "#oo#ooooooooooo#",
    "#oooooooooooooo#",
    ".#ooooooooooooo#",
    ".#oooooooooooo#.",
    "..#ooooooooooo#.",
    "..#oooooooooo#..",
    "...#ooooooooo#..",
    "....#########...",
    "................",
    "................",
)
# The point of the cursor that counts as the pointer position: the middle of the fist.
CLOSED_HAND_HOTSPOT = (8, 8)


def xbm_text(name: str, picture: Sequence[str], keep: Callable[[str], bool],
             hotspot: Tuple[int, int]) -> str:
    """An X bitmap file for ``picture``, with the cells ``keep`` accepts set to 1.

    Rows are packed eight cells to a byte, least significant bit first, as the format requires.
    """
    width, height = len(picture[0]), len(picture)
    data = []
    for row in picture:
        for start in range(0, width, 8):
            byte = 0
            for bit, cell in enumerate(row[start:start + 8]):
                if keep(cell):
                    byte |= 1 << bit
            data.append(byte)
    words = [f"0x{byte:02x}" for byte in data]
    lines = [", ".join(words[i:i + 12]) for i in range(0, len(words), 12)]
    return (
        f"#define {name}_width {width}\n#define {name}_height {height}\n"
        f"#define {name}_x_hot {hotspot[0]}\n#define {name}_y_hot {hotspot[1]}\n"
        f"static unsigned char {name}_bits[] = {{\n   " + ",\n   ".join(lines) + "};\n"
    )


def closed_hand_xbm_texts() -> Tuple[str, str]:
    """The contents of the closed-hand source and mask files: the outline, and outline plus fill."""
    source = xbm_text("closed_hand", CLOSED_HAND_PICTURE, lambda cell: cell == "#", CLOSED_HAND_HOTSPOT)
    mask = xbm_text("closed_hand_mask", CLOSED_HAND_PICTURE, lambda cell: cell in "#o", CLOSED_HAND_HOTSPOT)
    return source, mask


def bitmap_cursor_spec(source: str, mask: str, foreground: str = "black",
                       background: str = "white") -> str:
    """Tk's X11 form of a two-colour bitmap cursor. The paths are braced so spaces survive."""
    return f"{{@{source}}} {{{mask}}} {foreground} {background}"


def closed_hand_candidates() -> Tuple[str, ...]:
    """Closed-hand cursors to try, best first: the macOS one, the shipped bitmap, then the move arrow."""
    return ("closedhand", bitmap_cursor_spec(CLOSED_HAND_SOURCE, CLOSED_HAND_MASK), MOVE_CURSOR)


def first_supported_cursor(widget: Any, candidates: Sequence[str]) -> str:
    """The first of ``candidates`` that Tk accepts on this platform, or "" if none is.

    Tk only reports a bad cursor when it is applied, so each is tried on ``widget``, whose own
    cursor is put back afterwards.
    """
    original = widget.cget("cursor")
    chosen = ""
    for spec in candidates:
        try:
            widget.configure(cursor=spec)
        except tk.TclError:
            continue
        chosen = spec
        break
    widget.configure(cursor=original)
    return chosen
