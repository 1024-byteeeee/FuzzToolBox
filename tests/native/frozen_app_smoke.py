"""Verify frozen startup, visible-window readiness, and single-instance IPC."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

SERVER_NAME = "1024-byteeeee.FuzzToolBox"
RUNTIME_PROTOCOL_VERSION = 1


def resolve_application(path: Path) -> tuple[Path, Path]:
    """Return the executable and directory that owns the runtime lock."""
    application = path.resolve()
    if application.suffix == ".app":
        executable = application / "Contents" / "MacOS" / "FuzzToolBox"
        lock_root = application
    else:
        executable = application
        lock_root = application.parent
    if not executable.is_file():
        raise FileNotFoundError(f"Frozen application executable not found: {executable}")
    return executable, lock_root


def single_instance_lock_path(lock_root: Path) -> Path:
    digest = hashlib.sha256(SERVER_NAME.encode("utf-8")).hexdigest()[:20]
    return lock_root / f"fuzztoolbox-{digest}.lock"


def runtime_marker_path(lock_root: Path, marker: str) -> Path:
    digest = hashlib.sha256(SERVER_NAME.encode("utf-8")).hexdigest()[:20]
    return lock_root / f"fuzztoolbox-{digest}.{marker}.json"


def marker_matches(path: Path, *, pid: int, activation: bool = False) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    matches = bool(
        payload.get("protocol") == RUNTIME_PROTOCOL_VERSION
        and payload.get("pid") == pid
        and payload.get("window_visible") is True
    )
    if activation:
        return matches and isinstance(payload.get("sequence"), int) and (
            payload["sequence"] >= 1
        )
    return matches


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    description: str,
    process: subprocess.Popen[bytes] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                f"Frozen application exited while waiting for {description} "
                f"(code {process.returncode})"
            )
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(f"Timed out after {timeout:g}s waiting for {description}")


def stop_process(process: subprocess.Popen[bytes], timeout: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _read_log(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return content[-8_000:]


def smoke_test(
    application: Path,
    *,
    startup_timeout: float = 30.0,
    secondary_timeout: float = 12.0,
) -> None:
    executable, lock_root = resolve_application(application)
    lock_path = single_instance_lock_path(lock_root)
    ready_path = runtime_marker_path(lock_root, "ready")
    activation_path = runtime_marker_path(lock_root, "activation")
    pre_existing = [
        path for path in (lock_path, ready_path, activation_path) if path.exists()
    ]
    if pre_existing:
        paths = ", ".join(str(path) for path in pre_existing)
        raise RuntimeError(f"Refusing to start with pre-existing runtime files: {paths}")

    primary: subprocess.Popen[bytes] | None = None
    secondary: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="fuzztoolbox-frozen-smoke-") as temp_dir:
        primary_log_path = Path(temp_dir) / "primary.log"
        secondary_log_path = Path(temp_dir) / "secondary.log"
        try:
            with primary_log_path.open("wb") as primary_log:
                primary = subprocess.Popen(
                    [str(executable)],
                    stdin=subprocess.DEVNULL,
                    stdout=primary_log,
                    stderr=subprocess.STDOUT,
                )
            wait_until(
                lock_path.is_file,
                timeout=startup_timeout,
                description="the single-instance lock",
                process=primary,
            )
            wait_until(
                lambda: marker_matches(ready_path, pid=primary.pid),
                timeout=startup_timeout,
                description="a visible and event-loop-ready main window",
                process=primary,
            )

            with secondary_log_path.open("wb") as secondary_log:
                secondary = subprocess.Popen(
                    [str(executable)],
                    stdin=subprocess.DEVNULL,
                    stdout=secondary_log,
                    stderr=subprocess.STDOUT,
                )
            try:
                secondary_code = secondary.wait(timeout=secondary_timeout)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Second frozen instance did not exit after notifying the primary"
                ) from exc
            if secondary_code != 0:
                raise RuntimeError(
                    f"Second frozen instance exited with code {secondary_code}"
                )
            if primary.poll() is not None:
                raise RuntimeError(
                    "Primary frozen instance exited after the second launch "
                    f"(code {primary.returncode})"
                )
            if not lock_path.is_file():
                raise RuntimeError("Primary single-instance lock disappeared unexpectedly")
            wait_until(
                lambda: marker_matches(
                    activation_path,
                    pid=primary.pid,
                    activation=True,
                ),
                timeout=secondary_timeout,
                description="confirmed activation of the existing main window",
                process=primary,
            )
        except Exception as exc:
            logs = []
            for label, path in (
                ("primary", primary_log_path),
                ("secondary", secondary_log_path),
            ):
                content = _read_log(path)
                if content:
                    logs.append(f"--- {label} output ---\n{content}")
            if logs:
                raise RuntimeError(f"{exc}\n" + "\n".join(logs)) from exc
            raise
        finally:
            if secondary is not None:
                stop_process(secondary)
            if primary is not None:
                stop_process(primary)
            # Forced termination cannot run QApplication.aboutToQuit.  Remove
            # only the known build-artifact lock after both processes stop so
            # the unpacked application stays clean for subsequent CI steps.
            for path in (lock_path, ready_path, activation_path):
                path.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", required=True, type=Path)
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--secondary-timeout", type=float, default=12.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if argv is None else argv)
    smoke_test(
        options.application,
        startup_timeout=options.startup_timeout,
        secondary_timeout=options.secondary_timeout,
    )
    print("Frozen application startup and single-instance behavior verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
