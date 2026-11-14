from __future__ import annotations

import unittest

from drawings import (
    BOX, DASHED, DOTTED, ELLIPSE, LINE, SEGMENT, SOLID, STYLE_DASHES, SWATCH_WIDTH,
    TOOLBOX_MARGIN, TOOLBOX_ROWS, Drawing, clip_line, distance_to_segment, fill_applicable, hit_test,
    toolbox_layout, toolbox_rows,
)

VIEW = (0.0, 0.0, 400.0, 300.0)
COLORS = ("Red", "Blue", "Orange", "Green", "Violet")


class ClipLineTests(unittest.TestCase):
    def test_diagonal_line_is_clipped_to_bounds(self) -> None:
        clipped = clip_line((-100.0, -100.0), (500.0, 500.0), VIEW)
        self.assertEqual(clipped, (0.0, 0.0, 300.0, 300.0))

    def test_horizontal_line_spans_full_width(self) -> None:
        self.assertEqual(clip_line((50.0, 120.0), (60.0, 120.0), VIEW), (0.0, 120.0, 400.0, 120.0))

    def test_vertical_line_spans_full_height(self) -> None:
        self.assertEqual(clip_line((90.0, -5.0), (90.0, 10.0), VIEW), (90.0, 0.0, 90.0, 300.0))

    def test_line_missing_view_returns_none(self) -> None:
        self.assertIsNone(clip_line((-50.0, 400.0), (-10.0, 500.0), VIEW))

    def test_degenerate_line_returns_none(self) -> None:
        self.assertIsNone(clip_line((10.0, 10.0), (10.0, 10.0), VIEW))


class HitTestTests(unittest.TestCase):
    def test_line_hits_anywhere_along_its_extension(self) -> None:
        self.assertTrue(hit_test(LINE, (0.0, 0.0), (10.0, 10.0), 300.0, 300.0))
        self.assertFalse(hit_test(LINE, (0.0, 0.0), (10.0, 10.0), 300.0, 320.0))

    def test_segment_only_hits_between_its_ends(self) -> None:
        self.assertTrue(hit_test(SEGMENT, (0.0, 0.0), (100.0, 0.0), 50.0, 3.0))
        self.assertFalse(hit_test(SEGMENT, (0.0, 0.0), (100.0, 0.0), 150.0, 0.0))

    def test_segment_distance_clamps_to_endpoints(self) -> None:
        self.assertAlmostEqual(distance_to_segment(-3.0, 4.0, (0.0, 0.0), (10.0, 0.0)), 5.0)

    def test_box_hits_its_interior_not_just_outline(self) -> None:
        self.assertTrue(hit_test(BOX, (0.0, 0.0), (100.0, 100.0), 50.0, 50.0))
        self.assertFalse(hit_test(BOX, (0.0, 0.0), (100.0, 100.0), 150.0, 50.0))

    def test_box_hit_ignores_anchor_order(self) -> None:
        self.assertTrue(hit_test(BOX, (100.0, 100.0), (0.0, 0.0), 50.0, 50.0))

    def test_ellipse_hits_inside_but_not_bounding_corner(self) -> None:
        self.assertTrue(hit_test(ELLIPSE, (0.0, 0.0), (100.0, 100.0), 50.0, 50.0))
        self.assertFalse(hit_test(ELLIPSE, (0.0, 0.0), (100.0, 100.0), 4.0, 4.0))


class DrawingModelTests(unittest.TestCase):
    def test_translated_moves_both_anchors(self) -> None:
        drawing = Drawing(1, BOX, SOLID, "#1e88e5", False, (2.0, 10.0), (5.0, 20.0))
        moved = drawing.translated(3.0, -4.0)
        self.assertEqual(moved.start, (5.0, 6.0))
        self.assertEqual(moved.end, (8.0, 16.0))
        self.assertEqual(moved.id, drawing.id)
        self.assertEqual(drawing.start, (2.0, 10.0))

    def test_only_box_and_ellipse_accept_fill(self) -> None:
        self.assertTrue(fill_applicable(BOX))
        self.assertTrue(fill_applicable(ELLIPSE))
        self.assertFalse(fill_applicable(LINE))
        self.assertFalse(fill_applicable(SEGMENT))
        self.assertFalse(fill_applicable(None))

    def test_style_dashes_cover_all_styles(self) -> None:
        self.assertEqual(STYLE_DASHES[SOLID], ())
        self.assertTrue(STYLE_DASHES[DASHED])
        self.assertTrue(STYLE_DASHES[DOTTED])


