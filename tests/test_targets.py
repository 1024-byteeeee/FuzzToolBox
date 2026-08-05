import unittest

from ip_scanner.targets import parse_ports, parse_target


class TargetTests(unittest.TestCase):
    def test_cidr_is_lazy_and_complete(self):
        target = parse_target("192.168.1.9/30")
        self.assertEqual(target.total, 4)
        self.assertEqual(
            list(target),
            ["192.168.1.8", "192.168.1.9", "192.168.1.10", "192.168.1.11"],
        )

    def test_range(self):
        target = parse_target("10.0.0.2-10.0.0.4")
        self.assertEqual(target.total, 3)
        self.assertEqual(list(target), ["10.0.0.2", "10.0.0.3", "10.0.0.4"])

    def test_reversed_range_rejected(self):
        with self.assertRaises(ValueError):
            parse_target("10.0.0.4-10.0.0.2")

    def test_ports(self):
        self.assertEqual(parse_ports("443,80,8000-8002,80"), [80, 443, 8000, 8001, 8002])


if __name__ == "__main__":
    unittest.main()

