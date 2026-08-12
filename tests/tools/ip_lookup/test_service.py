import unittest
from unittest.mock import patch

from fuzztoolbox.tools.ip_lookup.page import format_report
from fuzztoolbox.tools.ip_lookup.service import (
    LookupReport,
    SourceResult,
    classify_ip,
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
