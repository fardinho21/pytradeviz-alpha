from __future__ import annotations

import datetime
import os
import tempfile
import unittest

from labeled_selections import (
    export_path,
    format_for_path,
    from_json_text,
    from_xml_text,
    merge_selections,
    read_selections,
    to_json_text,
    to_xml_text,
    write_selections,
    xml_tag,
)


def record(open_: float, sma_3d=None) -> dict:
    return {
        "open": open_, "high": open_ + 1, "low": open_ - 1, "close": open_ + 0.5,
        "rsi": 55.0, "3d_sma": sma_3d, "7d_sma": None, "2wk_sma": None, "1mo_sma": None,
        "bollinger_middle": open_, "bollinger_upper": open_ + 2.0, "bollinger_lower": open_ - 2.0,
        "top_bol_intersect": True, "btm_bol_intersect": False, "rsi_os": None, "rsi_ob": False,
    }


class FormatTests(unittest.TestCase):
    def test_extension_selects_format(self) -> None:
        self.assertEqual(format_for_path("a/b/selections.JSON"), "json")
        self.assertEqual(format_for_path("selections.xml"), "xml")

    def test_other_extensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            format_for_path("selections.csv")

    def test_export_path_uses_timestamp(self) -> None:
        now = datetime.datetime(2025, 3, 4, 9, 5, 7)
        self.assertEqual(
            export_path("data/labeled_data", "json", now),
            os.path.join("data/labeled_data", "selections_20250304_090507.json"),
        )


class MergeTests(unittest.TestCase):
    def test_records_are_appended_per_label(self) -> None:
        base = {"up": [record(1)]}
        extra = {"up": [record(2)], "down": [record(3)]}
        merged = merge_selections(base, extra)
        self.assertEqual([r["open"] for r in merged["up"]], [1, 2])
        self.assertEqual([r["open"] for r in merged["down"]], [3])

    def test_inputs_are_not_modified(self) -> None:
        base = {"up": [record(1)]}
        merge_selections(base, {"up": [record(2)]})
        self.assertEqual(len(base["up"]), 1)


class JsonRoundTripTests(unittest.TestCase):
    def test_round_trip_keeps_values_and_none(self) -> None:
        selections = {"up trend": [record(10, sma_3d=9.5)]}
        restored = from_json_text(to_json_text(selections))
        self.assertEqual(restored, selections)

    def test_json_keys_follow_label_candle_layout(self) -> None:
        text = to_json_text({"up": [record(1), record(2)]})
        self.assertIn('"up_candle_0"', text)
        self.assertIn('"up_candle_1"', text)

    def test_invalid_json_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            from_json_text("{not json")

    def test_non_numeric_value_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            from_json_text('{"up": {"up_candle_0": {"open": "abc"}}}')


class BooleanFieldTests(unittest.TestCase):
    def test_json_writes_true_false_and_null(self) -> None:
        text = to_json_text({"up": [record(1)]})
        self.assertIn('"top_bol_intersect": true', text)
        self.assertIn('"btm_bol_intersect": false', text)
        self.assertIn('"rsi_os": null', text)

    def test_json_round_trip_keeps_booleans(self) -> None:
        selections = {"up": [record(1), record(2)]}
        restored = from_json_text(to_json_text(selections))
        self.assertIs(restored["up"][0]["top_bol_intersect"], True)
        self.assertIs(restored["up"][0]["btm_bol_intersect"], False)
        self.assertIsNone(restored["up"][0]["rsi_os"])
        self.assertEqual(restored, selections)

    def test_xml_writes_lowercase_true_false(self) -> None:
        text = to_xml_text({"up": [record(1)]})
        self.assertIn('top_bol_intersect="true"', text)
        self.assertIn('btm_bol_intersect="false"', text)
        self.assertIn('rsi_os=""', text)

    def test_xml_round_trip_keeps_booleans(self) -> None:
        selections = {"up": [record(1)]}
        restored = from_xml_text(to_xml_text(selections))
        self.assertIs(restored["up"][0]["top_bol_intersect"], True)
        self.assertIs(restored["up"][0]["btm_bol_intersect"], False)
        self.assertIsNone(restored["up"][0]["rsi_os"])
        self.assertEqual(restored, selections)

    def test_non_boolean_text_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            from_json_text('{"up": {"up_candle_0": {"rsi_ob": "maybe"}}}')
        with self.assertRaises(ValueError):
            from_xml_text('<Selections><up label="up"><upCandle0 rsi_ob="yes"/></up></Selections>')

    def test_files_without_flag_keys_still_load(self) -> None:
        old = {"up": [{k: v for k, v in record(1).items() if k not in (
            "top_bol_intersect", "btm_bol_intersect", "rsi_os", "rsi_ob")}]}
        text = to_json_text(old)
        restored = from_json_text(text)
        self.assertIsNone(restored["up"][0]["rsi_ob"])
        self.assertEqual(restored["up"][0]["open"], 1)


class XmlRoundTripTests(unittest.TestCase):
    def test_round_trip_keeps_values_and_none(self) -> None:
        selections = {"up": [record(10, sma_3d=9.5), record(11)]}
        restored = from_xml_text(to_xml_text(selections))
        self.assertEqual(restored, selections)

    def test_label_with_spaces_is_recovered_from_attribute(self) -> None:
        selections = {"my label 1": [record(4)]}
        text = to_xml_text(selections)
        self.assertIn('<my_label_1 label="my label 1">', text)
        self.assertEqual(from_xml_text(text), selections)

    def test_sma_attributes_are_valid_xml_names(self) -> None:
        text = to_xml_text({"up": [record(1, sma_3d=2.0)]})
        self.assertIn('sma_3d="2.0"', text)
        self.assertNotIn(' 3d_sma=', text)

    def test_invalid_xml_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            from_xml_text("<Selections><unclosed></Selections>")

    def test_wrong_root_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            from_xml_text("<Other/>")


class XmlTagTests(unittest.TestCase):
    def test_invalid_characters_are_replaced(self) -> None:
        self.assertEqual(xml_tag("buy signal!"), "buy_signal_")

    def test_leading_digit_gets_prefix(self) -> None:
        self.assertEqual(xml_tag("1st"), "L_1st")

    def test_reserved_xml_prefix_gets_prefix(self) -> None:
        self.assertEqual(xml_tag("xml data"), "L_xml_data")


class FileTests(unittest.TestCase):
    def test_write_and_read_both_formats(self) -> None:
        selections = {"up": [record(1, sma_3d=0.5)]}
        with tempfile.TemporaryDirectory() as directory:
            for name in ("out/selections.json", "out/selections.xml"):
                path = os.path.join(directory, name)
                write_selections(path, selections)
                self.assertEqual(read_selections(path), selections)


if __name__ == "__main__":
    unittest.main()
