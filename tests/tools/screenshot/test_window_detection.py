import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect

from fuzztoolbox.tools.screenshot import window_detection


class WindowDetectionTests(unittest.TestCase):
    def test_dispatches_to_windows_enumerator(self):
        expected = [QRect(10, 20, 300, 200)]
        with (
            patch.object(window_detection.sys, "platform", "win32"),
            patch.object(
                window_detection, "_windows_window_rects", return_value=expected
            ) as enumerator,
        ):
            self.assertEqual(window_detection.enumerate_window_rects(), expected)
            enumerator.assert_called_once_with(include_current_process=False)

    def test_dispatches_to_macos_enumerator(self):
        expected = [QRect(10, 20, 300, 200)]
        with (
            patch.object(window_detection.sys, "platform", "darwin"),
            patch.object(
                window_detection, "_macos_window_rects", return_value=expected
            ) as enumerator,
        ):
            self.assertEqual(
                window_detection.enumerate_window_rects(
                    include_current_process=True
                ),
                expected,
            )
            enumerator.assert_called_once_with(include_current_process=True)

    def test_native_enumeration_failure_falls_back_to_manual_selection(self):
        with (
            patch.object(window_detection.sys, "platform", "darwin"),
            patch.object(
                window_detection,
                "_macos_window_rects",
                side_effect=OSError("unavailable"),
            ),
        ):
            self.assertEqual(window_detection.enumerate_window_rects(), [])

    def test_macos_system_layers_are_supported_without_accepting_desktop(self):
        self.assertTrue(
            window_detection._use_macos_window(
                "Control Center", "WiFi", 25, (1200, 0, 42, 30)
            )
        )
        self.assertTrue(
            window_detection._use_macos_window(
                "Dock", "", 20, (200, 820, 1040, 80)
            )
        )
        self.assertTrue(
            window_detection._use_macos_window(
                "Notification Center", "", 18, (900, 40, 480, 760)
            )
        )
        self.assertFalse(
            window_detection._use_macos_window(
                "Window Server", "Desktop", 20, (0, 0, 1440, 900)
            )
        )

if __name__ == "__main__":
    unittest.main()