class ToolboxLayoutTests(unittest.TestCase):
    def test_toolbox_sits_in_bottom_right_of_view(self) -> None:
        toolbox = toolbox_layout(VIEW, COLORS)
        left, top, right, bottom = toolbox.bounds
        self.assertLess(right, VIEW[2])
        self.assertLess(bottom, VIEW[3])
        self.assertGreater(left, VIEW[0])
        self.assertGreater(top, VIEW[1])
        self.assertAlmostEqual(VIEW[2] - right, VIEW[3] - bottom)
        self.assertAlmostEqual(VIEW[3] - bottom, TOOLBOX_MARGIN)

    def test_every_button_is_inside_toolbox_and_none_overlap(self) -> None:
        toolbox = toolbox_layout(VIEW, COLORS)
        self.assertEqual(len(toolbox.buttons), sum(len(row) for row in toolbox_rows(COLORS)))
        for button in toolbox.buttons:
            left, top, right, bottom = button.bounds
            self.assertTrue(toolbox.contains(left, top))
            self.assertTrue(toolbox.contains(right, bottom))
        for index, first in enumerate(toolbox.buttons):
            for second in toolbox.buttons[index + 1:]:
                fl, ft, fr, fb = first.bounds
                sl, st, sr, sb = second.bounds
                self.assertFalse(fl < sr and sl < fr and ft < sb and st < fb)

    def test_rows_are_stacked_in_order(self) -> None:
        toolbox = toolbox_layout(VIEW, COLORS)
        rows: list = []
        for button in toolbox.buttons:
            top = button.bounds[1]
            if not rows or rows[-1][0] != top:
                rows.append((top, []))
            rows[-1][1].append(button.key)
        self.assertEqual(
            [keys for _, keys in rows],
            [[key for key, _ in row] for row in toolbox_rows(COLORS)],
        )
        tops = [top for top, _ in rows]
        self.assertEqual(tops, sorted(tops))

    def test_button_at_returns_the_button_under_point(self) -> None:
        toolbox = toolbox_layout(VIEW, COLORS)
        for button in toolbox.buttons:
            left, top, right, bottom = button.bounds
            self.assertIs(toolbox.button_at((left + right) / 2, (top + bottom) / 2), button)
        self.assertIsNone(toolbox.button_at(0.0, 0.0))

    def test_colour_row_sits_between_fill_and_controls(self) -> None:
        rows = toolbox_rows(COLORS)
        self.assertEqual(len(rows), len(TOOLBOX_ROWS) + 1)
        self.assertEqual(rows[2], TOOLBOX_ROWS[2])
        self.assertEqual([key for key, _ in rows[3]], [("color", name) for name in COLORS])
        self.assertEqual(rows[4], TOOLBOX_ROWS[3])

    def test_colour_swatches_are_narrower_than_text_buttons(self) -> None:
        toolbox = toolbox_layout(VIEW, COLORS)
        swatches = [button for button in toolbox.buttons if button.key[0] == "color"]
        self.assertEqual(len(swatches), len(COLORS))
        for swatch in swatches:
            self.assertEqual(swatch.bounds[2] - swatch.bounds[0], SWATCH_WIDTH)
            self.assertEqual(swatch.text, "")

    def test_small_view_clamps_toolbox_inside_view(self) -> None:
        toolbox = toolbox_layout((0.0, 0.0, 120.0, 60.0), COLORS)
        left, top, _, _ = toolbox.bounds
        self.assertGreaterEqual(left, 0.0)
        self.assertGreaterEqual(top, 0.0)


if __name__ == "__main__":
    unittest.main()
