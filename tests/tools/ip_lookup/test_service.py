import socket
import struct
import unittest
from unittest.mock import patch

from fuzztoolbox.tools.ip_lookup.page import format_report
from fuzztoolbox.tools.ip_lookup.service import (
    LookupReport,
    SourceResult,
    _discover_ipv4_via_dns,
    _ssl_context,
    classify_ip,
    discover_public_ip,
    lookup,
    parse_public_ip,
)


class IPLookupServiceTests(unittest.TestCase):
    def test_public_ip_validation_and_classification(self):
        self.assertEqual(parse_public_ip(" 8.8.8.8 "), "8.8.8.8")
        self.assertEqual(classify_ip("8.8.8.8"), "IPv4 · 公网地址")
        self.assertIn("私有地址", classify_ip("192.168.1.1"))
        with self.assertRaises(ValueError):
            parse_public_ip("192.168.1.1")

    @patch("fuzztoolbox.tools.ip_lookup.service._read_text")
    def test_public_ip_discovery_falls_back_between_services(self, read_text):
        read_text.side_effect = [OSError("unavailable"), "not an ip", "8.8.8.8\n"]
        self.assertEqual(discover_public_ip(4), "8.8.8.8")
        self.assertEqual(read_text.call_count, 3)

    @patch("fuzztoolbox.tools.ip_lookup.service._read_text")
    def test_public_ip_discovery_accepts_json_and_rejects_wrong_version(self, read_text):
        read_text.side_effect = [
            '{"ip":"2606:4700:4700::1111"}',
            "not an ip",
            "8.8.8.8",
        ]
        self.assertEqual(discover_public_ip(4), "8.8.8.8")

    def test_public_ip_discovery_rejects_unknown_version(self):
        with self.assertRaises(ValueError):
            discover_public_ip(5)

    @patch("fuzztoolbox.tools.ip_lookup.service._discover_ipv4_via_dns")
    @patch("fuzztoolbox.tools.ip_lookup.service._read_text", side_effect=OSError("offline"))
    def test_public_ip_discovery_uses_dns_after_https_sources(self, read_text, dns):
        dns.return_value = "8.8.4.4"
        self.assertEqual(discover_public_ip(4), "8.8.4.4")
        self.assertEqual(read_text.call_count, 6)
        dns.assert_called_once()

    @patch("fuzztoolbox.tools.ip_lookup.service.socket.socket")
    @patch("fuzztoolbox.tools.ip_lookup.service.os.urandom", return_value=b"\x12\x34")
    def test_opendns_response_is_parsed(self, _random, socket_class):
        question = b"\x04myip\x07opendns\x03com\x00\x00\x01\x00\x01"
        answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton("8.8.8.8")
        response = b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + question + answer
        socket_class.return_value.recvfrom.return_value = (response, ("208.67.222.222", 53))
        self.assertEqual(_discover_ipv4_via_dns(), "8.8.8.8")
        socket_class.return_value.sendto.assert_called_once()
        socket_class.return_value.close.assert_called_once()

    @patch("fuzztoolbox.tools.ip_lookup.service.platform.system", return_value="Darwin")
    @patch("fuzztoolbox.tools.ip_lookup.service.Path.is_file", return_value=True)
    @patch("fuzztoolbox.tools.ip_lookup.service.subprocess.run")
    @patch("fuzztoolbox.tools.ip_lookup.service.ssl.create_default_context")
    def test_macos_ssl_context_loads_native_certificates(self, create_context, run, _exists, _system):
        context = create_context.return_value
        run.return_value.returncode = 0
        run.return_value.stdout = b"-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n"
        _ssl_context.cache_clear()
        self.assertIs(_ssl_context(), context)
        self.assertGreaterEqual(context.load_verify_locations.call_count, 3)
        _ssl_context.cache_clear()

    @patch("fuzztoolbox.tools.ip_lookup.service.reverse_dns")
    @patch("fuzztoolbox.tools.ip_lookup.service._read_json")
    def test_lookup_merges_location_sources(self, read_json, reverse_dns):
        read_json.side_effect = [
            {
                "success": True,
                "country": "United States",
                "region": "California",
                "city": "Mountain View",
                "connection": {"asn": 15169, "isp": "Google", "org": "Google LLC"},
            },
            {
                "country_name": "United States",
                "region": "California",
                "city": "Mountain View",
                "asn": "AS15169",
                "org": "Google LLC",
            },
        ]
        reverse_dns.return_value = "dns.google"

        report = lookup("8.8.8.8")

        self.assertEqual(report.ptr, "dns.google")
        self.assertEqual(report.merged("asn"), 15169)
        self.assertEqual(len(report.sources), 2)

    def test_report_contains_only_requested_summary(self):
        report = LookupReport(
            "1.1.1.1",
            "IPv4 · 公网地址",
            "one.one.one.one",
            "1.1.1.1",
            "2606:4700:4700::1111",
            [SourceResult("source", {"country": "Australia", "asn": "AS13335"})],
        )
        text = format_report(report)
        self.assertIn("当前公网 IPv6：2606:4700:4700::1111", text)
        self.assertNotIn("网络类型标签", text)
        self.assertNotIn("TCP 常用端口", text)
        self.assertNotIn("多数据源对比", text)


if __name__ == "__main__":
    unittest.main()
