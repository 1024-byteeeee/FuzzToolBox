import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QWidget

from fuzztoolbox.ui.system_tray import SystemTrayController


class _TrayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.restore_calls = 0

    def restore_from_tray(self):
        self.restore_calls += 1

    def request_application_quit(self):
        pass


class SystemTrayControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tray_menu_is_themeable_and_contains_only_window_and_quit(self):
        window = _TrayWindow()
        controller = SystemTrayController(window, Path("missing-test-icon.png"))
        self.addCleanup(controller.tray.hide)
        self.addCleanup(window.deleteLater)

        self.assertEqual(controller.menu.objectName(), "trayMenu")
        self.assertEqual([action.text() for action in controller.actions], ["显示主窗口", "退出"])
        self.assertEqual([action.text() for action in controller.menu.actions()], ["显示主窗口", "退出"])
        self.assertIsNone(controller.tray.contextMenu())

    def test_restore_runs_after_the_tray_menu_event_finishes(self):
        window = _TrayWindow()
        controller = SystemTrayController(window, Path("missing-test-icon.png"))
        self.addCleanup(controller.tray.hide)
        self.addCleanup(window.deleteLater)

        with patch("fuzztoolbox.ui.system_tray.QTimer.singleShot") as single_shot:
            controller.actions[0].trigger()

        single_shot.assert_called_once_with(0, window.restore_from_tray)
        self.assertEqual(window.restore_calls, 0)


if __name__ == "__main__":
    unittest.main()
