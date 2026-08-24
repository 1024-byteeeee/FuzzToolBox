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

    def test_background_capture_hides_without_restoring_main_window(self):
        for finish_method in ("_completed", "_cancelled"):
            with self.subTest(finish_method=finish_method):
                page = ScreenshotPage()
                overlay = Mock()
                with patch(
                    "fuzztoolbox.tools.screenshot.page.ScreenshotOverlay",
                    return_value=overlay,
                ), patch(
                    "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
                ) as hide_window, patch(
                    "fuzztoolbox.tools.screenshot.page.show_window_instantly"
                ) as show_window, patch.object(page, "_wait_for_hide"):
                    page.start_capture(
                        keep_main_window=False,
                        restore_main_window=False,
                    )
                    getattr(page, finish_method)()

                hide_window.assert_called_once_with(page)
                show_window.assert_not_called()
                self.assertFalse(page._restore_window_after_capture)
                page.close()

    def test_page_capture_restores_main_window_when_finished(self):
        page = ScreenshotPage()
        overlay = Mock()
        with patch(
            "fuzztoolbox.tools.screenshot.page.ScreenshotOverlay",
            return_value=overlay,
        ), patch(
            "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
        ) as hide_window, patch(
            "fuzztoolbox.tools.screenshot.page.show_window_instantly"
        ) as show_window, patch.object(page, "_wait_for_hide"):
            page.start_capture(keep_main_window=False)
            page._completed()

        hide_window.assert_called_once_with(page)
        show_window.assert_called_once_with(page)
        self.assertFalse(page._restore_window_after_capture)
        page.close()

    def test_background_capture_rehides_a_window_reordered_by_macos(self):
        page = ScreenshotPage()
        overlay = Mock()
        with patch(
            "fuzztoolbox.tools.screenshot.page.native_window_is_visible",
            return_value=True,
        ), patch(
            "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
        ) as hide_window, patch(
            "fuzztoolbox.tools.screenshot.page.QTimer.singleShot"
        ) as single_shot, patch(
            "fuzztoolbox.tools.screenshot.page.time.monotonic",
            return_value=10.1,
        ):
            page._wait_for_hide(overlay, page, 10.0)

        hide_window.assert_called_once_with(page)
        overlay.begin.assert_not_called()
        self.assertEqual(single_shot.call_args.args[0], 25)
        page.close()

    def test_background_capture_keeps_window_hidden_until_pixels_are_frozen(self):
        page = ScreenshotPage()
        overlay = Mock()
        page._overlay = overlay
        page._hidden_capture_overlay = overlay

        with patch(
            "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
        ) as hide_window, patch(
            "fuzztoolbox.tools.screenshot.page.QTimer.singleShot"
        ) as single_shot:
            page._keep_main_hidden(overlay, page)

        hide_window.assert_called_once_with(page)
        self.assertEqual(single_shot.call_args.args[0], 25)

        page._capture_ready(overlay)
        with patch(
            "fuzztoolbox.tools.screenshot.page.hide_window_instantly"
        ) as hide_window, patch(
            "fuzztoolbox.tools.screenshot.page.QTimer.singleShot"
        ) as single_shot:
            page._keep_main_hidden(overlay, page)

        hide_window.assert_not_called()
        single_shot.assert_not_called()
        page._overlay = None
        page.close()


if __name__ == "__main__":
    unittest.main()
