import csv
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from paginated_price_data import PaginatedPriceData


def csv_text(records):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["source"])
    writer.writerow(["unix", "date", "symbol", "open", "high", "low", "close"])
    writer.writerows(records)
    return output.getvalue()


def row(date, symbol="asset", prices=("1", "3", "0.5", "2")):
    return ["0", date + " 00:00:00", symbol, *prices]


def dates(page):
    return ["-".join(record[0]) for record in page]


class PaginatedPriceDataTests(unittest.TestCase):
    def make_file(self, text):
        path = Path("tests") / f".pagination-test-{uuid4().hex}.csv"
        path.write_text(text, encoding="utf-8", newline="")
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def source_for(self, records):
        return PaginatedPriceData(self.make_file(csv_text(records)))

    def test_calendar_boundaries_gaps_and_final_partial_page(self):
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
                                    {"rsi": 0, "ema": 0, "sma": 0}])
        first[0][-1]["rsi"] = 20
        self.assertEqual(first[1][-1]["rsi"], 0)

    def test_leap_day_anchor_and_exclusive_timestamp_boundaries(self):
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

    def test_quoted_fields_and_multiline_records(self):
        source = self.source_for([
            row("2021-01-01", 'quoted, "asset"\nline'),
            row("2020-01-01", "another, asset"),
        ])
        self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        self.assertEqual(dates(source.load_next()), ["2021-01-01"])

    def test_state_and_empty_data(self):
        with self.assertRaisesRegex(ValueError, "no price records"):
            self.source_for([])
        source = self.source_for([row("2020-01-01")])
        with self.assertRaisesRegex(RuntimeError, "initial"):
            source.load_next()
        self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
        self.assertEqual(source.load_next(), [])
        with self.assertRaisesRegex(RuntimeError, "already"):
            source.load_initial()

    def test_validation_of_order_dates_headers_and_csv(self):
        for records in (
            [row("2020-01-01"), row("2021-01-01")],
            [row("2020-01-01"), row("2020-01-01")],
        ):
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, "descending"):
                self.source_for(records)
        for bad_date in ("2020-02-30", "2020-1-01", "not-a-date"):
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

    def test_custom_header_count(self):
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

    def test_lazy_ohlc_validation_and_transactional_retry(self):
        for bad_prices in (("bad", "1", "1", "1"), ("nan", "1", "1", "1"), ("1",)):
            with self.subTest(prices=bad_prices):
                source = self.source_for([row("2022-01-01", prices=bad_prices), row("2020-01-01")])
                self.assertEqual(dates(source.load_initial()), ["2020-01-01"])
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, "OHLC"):
                        source.load_next()
                    self.assertTrue(source.has_more)

    def test_initial_failure_does_not_consume_or_start(self):
        source = self.source_for([row("2020-01-01", prices=("bad", "1", "1", "1"))])
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "OHLC"):
                source.load_initial()
            self.assertTrue(source.has_more)
        with self.assertRaisesRegex(RuntimeError, "initial"):
            source.load_next()

    def test_failed_page_does_not_consume_valid_rows_or_skip_interval(self):
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

    def test_path_input_and_page_reads(self):
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

    def test_read_failure_mid_page_is_retryable(self):
        path = self.make_file(csv_text([
            row("2022-01-03"), row("2022-01-02"), row("2020-01-01"),
        ]))
        source = PaginatedPriceData(path)
        source.load_initial()

        class FailingRead:
            def __init__(self):
                self.file = path.open(encoding="utf-8-sig", newline="")
                self.reads = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.file.close()

            def seek(self, offset):
                return self.file.seek(offset)

            def readline(self):
                self.reads += 1
                if self.reads == 2:
                    raise OSError("read failed")
                return self.file.readline()

        with patch("paginated_price_data.open", return_value=FailingRead()):
            with self.assertRaisesRegex(OSError, "read failed"):
                source.load_next()
        self.assertTrue(source.has_more)
        self.assertEqual(dates(source.load_next()), ["2022-01-02", "2022-01-03"])

    def test_changed_timestamp_and_truncated_file_are_retryable(self):
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

    def test_datetime_max_boundary(self):
        source = self.source_for([row("9999-12-31"), row("9999-01-31")])
        self.assertEqual(dates(source.load_initial()), ["9999-01-31", "9999-12-31"])
        self.assertFalse(source.has_more)

    def test_real_sample_is_complete_and_chronological(self):
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


if __name__ == "__main__":
    unittest.main()
