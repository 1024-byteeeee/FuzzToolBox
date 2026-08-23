import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from fuzztoolbox.core.network_info import (
    NetworkInfo,
    _gateway_for_interface,
    _macos_network_info,
    _prefix_from_hex_netmask,
    _psutil_network_info,
    _run,
    _windows_network_info,
)


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
        with patch("fuzztoolbox.core.network_info._run", side_effect=[route, details]):
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

    def test_scan_defaults_come_from_network(self):
        info = NetworkInfo("Ethernet", "192.168.8.42", 24)
        self.assertEqual(info.cidr, "192.168.8.0/24")
        self.assertEqual(info.scan_range, ("192.168.8.1", "192.168.8.254"))

    def test_point_to_point_scan_range(self):
        self.assertEqual(
            NetworkInfo(ip="10.0.0.2", prefix_length=31).scan_range,
            ("10.0.0.2", "10.0.0.3"),
        )

    def test_windows_network_parsing(self):
        output = "Ethernet|10.2.2.20|24|10.2.2.1|AA-BB-CC-DD-EE-FF\n"
        with patch("fuzztoolbox.core.network_info._run", return_value=output) as run:
            info = _windows_network_info()
        command = run.call_args.args[0]
        self.assertIn("-File", command)
        self.assertTrue(command[-1].endswith("get_network_info.ps1"))
        self.assertNotIn("-Command", command)
        self.assertEqual(info.interface, "Ethernet")
        self.assertEqual(info.ip, "10.2.2.20")
        self.assertEqual(info.prefix_length, 24)
        self.assertEqual(info.mac, "AA:BB:CC:DD:EE:FF")

    @patch("fuzztoolbox.core.network_info.platform.system", return_value="Windows")
    def test_windows_gateway_script_receives_interface_as_an_argument(self, _system):
        interface = "Ethernet 'Office'"
        with patch("fuzztoolbox.core.network_info._run", return_value="10.2.2.1\n") as run:
            gateway = _gateway_for_interface(interface)
        command = run.call_args.args[0]
        self.assertEqual(gateway, "10.2.2.1")
        self.assertTrue(command[-2].endswith("get_interface_gateway.ps1"))
        self.assertEqual(command[-1], interface)
        self.assertNotIn("-Command", command)

    def test_physical_lan_wins_over_vpn_when_route_lookup_fails(self):
        interfaces = {
            "en0": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="172.16.255.139",
                    netmask="255.255.0.0",
                ),
                SimpleNamespace(
                    family=psutil.AF_LINK,
                    address="AA:BB:CC:DD:EE:01",
                    netmask=None,
                ),
            ],
            "utun6": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="198.18.0.1",
                    netmask="255.255.255.252",
                )
            ],
        }
        stats = {
            "en0": SimpleNamespace(isup=True),
            "utun6": SimpleNamespace(isup=True),
        }
        with patch("fuzztoolbox.core.network_info._socket_source_ip", return_value="198.18.0.1"), patch(
            "fuzztoolbox.core.network_info.psutil.net_if_addrs", return_value=interfaces
        ), patch("fuzztoolbox.core.network_info.psutil.net_if_stats", return_value=stats):
            info = _psutil_network_info()
        self.assertEqual(info.interface, "en0")
        self.assertEqual(info.ip, "172.16.255.139")
        self.assertEqual(info.scan_range, ("172.16.0.1", "172.16.255.254"))

    def test_windows_virtual_adapter_does_not_beat_physical_adapter(self):
        interfaces = {
            "vEthernet (Default Switch)": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="192.168.50.1",
                    netmask="255.255.255.0",
                )
            ],
            "以太网": [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address="192.168.1.20",
                    netmask="255.255.255.0",
                )
            ],
        }
        stats = {name: SimpleNamespace(isup=True) for name in interfaces}
        with patch("fuzztoolbox.core.network_info._socket_source_ip", return_value=None), patch(
            "fuzztoolbox.core.network_info.psutil.net_if_addrs", return_value=interfaces
        ), patch("fuzztoolbox.core.network_info.psutil.net_if_stats", return_value=stats):
            info = _psutil_network_info()
        self.assertEqual(info.interface, "以太网")
        self.assertEqual(info.cidr, "192.168.1.0/24")

    def test_missing_netmask_keeps_ip_without_inventing_a_range(self):
        interfaces = {
            "Ethernet": [
                SimpleNamespace(family=socket.AF_INET, address="10.1.2.3", netmask=None)
            ]
        }
        with patch("fuzztoolbox.core.network_info._socket_source_ip", return_value="10.1.2.3"), patch(
            "fuzztoolbox.core.network_info.psutil.net_if_addrs", return_value=interfaces
        ), patch(
            "fuzztoolbox.core.network_info.psutil.net_if_stats",
            return_value={"Ethernet": SimpleNamespace(isup=True)},
        ):
            info = _psutil_network_info()
        self.assertEqual(info.ip, "10.1.2.3")
        self.assertIsNone(info.scan_range)

    @patch("fuzztoolbox.core.network_info.platform.system", return_value="Windows")
    @patch("fuzztoolbox.core.subprocess_utils.platform.system", return_value="Windows")
    @patch("fuzztoolbox.core.network_info.subprocess.run")
    def test_windows_commands_are_hidden(self, run, _subprocess_system, _system):
        run.return_value.stdout = ""
        _run(["ipconfig"])
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)


if __name__ == "__main__":
    unittest.main()
