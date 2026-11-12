from __future__ import annotations

import csv
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from typing import Any, Iterable, List, Sequence, TextIO
from uuid import uuid4

from paginated_price_data import PaginatedPriceData


def csv_text(records: Iterable[Sequence[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["source"])
    writer.writerow(["unix", "date", "symbol", "open", "high", "low", "close"])
    writer.writerows(records)
    return output.getvalue()


def row(
    date: str, symbol: str = "asset", prices: Sequence[str] = ("1", "3", "0.5", "2")
) -> List[str]:
    return ["0", date + " 00:00:00", symbol, *prices]


def dates(page: Iterable[Sequence[Any]]) -> List[str]:
    return ["-".join(record[0]) for record in page]


class PaginatedPriceDataTests(unittest.TestCase):
    def make_file(self, text: str) -> Path:
        path = Path("tests") / f".pagination-test-{uuid4().hex}.csv"
        path.write_text(text, encoding="utf-8", newline="")
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def source_for(self, records: Iterable[Sequence[str]]) -> PaginatedPriceData:
        return PaginatedPriceData(self.make_file(csv_text(records)))

    def test_calendar_boundaries_gaps_and_final_partial_page(self) -> None:
        source = self.source_for([
            row("2025-03-31"), row("2024-10-31"), row("2024-08-01"),
            row("2024-07-31"), row("2024-04-30"), row("2024-01-31"),
            row("2024-01-30"), row("2023-02-01"), row("2023-01-31"),
        ])
        self.assertTrue(source.has_more)
        first = source.load_initial()
        self.assertEqual(dates(first), ["2023-01-31", "2023-02-01", "2024-01-30"])
        self.assertEqual(dates(source.load_next()), ["2024-01-31"])
        self.assertEqual(dates(source.load_next()), ["2024-04-30"])
        self.assertEqual(dates(source.load_next()), ["2024-07-31", "2024-08-01"])
        self.assertEqual(dates(source.load_next()), ["2024-10-31"])
        self.assertEqual(dates(source.load_next()), ["2025-03-31"])
        self.assertFalse(source.has_more)
        self.assertEqual(source.load_next(), [])
        self.assertEqual(first[0], [["2023", "01", "31"], 1.0, 3.0, 0.5, 2.0,
                                    {"rsi": None, "ema": None, "sma": None}])
        first[0][-1]["rsi"] = 20
        self.assertIsNone(first[1][-1]["rsi"])

    def test_leap_day_anchor_and_exclusive_timestamp_boundaries(self) -> None:
        source = self.source_for([
            ["0", "2025-05-29 12:30:01", "x", "1", "2", "0", "1"],
            ["0", "2025-05-29 12:30:00", "x", "1", "2", "0", "1"],
            ["0", "2025-02-28 12:30:00", "x", "1", "2", "0", "1"],
            ["0", "2025-02-28 12:29:59", "x", "1", "2", "0", "1"],
            ["0", "2024-02-29 12:30:00", "x", "1", "2", "0", "1"],
        ])
        self.assertEqual(dates(source.load_initial()), ["2024-02-29", "2025-02-28"])
        self.assertEqual(dates(source.load_next()), ["2025-02-28"])
        self.assertEqual(dates(source.load_next()), ["2025-05-29", "2025-05-29"])
        self.assertFalse(source.has_more)

    def test_quoted_fields_and_multiline_records(self) -> None:
        source = self.source_for([
            row("2021-01-01", 'quoted, "asset"\nline'),
            row("2020-01-01", "another, asset"),
        ])
        self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        self.assertEqual(dates(source.load_next()), ["2021-01-01"])

    def test_state_and_empty_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "no price records"):
            self.source_for([])
        source = self.source_for([row("2020-01-01")])
        with self.assertRaisesRegex(RuntimeError, "initial"):
            source.load_next()
        self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        self.assertEqual(source.load_next(), [])
        with self.assertRaisesRegex(RuntimeError, "already"):
            source.load_initial()

    def test_validation_of_order_dates_headers_and_csv(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate date"):
            self.source_for([row("2020-01-01"), row("2020-01-01")])
        for bad_date in ("2020-02-30", "not-a-date", "01/02/2020", "2020-01-01T25:00:00"):
            with self.subTest(date=bad_date), self.assertRaisesRegex(ValueError, "invalid date"):
                self.source_for([row(bad_date)])
        for text, message in (
            ("one header\n", "2 header"),
            ("one\ntwo\nx\n", "missing date"),
            ('one\ntwo\n"unterminated', "Malformed CSV"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    PaginatedPriceData(self.make_file(text))

    def test_custom_header_count(self) -> None:
        for count in (0, 1, 3):
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            for _ in range(count):
                writer.writerow(["header"])
            writer.writerow(row("2020-01-01"))
            with self.subTest(count=count):
                source = PaginatedPriceData(self.make_file(output.getvalue()), skip_lines=count)
                self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        for count in (-1, 1.5, True, "2"):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "skip_lines"):
                PaginatedPriceData("unused.csv", skip_lines=count)

    def test_lazy_ohlc_validation_and_transactional_retry(self) -> None:
        for bad_prices in (("bad", "1", "1", "1"), ("nan", "1", "1", "1"), ("1",)):
            with self.subTest(prices=bad_prices):
                source = self.source_for([row("2022-01-01", prices=bad_prices), row("2020-01-01")])
                self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, "OHLC"):
                        source.load_next()
                    self.assertTrue(source.has_more)

    def test_initial_failure_does_not_consume_or_start(self) -> None:
        source = self.source_for([row("2020-01-01", prices=("bad", "1", "1", "1"))])
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "OHLC"):
                source.load_initial()
            self.assertTrue(source.has_more)
        with self.assertRaisesRegex(RuntimeError, "initial"):
            source.load_next()

    def test_failed_page_does_not_consume_valid_rows_or_skip_interval(self) -> None:
        path = self.make_file(csv_text([
            row("2022-01-03", prices=("bad", "3", "0.5", "2")),
            row("2022-01-02"),
            row("2020-01-01"),
        ]))
        source = PaginatedPriceData(path)
        self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "invalid OHLC"):
                source.load_next()
            self.assertTrue(source.has_more)
        path.write_bytes(path.read_bytes().replace(b",bad,", b",1.0,"))
        self.assertEqual(dates(source.load_next()), ["2022-01-02", "2022-01-03"])
        self.assertFalse(source.has_more)

    def test_path_input_and_page_reads(self) -> None:
        path = self.make_file(csv_text([row("2022-01-01"), row("2020-01-01")]))
        import builtins
        with patch("builtins.open", wraps=builtins.open) as opened:
            source = PaginatedPriceData(path)
            opened.assert_called_once_with(path, encoding="utf-8-sig", newline="")
            self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
            self.assertEqual(dates(source.load_next()), ["2022-01-01"])
            self.assertEqual(opened.call_count, 3)
            self.assertEqual(source.load_next(), [])
            self.assertEqual(opened.call_count, 3)

    def test_read_failure_mid_page_is_retryable(self) -> None:
        path = self.make_file(csv_text([
            row("2022-01-03"), row("2022-01-02"), row("2020-01-01"),
        ]))
        source = PaginatedPriceData(path)
        source.load_initial()

        class FailingRead:
            def __init__(self) -> None:
                self.file: TextIO = path.open(encoding="utf-8-sig", newline="")
                self.reads = 0

            def __enter__(self) -> FailingRead:
                return self

            def __exit__(self, *args: object) -> None:
                self.file.close()

            def seek(self, offset: int) -> int:
                return self.file.seek(offset)

            def readline(self) -> str:
                self.reads += 1
                if self.reads == 2:
                    raise OSError("read failed")
                return self.file.readline()

        with patch("paginated_price_data.open", return_value=FailingRead()):
            with self.assertRaisesRegex(OSError, "read failed"):
                source.load_next()
        self.assertTrue(source.has_more)
        self.assertEqual(dates(source.load_next()), ["2022-01-02", "2022-01-03"])

    def test_changed_timestamp_and_truncated_file_are_retryable(self) -> None:
        original = csv_text([row("2022-01-01"), row("2020-01-01")])
        path = self.make_file(original)
        source = PaginatedPriceData(path)
        source.load_initial()
        path.write_text(original.replace("2022-01-01", "2022-01-02"), newline="")
        with self.assertRaisesRegex(ValueError, "timestamp changed"):
            source.load_next()
        path.write_text("", newline="")
        with self.assertRaisesRegex(ValueError, "missing"):
            source.load_next()
        self.assertTrue(source.has_more)
        path.write_text(original, newline="")
        self.assertEqual(dates(source.load_next()), ["2022-01-01"])

    def test_datetime_max_boundary(self) -> None:
        source = self.source_for([row("9999-12-31"), row("9999-01-31")])
        self.assertEqual(dates(source.load_initial()), ["9999-01-31", "9999-12-31"])
        self.assertFalse(source.has_more)

    def test_real_sample_is_complete_and_chronological(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "data.csv"
        with path.open(newline="") as file:
            reader = csv.reader(file)
            next(reader)
            next(reader)
            expected = [record[1][:10] for record in reader][::-1]
        source = PaginatedPriceData(path)
        actual = dates(source.load_initial())
        while source.has_more:
            page = source.load_next()
            self.assertTrue(page)
            actual.extend(dates(page))
        self.assertEqual(actual, expected)

    def test_named_columns_are_found_case_insensitively_in_any_order(self) -> None:
        text = (
            "Source line\n"
            "Volume,CLOSE,Symbol,Date,Low,OPEN,High,tradecount\n"
            "10,2,asset,2024-01-02 00:00:00,0.5,1,3,7\n"
            "20,1.5,asset,2024-01-01 00:00:00,0.25,0.75,2,8\n"
        )
        source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
        page = source.load_initial()
        self.assertEqual(dates(page), ["2024-01-01", "2024-01-02"])
        self.assertEqual(page[0][1:5], [0.75, 2.0, 0.25, 1.5])
        self.assertEqual(page[1][1:5], [1.0, 3.0, 0.5, 2.0])

    def test_datetime_column_name_is_accepted(self) -> None:
        text = (
            "datetime,open,high,low,close\n"
            "2024-01-02 00:00:00,1,3,0.5,2\n"
            "2024-01-01 00:00:00,1,3,0.5,2\n"
        )
        source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
        self.assertEqual(dates(source.load_initial()), ["2024-01-01", "2024-01-02"])

    def test_named_header_after_leading_records_is_used(self) -> None:
        text = (
            "https://example.com\n"
            "unix,date,open,high,low,close\n"
            "0,2024-01-02 00:00:00,1,3,0.5,2\n"
            "0,2024-01-01 00:00:00,4,6,3.5,5\n"
        )
        source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
        page = source.load_initial()
        self.assertEqual(page[0][1:5], [4.0, 6.0, 3.5, 5.0])

    def test_require_named_columns_rejects_unnamed_headers(self) -> None:
        text = "a,b,c,d,e,f,g\n0,2024-01-01 00:00:00,x,1,3,0.5,2\n"
        with self.assertRaisesRegex(ValueError, "must name a date column"):
            PaginatedPriceData(self.make_file(text), require_named_columns=True)

    def test_named_header_missing_one_ohlc_column_is_rejected_when_required(self) -> None:
        text = "date,open,high,low\n2024-01-01 00:00:00,1,3,0.5\n"
        with self.assertRaisesRegex(ValueError, "must name a date column"):
            PaginatedPriceData(self.make_file(text), require_named_columns=True)

    def test_positional_fallback_still_applies_without_named_header(self) -> None:
        text = "a\nb\n" + "0,2024-01-01 00:00:00,x,1,3,0.5,2\n"
        source = PaginatedPriceData(self.make_file(text))
        self.assertEqual(dates(source.load_initial()), ["2024-01-01"])


    def test_ascending_and_descending_files_load_oldest_first(self) -> None:
        ascending = self.source_for([row("2020-01-01"), row("2020-06-01")])
        descending = self.source_for([row("2020-06-01"), row("2020-01-01")])
        self.assertEqual(dates(ascending.load_initial()), ["2020-01-01", "2020-06-01"])
        self.assertEqual(dates(descending.load_initial()), ["2020-01-01", "2020-06-01"])

    def test_common_date_formats_are_accepted(self) -> None:
        for date_text in (
            "2020-01-02", "2020-01-02 10:30", "2020-01-02 10:30:00",
            "2020-01-02T10:30:00", "2020/01/02", "2020/01/02 10:30:00", "2020-1-2",
        ):
            with self.subTest(date=date_text):
                text = "date,open,high,low,close\n" + f"{date_text},1,3,0.5,2\n"
                source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
                self.assertEqual(dates(source.load_initial()), ["2020-01-02"])

    def test_date_only_and_time_rows_are_compared_by_timestamp(self) -> None:
        text = (
            "date,open,high,low,close\n"
            "2020-01-02 09:00,1,3,0.5,2\n"
            "2020-01-02 15:00,1,3,0.5,2\n"
        )
        source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
        self.assertEqual(len(source.load_initial()), 2)

    def test_dollar_prefixed_prices_are_accepted(self) -> None:
        text = (
            "Date,Volume,Open,High,Low,Close\n"
            "2020-01-02,10,$38.58,$39.39,$38.55,$39.25\n"
        )
        source = PaginatedPriceData(self.make_file(text), require_named_columns=True)
        self.assertEqual(source.load_initial()[0][1:5], [38.58, 39.39, 38.55, 39.25])

    def test_real_ascending_dollar_samples_page_completely(self) -> None:
        root = Path(__file__).resolve().parent.parent / "data"
        for name in ("AMZN_10_year_OHLC.csv", "APPL_10_year_OHLC.csv"):
            with self.subTest(file=name):
                source = PaginatedPriceData(root / name, require_named_columns=True)
                actual = dates(source.load_initial())
                while source.has_more:
                    page = source.load_next()
                    self.assertTrue(page)
                    actual.extend(dates(page))
                self.assertEqual(actual[0], "2016-11-07")
                self.assertEqual(actual, sorted(actual))
                self.assertEqual(len(actual), len(set(actual)))


if __name__ == "__main__":
    unittest.main()
