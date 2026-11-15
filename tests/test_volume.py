from __future__ import annotations

import contextlib
import csv
import io
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, List
from uuid import uuid4

import unittest

from indicators import on_balance_volume
from paginated_price_data import PaginatedPriceData
from pytradeviz import PyTradeViz
from test_roi import load_price_rows
from timeframes import resample
from trend import DOWN, SIDEWAYS, UP, layered_trend_details, layered_trend_states, obv_direction_states

AMZN_PATH = Path(__file__).resolve().parents[1] / "data" / "AMZN_10_year_OHLC.csv"
NO_VOLUME = {"rsi": None, "ema": None, "sma": None}


def load_amzn_rows() -> List[List[Any]]:
    source = PaginatedPriceData(AMZN_PATH, require_named_columns=True)
    rows = source.load_initial()
    while source.has_more:
        rows.extend(source.load_next())
    return rows


def ohlcv_csv(records: List[List[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["date", "open", "high", "low", "close", "volume"])
    writer.writerows(records)
    return output.getvalue()


class VolumeLoaderTests(unittest.TestCase):
    def make_file(self, text: str) -> Path:
        path = Path(__file__).resolve().parent / f".volume-test-{uuid4().hex}.csv"
        path.write_text(text, encoding="utf-8", newline="")
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_a_volume_column_is_stored_in_each_row(self) -> None:
        path = self.make_file(ohlcv_csv([
            ["2024-01-02", "1", "2", "0.5", "1.5", "1,234"],
            ["2024-01-03", "1.5", "2.5", "1", "2", "250"],
        ]))
        source = PaginatedPriceData(path, require_named_columns=True)
        rows = source.load_initial()
        self.assertTrue(source.has_volume)
        self.assertEqual([row[5]["volume"] for row in rows], [1234.0, 250.0])
        self.assertEqual(rows[0][1:5], [1.0, 2.0, 0.5, 1.5])

    def test_a_file_without_volume_keeps_the_original_row_shape(self) -> None:
        path = self.make_file("date,open,high,low,close\n2024-01-02,1,2,0.5,1.5\n")
        source = PaginatedPriceData(path, require_named_columns=True)
        rows = source.load_initial()
        self.assertFalse(source.has_volume)
        self.assertEqual(rows[0][5], NO_VOLUME)

    def test_the_amzn_file_reports_its_volume(self) -> None:
        source = PaginatedPriceData(AMZN_PATH, require_named_columns=True)
        first = source.load_initial()[0]
        self.assertTrue(source.has_volume)
        self.assertEqual(first[5]["volume"], 119546760.0)

    def test_negative_or_unreadable_volume_is_rejected(self) -> None:
        for bad in ("-5", "abc", "nan"):
            with self.subTest(volume=bad):
                path = self.make_file(ohlcv_csv([["2024-01-02", "1", "2", "0.5", "1.5", bad]]))
                source = PaginatedPriceData(path, require_named_columns=True)
                with self.assertRaisesRegex(ValueError, "invalid volume"):
                    source.load_initial()


class VolumeResampleTests(unittest.TestCase):
    def day(self, date: str, volume: float = None) -> List[Any]:
        year, month, day = date.split("-")
        indicators = dict(NO_VOLUME) if volume is None else {**NO_VOLUME, "volume": volume}
        return [[year, month, day], 1.0, 2.0, 0.5, 1.5, indicators]

    def test_a_bucket_sums_the_volume_of_its_days(self) -> None:
        rows = [self.day("2024-01-01", 100.0), self.day("2024-01-02", 200.0), self.day("2024-01-03", 300.0)]
        (candle,) = resample(rows, "2W")
        self.assertEqual(candle[5]["volume"], 600.0)

    def test_rows_without_volume_stay_without_it(self) -> None:
        rows = [self.day("2024-01-01"), self.day("2024-01-02")]
        (candle,) = resample(rows, "2W")
        self.assertEqual(candle[5], NO_VOLUME)


class OnBalanceVolumeTests(unittest.TestCase):
    def test_volume_is_added_on_up_closes_and_taken_away_on_down_closes(self) -> None:
        self.assertEqual(on_balance_volume([10, 11, 11, 9], [100, 50, 70, 30]), [0, 50, 50, 20])

    def test_direction_is_compared_with_its_own_average(self) -> None:
        closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        volumes = [10.0] * 6
        states = obv_direction_states(closes, volumes, period=3)
        self.assertEqual(states[:2], [None, None])
        self.assertEqual(states[-1], UP)
        self.assertEqual(obv_direction_states([5.0, 4.0, 3.0, 2.0], [10.0] * 4, period=2)[-1], DOWN)


class VolumeConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rows = load_amzn_rows()
        cls.highs = [row[2] for row in rows]
        cls.lows = [row[3] for row in rows]
        cls.closes = [row[4] for row in rows]
        cls.volumes = [row[5]["volume"] for row in rows]
        cls.base = layered_trend_states(cls.highs, cls.lows, cls.closes)
        cls.confirmed = layered_trend_states(cls.highs, cls.lows, cls.closes, volumes=cls.volumes)
        cls.obv = obv_direction_states(cls.closes, cls.volumes)

    def test_without_volumes_the_labels_are_unchanged(self) -> None:
        self.assertEqual(layered_trend_states(self.highs, self.lows, self.closes, volumes=None), self.base)

    def test_a_trend_is_kept_only_when_volume_agrees(self) -> None:
        for base, confirmed, obv in zip(self.base, self.confirmed, self.obv):
            if confirmed in (UP, DOWN):
                self.assertEqual(confirmed, base)
                self.assertEqual(confirmed, obv)
            if base in (UP, DOWN) and confirmed is not None and confirmed != base:
                self.assertEqual(confirmed, SIDEWAYS)
                self.assertNotEqual(obv, base)

    def test_volume_downgrades_some_trends_on_the_amzn_data(self) -> None:
        downgraded = sum(1 for base, confirmed in zip(self.base, self.confirmed)
                         if base in (UP, DOWN) and confirmed == SIDEWAYS)
        self.assertGreater(downgraded, 0)

    def test_volume_labels_use_only_earlier_candles(self) -> None:
        cut = 400
        prefix = layered_trend_states(
            self.highs[:cut], self.lows[:cut], self.closes[:cut], volumes=self.volumes[:cut])
        self.assertEqual(prefix, self.confirmed[:cut])

    def test_details_pair_each_state_with_its_adx(self) -> None:
        details = layered_trend_details(self.highs, self.lows, self.closes, volumes=self.volumes)
        self.assertEqual([state for state, _adx in details], self.confirmed)


class VolumeTrendWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": load_amzn_rows()})
        self.addCleanup(self.destroy_window)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def destroy_window(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.viz.window.destroy()

    def descendants(self, widget: tk.Misc, cls: type) -> List[tk.Misc]:
        found: List[tk.Misc] = []
        for child in widget.winfo_children():
            if isinstance(child, cls):
                found.append(child)
            found.extend(self.descendants(child, cls))
        return found

    def open_window(self) -> tk.Toplevel:
        before = set(self.viz.window.winfo_children())
        self.viz.open_trend_window(tk)
        self.viz.window.update()
        (window,) = [w for w in self.viz.window.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
        return window

    def checkbox(self, window: tk.Misc) -> tk.Checkbutton:
        return next(c for c in self.descendants(window, tk.Checkbutton) if c.cget("text") == "Include volume")

    def button(self, window: tk.Misc, text: str) -> tk.Button:
        return next(b for b in self.descendants(window, tk.Button) if b.cget("text") == text)

    def set_checkbox(self, window: tk.Misc, value: bool) -> None:
        window.setvar(str(self.checkbox(window).cget("variable")), "1" if value else "0")

    def checkbox_value(self, window: tk.Misc) -> bool:
        return window.getvar(str(self.checkbox(window).cget("variable"))) == "1"

    def test_include_volume_is_off_by_default(self) -> None:
        self.assertFalse(self.viz.trend_applied["include_volume"])
        window = self.open_window()
        self.assertEqual(self.checkbox(window).cget("state"), "normal")
        self.assertFalse(self.checkbox_value(window))

    def test_apply_with_include_volume_recomputes_the_trend(self) -> None:
        window = self.open_window()
        self.set_checkbox(window, True)
        self.viz.trend_applied = {**self.viz.trend_applied, "enabled": True}
        self.button(window, "Apply").invoke()
        self.viz.window.update()
        self.assertTrue(self.viz.trend_applied["include_volume"])
        rows = self.viz.price_data
        expected = layered_trend_details(
            [row[2] for row in rows], [row[3] for row in rows], [row[4] for row in rows],
            volumes=[row[5]["volume"] for row in rows])
        self.assertEqual(self.viz.trend_details(), expected)

    def test_apply_without_include_volume_restores_the_plain_trend(self) -> None:
        window = self.open_window()
        self.set_checkbox(window, True)
        self.button(window, "Apply").invoke()
        window = self.open_window()
        self.set_checkbox(window, False)
        self.button(window, "Apply").invoke()
        self.assertFalse(self.viz.trend_applied["include_volume"])
        rows = self.viz.price_data
        plain = layered_trend_details([row[2] for row in rows], [row[3] for row in rows], [row[4] for row in rows])
        self.assertEqual(self.viz.trend_details(), plain)

    def test_cancel_leaves_include_volume_unchanged(self) -> None:
        window = self.open_window()
        self.set_checkbox(window, True)
        self.button(window, "Cancel").invoke()
        self.assertFalse(self.viz.trend_applied["include_volume"])

    def test_the_checkbox_is_disabled_when_the_data_has_no_volume(self) -> None:
        self.viz.replace_price_data(load_price_rows(), None)
        window = self.open_window()
        self.assertEqual(self.checkbox(window).cget("state"), "disabled")
        self.set_checkbox(window, True)
        self.button(window, "Apply").invoke()
        self.assertFalse(self.viz.trend_applied["include_volume"])

    def test_toggling_the_trend_keeps_the_volume_choice(self) -> None:
        self.viz.trend_applied = {**self.viz.trend_applied, "include_volume": True}
        self.viz.toggle_trend()
        self.assertTrue(self.viz.trend_applied["include_volume"])
        self.assertTrue(self.viz.trend_applied["enabled"])


if __name__ == "__main__":
    unittest.main()
