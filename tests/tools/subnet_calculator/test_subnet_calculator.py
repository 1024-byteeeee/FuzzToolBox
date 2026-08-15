import unittest

from fuzztoolbox.tools.subnet_calculator.calculator import (
    FLSMPlan,
    allocate_vlsm,
    flsm_by_count,
    network_summary,
    parse_host_requirements,
    parse_network,
)


class SubnetCalculatorTests(unittest.TestCase):
    def test_parse_ipv4_dotted_mask_normalizes_network(self):
        network = parse_network("192.168.1.99/255.255.255.0")
        self.assertEqual(network.with_prefixlen, "192.168.1.0/24")

    def test_parse_ipv6_network(self):
        network = parse_network("2001:db8::1234/48")
        self.assertEqual(network.with_prefixlen, "2001:db8::/48")

    def test_ipv4_point_to_point_has_two_usable_addresses(self):
        summary = network_summary(parse_network("192.0.2.0/31"))
        self.assertEqual(summary["首个可用地址"], "192.0.2.0")
        self.assertEqual(summary["最后可用地址"], "192.0.2.1")
        self.assertEqual(summary["可用地址数"], 2)

    def test_ipv4_single_host_network_has_one_usable_address(self):
        summary = network_summary(parse_network("192.0.2.9/32"))
        self.assertEqual(summary["首个可用地址"], "192.0.2.9")
        self.assertEqual(summary["最后可用地址"], "192.0.2.9")
        self.assertEqual(summary["可用地址数"], 1)

    def test_ipv6_summary_has_no_broadcast(self):
        summary = network_summary(parse_network("2001:db8::/126"))
        self.assertEqual(summary["广播地址"], "—")
        self.assertEqual(summary["可用地址数"], 4)

    def test_flsm_is_lazy_and_can_locate_ip(self):
        plan = FLSMPlan(parse_network("10.0.0.0/8"), 24)
        self.assertEqual(plan.total, 65536)
        self.assertEqual(plan.subnet_at(257).with_prefixlen, "10.1.1.0/24")
        self.assertEqual(plan.index_for_ip("10.1.1.99"), 257)

    def test_flsm_count_rounds_up_to_power_of_two(self):
        plan = flsm_by_count(parse_network("192.168.1.0/24"), 5)
        self.assertEqual(plan.target_prefix, 27)
        self.assertEqual(plan.total, 8)

    def test_ipv4_vlsm_allocates_largest_requirements_first(self):
        rows = allocate_vlsm(parse_network("192.168.10.0/24"), [10, 100, 50])
        self.assertEqual(
            [row.network.with_prefixlen for row in rows],
            ["192.168.10.0/25", "192.168.10.128/26", "192.168.10.192/28"],
        )
        self.assertEqual([row.request_index for row in rows], [2, 3, 1])
        self.assertGreaterEqual(rows[0].usable, 100)

    def test_ipv6_vlsm_allocates_address_capacity(self):
        rows = allocate_vlsm(parse_network("2001:db8::/120"), [50, 100])
        self.assertEqual(rows[0].network.with_prefixlen, "2001:db8::/121")
        self.assertEqual(rows[1].network.with_prefixlen, "2001:db8::80/122")

    def test_vlsm_allocations_do_not_overlap_and_stay_inside_base_network(self):
        base = parse_network("10.20.0.0/20")
        rows = allocate_vlsm(base, [1, 2, 3, 30, 62, 100, 500])
        networks = [row.network for row in rows]
        self.assertTrue(all(network.subnet_of(base) for network in networks))
        self.assertTrue(all(row.usable >= row.requested_hosts for row in rows))
        for index, network in enumerate(networks):
            self.assertTrue(all(not network.overlaps(other) for other in networks[index + 1 :]))

    def test_equal_vlsm_requirements_keep_input_order(self):
        rows = allocate_vlsm(parse_network("10.0.0.0/24"), [10, 10, 10])
        self.assertEqual([row.request_index for row in rows], [1, 2, 3])

    def test_vlsm_reports_insufficient_space(self):
        with self.assertRaisesRegex(ValueError, "空间不足|超出"):
            allocate_vlsm(parse_network("192.168.1.0/30"), [2, 2, 2])

    def test_host_requirements_accept_chinese_comma_and_newline(self):
        self.assertEqual(parse_host_requirements("100，50\n20"), [100, 50, 20])


if __name__ == "__main__":
    unittest.main()
