import unittest

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.screenshot.annotations import (
    annotation_contains,
    append_brush_points,
    distance_to_segment,
    new_annotation,
    translate_annotations,
)
from fuzztoolbox.tools.screenshot.capture_backend import (
    ScreenCaptureCoordinator,
    capture_screens,
    compose_desktop,
    virtual_geometry,
)
from fuzztoolbox.tools.screenshot.renderer import AnnotationRenderer
from fuzztoolbox.tools.screenshot.selection import (
    handle_points,
    hit_handle,
    macos_dock_regions,
    resize_selection,
    unique_regions,
)


class FakeScreen:
    def __init__(self, geometry):
        self._geometry = QRect(geometry)

    def geometry(self):
        return QRect(self._geometry)


class SelectionGeometryTests(unittest.TestCase):
    def test_handles_and_hit_testing_share_one_geometry_model(self):
        rect = QRect(100, 80, 400, 300)

        points = handle_points(rect)

        self.assertEqual(points["t"], QPoint(299, 80))
        self.assertEqual(hit_handle(rect, points["br"] + QPoint(3, -2)), "br")
        self.assertEqual(hit_handle(rect, QPoint(300, 220)), "")

    def test_resize_normalizes_and_clips_to_desktop_bounds(self):
        resized = resize_selection(
            QRect(100, 100, 200, 150),
            "tl",
            QPoint(350, -20),
            QRect(0, 0, 500, 400),
        )

        self.assertEqual(resized, QRect(300, 0, 50, 250))

    def test_dock_inference_and_region_deduplication(self):
        geometry = QRect(0, 0, 1440, 900)
        dock = macos_dock_regions(geometry, QRect(0, 30, 1440, 810))

        self.assertEqual(dock, [QRect(0, 840, 1440, 60)])
        self.assertEqual(unique_regions(dock + dock), dock)


class AnnotationStateTests(unittest.TestCase):
    def test_annotation_owns_mutable_values_and_interpolates_brush_motion(self):
        start = QPoint(10, 10)
        color = QColor("#ff4d4f")
        annotation = new_annotation("pen", start, start, color, 4)
        start.setX(99)
        color.setBlue(255)

        append_brush_points(annotation, QPoint(110, 10))

        self.assertEqual(annotation["start"], QPoint(10, 10))
        self.assertEqual(annotation["color"], QColor("#ff4d4f"))
        self.assertGreater(len(annotation["points"]), 2)
        self.assertEqual(annotation["points"][-1], QPoint(110, 10))

    def test_hit_testing_covers_strokes_without_selecting_shape_interior(self):
        rectangle = new_annotation(
            "rect", QPoint(20, 20), QPoint(120, 90), QColor(Qt.red), 3
        )
        arrow = new_annotation(
            "arrow", QPoint(10, 10), QPoint(110, 10), QColor(Qt.red), 4
        )

        self.assertTrue(annotation_contains(rectangle, QPoint(20, 50)))
        self.assertFalse(annotation_contains(rectangle, QPoint(70, 50)))
        self.assertTrue(annotation_contains(arrow, QPoint(60, 13)))
        self.assertEqual(
            distance_to_segment(QPoint(50, 20), QPoint(0, 0), QPoint(100, 0)),
            20,
        )

    def test_translate_moves_endpoints_and_brush_points_together(self):
        annotation = new_annotation(
            "mosaic", QPoint(10, 20), QPoint(10, 20), QColor(Qt.black), 8
        )
        annotation["points"].append(QPoint(20, 30))

        translate_annotations([annotation], QPoint(7, -4))

        self.assertEqual(annotation["start"], QPoint(17, 16))
        self.assertEqual(annotation["end"], QPoint(17, 16))
        self.assertEqual(annotation["points"], [QPoint(17, 16), QPoint(27, 26)])


class CaptureAndRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_capture_and_composition_keep_screen_positions(self):
        screens = [FakeScreen(QRect(-40, 0, 40, 30)), FakeScreen(QRect(0, 0, 50, 30))]

        def grabber(screen):
            pixmap = QPixmap(screen.geometry().size())
            pixmap.fill(Qt.red if screen.geometry().x() < 0 else Qt.blue)
            return pixmap

        geometry = virtual_geometry(screens)
        shots = capture_screens(screens, grabber)
        desktop, ratio = compose_desktop(shots, geometry)
        image = desktop.toImage()

        self.assertEqual(geometry, QRect(-40, 0, 90, 30))
        self.assertEqual(ratio, 1.0)
        self.assertEqual(image.pixelColor(10, 10), QColor(Qt.red))
        self.assertEqual(image.pixelColor(70, 10), QColor(Qt.blue))

    def test_capture_coordinator_reports_one_synchronous_result(self):
        screen = FakeScreen(QRect(0, 0, 20, 10))
        coordinator = ScreenCaptureCoordinator(lambda _screen: QPixmap(20, 10))
        results = []
        failures = []
        coordinator.ready.connect(results.append)
        coordinator.failed.connect(lambda: failures.append(True))

        coordinator.capture([screen])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0][0], screen.geometry())
        self.assertEqual(failures, [])

    def test_capture_coordinator_converts_native_failure_to_signal(self):
        coordinator = ScreenCaptureCoordinator(
            lambda _screen: (_ for _ in ()).throw(RuntimeError("denied"))
        )
        failures = []
        coordinator.failed.connect(lambda: failures.append(True))

        coordinator._capture_now([FakeScreen(QRect(0, 0, 20, 10))])

        self.assertEqual(failures, [True])

    def test_renderer_paints_annotation_without_widget_state(self):
        desktop = QPixmap(120, 90)
        desktop.fill(Qt.white)
        output = QPixmap(120, 90)
        output.fill(Qt.transparent)
        annotation = new_annotation(
            "rect", QPoint(20, 20), QPoint(90, 60), QColor(Qt.red), 4
        )
        painter = QPainter(output)

        AnnotationRenderer(
            desktop,
            QRect(0, 0, 120, 90),
            1.0,
            self.app.font().family(),
        ).paint(painter, annotation)
        painter.end()

        self.assertGreater(output.toImage().pixelColor(20, 40).alpha(), 0)


if __name__ == "__main__":
    unittest.main()
