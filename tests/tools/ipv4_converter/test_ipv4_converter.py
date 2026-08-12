import unittest

from fuzztoolbox.tools.ipv4_converter.converter import convert_ipv4


class IPv4ConverterTests(unittest.TestCase):
    def test_standard_formats(self):
        result = convert_ipv4("192.168.1.1")
        self.assertEqual(result.binary, "11000000.10101000.00000001.00000001")
        self.assertEqual(result.decimal, "3232235777")
        self.assertEqual(result.hexadecimal, "0xC0A80101")
        self.assertEqual(result.ipv6, "0000:0000:0000:0000:0000:ffff:c0a8:0101")
        self.assertEqual(result.ipv6_short, "::ffff:192.168.1.1")

    def test_boundary_addresses(self):
        self.assertEqual(convert_ipv4("0.0.0.0").decimal, "0")
        self.assertEqual(convert_ipv4("255.255.255.255").hexadecimal, "0xFFFFFFFF")

    def test_invalid_and_cidr_inputs_are_rejected(self):
        for value in ("", "192.168.1.256", "192.168.1", "192.168.1.1/24", "::1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_ipv4(value)


if __name__ == "__main__":
    unittest.main()
