import unittest

from fuzztoolbox.tools.roman_numeral.converter import (
    integer_to_roman,
    roman_to_integer,
)


class RomanNumeralConverterTests(unittest.TestCase):
    def test_integer_to_roman_uses_canonical_subtractive_notation(self):
        cases = {1: "I", 4: "IV", 9: "IX", 40: "XL", 944: "CMXLIV", 3999: "MMMCMXCIX"}
        for number, numeral in cases.items():
            with self.subTest(number=number):
                self.assertEqual(integer_to_roman(number), numeral)

    def test_roman_to_integer_is_case_insensitive_and_trims_space(self):
        self.assertEqual(roman_to_integer("  mmxxvi  "), 2026)

    def test_all_supported_numbers_round_trip(self):
        for number in range(1, 4000):
            self.assertEqual(roman_to_integer(integer_to_roman(number)), number)

    def test_invalid_or_noncanonical_roman_numerals_are_rejected(self):
        for value in ("", "IIII", "VV", "VX", "IC", "IIV", "MMMM", "ABC"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                roman_to_integer(value)

    def test_invalid_integer_values_are_rejected(self):
        for value in (0, 4000, -1, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer_to_roman(value)


if __name__ == "__main__":
    unittest.main()
