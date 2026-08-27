import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.screenshot.annotations import (
    annotation_contains,
    annotation_geometry,
    append_brush_points,
    distance_to_segment,
    new_annotation,
    resize_annotation,
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
    move_selection,
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

    def test_move_clamps_to_vertical_edges_in_one_step(self):
        bounds = QRect(0, 0, 900, 600)
        selection = QRect(100, 100, 400, 300)

        moved_to_top = move_selection(selection, QPoint(0, -1000), bounds)
        moved_to_bottom = move_selection(selection, QPoint(0, 1000), bounds)

        self.assertEqual(moved_to_top.top(), bounds.top())
        self.assertEqual(moved_to_bottom.bottom(), bounds.bottom())

    def test_dock_inference_and_region_deduplication(self):
        geometry = QRect(0, 0, 1440, 900)
        dock = macos_dock_regions(geometry, QRect(0, 30, 1440, 810))

        self.assertEqual(dock, [QRect(0, 840, 1440, 60)])
        self.assertEqual(unique_regions(dock + dock), dock)


class AnnotationStateTests(unittest.TestCase):
    def test_resizing_annotation_maps_all_geometry_into_new_bounds(self):
        annotation = new_annotation(
            "arrow", QPoint(10, 20), QPoint(110, 70), QColor(Qt.red), 4
        )

        resize_annotation(annotation, QRect(10, 20, 101, 51), QRect(20, 40, 201, 101))

        self.assertEqual(annotation["start"], QPoint(20, 40))
        self.assertEqual(annotation["end"], QPoint(220, 140))
        self.assertEqual(annotation_geometry(annotation), QRect(20, 40, 201, 101))

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

    def test_long_pen_hit_test_only_checks_the_matching_segment_chunk(self):
        annotation = new_annotation(
            "pen", QPoint(0, 20), QPoint(0, 20), QColor(Qt.red), 4
        )
        annotation["points"] = [QPoint(index, 20) for index in range(20_000)]
        annotation["end"] = QPoint(annotation["points"][-1])
        annotation["_point_bounds"] = QRect(
            annotation["points"][0], annotation["points"][-1]
        )
        annotation["_point_bounds_count"] = len(annotation["points"])

        with patch(
            "fuzztoolbox.tools.screenshot.annotations.distance_to_segment",
            wraps=distance_to_segment,
        ) as distance:
            contains = annotation_contains(annotation, QPoint(19_990, 22))

        self.assertTrue(contains)
        self.assertLessEqual(distance.call_count, 128)

    def test_translate_moves_endpoints_and_brush_points_together(self):
        annotation = new_annotation(
            "mosaic", QPoint(10, 20), QPoint(10, 20), QColor(Qt.black), 8
        )
        annotation["points"].append(QPoint(20, 30))

        translate_annotations([annotation], QPoint(7, -4))

        self.assertEqual(annotation["start"], QPoint(17, 16))
        self.assertEqual(annotation["end"], QPoint(17, 16))
        self.assertEqual(annotation["points"], [QPoint(17, 16), QPoint(27, 26)])

    def test_long_brush_resize_keeps_endpoints_aligned_with_points(self):
        annotation = new_annotation(
            "pen", QPoint(1, 1), QPoint(1, 1), QColor(Qt.red), 4
        )
        annotation["points"] = [QPoint(1, 1) for _ in range(128)]

        resize_annotation(annotation, QRect(0, 0, 3, 3), QRect(0, 0, 6, 6))

        self.assertEqual(annotation["start"], annotation["points"][0])
        self.assertEqual(annotation["end"], annotation["points"][-1])

    def test_fragment_hit_test_checks_the_full_logical_pixel_cell(self):
        image = QImage(2, 2, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        image.setPixelColor(1, 1, QColor("#ff4d4f"))
        fragment = {
            "kind": "fragment",
            "start": QPoint(10, 10),
            "end": QPoint(10, 10),
            "color": QColor("#ff4d4f"),
            "width": 4,
            "image": image,
        }

        self.assertTrue(annotation_contains(fragment, QPoint(10, 10)))


class CaptureAndRendererTests(unittest.TestCase):
    def test_pixelated_source_preserves_exact_source_colors(self):
        color = QColor("#21bf55")
        desktop = QPixmap(64, 64)
        desktop.fill(color)
        renderer = AnnotationRenderer(desktop, QRect(0, 0, 64, 64), 1, "Arial")

        pixelated = renderer._cached_pixelated_source(desktop).toImage()

        self.assertEqual(pixelated.pixelColor(8, 8), color)
        self.assertEqual(pixelated.pixelColor(55, 55), color)

    def test_mosaic_brush_uses_a_square_footprint(self):
        desktop = QPixmap(100, 100)
        desktop.fill(Qt.white)
        renderer = AnnotationRenderer(desktop, QRect(0, 0, 100, 100), 1, "Arial")
        annotation = new_annotation(
            "mosaic", QPoint(50, 50), QPoint(50, 50), QColor(Qt.black), 8
        )

        path = renderer._mosaic_path(annotation)

        self.assertTrue(path.contains(QPoint(39, 39)))
        self.assertTrue(path.contains(QPoint(61, 61)))

    def test_pen_path_cache_is_invalidated_when_interior_geometry_changes(self):
        desktop = QPixmap(140, 80)
        renderer = AnnotationRenderer(desktop, QRect(0, 0, 140, 80), 1, "Arial")
        annotation = new_annotation(
            "pen", QPoint(10, 20), QPoint(10, 20), QColor(Qt.black), 4
        )
        annotation["points"] = [QPoint(10, 20), QPoint(50, 30), QPoint(10, 40)]

        before = renderer._stroke_path(annotation).boundingRect()
        resize_annotation(annotation, QRect(10, 20, 41, 21), QRect(10, 20, 81, 21))
        after = renderer._stroke_path(annotation).boundingRect()

        self.assertEqual(round(before.right()), 50)
        self.assertEqual(round(after.right()), 90)

    def test_mosaic_mask_cache_is_invalidated_when_interior_geometry_changes(self):
        desktop = QPixmap(140, 80)
        renderer = AnnotationRenderer(desktop, QRect(0, 0, 140, 80), 1, "Arial")
        annotation = new_annotation(
            "mosaic", QPoint(10, 20), QPoint(10, 20), QColor(Qt.black), 4
        )
        annotation["points"] = [QPoint(10, 20), QPoint(50, 30), QPoint(10, 40)]

        before = renderer._mosaic_path(annotation).boundingRect()
        resize_annotation(annotation, QRect(10, 20, 41, 21), QRect(10, 20, 81, 21))
        after = renderer._mosaic_path(annotation).boundingRect()

        self.assertEqual(round(before.right()), 56)
        self.assertEqual(round(after.right()), 96)

    def test_pixelation_keeps_a_complete_partial_edge_block(self):
        desktop = QPixmap(25, 12)
        painter = QPainter(desktop)
        painter.fillRect(QRect(0, 0, 12, 12), QColor("#ff0000"))
        painter.fillRect(QRect(12, 0, 12, 12), QColor("#00ff00"))
        painter.fillRect(QRect(24, 0, 1, 12), QColor("#0000ff"))
        painter.end()
        renderer = AnnotationRenderer(desktop, QRect(0, 0, 25, 12), 1, "Arial")

        result = renderer._cached_pixelated_source(desktop).toImage()

        self.assertGreater(result.pixelColor(24, 6).blue(), 200)

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

    def test_long_mosaic_stroke_draws_one_cached_source_instead_of_each_point(self):
        desktop = QPixmap(1200, 800)
        desktop.fill(Qt.white)
        annotation = new_annotation(
            "mosaic", QPoint(10, 40), QPoint(10, 40), QColor(Qt.black), 8
        )
        for x in range(11, 1011):
            annotation["points"].append(QPoint(x, 40))
        renderer = AnnotationRenderer(
            desktop,
            QRect(0, 0, 1200, 800),
            1.0,
            self.app.font().family(),
        )
        painter = Mock()

        renderer.paint_mosaic_stroke(painter, annotation)

        self.assertEqual(painter.drawPixmap.call_count, 1)

    def test_long_pen_reuses_its_compiled_path_until_geometry_changes(self):
        desktop = QPixmap(1200, 800)
        annotation = new_annotation(
            "pen", QPoint(10, 40), QPoint(10, 40), QColor(Qt.black), 4
        )
        for x in range(11, 1011):
            annotation["points"].append(QPoint(x, 40))
        renderer = AnnotationRenderer(
            desktop,
            QRect(0, 0, 1200, 800),
            1.0,
            self.app.font().family(),
        )

        first = renderer._stroke_path(annotation)
        second = renderer._stroke_path(annotation)
        annotation["points"].append(QPoint(1011, 40))
        third = renderer._stroke_path(annotation)

        self.assertIs(first, second)
        self.assertIs(second, third)
        self.assertEqual(third.elementCount(), len(annotation["points"]))

    def test_long_pen_rasterizes_as_bounded_connected_polylines(self):
        renderer = AnnotationRenderer(QPixmap(), QRect(), 1.0, "Arial")
        annotation = new_annotation(
            "pen", QPoint(10, 40), QPoint(10, 40), QColor(Qt.black), 4
        )
        annotation["points"] = [QPoint(10 + index, 40) for index in range(600)]
        painter = Mock()

        renderer._paint_pen(painter, annotation)

        polylines = [call.args[0] for call in painter.drawPolyline.call_args_list]
        self.assertGreater(len(polylines), 1)
        self.assertTrue(all(len(polyline) <= 65 for polyline in polylines))
        for previous, following in zip(polylines, polylines[1:]):
            self.assertEqual(previous[-1], following[0])
        painter.drawPath.assert_not_called()

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
