import unittest
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
        self.coordinators = []

    def tearDown(self):
        for coordinator in reversed(self.coordinators):
            coordinator.close()
        self.app.processEvents()

    def coordinator(self):
        coordinator = SingleInstanceCoordinator(self.server_name)
        self.coordinators.append(coordinator)
        return coordinator

    def test_first_instance_becomes_primary(self):
        self.assertIs(self.coordinator().acquire(), InstanceRole.PRIMARY)

    def test_second_instance_notifies_primary_and_exits(self):
        primary = self.coordinator()
        secondary = self.coordinator()
        activations = QSignalSpy(primary.activation_requested)

        self.assertIs(primary.acquire(), InstanceRole.PRIMARY)
        self.assertIs(secondary.acquire(), InstanceRole.SECONDARY)
        if activations.count() == 0:
            self.assertTrue(activations.wait(1000))

        self.assertEqual(activations.count(), 1)

    def test_closed_primary_allows_a_new_primary(self):
        primary = self.coordinator()
        replacement = self.coordinator()

        self.assertIs(primary.acquire(), InstanceRole.PRIMARY)
        primary.close()
        self.assertIs(replacement.acquire(), InstanceRole.PRIMARY)


if __name__ == "__main__":
    unittest.main()
