from __future__ import annotations

import contextlib
import copy
import io
import tkinter as tk
import unittest
from tkinter import ttk
from typing import Any, Iterator, List
from unittest import mock

from indicators import (
    ADX_PERIOD, ADX_TREND_LEVEL, INDICATOR_SETTING_FIELDS, Indicators, RSI_DEFAULT_PERIOD,
    RSI_OVERBOUGHT, RSI_OVERSOLD, STOCH_D_PERIOD, STOCH_K_PERIOD, STOCH_OVERBOUGHT,
    STOCH_OVERSOLD, WILLIAMS_R_OVERBOUGHT, WILLIAMS_R_OVERSOLD, WILLIAMS_R_PERIOD,
    default_indicator_settings, rsi_crosses_level, validate_indicator_settings,
)
from indicators_help import INDICATOR_DETAILED_HELP
from pytradeviz import INDICATOR_TITLES, PyTradeViz, format_setting_value
from test_indicator_toggle import load_price_rows


def all_widgets(widget: Any) -> Iterator[Any]:
    for child in widget.winfo_children():
        yield child
        yield from all_widgets(child)


def find_toplevel(root: Any, title: str) -> Any:
    for widget in all_widgets(root):
        if isinstance(widget, tk.Toplevel) and widget.title() == title:
            return widget
    return None


def button(window: Any, text: str) -> Any:
    return next(w for w in all_widgets(window) if isinstance(w, tk.Button) and w.cget("text") == text)


def entries(window: Any) -> List[Any]:
    return [w for w in all_widgets(window) if isinstance(w, tk.Entry)]


def set_entries(window: Any, values: List[str]) -> None:
    for entry, value in zip(entries(window), values):
        entry.delete(0, "end")
        entry.insert(0, value)


