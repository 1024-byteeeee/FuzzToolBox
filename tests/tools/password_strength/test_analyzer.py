import math
import unittest

from fuzztoolbox.tools.password_strength.analyzer import (
    analyze_password,
    format_crack_time,
    infer_charset_size,
)


class PasswordStrengthAnalyzerTests(unittest.TestCase):
    def test_character_classes_build_the_expected_pool(self):
        self.assertEqual(infer_charset_size("abc"), 26)
        self.assertEqual(infer_charset_size("aA1!"), 94)
        self.assertEqual(infer_charset_size("a A"), 53)
        self.assertEqual(infer_charset_size("密码"), 2)

    def test_entropy_search_space_and_score_are_consistent(self):
        result = analyze_password("aA1!aA1!")
        self.assertEqual(result.length, 8)
        self.assertEqual(result.charset_size, 94)
        self.assertAlmostEqual(result.entropy, 8 * math.log2(94))
        self.assertEqual(result.average_guesses, 94**8 // 2)
        self.assertEqual(result.score, round(result.entropy / 128 * 100))

    def test_empty_password_has_zero_strength(self):
        result = analyze_password("")
        self.assertEqual((result.length, result.charset_size, result.score), (0, 0, 0))
        self.assertEqual(result.crack_time, "立即")

    def test_crack_time_formats_small_and_large_values(self):
        self.assertEqual(format_crack_time(1), "少于 1 毫秒")
        self.assertIn("秒", format_crack_time(20_000_000_000))
        self.assertIn("年", format_crack_time(10**40))

    def test_score_is_capped_at_one_hundred(self):
        self.assertEqual(analyze_password("aA1!" * 40).score, 100)

    def test_invalid_cracking_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            format_crack_time(100, 0)


if __name__ == "__main__":
    unittest.main()
