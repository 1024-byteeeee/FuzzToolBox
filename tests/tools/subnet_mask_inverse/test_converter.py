import unittest

from fuzztoolbox.tools.subnet_mask_inverse.converter import convert_mask


class SubnetMaskInverseTests(unittest.TestCase):
    def test_subnet_mask_converts_to_wildcard_and_cidr(self):
        result = convert_mask("255.255.255.0")
        self.assertEqual(result.input_type, "子网掩码")
        self.assertEqual(result.wildcard_mask, "0.0.0.255")
        self.assertEqual(result.prefix, 24)
        self.assertEqual(result.total_addresses, 256)
        self.assertEqual(result.usable_hosts, 254)

    def test_wildcard_mask_converts_to_subnet_mask(self):
        result = convert_mask("0.0.15.255")
        self.assertEqual(result.input_type, "通配符掩码")
        self.assertEqual(result.subnet_mask, "255.255.240.0")
        self.assertEqual(result.prefix, 20)

    def test_cidr_accepts_slash_and_plain_number(self):
        self.assertEqual(convert_mask("/26").subnet_mask, "255.255.255.192")
        self.assertEqual(convert_mask("26").wildcard_mask, "0.0.0.63")

    def test_prefix_boundaries_and_point_to_point_capacity(self):
        self.assertEqual(convert_mask("/0").total_addresses, 1 << 32)
        self.assertEqual(convert_mask("/31").usable_hosts, 2)
        self.assertEqual(convert_mask("/32").usable_hosts, 1)

    def test_binary_outputs_have_four_octets(self):
        result = convert_mask("/24")
        self.assertEqual(result.subnet_binary, "11111111.11111111.11111111.00000000")
        self.assertEqual(result.wildcard_binary, "00000000.00000000.00000000.11111111")

    def test_rejects_non_contiguous_and_invalid_values(self):
        for value in ("255.0.255.0", "0.255.0.255", "/33", "-1", "hello", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_mask(value)


if __name__ == "__main__":
    unittest.main()
