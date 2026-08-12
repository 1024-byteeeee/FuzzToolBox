import unittest

from fuzztoolbox.tools.datetime_converter.converter import (
    convert_datetime,
    convert_timestamp,
    parse_timezone,
)


class DateTimeConverterTests(unittest.TestCase):
    def test_epoch_outputs_all_supported_formats(self):
        rows = dict(convert_timestamp("0", "seconds", "UTC").rows())
        self.assertEqual(rows["Unix 时间戳（秒）"], "0")
        self.assertEqual(rows["Unix 时间戳（毫秒）"], "0")
        self.assertEqual(rows["ISO 8601"], "1970-01-01T00:00:00+00:00")
        self.assertEqual(rows["HTTP 日期"], "Thu, 01 Jan 1970 00:00:00 GMT")
        self.assertEqual(rows["星期"], "星期四")

    def test_milliseconds_and_microseconds_are_exact(self):
        milli = dict(convert_timestamp("1700000000123", "auto", "UTC").rows())
        self.assertEqual(milli["Unix 时间戳（毫秒）"], "1700000000123")
        self.assertEqual(milli["Unix 时间戳（微秒）"], "1700000000123000")
        micro = dict(convert_timestamp("1700000000123456", "auto", "UTC").rows())
        self.assertEqual(micro["Unix 时间戳（微秒）"], "1700000000123456")

    def test_iso_input_respects_explicit_offset_and_converts_target(self):
        rows = dict(convert_datetime("2026-04-13T17:00:00+08:00", "UTC").rows())
        self.assertEqual(rows["Unix 时间戳（秒）"], "1776070800")
        self.assertEqual(rows["标准日期时间"], "2026-04-13 09:00:00")
        self.assertEqual(rows["UTC 偏移"], "UTC")

    def test_naive_input_uses_selected_custom_offset(self):
        rows = dict(convert_datetime("2026-04-13 17:00:00", "UTC+08:00").rows())
        self.assertEqual(rows["Unix 时间戳（秒）"], "1776070800")
        self.assertEqual(rows["RFC 3339"], "2026-04-13T17:00:00.000+08:00")

    def test_negative_timestamp_and_validation(self):
        rows = dict(convert_timestamp("-1", "seconds", "UTC").rows())
        self.assertEqual(rows["标准日期时间"], "1969-12-31 23:59:59")
        with self.assertRaisesRegex(ValueError, "整数"):
            convert_timestamp("1.5", "seconds", "UTC")
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            convert_datetime("13/40/2026", "UTC")

    def test_timezone_offset_validation(self):
        self.assertEqual(parse_timezone("UTC+05:30").utcoffset(None).total_seconds(), 19800)
        with self.assertRaisesRegex(ValueError, "-14:00"):
            parse_timezone("UTC+14:30")


if __name__ == "__main__":
    unittest.main()
