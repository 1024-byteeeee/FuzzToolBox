import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tests.native.frozen_app_smoke import (
    SERVER_NAME,
    marker_matches,
    resolve_application,
    runtime_marker_path,
    single_instance_lock_path,
    smoke_test,
)


class FrozenApplicationSmokeHelperTests(unittest.TestCase):
    def test_resolves_macos_bundle_executable_and_lock_root(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "FuzzToolBox.app"
            executable = bundle / "Contents" / "MacOS" / "FuzzToolBox"
            executable.parent.mkdir(parents=True)
            executable.touch()

            resolved_executable, lock_root = resolve_application(bundle)

            self.assertEqual(resolved_executable, executable.resolve())
            self.assertEqual(lock_root, bundle.resolve())

    def test_resolves_windows_executable_and_lock_root(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "FuzzToolBox.exe"
            executable.touch()

            resolved_executable, lock_root = resolve_application(executable)

            self.assertEqual(resolved_executable, executable.resolve())
            self.assertEqual(lock_root, executable.parent.resolve())

    def test_single_instance_lock_name_matches_application_protocol(self):
        root = Path("build")
        digest = hashlib.sha256(SERVER_NAME.encode("utf-8")).hexdigest()[:20]

        self.assertEqual(
            single_instance_lock_path(root),
            root / f"fuzztoolbox-{digest}.lock",
        )

    def test_missing_executable_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(FileNotFoundError),
        ):
            resolve_application(Path(directory) / "missing.exe")

    def test_ready_marker_must_match_primary_pid_and_visibility(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = runtime_marker_path(Path(directory), "ready")
            marker.write_text(
                json.dumps(
                    {"protocol": 1, "pid": 42, "window_visible": True}
                ),
                encoding="utf-8",
            )

            self.assertTrue(marker_matches(marker, pid=42))
            self.assertFalse(marker_matches(marker, pid=43))

    def test_activation_marker_requires_positive_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = runtime_marker_path(Path(directory), "activation")
            marker.write_text(
                json.dumps(
                    {
                        "protocol": 1,
                        "pid": 42,
                        "window_visible": True,
                        "sequence": 0,
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(marker_matches(marker, pid=42, activation=True))

            marker.write_text(
                json.dumps(
                    {
                        "protocol": 1,
                        "pid": 42,
                        "window_visible": True,
                        "sequence": 1,
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(marker_matches(marker, pid=42, activation=True))

    @unittest.skipIf(
        os.name == "nt",
        "POSIX-only: simulates a frozen app with an executable shebang "
        "script, which Windows cannot launch directly",
    )
    def test_lock_without_ready_window_is_rejected(self):
        """A process holding only the early startup lock is not UI-ready."""
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-frozen-app"
            digest = hashlib.sha256(SERVER_NAME.encode("utf-8")).hexdigest()[:20]
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import os\n"
                "import pathlib\n"
                "import time\n"
                f"lock = pathlib.Path(__file__).parent / 'fuzztoolbox-{digest}.lock'\n"
                "try:\n"
                "    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)\n"
                "except FileExistsError:\n"
                "    raise SystemExit(0)\n"
                "try:\n"
                "    time.sleep(5)\n"
                "finally:\n"
                "    os.close(descriptor)\n",
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(TimeoutError):
                smoke_test(
                    executable,
                    startup_timeout=0.4,
                    secondary_timeout=0.4,
                )


if __name__ == "__main__":
    unittest.main()
