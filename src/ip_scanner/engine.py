import asyncio
import contextlib
import ipaddress
import platform
import re
import socket
import time
from typing import Awaitable, Callable, List, Optional

from .models import ScanConfig, ScanProgress, ScanResult
from .targets import TargetRange


ResultCallback = Callable[[List[ScanResult]], None]
ProgressCallback = Callable[[ScanProgress], None]


class ScanCancelled(Exception):
    pass


class Scanner:
    """Bounded producer/consumer scanner; memory use is independent of target size."""

    def __init__(self, config: ScanConfig):
        config.validate()
        self.config = config
        self._cancelled = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    async def scan(
        self,
        targets: TargetRange,
        on_results: Optional[ResultCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        batch_size: int = 100,
    ) -> List[ScanResult]:
        started = time.monotonic()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.config.concurrency * 2)
        result_queue: asyncio.Queue = asyncio.Queue()
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
            last = await (self._tcp_probe(ip) if self.config.method == "tcp" else self._ping_probe(ip))
            if last.is_alive:
                last.mac = await self._lookup_mac(ip)
                if self.config.resolve_hostname:
                    last.hostname = await self._resolve_hostname(ip)
                return last
            if attempt < self.config.retries:
                await asyncio.sleep(0.05)
        return last or ScanResult(ip=ip, is_alive=False, method=self.config.method)

    async def _tcp_probe(self, ip: str) -> ScanResult:
        started = time.monotonic()
        tunnel_route = await self._is_private_tunnel_route(ip)
        controls = []
        if tunnel_route:
            controls = [port for port in (65534, 65533, 65532) if port not in self.config.ports][:2]
        stability_timeout = 4.0 if tunnel_route else min(0.15, self.config.timeout)
        ports_to_check = list(self.config.ports) + controls
        all_checks = await asyncio.gather(
            *(self._connect_port(ip, port, stability_timeout) for port in ports_to_check)
        )
        checks = all_checks[: len(self.config.ports)]
        open_ports = [port for port, is_open in zip(self.config.ports, checks) if is_open]

        # TUN-style transparent proxies may accept every TCP connection locally.
        # Probe two unused high ports as controls; if both are also accepted, the
        # apparent result is interception rather than evidence of target ports.
        intercepted = False
        if open_ports and tunnel_route:
            control_results = all_checks[len(self.config.ports) :]
            intercepted = bool(control_results) and all(control_results)
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

    async def _connect_port(self, ip: str, port: int, stability_timeout: float) -> bool:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=self.config.timeout
            )
            # A transparent proxy often accepts and immediately closes a fake
            # connection. A banner or a connection that remains open is genuine.
            try:
                data = await asyncio.wait_for(
                    reader.read(1), timeout=stability_timeout
                )
                return bool(data)
            except asyncio.TimeoutError:
                return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def _ping_probe(self, ip: str) -> ScanResult:
        system = platform.system()
        timeout_ms = max(1, int(self.config.timeout * 1000))
        if system == "Windows":
            args = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        elif system == "Darwin":
            args = ["/sbin/ping", "-n", "-c", "1", "-W", str(timeout_ms), ip]
        else:
            args = ["ping", "-n", "-c", "1", "-W", str(max(1, int(self.config.timeout))), ip]
        started = time.monotonic()
        command_result = await self._run_command(args, self.config.timeout + 0.5)
        if command_result is None:
            return ScanResult(ip=ip, is_alive=False, method="ping", error="ping timeout")
        return_code, stdout = command_result
        alive = return_code == 0
        text = stdout.decode(errors="ignore")
        match = re.search(r"time[=<]([0-9.]+)\s*ms", text, re.IGNORECASE)
        measured = float(match.group(1)) if match else (time.monotonic() - started) * 1000
        return ScanResult(
            ip=ip,
            is_alive=alive,
            method="ping",
            response_time_ms=round(measured, 2) if alive else None,
        )

    async def _resolve_hostname(self, ip: str) -> Optional[str]:
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(loop.run_in_executor(None, socket.gethostbyaddr, ip), 1.0)
            hostname = result[0].rstrip(".")
            if hostname and hostname != ip:
                return hostname
        except (asyncio.TimeoutError, OSError):
            pass

        # System resolvers may know DHCP/mDNS names that Python's resolver misses.
        system = platform.system()
        commands = []
        if system == "Darwin":
            commands = [
                ["/usr/bin/dscacheutil", "-q", "host", "-a", "ip_address", ip],
                ["/usr/bin/dig", "+short", "-x", ip],
            ]
        elif system == "Windows":
            commands = [["nslookup", ip]]
        else:
            commands = [["getent", "hosts", ip], ["host", ip]]
        for command in commands:
            command_result = await self._run_command(command, timeout=1.0)
            if command_result is None:
                continue
            return_code, stdout = command_result
            if return_code != 0:
                continue
            hostname = self._parse_hostname(stdout.decode(errors="ignore"), ip)
            if hostname:
                return hostname
        return None

    @staticmethod
    def _parse_hostname(text: str, ip: str) -> Optional[str]:
        patterns = [
            r"(?im)^\s*name:\s*(\S+)",
            r"(?im)^\s*name\s*=\s*(\S+)",
            r"(?im)domain name pointer\s+(\S+)",
            r"(?im)^\s*" + re.escape(ip) + r"\s+(\S+)",
            r"(?m)^\s*([A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9._-]+)\.?\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                hostname = match.group(1).rstrip(".")
                if hostname not in {ip, "localhost"}:
                    return hostname
        return None

    async def _lookup_mac(self, ip: str) -> Optional[str]:
        system = platform.system()
        if system == "Windows":
            args = ["arp", "-a", ip]
        elif system == "Darwin":
            args = ["/usr/sbin/arp", "-n", ip]
        else:
            args = ["ip", "neigh", "show", ip]
        command_result = await self._run_command(args, timeout=0.8)
        if command_result is None:
            return None
        _, stdout = command_result
        return self._parse_mac(stdout.decode(errors="ignore"))

    @staticmethod
    async def _run_command(args: List[str], timeout: float):
        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
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

    async def _is_private_tunnel_route(self, ip: str) -> bool:
        address = ipaddress.IPv4Address(ip)
        if not address.is_private or address.is_loopback:
            return False
        system = platform.system()
        if system == "Darwin":
            command = ["/sbin/route", "-n", "get", ip]
        elif system == "Linux":
            command = ["ip", "route", "get", ip]
        else:
            return False
        result = await self._run_command(command, timeout=0.8)
        if result is None:
            return False
        _, stdout = result
        text = stdout.decode(errors="ignore")
        if system == "Darwin":
            match = re.search(r"^\s*interface:\s*(\S+)", text, re.MULTILINE)
        else:
            match = re.search(r"\bdev\s+(\S+)", text)
        if not match:
            return False
        interface = match.group(1).lower()
        return interface.startswith(("utun", "tun", "tap", "wg"))
