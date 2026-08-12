import struct
import unittest

from fuzztoolbox.tools.ip_scanner.hostname import (
    _dns_query,
    _encode_dns_name,
    build_nbstat_query,
    parse_dns_ptr,
    parse_nbstat_response,
)


class HostnameProtocolTests(unittest.TestCase):
    def test_mdns_ptr_response_with_compressed_owner(self):
        reverse_name = "20.1.168.192.in-addr.arpa"
        question = _dns_query(reverse_name, transaction_id=0, unicast_response=True)[12:]
        hostname = _encode_dns_name("office-mac.local")
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 12, 1, 120, len(hostname)) + hostname
        packet = struct.pack("!HHHHHH", 0, 0x8400, 1, 1, 0, 0) + question + answer

        self.assertEqual(parse_dns_ptr(packet, reverse_name), "office-mac.local")

    def test_mdns_ignores_ptr_for_another_address(self):
        reverse_name = "20.1.168.192.in-addr.arpa"
        other_name = "21.1.168.192.in-addr.arpa"
        question = _dns_query(other_name, transaction_id=0)[12:]
        hostname = _encode_dns_name("wrong.local")
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 12, 1, 120, len(hostname)) + hostname
        packet = struct.pack("!HHHHHH", 0, 0x8400, 1, 1, 0, 0) + question + answer

        self.assertIsNone(parse_dns_ptr(packet, reverse_name))

    def test_nbstat_returns_unique_workstation_name(self):
        transaction_id = 0x1234
        question = build_nbstat_query(transaction_id)[12:]
        group = b"WORKGROUP".ljust(15) + b"\x00" + struct.pack("!H", 0x8000)
        workstation = b"OFFICE-PC".ljust(15) + b"\x00" + struct.pack("!H", 0)
        data = bytes([2]) + group + workstation
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 0x21, 1, 0, len(data)) + data
        packet = struct.pack("!HHHHHH", transaction_id, 0x8500, 1, 1, 0, 0) + question + answer

        self.assertEqual(parse_nbstat_response(packet, transaction_id), "OFFICE-PC")

    def test_nbstat_rejects_another_transaction(self):
        packet = struct.pack("!HHHHHH", 0x9999, 0x8500, 0, 0, 0, 0)
        self.assertIsNone(parse_nbstat_response(packet, 0x1234))


if __name__ == "__main__":
    unittest.main()
