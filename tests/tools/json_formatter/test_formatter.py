import unittest

from fuzztoolbox.tools.json_formatter.formatter import (
    JSONValidationError,
    compact_json,
    format_json,
    parse_json,
    validate_json,
)


class JSONFormatterTests(unittest.TestCase):
    def test_formats_nested_json_and_preserves_unicode(self):
        result = format_json('{"名称":"工具箱","items":[1,true,null]}', 2)
        self.assertIn('"名称": "工具箱"', result)
        self.assertIn("\n  \"items\": [", result)
        self.assertNotIn("\\u", result)
        self.assertEqual(parse_json(result)["items"], [1, True, None])

    def test_supports_four_spaces_tabs_and_key_sorting(self):
        four_spaces = format_json('{"b":2,"a":1}', 4, sort_keys=True)
        self.assertLess(four_spaces.index('"a"'), four_spaces.index('"b"'))
        self.assertIn('\n    "a"', four_spaces)
        tabs = format_json('{"nested":{"ok":true}}', "\t")
        self.assertIn('\n\t"nested"', tabs)

    def test_compacts_json_without_escaping_unicode(self):
        self.assertEqual(compact_json('{ "名称": "工具箱", "ok": true }'), '{"名称":"工具箱","ok":true}')

    def test_invalid_json_reports_line_column_and_position(self):
        source = '{\n  "name": "tool",\n  "enabled": tru\n}'
        with self.assertRaises(JSONValidationError) as context:
            parse_json(source)
        details = context.exception.details
        self.assertEqual(details.line, 3)
        self.assertGreater(details.column, 1)
        self.assertGreater(details.position, 0)
        self.assertIn("第 3 行", str(context.exception))
        self.assertEqual(validate_json(source), details)

    def test_empty_input_and_invalid_indent_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "请输入 JSON"):
            parse_json("   \n")
        with self.assertRaisesRegex(ValueError, "缩进仅支持"):
            format_json("{}", 8)

    def test_valid_scalar_json_is_supported(self):
        self.assertEqual(parse_json("42"), 42)
        self.assertEqual(compact_json('"文本"'), '"文本"')


if __name__ == "__main__":
    unittest.main()