class SettingsValidationTests(unittest.TestCase):
    def test_defaults_match_the_indicator_constants(self) -> None:
        defaults = default_indicator_settings()
        self.assertEqual(defaults["RSI"], {"period": RSI_DEFAULT_PERIOD,
                                           "overbought": RSI_OVERBOUGHT, "oversold": RSI_OVERSOLD})
        self.assertEqual(defaults["ADX"], {"period": ADX_PERIOD, "trend_level": ADX_TREND_LEVEL})
        self.assertEqual(defaults["STOSC"], {"k_period": STOCH_K_PERIOD, "d_period": STOCH_D_PERIOD,
                                             "overbought": STOCH_OVERBOUGHT, "oversold": STOCH_OVERSOLD})
        self.assertEqual(defaults["W%R"], {"period": WILLIAMS_R_PERIOD,
                                           "overbought": WILLIAMS_R_OVERBOUGHT,
                                           "oversold": WILLIAMS_R_OVERSOLD})

    def test_every_indicator_has_settings_and_a_title(self) -> None:
        self.assertEqual(set(INDICATOR_SETTING_FIELDS), set(INDICATOR_TITLES))
        self.assertEqual(set(INDICATOR_DETAILED_HELP), set(INDICATOR_TITLES))

    def test_defaults_validate_back_to_the_same_values(self) -> None:
        for mode, defaults in default_indicator_settings().items():
            raw = {key: format_setting_value(value) for key, value in defaults.items()}
            self.assertEqual(validate_indicator_settings(mode, raw), defaults, mode)

    def test_text_is_parsed_into_numbers(self) -> None:
        values = validate_indicator_settings("STOSC", {
            "k_period": " 21 ", "d_period": "5", "overbought": "75.5", "oversold": "25",
        })
        self.assertEqual(values, {"k_period": 21, "d_period": 5, "overbought": 75.5, "oversold": 25.0})
        self.assertIsInstance(values["k_period"], int)

    def test_rejects_text_that_is_not_a_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "Period \\(candles\\) must be a whole number"):
            validate_indicator_settings("RSI", {"period": "seven", "overbought": "70", "oversold": "30"})
        with self.assertRaisesRegex(ValueError, "Overbought level must be a number"):
            validate_indicator_settings("RSI", {"period": "7", "overbought": "", "oversold": "30"})

    def test_rejects_fractional_periods(self) -> None:
        with self.assertRaisesRegex(ValueError, "whole number"):
            validate_indicator_settings("ADX", {"period": "14.5", "trend_level": "25"})

    def test_rejects_nan_and_infinity(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a number"):
            validate_indicator_settings("RSI", {"period": "7", "overbought": "nan", "oversold": "30"})
        with self.assertRaisesRegex(ValueError, "must be a number"):
            validate_indicator_settings("RSI", {"period": "7", "overbought": "inf", "oversold": "30"})

    def test_periods_have_minimums(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 2 and any"):
            validate_indicator_settings("W%R", {"period": "1", "overbought": "-20", "oversold": "-80"})
        # %D may be 1 (no smoothing) but %K may not.
        values = validate_indicator_settings("STOSC", {
            "k_period": "14", "d_period": "1", "overbought": "80", "oversold": "20",
        })
        self.assertEqual(values["d_period"], 1)
        with self.assertRaisesRegex(ValueError, "%D period"):
            validate_indicator_settings("STOSC", {
                "k_period": "14", "d_period": "0", "overbought": "80", "oversold": "20",
            })

    def test_levels_are_limited_to_the_indicator_scale(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            validate_indicator_settings("RSI", {"period": "7", "overbought": "101", "oversold": "30"})
        with self.assertRaisesRegex(ValueError, "between -100 and 0"):
            validate_indicator_settings("W%R", {"period": "14", "overbought": "5", "oversold": "-80"})

    def test_overbought_must_be_above_oversold(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be above oversold"):
            validate_indicator_settings("RSI", {"period": "7", "overbought": "30", "oversold": "70"})
        with self.assertRaisesRegex(ValueError, "must be above oversold"):
            validate_indicator_settings("W%R", {"period": "14", "overbought": "-80", "oversold": "-20"})

    def test_adx_trend_level_has_no_overbought_rule(self) -> None:
        values = validate_indicator_settings("ADX", {"period": "14", "trend_level": "0"})
        self.assertEqual(values, {"period": 14, "trend_level": 0.0})


class ParameterisedCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()[:200]
        self.indicators = Indicators(price_data=self.price_data)

    def test_adx_recomputes_when_the_period_changes(self) -> None:
        fourteen = self.indicators.calculate_ADX(14)
        seven = self.indicators.calculate_ADX(7)
        self.assertNotEqual(fourteen, seven)
        self.assertEqual(self.indicators.calculate_ADX(14), fourteen)

    def test_stochastic_recomputes_when_either_period_changes(self) -> None:
        base = self.indicators.calculate_stochastic(14, 3)
        smoothed = self.indicators.calculate_stochastic(14, 5)
        faster = self.indicators.calculate_stochastic(9, 3)
        self.assertEqual(base[0], smoothed[0])
        self.assertNotEqual(base[1], smoothed[1])
        self.assertNotEqual(base[0], faster[0])

    def test_williams_r_recomputes_when_the_period_changes(self) -> None:
        fourteen = self.indicators.calculate_williams_r(14)
        five = self.indicators.calculate_williams_r(5)
        self.assertNotEqual(fourteen, five)
        self.assertEqual(five, self.indicators.calculate_williams_r(5))


class RSIPeriodTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()[:150]

    def fresh_rsi(self, period: int) -> List[Any]:
        rows = copy.deepcopy(self.price_data)
        for row in rows:
            row[5]["rsi"] = None
        Indicators(price_data=rows).calculate_RSI_incremental(period)
        return [row[5]["rsi"] for row in rows]

    def test_full_recompute_matches_a_fresh_calculation_and_clears_old_values(self) -> None:
        rows = copy.deepcopy(self.price_data)
        indicators = Indicators(price_data=rows)
        indicators.calculate_RSI_incremental(7)
        indicators.calculate_RSI_full(14)

        self.assertEqual([row[5]["rsi"] for row in rows], self.fresh_rsi(14))
        # The first 14 candles cannot have a 14-candle RSI yet, so no stale 7-period value may remain.
        self.assertTrue(all(row[5]["rsi"] is None for row in rows[:14]))

    def test_incremental_calculation_refuses_a_different_period(self) -> None:
        rows = copy.deepcopy(self.price_data)
        indicators = Indicators(price_data=rows)
        indicators.calculate_RSI_incremental(7)
        with self.assertRaises(ValueError):
            indicators.calculate_RSI_incremental(14)


class IndicatorSettingsWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.price_data = load_price_rows()
        with contextlib.redirect_stdout(io.StringIO()):
            self.viz = PyTradeViz(tk, ttk, {"price_data": self.price_data})
        self.addCleanup(self.viz.window.destroy)
        self.viz.window.geometry("1200x800")
        self.viz.window.update()

    def open_settings(self, mode: str) -> Any:
        self.viz.open_indicator_settings_window(tk, mode)
        self.viz.window.update()
        window = find_toplevel(self.viz.window, INDICATOR_TITLES[mode])
        self.assertIsNotNone(window)
        return window

    def test_indicators_menu_has_one_entry_per_indicator(self) -> None:
        menu = self.viz.initialize_indicators_menu(tk)
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
                  if menu.type(i) == "command"]
        for title in ("Relative Strength Index (RSI)", "Avg. Directional Index (ADX)",
                      "Stochastic Oscillator (STOSC)", "Williams %R (W%R)"):
            self.assertIn(title, labels)
        self.assertNotIn("RSI", [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
                                 if menu.type(i) == "cascade"])

    def test_menu_entry_opens_only_its_own_window(self) -> None:
        menu = self.viz.initialize_indicators_menu(tk)
        index = next(i for i in range(menu.index("end") + 1)
                     if menu.type(i) == "command" and menu.entrycget(i, "label") == INDICATOR_TITLES["STOSC"])
        menu.invoke(index)
        self.viz.window.update()
        self.assertIsNotNone(find_toplevel(self.viz.window, INDICATOR_TITLES["STOSC"]))
        self.assertIsNone(find_toplevel(self.viz.window, INDICATOR_TITLES["RSI"]))

    def test_each_window_has_cancel_apply_and_help_in_that_order(self) -> None:
        for mode in ("RSI", "ADX", "STOSC", "W%R"):
            window = self.open_settings(mode)
            texts = [w.cget("text") for w in all_widgets(window) if isinstance(w, tk.Button)]
            # Minimize has a row of its own above the settings.
            self.assertEqual(texts, ["Minimize", "Cancel", "Apply", "Help"], mode)
            window.destroy()

    def test_each_window_shows_one_entry_per_parameter_with_its_current_value(self) -> None:
        window = self.open_settings("W%R")
        values = [entry.get() for entry in entries(window)]
        self.assertEqual(values, ["14", "-20", "-80"])

    def test_cancel_closes_without_changing_settings(self) -> None:
        window = self.open_settings("ADX")
        set_entries(window, ["5", "40"])
        button(window, "Cancel").invoke()
        self.viz.window.update()
        self.assertIsNone(find_toplevel(self.viz.window, INDICATOR_TITLES["ADX"]))
        self.assertEqual(self.viz.indicator_settings["ADX"], default_indicator_settings()["ADX"])

    def test_apply_stores_settings_and_shows_the_indicator(self) -> None:
        window = self.open_settings("STOSC")
        set_entries(window, ["21", "5", "75", "25"])
        button(window, "Apply").invoke()
        self.viz.window.update()

        self.assertEqual(self.viz.indicator_settings["STOSC"],
                         {"k_period": 21, "d_period": 5, "overbought": 75.0, "oversold": 25.0})
        self.assertEqual(self.viz.indicator_mode, "STOSC")
        self.assertTrue(self.viz.canvas_indicators.find_withtag("stoch"))
        self.assertFalse(self.viz.canvas_indicators.find_withtag("rsi"))
        levels = sorted(self.viz.canvas_indicators.coords(item)[1]
                        for item in self.viz.canvas_indicators.find_withtag("indicator_level"))
        self.assertEqual(levels, [100 - 75, 100 - 25])
        # Apply keeps the window open so the user can see the result.
        self.assertIsNotNone(find_toplevel(self.viz.window, INDICATOR_TITLES["STOSC"]))

    def test_apply_with_an_invalid_value_shows_an_error_and_changes_nothing(self) -> None:
        window = self.open_settings("RSI")
        set_entries(window, ["7", "30", "70"])  # overbought below oversold
        with mock.patch("tkinter.messagebox.showerror") as showerror:
            button(window, "Apply").invoke()
        showerror.assert_called_once()
        self.assertIn("must be above oversold", showerror.call_args.args[1])
        self.assertEqual(self.viz.indicator_settings["RSI"], default_indicator_settings()["RSI"])

    def test_changing_the_rsi_period_recomputes_stored_rsi(self) -> None:
        window = self.open_settings("RSI")
        set_entries(window, ["14", "70", "30"])
        button(window, "Apply").invoke()

        expected = copy.deepcopy(self.price_data)
        for row in expected:
            row[5]["rsi"] = None
        Indicators(price_data=expected).calculate_RSI_full(14)
        self.assertEqual([row[5]["rsi"] for row in self.viz.price_data],
                         [row[5]["rsi"] for row in expected])
        self.assertIsNone(self.viz.price_data[13][5]["rsi"])
        self.assertIsNotNone(self.viz.price_data[-1][5]["rsi"])

    def test_labeled_export_flags_follow_the_rsi_levels(self) -> None:
        self.viz.apply_indicator_settings("RSI", {"period": 7, "overbought": 60.0, "oversold": 40.0})
        # Find a candle where RSI crosses 60 upward, and check the export flag agrees with that.
        index = next(i for i in range(1, len(self.viz.price_data))
                     if rsi_crosses_level(self.viz.price_data[i - 1][5]["rsi"],
                                          self.viz.price_data[i][5]["rsi"], 60.0))
        record = self.viz.labeled_candle_record(index)
        self.assertIs(record["rsi_ob"], True)
        self.assertEqual(record["rsi_os"], rsi_crosses_level(
            self.viz.price_data[index - 1][5]["rsi"], record["rsi"], 40.0))

    def test_rsi_levels_on_the_canvas_follow_the_settings(self) -> None:
        self.viz.apply_indicator_settings("RSI", {"period": 7, "overbought": 65.0, "oversold": 35.0})
        levels = sorted(self.viz.canvas_indicators.coords(item)[1]
                        for item in self.viz.canvas_indicators.find_withtag("indicator_level"))
        self.assertEqual(levels, [100 - 65, 100 - 35])

    def test_adx_trend_level_follows_the_settings(self) -> None:
        self.viz.apply_indicator_settings("ADX", {"period": 14, "trend_level": 40.0})
        ys = [self.viz.canvas_indicators.coords(item)[1]
              for item in self.viz.canvas_indicators.find_withtag("indicator_level")]
        self.assertEqual(ys, [100 - 40.0])

    def test_williams_r_levels_are_shifted_onto_the_canvas(self) -> None:
        self.viz.apply_indicator_settings("W%R", {"period": 14, "overbought": -10.0, "oversold": -90.0})
        levels = sorted(self.viz.canvas_indicators.coords(item)[1]
                        for item in self.viz.canvas_indicators.find_withtag("indicator_level"))
        self.assertEqual(levels, [100 - (-10.0 + 100), 100 - (-90.0 + 100)])

    def test_settings_are_kept_per_timeframe_tab(self) -> None:
        self.viz.apply_indicator_settings("RSI", {"period": 14, "overbought": 70.0, "oversold": 30.0})
        self.viz.select_timeframe("2W")
        # A new tab starts from a copy of the current settings...
        self.assertEqual(self.viz.indicator_settings["RSI"]["period"], 14)
        self.viz.apply_indicator_settings("RSI", {"period": 21, "overbought": 70.0, "oversold": 30.0})
        self.viz.select_timeframe("Daily")
        # ...and changing one tab leaves the others alone.
        self.assertEqual(self.viz.indicator_settings["RSI"]["period"], 14)
        self.viz.select_timeframe("2W")
        self.assertEqual(self.viz.indicator_settings["RSI"]["period"], 21)

    def test_help_window_describes_the_settings(self) -> None:
        window = self.open_settings("STOSC")
        button(window, "Help").invoke()
        self.viz.window.update()
        help_window = find_toplevel(window, "Stochastic Oscillator (STOSC) Help")
        self.assertIsNotNone(help_window)
        text = next(w for w in all_widgets(help_window) if isinstance(w, tk.Text))
        body = text.get("1.0", "end")
        self.assertIn("STOSC (Stochastic Oscillator)", body)
        self.assertIn("%K period (default 14", body)
        self.assertIn("%D period (default 3", body)
        self.assertIn("Overbought level (default 80)", body)
        self.assertIn("Settings", body)
        button(help_window, "Close").invoke()
        self.viz.window.update()


if __name__ == "__main__":
    unittest.main()
