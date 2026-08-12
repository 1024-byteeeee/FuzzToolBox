import unittest

from fuzztoolbox.tools.text_statistics.analyzer import analyze_text, format_report


class TextStatisticsTests(unittest.TestCase):
    def test_empty_text_has_zero_lines_and_sizes(self):
        stats = analyze_text("")
        self.assertEqual(stats.characters, 0)
        self.assertEqual(stats.lines, 0)
        self.assertEqual(stats.utf8_bytes, 0)

    def test_mixed_cjk_latin_and_numbers_have_clear_counting_rules(self):
        stats = analyze_text("你好 OpenAI 2026")
        self.assertEqual(stats.cjk_characters, 2)
        self.assertEqual(stats.words, 2)
        self.assertEqual(stats.word_units, 4)
        self.assertEqual(stats.digits, 4)

    def test_lines_paragraphs_sentences_and_encoding_sizes(self):
        text = "第一句。\n第二句！\n\nHello world."
        stats = analyze_text(text)
        self.assertEqual(stats.lines, 4)
        self.assertEqual(stats.non_empty_lines, 3)
        self.assertEqual(stats.blank_lines, 1)
        self.assertEqual(stats.paragraphs, 2)
        self.assertEqual(stats.sentences, 3)
        self.assertEqual(stats.utf8_bytes, len(text.encode("utf-8")))
        self.assertEqual(stats.utf16_bytes, len(text.encode("utf-16-le")))

    def test_crlf_is_normalized_and_report_is_copyable(self):
        stats = analyze_text("a\r\n\r\nb")
        self.assertEqual(stats.lines, 3)
        report = format_report(stats)
        self.assertIn("UTF-8 字节数：4 字节", report)
        self.assertNotIn("KiB", report)


if __name__ == "__main__":
    unittest.main()
