import unittest
from unittest.mock import patch

from ip_scanner.network_info import NetworkInfo, _macos_network_info, _prefix_from_hex_netmask


class NetworkInfoTests(unittest.TestCase):
    def test_hex_netmask_to_prefix(self):
        self.assertEqual(_prefix_from_hex_netmask("0xffffff00"), 24)
        self.assertEqual(_prefix_from_hex_netmask("0xffff0000"), 16)

    def test_macos_network_parsing(self):
        route = "gateway: 192.168.1.1\ninterface: en0\n"
        details = (
            "en0: flags=8863<UP>\n"
            "\tether aa:bb:cc:dd:ee:ff\n"
            "\tinet 192.168.1.20 netmask 0xffffff00 broadcast 192.168.1.255\n"
        )
        with patch("ip_scanner.network_info._run", side_effect=[route, details]):
            info = _macos_network_info()
        self.assertEqual(info.interface, "en0")
        self.assertEqual(info.address, "192.168.1.20")
        self.assertEqual(info.netmask, "255.255.255.0")
        self.assertEqual(info.gateway, "192.168.1.1")
        self.assertEqual(info.mac, "AA:BB:CC:DD:EE:FF")

    def test_display_text(self):
        info = NetworkInfo("en0", "10.0.0.2", 24, "10.0.0.1", "AA:BB:CC:DD:EE:FF")
        self.assertIn("IP 10.0.0.2", info.display_text())
        self.assertIn("子网掩码 255.255.255.0", info.display_text())
        self.assertIn("网关 10.0.0.1", info.display_text())


if __name__ == "__main__":
    unittest.main()
