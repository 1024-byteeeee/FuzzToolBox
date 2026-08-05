import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from ip_scanner.engine import ScanCancelled, Scanner
from ip_scanner.models import ScanConfig, ScanResult
from ip_scanner.network_info import NetworkInfo
from ip_scanner.targets import parse_target


class EngineTests(unittest.IsolatedAsyncioTestCase):
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
        scanner._is_private_tunnel_route = AsyncMock(return_value=True)

        async def connect_port(_ip, port, _stability_timeout):
            return port == 25224

        scanner._connect_port = connect_port
        result = await scanner._tcp_probe("10.2.2.2")
        self.assertTrue(result.is_alive)
        self.assertEqual(result.open_ports, [25224])

    async def test_tcp_rejects_tunnel_that_accepts_every_port(self):
        scanner = Scanner(ScanConfig(method="tcp", ports=[22, 80], timeout=0.05, concurrency=1))
        scanner._is_private_tunnel_route = AsyncMock(return_value=True)
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

    async def test_private_tunnel_route_is_rejected(self):
        scanner = Scanner(ScanConfig())
        scanner._run_command = AsyncMock(
            return_value=(0, b"   route to: 192.168.2.1\n  interface: utun6\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Darwin"):
            self.assertTrue(await scanner._is_private_tunnel_route("192.168.2.1"))

    async def test_private_physical_route_is_allowed(self):
        scanner = Scanner(ScanConfig())
        scanner._run_command = AsyncMock(
            return_value=(0, b" route to: 172.16.1.1\ninterface: en0\n")
        )
        with patch("ip_scanner.engine.platform.system", return_value="Darwin"):
            self.assertFalse(await scanner._is_private_tunnel_route("172.16.1.1"))

    def test_hostname_parser_handles_macos_cache(self):
        output = "name: printer.local\nip_address: 172.16.1.20\n"
        self.assertEqual(
            Scanner._parse_hostname(output, "172.16.1.20"),
            "printer.local",
        )

    def test_hostname_parser_handles_reverse_dns(self):
        self.assertEqual(
            Scanner._parse_hostname("router.example.net.\n", "203.0.113.1"),
            "router.example.net",
        )

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

    async def test_local_host_is_not_excluded_when_ping_is_blocked(self):
        local = NetworkInfo("Ethernet", "192.168.1.20", 24, mac="AA:BB:CC:DD:EE:FF")
        scanner = Scanner(
            ScanConfig(method="ping", resolve_hostname=True, include_dead=True),
            local,
        )
        scanner._ping_probe = AsyncMock(
            return_value=ScanResult(ip=local.ip, is_alive=False, method="ping")
        )
        with patch("ip_scanner.engine.socket.gethostname", return_value="my-computer.local"):
            result = await scanner._probe(local.ip)
        self.assertTrue(result.is_alive)
        self.assertEqual(result.mac, local.mac)
        self.assertEqual(result.hostname, "my-computer.local")
        self.assertEqual(result.response_time_ms, 0.0)

    async def test_local_host_is_online_even_without_requested_tcp_port(self):
        local = NetworkInfo("en0", "10.0.0.5", 24)
        scanner = Scanner(ScanConfig(method="tcp", ports=[65535]), local)
        scanner._tcp_probe = AsyncMock(
            return_value=ScanResult(ip=local.ip, is_alive=False, method="tcp")
        )
        result = await scanner._probe(local.ip)
        self.assertTrue(result.is_alive)
        self.assertEqual(result.open_ports, [])


if __name__ == "__main__":
    unittest.main()
