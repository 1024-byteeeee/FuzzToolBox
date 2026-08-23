import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.screenshot.page import ScreenshotPage


class ScreenshotPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_keep_main_mode_starts_without_hiding_window(self):
        page = ScreenshotPage()
        overlay = Mock()
        with patch(
            "fuzztoolbox.tools.screenshot.page.ScreenshotOverlay",
            return_value=overlay,
        ) as overlay_type, patch(
            "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
        ) as hide_window, patch(
            "fuzztoolbox.tools.screenshot.page.QTimer.singleShot"
        ) as single_shot:
            page.start_capture(keep_main_window=True)

        hide_window.assert_not_called()
        overlay_type.assert_called_once_with(include_app_window=True)
        self.assertFalse(page._restore_window_after_capture)
        self.assertTrue(overlay.completed.connect.called)
        self.assertTrue(overlay.cancelled.connect.called)
        single_shot.assert_called_once()
        self.assertIs(single_shot.call_args.args[1], overlay.begin)
        page._overlay = None
        page.close()


if __name__ == "__main__":
    unittest.main()
