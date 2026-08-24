import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from fuzztoolbox.ui.single_instance import InstanceRole, SingleInstanceCoordinator


class SingleInstanceCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.server_name = f"fuzztoolbox-test-{uuid4().hex}"
        self.runtime_directory = tempfile.TemporaryDirectory(
            prefix="fuzztoolbox-single-instance-"
        )
        self.runtime_path = Path(self.runtime_directory.name)
        self.coordinators = []

    def tearDown(self):
        for coordinator in reversed(self.coordinators):
            coordinator.close()
        self.app.processEvents()
        self.runtime_directory.cleanup()

    def coordinator(self, runtime_path=None):
        coordinator = SingleInstanceCoordinator(
            self.server_name,
            runtime_dir=runtime_path or self.runtime_path,
        )
        self.coordinators.append(coordinator)
        return coordinator

    def start_secondary(self):
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "from fuzztoolbox.ui.single_instance import InstanceRole, "
                    "SingleInstanceCoordinator; "
                    "from pathlib import Path; "
                    "coordinator = SingleInstanceCoordinator("
                    "sys.argv[1], runtime_dir=Path(sys.argv[2])); "
                    "role = coordinator.acquire(); "
                    "sys.exit(0 if role is InstanceRole.SECONDARY "
                    "and coordinator.notification_succeeded else 2)"
                ),
                self.server_name,
                str(self.runtime_path),
            ]
        )

    def test_first_instance_becomes_primary(self):
        self.assertIs(self.coordinator().acquire(), InstanceRole.PRIMARY)

    def test_ready_marker_requires_visible_window_and_is_cleaned_up(self):
        primary = self.coordinator()
        self.assertIs(primary.acquire(), InstanceRole.PRIMARY)

        self.assertFalse(primary.publish_ready(lambda: False))
        self.assertFalse(primary.ready_path.exists())
        self.assertTrue(primary.publish_ready(lambda: True))
        payload = json.loads(primary.ready_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["window_visible"])

        primary.close()
        self.assertFalse(primary.ready_path.exists())
        self.assertFalse(primary.activation_path.exists())

    def test_second_instance_notifies_primary_and_exits(self):
        primary = self.coordinator()
        activations = QSignalSpy(primary.activation_requested)

        self.assertIs(primary.acquire(), InstanceRole.PRIMARY)
        self.assertTrue(primary.publish_ready(lambda: True))
        secondary = self.start_secondary()

        self.assertTrue(activations.wait(3000))
        self.app.processEvents()

        self.assertEqual(secondary.wait(timeout=3), 0)
        self.assertEqual(activations.count(), 1)
        payload = json.loads(primary.activation_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["sequence"], 1)
        self.assertTrue(payload["window_visible"])

    def test_closed_primary_allows_a_new_primary(self):
        primary = self.coordinator()
        replacement = self.coordinator()

        self.assertIs(primary.acquire(), InstanceRole.PRIMARY)
        primary.close()
        self.assertIs(replacement.acquire(), InstanceRole.PRIMARY)

    def test_same_server_name_is_isolated_by_runtime_directory(self):
        with tempfile.TemporaryDirectory(
            prefix="fuzztoolbox-single-instance-peer-"
        ) as peer_directory:
            first = self.coordinator()
            isolated = self.coordinator(Path(peer_directory))

            self.assertIs(first.acquire(), InstanceRole.PRIMARY)
            self.assertIs(isolated.acquire(), InstanceRole.PRIMARY)
            # Release QLockFile before TemporaryDirectory removes its parent;
            # otherwise Qt warns that it cannot remove its own lock at teardown.
            isolated.close()


if __name__ == "__main__":
    unittest.main()
