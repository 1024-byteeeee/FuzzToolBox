import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from ip_scanner.engine import ScanCancelled, Scanner
from ip_scanner.models import ScanConfig, ScanResult
from ip_scanner.network_info import NetworkInfo
from ip_scanner.targets import parse_target


class EngineTests(unittest.IsolatedAsyncioTestCase):
    def test_excessive_concurrency_is_rejected(self):
        with self.assertRaises(ValueError):
            ScanConfig(concurrency=513).validate()

    async def test_alive_result_and_progress(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=[80], timeout=0.2, concurrency=2))
        scanner._probe = AsyncMock(
            side_effect=lambda ip: ScanResult(ip=ip, is_alive=True, method="tcp", open_ports=[80])
        )
        progress = []
        results = await scanner.scan(parse_target("127.0.0.1-127.0.0.2"), on_progress=progress.append)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.is_alive for result in results))
        self.assertEqual(progress[-1].scanned, 2)
        self.assertEqual(progress[-1].alive, 2)

    async def test_dead_results_not_retained_by_default(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=[1], timeout=0.05, concurrency=1))
        scanner._probe = AsyncMock(
            return_value=ScanResult(ip="127.0.0.1", is_alive=False, method="tcp")
        )
        self.assertEqual(await scanner.scan(parse_target("127.0.0.1")), [])

    async def test_dead_results_are_emitted_when_requested(self):
        scanner = Scanner(
            ScanConfig(method="tcp", ports=[1], timeout=0.05, concurrency=1, include_dead=True)
        )
        scanner._probe = AsyncMock(
            return_value=ScanResult(ip="127.0.0.1", is_alive=False, method="tcp")
        )
        batches = []
        results = await scanner.scan(parse_target("127.0.0.1"), on_results=batches.extend)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(batches), 1)
        self.assertFalse(batches[0].is_alive)

    async def test_tcp_finds_real_port_even_when_routed_through_tunnel(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=[25224], timeout=0.05, concurrency=1))

        async def connect_port(_ip, port, _stability_timeout):
            return port == 25224

        scanner._connect_port = connect_port
        result = await scanner._tcp_probe("10.2.2.2")
        self.assertTrue(result.is_alive)
        self.assertEqual(result.open_ports, [25224])

    async def test_tcp_rejects_tunnel_that_accepts_every_port(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=[22, 80], timeout=0.05, concurrency=1))
        scanner._connect_port = AsyncMock(return_value=True)
        result = await scanner._tcp_probe("192.168.2.1")
        self.assertFalse(result.is_alive)
        self.assertEqual(result.open_ports, [])
        self.assertIn("interception", result.error)

    def test_mac_parser(self):
        output = "? (192.168.1.1) at aa:bb:cc:12:34:56 on en0 ifscope [ethernet]"
        self.assertEqual(Scanner._parse_mac(output), "AA:BB:CC:12:34:56")

    def test_mac_parser_accepts_single_digit_octets(self):
        output = "? (224.0.0.251) at 1:0:5e:0:0:fb on en0"
        self.assertEqual(Scanner._parse_mac(output), "01:00:5E:00:00:FB")

    def test_hostname_validation_rejects_ping_status(self):
        self.assertIsNone(Scanner._clean_hostname("=32", "192.168.1.20"))

    async def test_hostname_stops_after_reverse_dns(self):
        scanner = Scanner(ScanConfig())
        with patch("ip_scanner.engine.reverse_dns", return_value="printer.local") as dns, patch(
            "ip_scanner.engine.multicast_dns"
        ) as mdns, patch("ip_scanner.engine.netbios_name") as netbios:
            self.assertEqual(await scanner._resolve_hostname("192.168.1.20"), "printer.local")
        dns.assert_called_once_with("192.168.1.20")
        mdns.assert_not_called()
        netbios.assert_not_called()

    async def test_local_hostname_falls_back_to_mdns_then_netbios(self):
        scanner = Scanner(
            ScanConfig(), NetworkInfo(ip="192.168.1.10", prefix_length=24)
        )
        with patch("ip_scanner.engine.reverse_dns", return_value=None), patch(
            "ip_scanner.engine.multicast_dns", return_value=None
        ) as mdns, patch("ip_scanner.engine.netbios_name", return_value="OFFICE-PC") as netbios:
            self.assertEqual(await scanner._resolve_hostname("192.168.1.20"), "OFFICE-PC")
        mdns.assert_called_once_with("192.168.1.20", "192.168.1.10")
        netbios.assert_called_once_with("192.168.1.20", "192.168.1.10")

    async def test_remote_hostname_does_not_use_link_local_protocols(self):
        scanner = Scanner(ScanConfig(), NetworkInfo(ip="192.168.1.10", prefix_length=24))
        with patch("ip_scanner.engine.reverse_dns", return_value=None), patch(
            "ip_scanner.engine.multicast_dns"
        ) as mdns, patch("ip_scanner.engine.netbios_name") as netbios:
            self.assertIsNone(await scanner._resolve_hostname("203.0.113.20"))
        mdns.assert_not_called()
        netbios.assert_not_called()

    async def test_getmac_library_is_used_before_platform_commands(self):
        scanner = Scanner(ScanConfig())
        scanner._run_command = AsyncMock()
        with patch(
            "ip_scanner.engine.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value="aa-bb-cc-dd-ee-ff",
        ):
            self.assertEqual(await scanner._lookup_mac("192.168.1.20"), "AA:BB:CC:DD:EE:FF")
        scanner._run_command.assert_not_awaited()

    async def test_worker_exception_becomes_result_instead_of_hanging(self):
        scanner = Scanner(
            ScanConfig(method="ping", concurrency=2, include_dead=True)
        )
        scanner._probe = AsyncMock(side_effect=RuntimeError("probe failed"))
        results = await asyncio.wait_for(
            scanner.scan(parse_target("192.0.2.1-192.0.2.2")),
            timeout=0.5,
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.error == "probe failed" for result in results))

    async def test_cancel_interrupts_in_flight_workers(self):
        scanner = Scanner(
            ScanConfig(method="ping", concurrency=4, include_dead=True)
        )

        async def slow_probe(ip):
            await asyncio.sleep(10)
            return ScanResult(ip=ip, is_alive=False, method="ping")

        scanner._probe = slow_probe
        task = asyncio.create_task(scanner.scan(parse_target("192.0.2.1-192.0.2.20")))
        await asyncio.sleep(0.02)
        scanner.cancel()
        with self.assertRaises(ScanCancelled):
            await asyncio.wait_for(task, timeout=0.5)

    async def test_ping_retry_recovers_first_pass_miss(self):
        scanner = Scanner(
            ScanConfig(method="ping", retries=1, concurrency=1, include_dead=True)
        )
        scanner._ping_probe = AsyncMock(
            side_effect=[
                ScanResult(ip="192.168.1.20", is_alive=False, method="ping"),
                ScanResult(ip="192.168.1.20", is_alive=True, method="ping"),
            ]
        )
        scanner._lookup_mac = AsyncMock(return_value="AA:BB:CC:DD:EE:FF")
        result = await scanner._probe("192.168.1.20")
        self.assertTrue(result.is_alive)
        self.assertEqual(scanner._ping_probe.await_count, 2)
        self.assertEqual(scanner._ping_probe.await_args_list[0].args[1], 0.5)
        self.assertEqual(scanner._ping_probe.await_args_list[1].args[1], 1.0)

    async def test_ping_uses_three_adaptive_passes_before_offline(self):
        scanner = Scanner(
            ScanConfig(method="ping", timeout=0.5, retries=2, include_dead=True)
        )
        scanner._ping_probe = AsyncMock(
            return_value=ScanResult(ip="192.168.1.30", is_alive=False, method="ping")
        )
        with patch("ip_scanner.engine.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await scanner._probe("192.168.1.30")
        self.assertFalse(result.is_alive)
        self.assertEqual(
            [call.args[1] for call in scanner._ping_probe.await_args_list],
            [0.5, 1.0, 2.0],
        )
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [0.15, 0.3])

    async def test_any_target_is_only_online_after_a_successful_probe(self):
        scanner = Scanner(ScanConfig(method="ping", include_dead=True))
        scanner._ping_probe = AsyncMock(
            return_value=ScanResult(ip="192.168.1.20", is_alive=False, method="ping")
        )
        scanner._lookup_mac = AsyncMock()
        result = await scanner._probe("192.168.1.20")
        self.assertFalse(result.is_alive)
        scanner._lookup_mac.assert_not_awaited()

    async def test_windows_unreachable_reply_with_zero_exit_code_is_offline(self):
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5))
        scanner._run_command = AsyncMock(
            return_value=(
                0,
                b"Reply from 192.168.1.1: Destination host unreachable.\r\n",
            )
        )
        with patch("ip_scanner.engine.platform.system", return_value="Windows"):
            result = await scanner._ping_probe("192.168.1.99")
        self.assertFalse(result.is_alive)

    async def test_echo_reply_requires_target_ip_and_ttl(self):
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5))
        scanner._run_command = AsyncMock(
            return_value=(0, b"Reply from 192.168.1.99: bytes=32 time<1ms TTL=128\r\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Windows"):
            result = await scanner._ping_probe("192.168.1.99")
        self.assertTrue(result.is_alive)
        self.assertEqual(result.response_time_ms, 0.5)

    async def test_localized_ping_time_is_real_rtt_not_process_duration(self):
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5))
        scanner._run_command = AsyncMock(
            return_value=(0, "来自 192.168.1.99 的回复: 字节=32 时间=2,7ms TTL=128\r\n".encode())
        )
        with patch("ip_scanner.engine.platform.system", return_value="Windows"):
            result = await scanner._ping_probe("192.168.1.99")
        self.assertTrue(result.is_alive)
        self.assertEqual(result.response_time_ms, 2.7)

    async def test_unrecognized_ping_time_does_not_report_process_overhead(self):
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5))
        scanner._run_command = AsyncMock(
            return_value=(0, b"64 bytes from 192.168.1.99: ttl=64 latency unknown\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Darwin"):
            result = await scanner._ping_probe("192.168.1.99")
        self.assertTrue(result.is_alive)
        self.assertIsNone(result.response_time_ms)

    async def test_reply_from_different_ip_is_not_target_echo(self):
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5))
        scanner._run_command = AsyncMock(
            return_value=(0, b"64 bytes from 192.168.1.1: ttl=64 time=0.5 ms\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Darwin"):
            result = await scanner._ping_probe("192.168.1.10")
        self.assertFalse(result.is_alive)

    async def test_on_link_ping_binds_physical_source_address(self):
        network = NetworkInfo("en0", "192.168.1.20", 24)
        scanner = Scanner(ScanConfig(method="ping", timeout=0.5), network)
        scanner._run_command = AsyncMock(
            return_value=(0, b"64 bytes from 192.168.1.30: ttl=64 time=0.5 ms\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Darwin"):
            result = await scanner._ping_probe("192.168.1.30")
        self.assertTrue(result.is_alive)
        command = scanner._run_command.await_args.args[0]
        self.assertEqual(command[-3:], ["-S", "192.168.1.20", "192.168.1.30"])

    async def test_port_checks_have_a_global_concurrency_bound(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=list(range(1, 131)), concurrency=1))
        active = maximum = 0

        async def connect(_ip, _port, _timeout):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.001)
            active -= 1
            return False

        scanner._connect_port = connect
        results = await scanner._check_ports("192.0.2.1", scanner.config.ports, 0.05)
        self.assertEqual(len(results), 130)
        self.assertLessEqual(maximum, 32)


if __name__ == "__main__":
    unittest.main()
