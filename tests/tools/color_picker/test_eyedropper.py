import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QColorSpace, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.color_picker.eyedropper import (
    EyedropperOverlay,
    _to_srgb_pixmap,
    hide_window_instantly,
    show_window_instantly,
)


class EyedropperColorManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_srgb_image_is_kept_unchanged(self):
        image = QImage(1, 1, QImage.Format_RGBA8888)
        image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        image.setPixelColor(0, 0, QColor(12, 34, 56, 255))
        result = _to_srgb_pixmap(QPixmap.fromImage(image)).toImage()

        self.assertEqual(result.pixelColor(0, 0), QColor(12, 34, 56, 255))
        self.assertEqual(result.colorSpace(), QColorSpace(QColorSpace.NamedColorSpace.SRgb))

    def test_display_p3_image_is_converted_to_srgb(self):
        image = QImage(1, 1, QImage.Format_RGBA8888)
        image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))
        image.setPixelColor(0, 0, QColor(255, 0, 0, 255))
        result = _to_srgb_pixmap(QPixmap.fromImage(image)).toImage()

        self.assertEqual(result.colorSpace(), QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        # P3 red converted into sRGB is clipped at the gamut boundary, but
        # remains a valid opaque red rather than being interpreted as raw P3.
        self.assertEqual(result.pixelColor(0, 0).alpha(), 255)
        self.assertGreaterEqual(result.pixelColor(0, 0).red(), 240)

    def test_unprofiled_image_keeps_raw_pixels(self):
        image = QImage(1, 1, QImage.Format_RGBA8888)
        image.setPixelColor(0, 0, QColor(90, 80, 70, 255))
        result = _to_srgb_pixmap(QPixmap.fromImage(image)).toImage()

        self.assertEqual(result.pixelColor(0, 0), QColor(90, 80, 70, 255))

    def test_pixel_color_reads_channels_without_qrgb_unpacking(self):
        image = QImage(1, 1, QImage.Format_RGBA8888)
        image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        image.setPixelColor(0, 0, QColor(0x21, 0xBF, 0x55, 255))

        self.assertEqual(image.pixelColor(0, 0).name().upper(), "#21BF55")

    def test_frozen_eyedropper_overlay_cannot_be_resized_from_edges(self):
        overlay = EyedropperOverlay()
        geometry = QRect(-240, 30, 1680, 1050)

        overlay._lock_overlay_geometry(geometry)

        self.assertEqual(overlay.pos(), geometry.topLeft())
        self.assertEqual(overlay.size(), geometry.size())
        self.assertEqual(overlay.minimumSize(), geometry.size())
        self.assertEqual(overlay.maximumSize(), geometry.size())
        overlay.deleteLater()

    def test_overlay_is_an_independent_always_on_top_window(self):
        overlay = EyedropperOverlay()

        self.assertTrue(overlay.isWindow())
        self.assertTrue(overlay.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertIsNone(overlay.parentWidget())
        overlay.deleteLater()

    def test_native_hide_clears_compositor_pixels_before_ordering_window_out(self):
        widget = Mock()
        objc = Mock()
        objc.sel_registerName.side_effect = lambda name: name
        events = []
        objc.objc_msgSend.side_effect = lambda *_args: events.append("order-out")

        with patch(
            "fuzztoolbox.tools.color_picker.eyedropper._ns_window",
            return_value=123,
        ), patch(
            "fuzztoolbox.tools.color_picker.eyedropper._set_window_opacity_no_animation",
            side_effect=lambda _widget, opacity: events.append(f"opacity-{opacity}"),
        ), patch(
            "fuzztoolbox.tools.color_picker.eyedropper.ctypes.CDLL",
            return_value=objc,
        ):
            hide_window_instantly(widget)

        self.assertEqual(events[:2], ["opacity-0.0", "order-out"])
        widget.hide.assert_called_once_with()

    def test_native_show_restores_opacity_before_ordering_window_front(self):
        widget = Mock()
        objc = Mock()
        objc.sel_registerName.side_effect = lambda name: name
        events = []
        widget.show.side_effect = lambda: events.append("show")
        objc.objc_msgSend.side_effect = lambda *_args: events.append("order-front")

        with patch(
            "fuzztoolbox.tools.color_picker.eyedropper._ns_window",
            return_value=123,
        ), patch(
            "fuzztoolbox.tools.color_picker.eyedropper._set_window_opacity_no_animation",
            side_effect=lambda _widget, opacity: events.append(f"opacity-{opacity}"),
        ), patch(
            "fuzztoolbox.tools.color_picker.eyedropper.ctypes.CDLL",
            return_value=objc,
        ):
            show_window_instantly(widget)

        self.assertEqual(events[:3], ["opacity-1.0", "show", "order-front"])


if __name__ == "__main__":
    unittest.main()
