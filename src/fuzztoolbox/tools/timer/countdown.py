"""Monotonic-clock countdown state independent from the GUI."""
from __future__ import annotations

import math
import time
from typing import Callable


class CountdownTimer:
    def __init__(self, duration: float = 300, clock: Callable[[], float] | None = None):
        if duration <= 0:
            raise ValueError("计时时长必须大于 0")
        self.clock = clock or time.monotonic
        self.duration = float(duration)
        self._remaining = float(duration)
        self._deadline: float | None = None
        self.state = "idle"

    @property
    def remaining(self) -> float:
        if self.state != "running" or self._deadline is None:
            return self._remaining
        value = max(0.0, self._deadline - self.clock())
        if value <= 0:
            self._remaining = 0.0
            self._deadline = None
            self.state = "finished"
        return value

    @property
    def progress(self) -> float:
        if self.duration <= 0:
            return 0.0
        return min(1.0, max(0.0, 1.0 - self.remaining / self.duration))

    def set_duration(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("计时时长不能小于 0")
        if self.state in ("running", "paused"):
            raise RuntimeError("计时过程中不能修改时长")
        self.duration = float(seconds)
        self._remaining = float(seconds)
        self._deadline = None
        self.state = "idle"

    def start(self) -> None:
        if self._remaining <= 0:
            raise ValueError("计时时长必须大于 0")
        if self.state not in ("idle", "finished"):
            return
        if self.state == "finished":
            self._remaining = self.duration
        self._deadline = self.clock() + self._remaining
        self.state = "running"

    def pause(self) -> None:
        if self.state != "running":
            return
        self._remaining = self.remaining
        if self.state == "finished":
            return
        self._deadline = None
        self.state = "paused"

    def resume(self) -> None:
        if self.state != "paused":
            return
        self._deadline = self.clock() + self._remaining
        self.state = "running"

    def reset(self) -> None:
        self._remaining = self.duration
        self._deadline = None
        self.state = "idle"


class StopwatchTimer:
    """A monotonic stopwatch with pause and resume support."""

    def __init__(self, clock: Callable[[], float] | None = None):
        self.clock = clock or time.monotonic
        self._elapsed = 0.0
        self._started_at: float | None = None
        self.state = "idle"

    @property
    def elapsed(self) -> float:
        if self.state == "running" and self._started_at is not None:
            return self._elapsed + max(0.0, self.clock() - self._started_at)
        return self._elapsed

    def start(self) -> None:
        if self.state != "idle":
            return
        self._started_at = self.clock()
        self.state = "running"

    def pause(self) -> None:
        if self.state != "running":
            return
        self._elapsed = self.elapsed
        self._started_at = None
        self.state = "paused"

    def resume(self) -> None:
        if self.state != "paused":
            return
        self._started_at = self.clock()
        self.state = "running"

    def reset(self) -> None:
        self._elapsed = 0.0
        self._started_at = None
        self.state = "idle"


def format_duration(seconds: float) -> str:
    total_ms = max(0, math.ceil(seconds * 1000 - 1e-9))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
