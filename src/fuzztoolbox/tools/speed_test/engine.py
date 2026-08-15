"""HTTP-based network speed measurement with no third-party dependency."""

from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..ip_lookup.service import _ssl_context

DOWNLOAD_URL = "https://speed.cloudflare.com/__down"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
USER_AGENT = "FuzzToolBox/2.1 Network-Speed-Test"


class SpeedTestCancelled(RuntimeError):
    """Raised when a running measurement is cancelled."""


@dataclass(frozen=True)
class SpeedTestResult:
    latency_ms: float
    jitter_ms: float
    download_mbps: float
    upload_mbps: float
    downloaded_bytes: int
    uploaded_bytes: int
    duration_seconds: float


ProgressCallback = Callable[[str, float, float], None]


class HttpTransport:
    """Small urllib transport kept separate for deterministic engine tests."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        # Reuse the packaged-app-aware certificate store used by IP lookup.
        self.context = _ssl_context()

    def download(self, size: int) -> tuple[int, float]:
        url = f"{DOWNLOAD_URL}?{urlencode({'bytes': size, 'cache': time.time_ns()})}"
        request = Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
        started = time.perf_counter()
        received = 0
        with urlopen(request, timeout=self.timeout, context=self.context) as response:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
        return received, max(time.perf_counter() - started, 1e-6)

    def upload(self, size: int) -> tuple[int, float]:
        body = b"0" * size
        request = Request(
            UPLOAD_URL,
            data=body,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/octet-stream",
                "Cache-Control": "no-cache",
            },
        )
        started = time.perf_counter()
        with urlopen(request, timeout=self.timeout, context=self.context) as response:
            response.read(1024)
        return size, max(time.perf_counter() - started, 1e-6)


class SpeedTestEngine:
    """Measure latency, jitter and sustained HTTP transfer throughput."""

    def __init__(self, transport=None, parallelism: int = 4):
        self.transport = transport or HttpTransport()
        self.parallelism = max(1, min(int(parallelism), 8))
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise SpeedTestCancelled("测速已停止")

    def _emit(
        self,
        callback: Optional[ProgressCallback],  # noqa: UP045 -- Python 3.9 support
        phase: str,
        progress: float,
        value: float = 0.0,
    ) -> None:
        if callback is not None:
            callback(phase, max(0.0, min(progress, 1.0)), value)

    def _latency(
        self, callback: Optional[ProgressCallback]  # noqa: UP045 -- Python 3.9 support
    ) -> tuple[float, float, int]:
        samples = []
        transferred = 0
        # First request warms DNS, TLS and the connection path; it is not scored.
        self.transport.download(1)
        for index in range(8):
            self._check_cancelled()
            count, elapsed = self.transport.download(1)
            transferred += count
            samples.append(elapsed * 1000.0)
            self._emit(callback, "latency", (index + 1) / 8, samples[-1])
        ordered = sorted(samples)
        trimmed = ordered[1:-1] if len(ordered) > 4 else ordered
        latency = statistics.median(trimmed)
        jitter = statistics.mean(
            abs(right - left) for left, right in zip(trimmed, trimmed[1:])
        ) if len(trimmed) > 1 else 0.0
        return latency, jitter, transferred

    def _throughput(
        self,
        method: str,
        sizes: tuple[int, ...],
        callback: Optional[ProgressCallback],  # noqa: UP045 -- Python 3.9 support
    ) -> tuple[float, int]:
        operation = getattr(self.transport, method)
        total_expected = sum(sizes)
        completed_bytes = 0
        total_elapsed = 0.0
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.parallelism) as executor:
            futures = [executor.submit(operation, size) for size in sizes]
            for future in as_completed(futures):
                self._check_cancelled()
                count, elapsed = future.result()
                completed_bytes += count
                total_elapsed += elapsed
                wall_elapsed = max(time.perf_counter() - started, 1e-6)
                current = completed_bytes * 8 / wall_elapsed / 1_000_000
                self._emit(callback, method, completed_bytes / total_expected, current)
        # Parallel requests overlap, so wall-clock duration is the meaningful denominator.
        wall_elapsed = max(time.perf_counter() - started, 1e-6)
        return completed_bytes * 8 / wall_elapsed / 1_000_000, completed_bytes

    def _transfer_plan(self, method: str) -> tuple[tuple[int, ...], int]:
        """Probe once, then target roughly 1.5 seconds of parallel transfer."""
        self._check_cancelled()
        probe_size = 1_000_000 if method == "download" else 500_000
        count, elapsed = getattr(self.transport, method)(probe_size)
        estimated_bytes_per_second = count / max(elapsed, 1e-6)
        per_stream = round(estimated_bytes_per_second * 1.5 / self.parallelism)
        minimum = 2_000_000 if method == "download" else 1_000_000
        maximum = 20_000_000 if method == "download" else 8_000_000
        per_stream = max(minimum, min(per_stream, maximum))
        return (per_stream,) * self.parallelism, count

    def run(
        self,
        callback: Optional[ProgressCallback] = None,  # noqa: UP045 -- Python 3.9 support
    ) -> SpeedTestResult:
        self._cancelled.clear()
        started = time.perf_counter()
        latency, jitter, latency_bytes = self._latency(callback)
        self._check_cancelled()
        download_plan, download_probe = self._transfer_plan("download")
        download, downloaded = self._throughput("download", download_plan, callback)
        self._check_cancelled()
        upload_plan, upload_probe = self._transfer_plan("upload")
        upload, uploaded = self._throughput("upload", upload_plan, callback)
        self._emit(callback, "complete", 1.0, 0.0)
        return SpeedTestResult(
            latency_ms=latency,
            jitter_ms=jitter,
            download_mbps=download,
            upload_mbps=upload,
            downloaded_bytes=downloaded + download_probe + latency_bytes,
            uploaded_bytes=uploaded + upload_probe,
            duration_seconds=time.perf_counter() - started,
        )
