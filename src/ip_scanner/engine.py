import asyncio
import contextlib
import ipaddress
import locale
import platform
import re
import socket
import subprocess
import time
from typing import Callable, List, Optional

from .models import ScanConfig, ScanProgress, ScanResult
from .network_info import NetworkInfo
from .targets import TargetRange


ResultCallback = Callable[[List[ScanResult]], None]
ProgressCallback = Callable[[ScanProgress], None]


class ScanCancelled(Exception):
    pass


class Scanner:
    """Bounded producer/consumer scanner; memory use is independent of target size."""

    def __init__(self, config: ScanConfig, network_info: Optional[NetworkInfo] = None):
        config.validate()
        self.config = config
        self.network_info = network_info or NetworkInfo()
        self._cancelled = asyncio.Event()
        self._port_semaphore = asyncio.Semaphore(max(32, min(config.concurrency * 4, 256)))
        # System resolvers may use blocking OS APIs internally. Keep their concurrency
        # bounded so a slow DNS server cannot exhaust the process-wide thread pool.
        self._hostname_semaphore = asyncio.Semaphore(min(config.concurrency, 32))

    def cancel(self) -> None:
        self._cancelled.set()

    async def scan(
        self,
        targets: TargetRange,
        on_results: Optional[ResultCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        batch_size: int = 100,
        retain_results: bool = True,
    ) -> List[ScanResult]:
        started = time.monotonic()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.concurrency * 2)
        result_queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.concurrency * 2)
        sentinel = object()

        async def producer() -> None:
            for ip in targets:
                if self._cancelled.is_set():
                    break
                await queue.put(ip)
            for _ in range(self.config.concurrency):
                await queue.put(sentinel)

        async def worker() -> None:
            while True:
                item = await queue.get()
                try:
                    if item is sentinel:
                        return
                    try:
                        result = await self._probe(str(item))
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        # One OS/network failure must not kill a worker and leave the
                        # coordinator waiting forever.
                        result = ScanResult(
                            ip=str(item),
                            is_alive=False,
                            method=self.config.method,
                            error=str(exc),
                        )
                    await result_queue.put(result)
                finally:
                    queue.task_done()

        producer_task = asyncio.create_task(producer())
        workers = [asyncio.create_task(worker()) for _ in range(self.config.concurrency)]
        scanned = alive = finished_workers = 0
        retained: List[ScanResult] = []
        batch: List[ScanResult] = []

        async def watch_worker(task: asyncio.Task) -> None:
            nonlocal finished_workers
            try:
                await task
            finally:
                finished_workers += 1

        watchers = [asyncio.create_task(watch_worker(task)) for task in workers]
        try:
            while finished_workers < len(workers) or not result_queue.empty():
                if self._cancelled.is_set():
                    raise ScanCancelled()
                try:
                    result = await asyncio.wait_for(result_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Flush partial batches on a timer so small/slow scans also update live.
                    if batch and on_results:
                        on_results(batch[:])
                        batch.clear()
                    if on_progress:
                        on_progress(ScanProgress(scanned, targets.total, alive, time.monotonic() - started))
                    continue
                scanned += 1
                if result.is_alive:
                    alive += 1
                if result.is_alive or self.config.include_dead:
                    if retain_results:
                        retained.append(result)
                    batch.append(result)
                if len(batch) >= batch_size and on_results:
                    on_results(batch[:])
                    batch.clear()
                if on_progress and (scanned % 50 == 0 or scanned == targets.total):
                    on_progress(ScanProgress(scanned, targets.total, alive, time.monotonic() - started))
            if batch and on_results:
                on_results(batch[:])
            if on_progress:
                on_progress(ScanProgress(scanned, targets.total, alive, time.monotonic() - started))
            if self._cancelled.is_set():
                raise ScanCancelled()
            return retained
        finally:
            if not producer_task.done():
                producer_task.cancel()
            for task in workers + watchers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(producer_task, *workers, *watchers, return_exceptions=True)

    async def _probe(self, ip: str) -> ScanResult:
        last = None
        for attempt in range(self.config.retries + 1):
            if self._cancelled.is_set():
                return ScanResult(ip=ip, is_alive=False, method=self.config.method, error="cancelled")
            if self.config.method == "tcp":
                last = await self._tcp_probe(ip)
            else:
                # Keep the first pass fast. Only addresses that fail are retried
                # with progressively longer waits, which also gives ARP/ND caches
                # and sleeping Wi-Fi clients time to become ready.
                probe_timeout = min(self.config.timeout * (2**attempt), 2.0)
                last = await self._ping_probe(ip, probe_timeout)
            if last.is_alive:
                last.mac = await self._lookup_mac(ip)
                if self.config.resolve_hostname:
                    last.hostname = await self._resolve_hostname(ip)
                return last
            if attempt < self.config.retries:
                await asyncio.sleep(0.15 * (attempt + 1))
        return last or ScanResult(ip=ip, is_alive=False, method=self.config.method)

    async def _tcp_probe(self, ip: str) -> ScanResult:
        started = time.monotonic()
        stability_timeout = min(0.2, self.config.timeout)
        checks = await self._check_ports(ip, self.config.ports, stability_timeout)
        open_ports = [port for port, is_open in zip(self.config.ports, checks) if is_open]

        intercepted = False
        if open_ports:
            controls = []
            control_port = 65535
            while len(controls) < 3 and control_port > 0:
                if control_port not in self.config.ports:
                    controls.append(control_port)
                control_port -= 131
            control_results = await self._check_ports(ip, controls, stability_timeout)
            intercepted = len(control_results) == 3 and all(control_results)
            if intercepted:
                open_ports = []

        elapsed = (time.monotonic() - started) * 1000
        return ScanResult(
            ip=ip,
            is_alive=bool(open_ports),
            method="tcp",
            response_time_ms=round(elapsed, 2) if open_ports else None,
            open_ports=open_ports,
            error="transparent TCP interception detected" if intercepted else None,
        )

    async def _check_ports(
        self, ip: str, ports: List[int], stability_timeout: float, batch_size: int = 64
    ) -> List[bool]:
        results = []
        for start in range(0, len(ports), batch_size):
            if self._cancelled.is_set():
                raise asyncio.CancelledError()
            batch = ports[start : start + batch_size]
            results.extend(
                await asyncio.gather(
                    *(self._bounded_connect_port(ip, port, stability_timeout) for port in batch)
                )
            )
        return results

    async def _bounded_connect_port(self, ip: str, port: int, stability_timeout: float) -> bool:
        async with self._port_semaphore:
            return await self._connect_port(ip, port, stability_timeout)

    async def _connect_port(self, ip: str, port: int, stability_timeout: float) -> bool:
        writer = None
        try:
            local_addr = (
                (self.network_info.ip, 0)
                if self.network_info.ip and self._is_on_link(ip)
                else None
            )
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, local_addr=local_addr),
                timeout=self.config.timeout,
            )
            # A completed TCP handshake is sufficient evidence that the port is
            # open. Transparent proxies are detected separately with controls.
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.5)

    async def _ping_probe(self, ip: str, timeout: Optional[float] = None) -> ScanResult:
        system = platform.system()
        effective_timeout = self.config.timeout if timeout is None else timeout
        timeout_ms = max(1, int(effective_timeout * 1000))
        source_ip = self.network_info.ip if self._is_on_link(ip) else None
        if system == "Windows":
            args = ["ping", "-n", "1", "-w", str(timeout_ms)]
            if source_ip:
                args.extend(["-S", source_ip])
            args.append(ip)
        elif system == "Darwin":
            args = ["/sbin/ping", "-n", "-c", "1", "-W", str(timeout_ms)]
            if source_ip:
                args.extend(["-S", source_ip])
            args.append(ip)
        else:
            return ScanResult(
                ip=ip,
                is_alive=False,
                method="ping",
                error=f"unsupported operating system: {system}",
            )
        command_result = await self._run_command(args, effective_timeout + 0.5)
        if command_result is None:
            return ScanResult(ip=ip, is_alive=False, method="ping", error="ping timeout")
        return_code, stdout = command_result
        text = stdout.decode(errors="ignore")
        alive = return_code == 0 and self._has_echo_reply(text, ip)
        measured = self._parse_ping_time(text, ip) if alive else None
        return ScanResult(
            ip=ip,
            is_alive=alive,
            method="ping",
            response_time_ms=round(measured, 2) if measured is not None else None,
            error=None if alive else "no echo reply from target",
        )

    @staticmethod
    def _has_echo_reply(text: str, ip: str) -> bool:
        address = re.escape(ip)
        ip_pattern = re.compile(rf"(?<![\d.]){address}(?![\d.])")
        ttl_pattern = re.compile(r"\bttl\s*[=:]\s*\d+", re.IGNORECASE)
        return any(ip_pattern.search(line) and ttl_pattern.search(line) for line in text.splitlines())

    @staticmethod
    def _parse_ping_time(text: str, ip: str) -> Optional[float]:
        """Extract network RTT only, never subprocess startup/teardown time."""
        address = re.escape(ip)
        ip_pattern = re.compile(rf"(?<![\d.]){address}(?![\d.])")
        ttl_pattern = re.compile(r"\bttl\s*[=:]\s*\d+", re.IGNORECASE)
        # The label before the comparator is localized on some Windows systems.
        # Matching the comparator + value + ms sequence works across those locales.
        time_pattern = re.compile(r"([=<＝＜])\s*([0-9]+(?:[.,][0-9]+)?)\s*ms\b", re.IGNORECASE)
        for line in text.splitlines():
            if not (ip_pattern.search(line) and ttl_pattern.search(line)):
                continue
            match = time_pattern.search(line)
            if not match:
                continue
            value = float(match.group(2).replace(",", "."))
            # Ping reports sub-millisecond RTT as "<1ms" without the exact value.
            return value / 2 if match.group(1) in {"<", "＜"} else value
        return None

    def _is_on_link(self, ip: str) -> bool:
        if not self.network_info.ip or self.network_info.prefix_length is None:
            return False
        try:
            network = ipaddress.IPv4Network(
                f"{self.network_info.ip}/{self.network_info.prefix_length}", strict=False
            )
            return ipaddress.IPv4Address(ip) in network
        except (ipaddress.AddressValueError, ValueError):
            return False

    async def _resolve_hostname(self, ip: str) -> Optional[str]:
        # gethostbyaddr uses the native resolver stack on every supported platform
        # (DNS, hosts file and platform-specific local name services). Bound and time
        # limit it, then fall back to cancellable platform tools for broader LAN support.
        async with self._hostname_semaphore:
            try:
                resolved = await asyncio.wait_for(
                    asyncio.to_thread(socket.gethostbyaddr, ip), timeout=2.0
                )
                hostname = self._clean_hostname(resolved[0], ip)
                if hostname:
                    return hostname
            except (asyncio.TimeoutError, OSError, socket.herror, socket.gaierror):
                pass

        system = platform.system()
        commands = []
        if system == "Darwin":
            commands = [
                ["/usr/bin/dscacheutil", "-q", "host", "-a", "ip_address", ip],
                ["/usr/bin/dig", "+short", "-x", ip],
                ["/usr/bin/host", ip],
            ]
        elif system == "Windows":
            commands = [
                ["ping", "-a", "-n", "1", "-w", "1000", ip],
                ["nbtstat", "-A", ip],
                ["nslookup", ip],
            ]
        else:
            return None
        command_timeout = 1.8 if system == "Windows" else 1.0
        for command in commands:
            command_result = await self._run_command(command, timeout=command_timeout)
            if command_result is None:
                continue
            return_code, stdout = command_result
            if return_code != 0:
                continue
            hostname = self._parse_hostname(self._decode_command_output(stdout), ip)
            if hostname:
                return hostname
        return None

    @staticmethod
    def _decode_command_output(value: bytes) -> str:
        encodings = (
            ("oem", locale.getpreferredencoding(False), "utf-8")
            if platform.system() == "Windows"
            else ("utf-8", locale.getpreferredencoding(False))
        )
        for encoding in dict.fromkeys(encodings):
            try:
                return value.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return value.decode(errors="ignore")

    @staticmethod
    def _clean_hostname(value: str, ip: str) -> Optional[str]:
        hostname = value.strip().rstrip(".")
        if not hostname or hostname.casefold() == "localhost" or hostname == ip:
            return None
        # Reject status fields accidentally captured from localized ping output,
        # such as "bytes=32" / "字节=32". Hostnames cannot contain these delimiters.
        if (
            len(hostname) > 253
            or not (hostname[0].isalnum() or hostname[0] == "_")
            or any(not (character.isalnum() or character in "._-") for character in hostname)
        ):
            return None
        try:
            ipaddress.ip_address(hostname)
            return None
        except ValueError:
            return hostname

    @staticmethod
    def _parse_hostname(text: str, ip: str) -> Optional[str]:
        patterns = [
            r"(?im)^\s*name:\s*(\S+)",
            r"(?im)^\s*name\s*=\s*(\S+)",
            r"(?im)^\s*名称\s*[:：]\s*(\S+)",
            r"(?im)domain name pointer\s+(\S+)",
            r"(?im)^\s*[^\r\n\[]*?([^\s\[\]=:]+)\s+\["
            + re.escape(ip)
            + r"\]",
            r"(?im)^\s*(\S+)\s+<00>\s+",
            r"(?im)^" + re.escape(ip) + r"\s*:\s*(\S+)",
            r"(?m)^\s*([A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9._-]+)\.?\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                hostname = Scanner._clean_hostname(match.group(1), ip)
                if hostname:
                    return hostname
        return None

    async def _lookup_mac(self, ip: str) -> Optional[str]:
        system = platform.system()
        if system == "Windows":
            args = ["arp", "-a", ip]
        elif system == "Darwin":
            args = ["/usr/sbin/arp", "-n", ip]
        else:
            return None
        command_result = await self._run_command(args, timeout=0.8)
        if command_result is None:
            return None
        _, stdout = command_result
        return self._parse_mac(stdout.decode(errors="ignore"))

    @staticmethod
    async def _run_command(args: List[str], timeout: float):
        try:
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                if platform.system() == "Windows"
                else 0
            )
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except (FileNotFoundError, OSError):
            return None
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return process.returncode, stdout
        except asyncio.TimeoutError:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=0.5)
            return None
        except asyncio.CancelledError:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=0.5)
            raise
        finally:
            transport = getattr(process, "_transport", None)
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.close()

    @staticmethod
    def _parse_mac(text: str) -> Optional[str]:
        match = re.search(r"(?i)\b(?:[0-9a-f]{1,2}[:-]){5}[0-9a-f]{1,2}\b", text)
        if not match:
            return None
        parts = re.split("[:-]", match.group(0))
        return ":".join(f"{int(part, 16):02X}" for part in parts)
