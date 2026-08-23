import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from fuzztoolbox.ui.system_tray import SystemTrayController


class _TrayWindow(QWidget):
    def restore_from_tray(self):
        pass

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


if __name__ == "__main__":
    unittest.main()
