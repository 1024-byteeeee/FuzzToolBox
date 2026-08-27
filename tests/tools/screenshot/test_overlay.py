import copy
import math
import platform
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
    QWheelEvent,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QFrame,
    QPushButton,
)

from fuzztoolbox.tools.screenshot.annotations import (
    annotation_bounds,
    annotation_contains,
    append_brush_points,
    new_annotation,
)
from fuzztoolbox.tools.screenshot.overlay import ScreenshotOverlay, ScreenshotScrollBar
from fuzztoolbox.tools.screenshot.selection import (
    handle_points,
    macos_dock_regions,
    resize_selection,
)


class ScreenshotOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.overlay = ScreenshotOverlay()
        self.overlay.resize(900, 600)

    def tearDown(self):
        self.overlay._remove_input_lock()
        if self.overlay._color_dialog is not None:
            self.overlay._color_dialog.reject()
        if self.overlay._save_dialog is not None:
            self.overlay._save_dialog.reject()
        self.overlay.close()
        self.overlay.deleteLater()
        self.app.processEvents()

    def test_escape_cancels_before_a_region_is_selected(self):
        cancelled = []
        self.overlay.cancelled.connect(lambda: cancelled.append(True))
        self.overlay.show()
        self.overlay.activateWindow()
        self.overlay.setFocus()
        self.app.processEvents()

        QTest.keyClick(self.overlay, Qt.Key_Escape)
        self.app.processEvents()

        self.assertEqual(cancelled, [True])
        self.assertTrue(self.overlay.isHidden())

    def test_magnifier_is_square(self):
        rect = self.overlay._magnifier_rect(QPoint(450, 300))

        self.assertEqual(rect.width(), rect.height())

    def test_selection_size_uses_output_pixel_resolution(self):
        self.overlay.selection = QRect(20, 30, 300, 200)
        self.overlay._dpr = 2.0

        self.assertEqual(self.overlay._selection_pixel_size(), QSize(600, 400))
        rendered = self.overlay._render_selection()
        self.assertEqual(rendered.size(), QSize(600, 400))

    def test_rounded_selection_output_has_transparent_corners(self):
        self.overlay.resize(160, 120)
        self.overlay.selection = QRect(20, 20, 100, 80)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#ff4d4f"))
        self.overlay._set_corner_radius(24)

        image = self.overlay._render_selection().toImage()

        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(50, 40).alpha(), 255)

    def test_corner_radius_control_has_a_fixed_one_hundred_pixel_range(self):
        self.overlay.selection = QRect(20, 20, 100, 40)

        self.overlay._set_corner_radius(99)
        self.overlay._sync_selection_options()

        self.assertEqual(self.overlay._corner_radius, 99)
        self.assertEqual(self.overlay.selection_options.radius_slider.maximum(), 100)

    def test_shadow_expands_output_and_preserves_transparent_padding(self):
        self.overlay.resize(160, 120)
        self.overlay.selection = QRect(20, 20, 100, 80)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#ff4d4f"))
        self.overlay._set_corner_radius(18)
        self.overlay._set_shadow_enabled(True)

        image = self.overlay._render_selection().toImage()

        self.assertGreater(image.width(), 100)
        self.assertGreater(image.height(), 80)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertGreaterEqual(
            image.pixelColor(image.width() // 2, 12).alpha(),
            30,
        )
        self.assertEqual(
            image.pixelColor(image.width() // 2, image.height() // 2).alpha(),
            255,
        )

    def test_disabling_shadow_keeps_the_selection_output_size(self):
        self.overlay.selection = QRect(20, 20, 100, 80)
        self.overlay._set_shadow_enabled(False)

        self.assertEqual(self.overlay._render_selection().size(), QSize(100, 80))

    def test_text_editor_commits_an_annotation_inline(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        self.overlay._set_font_size(32)
        self.overlay._begin_text_edit(QPoint(80, 90))
        editor = self.overlay._text_editor
        editor.setText("测试文字")
        completed = []
        self.overlay.completed.connect(lambda: completed.append(True))

        QTest.keyClick(editor, Qt.Key_Return)

        self.assertIsNone(self.overlay._text_editor)
        self.assertEqual(self.overlay._annotations[-1]["kind"], "text")
        self.assertEqual(self.overlay._annotations[-1]["text"], "测试文字")
        self.assertEqual(self.overlay._annotations[-1]["font_size"], 32)
        self.assertEqual(self.overlay._annotations[-1]["width"], 4)
        self.assertLess(self.overlay._annotations[-1]["size"].width(), editor.width())
        self.assertEqual(completed, [])

    def test_double_clicking_existing_text_reopens_and_updates_it(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = {
            "kind": "text",
            "start": QPoint(80, 90),
            "end": QPoint(80, 90),
            "color": QColor("#ff4d4f"),
            "width": 4,
            "font_size": 20.0,
            "font_family": self.overlay.font().family(),
            "size": QSize(140, 32),
            "text": "原始文字",
        }
        self.overlay._annotations.append(annotation)
        self.overlay.show()
        self.app.processEvents()

        QTest.mouseDClick(self.overlay, Qt.LeftButton, pos=QPoint(100, 105))

        self.assertIsNotNone(self.overlay._text_editor)
        self.assertEqual(self.overlay._text_editor.text(), "原始文字")
        self.assertEqual(self.overlay._annotations, [])
        self.overlay._text_editor.setText("修改后的文字")
        QTest.keyClick(self.overlay._text_editor, Qt.Key_Return)

        self.assertEqual(len(self.overlay._annotations), 1)
        self.assertIs(self.overlay._annotations[0], annotation)
        self.assertEqual(annotation["text"], "修改后的文字")

    def test_font_family_applies_to_editor_and_annotation(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        family = self.overlay.font().family()
        self.overlay._begin_text_edit(QPoint(80, 90))
        self.overlay._set_font_family(family)

        editor = self.overlay._text_editor
        editor.setText("字体测试")
        self.assertEqual(editor.property("annotationFontFamily"), family)
        QTest.keyClick(editor, Qt.Key_Return)

        self.assertEqual(self.overlay._annotations[-1]["font_family"], family)
        self.assertEqual(self.overlay.toolbar.font_button.toolTip(), family)

    def test_mosaic_uses_an_interpolated_brush_path(self):
        annotation = new_annotation(
            "mosaic",
            QPoint(20, 20),
            QPoint(20, 20),
            self.overlay._color,
            self.overlay._width,
        )

        append_brush_points(annotation, QPoint(120, 20))

        self.assertGreater(len(annotation["points"]), 2)
        self.assertEqual(annotation["points"][-1], QPoint(120, 20))

    def test_eraser_splits_a_pen_into_independent_fragments(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 6
        )
        append_brush_points(pen, QPoint(700, 160))
        eraser = new_annotation(
            "eraser", QPoint(360, 160), QPoint(360, 160), QColor(Qt.white), 6
        )
        append_brush_points(eraser, QPoint(440, 160))
        self.overlay._annotations.append(pen)
        self.overlay._current = eraser
        self.overlay._drag_mode = "annotate"

        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(440, 160)
        self.overlay.mouseReleaseEvent(release)

        fragments = self.overlay._annotations
        self.assertEqual(len(fragments), 2)
        self.assertTrue(all(item["kind"] == "fragment" for item in fragments))
        self.assertTrue(annotation_contains(fragments[0], QPoint(100, 160)))
        self.assertTrue(annotation_contains(fragments[1], QPoint(650, 160)))
        self.assertFalse(any(annotation_contains(item, QPoint(400, 160)) for item in fragments))
        self.assertEqual(
            self.overlay._committed_annotation_layer().toImage().pixelColor(400, 160).alpha(),
            0,
        )
        self.assertIsNone(self.overlay._annotation_at(QPoint(400, 160)))

    def test_eraser_that_misses_visible_pixels_keeps_original_vector(self):
        self.overlay.selection = QRect(0, 0, 160, 120)
        rectangle = new_annotation(
            "rect", QPoint(20, 20), QPoint(120, 90), QColor("#ff4d4f"), 4
        )
        eraser = new_annotation(
            "eraser", QPoint(70, 55), QPoint(70, 55), QColor(Qt.transparent), 4
        )

        result = self.overlay._erase_annotation(rectangle, eraser)

        self.assertEqual(result, [rectangle])
        self.assertIs(result[0], rectangle)

    def test_erased_mosaic_keeps_earlier_annotations_in_untouched_pixels(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        pen = new_annotation(
            "pen", QPoint(20, 45), QPoint(20, 45), QColor("#ff0000"), 20
        )
        append_brush_points(pen, QPoint(100, 45))
        mosaic = new_annotation(
            "mosaic", QPoint(20, 45), QPoint(20, 45), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(100, 45))
        eraser = new_annotation(
            "eraser", QPoint(85, 45), QPoint(85, 45), QColor(Qt.transparent), 4
        )
        self.overlay._annotations.extend((pen, mosaic))

        fragments = self.overlay._erase_annotation(mosaic, eraser)
        self.overlay._annotations = [pen, *fragments]
        self.overlay._invalidate_annotation_layer()
        result = self.overlay._render_selection().toImage()

        self.assertGreater(result.pixelColor(30, 45).red(), 200)
        self.assertLess(result.pixelColor(30, 45).blue(), 80)

    def test_moving_an_erased_fragment_clears_its_original_pixels(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 6
        )
        append_brush_points(pen, QPoint(700, 160))
        eraser = new_annotation(
            "eraser", QPoint(360, 160), QPoint(360, 160), QColor(Qt.white), 6
        )
        append_brush_points(eraser, QPoint(440, 160))
        self.overlay._annotations.append(pen)
        self.overlay._erase_annotations(eraser)
        fragment = min(self.overlay._annotations, key=lambda item: item["start"].x())
        self.overlay._active_annotation = fragment
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(100, 160)
        self.overlay._begin_element_move(fragment)

        self.overlay._move_active_annotation(QPoint(100, 220))
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(100, 220)
        with patch.object(self.overlay, "repaint") as repaint:
            self.overlay.mouseReleaseEvent(release)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(100, 160).alpha(), 0)
        self.assertGreater(layer.pixelColor(100, 220).alpha(), 0)
        self.assertTrue(repaint.called)

    def test_cached_move_preserves_original_annotation_z_order(self):
        self.overlay.selection = QRect(0, 0, 300, 200)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        lower = new_annotation(
            "pen", QPoint(40, 80), QPoint(40, 80), QColor("#ff0000"), 20
        )
        append_brush_points(lower, QPoint(100, 80))
        upper = new_annotation(
            "pen", QPoint(80, 80), QPoint(80, 80), QColor("#0000ff"), 20
        )
        append_brush_points(upper, QPoint(180, 80))
        self.overlay._annotations.extend((lower, upper))
        self.overlay._active_annotation = lower
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(60, 80)
        self.overlay._begin_element_move(lower)
        self.overlay._move_active_annotation(QPoint(100, 80))
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(100, 80)

        self.overlay.mouseReleaseEvent(release)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(50, 80).alpha(), 0)
        self.assertEqual(layer.pixelColor(110, 80), QColor("#0000ff"))

    def test_live_cached_move_preserves_original_annotation_z_order(self):
        self.overlay.selection = QRect(0, 0, 300, 200)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        lower = new_annotation(
            "pen", QPoint(40, 80), QPoint(40, 80), QColor("#ff0000"), 20
        )
        append_brush_points(lower, QPoint(100, 80))
        upper = new_annotation(
            "pen", QPoint(80, 80), QPoint(80, 80), QColor("#0000ff"), 20
        )
        append_brush_points(upper, QPoint(180, 80))
        self.overlay._annotations.extend((lower, upper))
        self.overlay._active_annotation = lower
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(60, 80)
        self.overlay._begin_element_move(lower)
        self.overlay._move_active_annotation(QPoint(100, 80))

        frame = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        frame.fill(Qt.transparent)
        self.overlay.render(frame)

        self.assertEqual(frame.pixelColor(110, 80), QColor("#0000ff"))

    def test_live_cached_move_uses_active_annotation_identity_for_z_order(self):
        self.overlay.selection = QRect(0, 0, 300, 200)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        lower = new_annotation(
            "pen", QPoint(40, 80), QPoint(40, 80), QColor("#ff0000"), 20
        )
        append_brush_points(lower, QPoint(100, 80))
        middle = new_annotation(
            "pen", QPoint(40, 80), QPoint(40, 80), QColor("#0000ff"), 20
        )
        append_brush_points(middle, QPoint(100, 80))
        active = copy.deepcopy(lower)
        self.overlay._annotations.extend((lower, middle, active))
        self.overlay._active_annotation = active
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(60, 80)
        self.overlay._begin_element_move(active)
        self.overlay._move_active_annotation(QPoint(100, 80))

        frame = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        frame.fill(Qt.transparent)
        self.overlay.render(frame)

        self.assertEqual(frame.pixelColor(60, 80), QColor("#0000ff"))

    def test_live_cached_move_feeds_upper_mosaic_from_the_moved_item(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        lower = new_annotation(
            "pen", QPoint(20, 20), QPoint(20, 20), QColor("#ff0000"), 20
        )
        append_brush_points(lower, QPoint(100, 20))
        mosaic = new_annotation(
            "mosaic", QPoint(20, 45), QPoint(20, 45), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(100, 45))
        self.overlay._annotations.extend((lower, mosaic))
        self.overlay._active_annotation = lower
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(60, 20)
        self.overlay._begin_element_move(lower)
        self.overlay._move_active_annotation(QPoint(60, 45))

        frame = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        frame.fill(Qt.transparent)
        self.overlay.render(frame)

        center = frame.pixelColor(60, 45)
        self.assertGreater(center.red(), center.blue())

    def test_live_cached_move_keeps_disjoint_suffix_with_a_mosaic(self):
        self.overlay.resize(180, 180)
        self.overlay.selection = QRect(0, 0, 180, 180)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        active = new_annotation(
            "pen", QPoint(20, 20), QPoint(20, 20), QColor("#ff0000"), 10
        )
        append_brush_points(active, QPoint(80, 20))
        mosaic = new_annotation(
            "mosaic", QPoint(20, 100), QPoint(20, 100), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(80, 100))
        upper = new_annotation(
            "pen", QPoint(20, 150), QPoint(20, 150), QColor("#00ff00"), 10
        )
        append_brush_points(upper, QPoint(80, 150))
        self.overlay._annotations.extend((active, mosaic, upper))
        self.overlay._active_annotation = active
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(40, 20)
        self.overlay._begin_element_move(active)
        self.overlay._move_active_annotation(QPoint(60, 20))

        frame = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        frame.fill(Qt.transparent)
        self.overlay.render(frame)

        self.assertTrue(self.overlay._dynamic_drag_scene().isNull())
        self.assertEqual(frame.pixelColor(50, 150), QColor("#00ff00"))

    def test_mosaic_suffix_does_not_rerasterize_the_cached_active_pen(self):
        self.overlay.resize(800, 500)
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        active = new_annotation(
            "pen", QPoint(20, 40), QPoint(20, 40), QColor("#ff0000"), 4
        )
        active["points"] = [QPoint(index, 40) for index in range(20, 780)]
        active["start"] = QPoint(active["points"][0])
        active["end"] = QPoint(active["points"][-1])
        mosaic = new_annotation(
            "mosaic", QPoint(20, 100), QPoint(20, 100), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(100, 100))
        self.overlay._annotations.extend((active, mosaic))
        self.overlay._active_annotation = active
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(200, 40)

        with patch.object(
            self.overlay,
            "_paint_annotation",
            wraps=self.overlay._paint_annotation,
        ) as paint_annotation:
            self.overlay._begin_element_move(active)

        active_calls = [
            call
            for call in paint_annotation.call_args_list
            if len(call.args) >= 2 and call.args[1] is active
        ]
        self.assertEqual(len(active_calls), 1)

    def test_mosaic_suffix_damage_is_included_in_pointer_update(self):
        self.overlay.resize(320, 220)
        self.overlay.selection = QRect(0, 0, 320, 220)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        active = new_annotation(
            "rect", QPoint(50, 50), QPoint(250, 150), QColor("#ff0000"), 4
        )
        mosaic = new_annotation(
            "mosaic", QPoint(40, 50), QPoint(40, 50), QColor(Qt.black), 12
        )
        append_brush_points(mosaic, QPoint(280, 50))
        self.overlay._annotations.extend((active, mosaic))
        self.overlay._active_annotation = active
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(150, 50)
        self.overlay._begin_element_move(active)
        before = QImage(
            self.overlay.size(), QImage.Format_ARGB32_Premultiplied
        )
        before.fill(Qt.transparent)
        self.overlay.render(before)
        move = Mock()
        move.position.return_value = QPointF(150, 80)

        with patch.object(self.overlay, "update") as update:
            self.overlay.mouseMoveEvent(move)

        dirty = QRegion(update.call_args.args[0])
        after = QImage(
            self.overlay.size(), QImage.Format_ARGB32_Premultiplied
        )
        after.fill(Qt.transparent)
        self.overlay.render(after)
        missed = []
        for y in range(self.overlay.height()):
            for x in range(self.overlay.width()):
                if before.pixel(x, y) != after.pixel(x, y) and not dirty.contains(
                    QPoint(x, y)
                ):
                    missed.append(QPoint(x, y))
                    break
            if missed:
                break
        self.assertEqual(missed, [])

    def test_cached_move_restores_pen_pixels_that_started_outside_selection(self):
        self.overlay.selection = QRect(0, 0, 300, 200)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(20, 0), QPoint(20, 0), QColor("#ff4d4f"), 20
        )
        append_brush_points(pen, QPoint(140, 0))
        self.overlay._annotations.append(pen)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(80, 0)
        self.overlay._begin_element_move(pen)
        self.overlay._move_active_annotation(QPoint(80, 30))
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(80, 30)

        self.overlay.mouseReleaseEvent(release)

        committed = self.overlay._committed_annotation_layer().toImage()
        self.overlay._invalidate_annotation_layer()
        canonical = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(committed, canonical)
        self.assertEqual(committed.pixelColor(80, 0).alpha(), 0)
        self.assertGreater(committed.pixelColor(80, 22).alpha(), 0)

    def test_fractional_dpr_cached_move_matches_canonical_render(self):
        ratio = 1.25
        self.overlay.resize(400, 300)
        self.overlay.selection = QRect(17, 13, 300, 200)
        self.overlay._dpr = ratio
        self.overlay._desktop = QPixmap(
            round(self.overlay.width() * ratio),
            round(self.overlay.height() * ratio),
        )
        self.overlay._desktop.setDevicePixelRatio(ratio)
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(25, 40), QPoint(25, 40), QColor("#ff4d4f"), 7
        )
        append_brush_points(pen, QPoint(305, 190))
        self.overlay._annotations.append(pen)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(100, 100)
        self.overlay._begin_element_move(pen)
        release = Mock()
        release.button.return_value = Qt.LeftButton
        self.overlay._move_active_annotation(QPoint(101, 100))
        release.position.return_value = QPointF(101, 100)

        self.overlay.mouseReleaseEvent(release)

        committed = self.overlay._committed_annotation_layer().toImage()
        self.overlay._invalidate_annotation_layer()
        canonical = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(committed, canonical)

    def test_moving_mosaic_recomposes_old_and_new_pixels(self):
        self.overlay.selection = QRect(0, 0, 300, 200)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#409eff"))
        mosaic = new_annotation(
            "mosaic", QPoint(80, 80), QPoint(80, 80), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(120, 80))
        self.overlay._annotations.append(mosaic)
        self.overlay._committed_annotation_layer()
        self.overlay._active_annotation = mosaic
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(100, 80)
        self.overlay._begin_element_move(mosaic)
        move = Mock()
        move.position.return_value = QPointF(100, 140)

        self.overlay.mouseMoveEvent(move)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(100, 80).alpha(), 0)
        self.assertGreater(layer.pixelColor(100, 140).alpha(), 0)

    def test_overlapping_component_bounds_do_not_duplicate_fragment_pixels(self):
        ratio = 2.0
        self.overlay._dpr = ratio
        image = QImage(200, 200, QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setPen(QPen(QColor("#ff4d4f"), 3))
        painter.drawLine(QPoint(10, 10), QPoint(10, 90))
        painter.drawLine(QPoint(10, 90), QPoint(90, 90))
        painter.drawLine(QPoint(90, 90), QPoint(90, 10))
        painter.drawPoint(QPoint(50, 50))
        painter.end()
        components = self.overlay._image_components(image)
        self.assertEqual(len(components), 2)
        source = {"color": QColor("#ff4d4f"), "width": 3}
        fragments = [
            self.overlay._fragment_from_component(
                image, QRect(0, 0, 100, 100), component, source
            )
            for component in components
        ]

        owners = []
        for fragment in fragments:
            local = QPoint(50, 50) - fragment["start"]
            pixel = QPoint(round(local.x() * ratio), round(local.y() * ratio))
            if (
                fragment["image"].rect().contains(pixel)
                and fragment["image"].pixelColor(pixel).alpha() > 0
            ):
                owners.append(fragment)

        self.assertEqual(len(owners), 1)

        self.overlay.selection = QRect(0, 0, 100, 100)
        self.overlay._desktop = QPixmap(
            round(self.overlay.width() * ratio),
            round(self.overlay.height() * ratio),
        )
        self.overlay._desktop.setDevicePixelRatio(ratio)
        self.overlay._desktop.fill(QColor("#202124"))
        self.overlay._annotations = fragments
        self.overlay._active_annotation = owners[0]
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(50, 50)
        self.overlay._begin_element_move(owners[0])
        self.overlay._move_active_annotation(QPoint(50, 70))
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(50, 70)
        self.overlay.mouseReleaseEvent(release)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(100, 100).alpha(), 0)
        self.assertGreater(layer.pixelColor(100, 140).alpha(), 0)

    def test_drag_preview_dirty_region_covers_every_changed_pixel(self):
        ratio = 2.0
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._dpr = ratio
        self.overlay._desktop = QPixmap(
            round(self.overlay.width() * ratio),
            round(self.overlay.height() * ratio),
        )
        self.overlay._desktop.setDevicePixelRatio(ratio)
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 200), QPoint(40, 200), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 200))
        self.overlay._annotations.append(pen)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(200, 200)
        self.overlay._begin_element_move(pen)

        before = QImage(
            round(self.overlay.width() * ratio),
            round(self.overlay.height() * ratio),
            QImage.Format_ARGB32_Premultiplied,
        )
        before.setDevicePixelRatio(ratio)
        before.fill(Qt.transparent)
        self.overlay.render(before)
        old_region = self.overlay._active_preview_region()

        self.overlay._move_active_annotation(QPoint(237, 229))
        after = QImage(
            round(self.overlay.width() * ratio),
            round(self.overlay.height() * ratio),
            QImage.Format_ARGB32_Premultiplied,
        )
        after.setDevicePixelRatio(ratio)
        after.fill(Qt.transparent)
        self.overlay.render(after)
        dirty = old_region.united(self.overlay._active_preview_region())

        missed = []
        for y in range(before.height()):
            for x in range(before.width()):
                if before.pixel(x, y) != after.pixel(x, y) and not dirty.contains(
                    QPoint(math.floor(x / ratio), math.floor(y / ratio))
                ):
                    missed.append(QPoint(x, y))
                    if len(missed) == 5:
                        break
            if len(missed) == 5:
                break

        self.assertEqual(missed, [])

    def test_starting_a_new_selection_repaints_the_old_frame_immediately(self):
        self.overlay.selection = QRect(100, 100, 300, 200)
        press = Mock()
        press.button.return_value = Qt.LeftButton
        press.position.return_value = QPointF(700, 450)

        with patch.object(self.overlay, "repaint") as repaint:
            self.overlay.mousePressEvent(press)

        self.assertEqual(self.overlay._drag_mode, "select")
        self.assertEqual(self.overlay.selection.topLeft(), QPoint(700, 450))
        self.assertTrue(
            any(call.args and call.args[0] == self.overlay.rect() for call in repaint.call_args_list)
        )

    def test_dragging_outside_an_annotated_selection_starts_a_clean_selection(self):
        self.overlay.selection = QRect(100, 100, 300, 200)
        annotation = new_annotation(
            "rect", QPoint(140, 140), QPoint(260, 220), QColor("#ff4d4f"), 4
        )
        self.overlay._annotations.append(annotation)
        self.overlay._active_annotation = annotation
        press = Mock()
        press.button.return_value = Qt.LeftButton
        press.position.return_value = QPointF(700, 450)

        self.overlay.mousePressEvent(press)

        self.assertEqual(self.overlay._drag_mode, "select")
        self.assertEqual(self.overlay._annotations, [])
        self.assertIsNone(self.overlay._active_annotation)
        self.assertEqual(self.overlay.selection, QRect(QPoint(700, 450), QPoint(700, 450)))

    def test_first_selection_drag_clears_the_previous_magnifier_pixels(self):
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        self.overlay._cursor_pos = QPoint(650, 450)
        magnifier = self.overlay._magnifier_rect(self.overlay._cursor_pos).adjusted(
            -3, -3, 3, 3
        )
        before = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        before.fill(Qt.transparent)
        self.overlay.render(before)
        press = Mock()
        press.button.return_value = Qt.LeftButton
        press.position.return_value = QPointF(650, 450)
        self.overlay.mousePressEvent(press)
        move = Mock()
        move.position.return_value = QPointF(300, 200)

        with patch.object(self.overlay, "update") as update:
            self.overlay.mouseMoveEvent(move)

        after = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        after.fill(Qt.transparent)
        self.overlay.render(after)
        dirty = QRegion(update.call_args.args[0])
        missed = []
        for y in range(magnifier.top(), magnifier.bottom() + 1):
            for x in range(magnifier.left(), magnifier.right() + 1):
                if before.pixel(x, y) != after.pixel(x, y) and not dirty.contains(
                    QPoint(x, y)
                ):
                    missed.append(QPoint(x, y))
                    if len(missed) == 5:
                        break
            if len(missed) == 5:
                break

        self.assertEqual(missed, [])

    def test_active_pen_extends_its_cached_layer_only_for_new_segments(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(600, 160))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        cached_count = self.overlay._current_stroke_point_count

        append_brush_points(pen, QPoint(700, 160))
        dirty = self.overlay._extend_current_stroke_cache()

        self.assertTrue(self.overlay._current_stroke_tiles)
        self.assertEqual(self.overlay._current_stroke_point_count, len(pen["points"]))
        self.assertGreater(self.overlay._current_stroke_point_count, cached_count)
        self.assertLess(dirty.width(), annotation_bounds(pen).width())

    def test_finished_pen_reuses_incremental_tiles_for_first_drag(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 300))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(700, 300)
        self.overlay.mouseReleaseEvent(release)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 220)

        with patch.object(
            self.overlay,
            "_render_drag_preview_layer",
            wraps=self.overlay._render_drag_preview_layer,
        ) as render_preview:
            self.overlay._begin_element_move(pen)

        self.assertFalse(render_preview.called)
        self.assertTrue(self.overlay._drag_preview_tiles)

    def test_selecting_cached_pen_keeps_cache_when_toolbar_width_differs(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 300))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(700, 300)
        self.overlay.mouseReleaseEvent(release)
        self.overlay._active_annotation = None
        self.overlay.toolbar.set_width(10)

        self.overlay._select_annotation(pen)
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 220)
        with patch.object(
            self.overlay,
            "_render_drag_preview_layer",
            wraps=self.overlay._render_drag_preview_layer,
        ) as render_preview:
            self.overlay._begin_element_move(pen)

        self.assertFalse(render_preview.called)

    def test_large_pen_preview_does_not_scan_its_full_alpha_mask(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        pen["points"] = [
            QPoint(40 + index % 700, 100 + (index * 37) % 300)
            for index in range(20_000)
        ]
        pen["start"] = QPoint(pen["points"][0])
        pen["end"] = QPoint(pen["points"][-1])
        self.overlay._annotations.append(pen)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 220)

        with patch.object(self.overlay, "_raster_tile_rects") as alpha_scan:
            self.overlay._begin_element_move(pen)

        alpha_scan.assert_not_called()
        self.assertTrue(self.overlay._drag_preview_tiles)

    def test_moved_pen_keeps_its_raster_preview_at_the_new_geometry(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 160))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(700, 160)
        self.overlay.mouseReleaseEvent(release)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 160)
        self.overlay._begin_element_move(pen)
        self.overlay._drag_preview_offset = QPoint(0, 80)
        release.position.return_value = QPointF(300, 240)
        self.overlay.mouseReleaseEvent(release)
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 240)

        with patch.object(
            self.overlay,
            "_render_drag_preview_layer",
            wraps=self.overlay._render_drag_preview_layer,
        ) as render_preview:
            self.overlay._begin_element_move(pen)

        self.assertFalse(render_preview.called)
        self.assertEqual(self.overlay._drag_preview_bounds.center().y(), 240)

    def test_resizing_finished_pen_keeps_its_configured_stroke_width(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(80, 140), QPoint(80, 140), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(680, 140))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(680, 140)
        self.overlay.mouseReleaseEvent(release)

        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "resize_element"
        self.overlay._handle = "bottom_right"
        self.overlay._drag_start = self.overlay._editable_annotation_bounds().bottomRight()
        self.overlay._begin_element_resize(pen)
        source = QRect(self.overlay._element_bounds_start)
        target = source.adjusted(-20, -30, 80, 30)
        self.overlay._resize_preview_bounds = target
        release.position.return_value = QPointF(target.bottomRight())

        self.overlay.mouseReleaseEvent(release)

        image = self.overlay._committed_annotation_layer().toImage()
        rows = [
            y
            for y in range(image.height())
            if any(image.pixelColor(x, y).alpha() for x in range(image.width()))
        ]
        self.assertLessEqual(max(rows) - min(rows) + 1, pen["width"] + 3)

        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = target.center()
        with patch.object(
            self.overlay,
            "_render_drag_preview_layer",
            wraps=self.overlay._render_drag_preview_layer,
        ) as render_preview:
            self.overlay._begin_element_move(pen)
        self.assertFalse(render_preview.called)

    def test_resized_pen_cache_does_not_capture_other_annotations_in_its_tiles(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        stable = new_annotation(
            "rect", QPoint(100, 100), QPoint(150, 150), QColor("#409eff"), 4
        )
        self.overlay._annotations.append(stable)
        pen = new_annotation(
            "pen", QPoint(40, 200), QPoint(40, 200), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 200))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(700, 200)
        self.overlay.mouseReleaseEvent(release)

        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "resize_element"
        self.overlay._handle = "r"
        self.overlay._drag_start = self.overlay._editable_annotation_bounds().center()
        self.overlay._begin_element_resize(pen)
        self.overlay._resize_preview_bounds.adjust(0, 0, -80, 0)
        self.overlay.mouseReleaseEvent(release)

        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 200)
        self.overlay._begin_element_move(pen)
        self.overlay._drag_preview_offset = QPoint(0, 100)
        self.overlay.mouseReleaseEvent(release)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(100, 125), QColor("#409eff"))
        self.assertEqual(layer.pixelColor(100, 225).alpha(), 0)

    def test_long_pen_resize_commits_geometry_only_on_release(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 4
        )
        append_brush_points(pen, QPoint(700, 300))
        self.overlay._annotations.append(pen)
        self.overlay._active_annotation = pen
        original_points = pen["points"]
        original_revision = pen["_geometry_revision"]
        handle = self.overlay._editable_annotation_bounds().bottomRight()

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=handle)
        QTest.mouseMove(self.overlay, handle + QPoint(-100, 80))

        self.assertEqual(self.overlay._drag_mode, "resize_element")
        self.assertIs(pen["points"], original_points)
        self.assertEqual(pen["_geometry_revision"], original_revision)

        QTest.mouseRelease(
            self.overlay, Qt.LeftButton, pos=handle + QPoint(-100, 80)
        )
        self.assertEqual(pen["_geometry_revision"], original_revision + 1)

    def test_mosaic_uses_a_hollow_brush_cursor(self):
        self.overlay._select_tool("mosaic")

        self.assertFalse(self.overlay.cursor().pixmap().isNull())

    def test_width_slider_and_number_input_stay_synchronized(self):
        self.overlay.toolbar.width_slider.setValue(150)

        self.assertEqual(self.overlay.toolbar.width_spin.value(), 15)
        self.assertEqual(self.overlay._width, 15)
        self.assertEqual(self.overlay.toolbar.width_button.text(), "粗细 15")
        self.assertEqual(self.overlay.toolbar.width_spin.maximum(), 15)

    def test_font_size_has_an_independent_slider_and_number_input(self):
        self.overlay.toolbar.font_size_slider.setValue(365)

        self.assertEqual(self.overlay.toolbar.font_size_spin.value(), 36.5)
        self.assertEqual(self.overlay._font_size, 36.5)
        self.assertEqual(self.overlay.toolbar.font_size_button.text(), "字号 36.5")
        self.assertEqual(self.overlay._width, 4)

    def test_font_size_supports_100_without_resizing_the_text_editor(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        self.overlay.toolbar.font_size_spin.setValue(100)

        self.overlay._begin_text_edit(QPoint(80, 90))

        self.assertEqual(self.overlay._font_size, 100)
        self.assertEqual(self.overlay._text_editor.height(), 38)
        self.assertGreaterEqual(self.overlay.toolbar.font_size_spin.width(), 100)

    def test_clicking_the_active_tool_again_cancels_it(self):
        button = self.overlay.toolbar._tool_buttons["rect"]

        button.click()
        self.assertEqual(self.overlay._tool, "rect")
        button.click()

        self.assertEqual(self.overlay._tool, "")
        self.assertFalse(button.isChecked())

    def test_custom_color_dialog_appears_above_the_overlay(self):
        with patch("fuzztoolbox.tools.screenshot.overlay._raise_window_level"):
            self.overlay._choose_custom_color()
            self.app.processEvents()

        self.assertIsNotNone(self.overlay._color_dialog)
        self.assertTrue(self.overlay._color_dialog.isVisible())
        button_texts = {
            button.text()
            for button in self.overlay._color_dialog.findChildren(QAbstractButton)
        }
        self.assertIn("确定", button_texts)
        self.assertIn("取消", button_texts)

    def test_custom_color_button_does_not_overlap_swatches(self):
        self.overlay.show()
        self.overlay.toolbar.color_palette.show()
        self.app.processEvents()

        swatch_bottom = max(
            swatch.geometry().bottom() for swatch in self.overlay.toolbar._swatches
        )
        custom = self.overlay.toolbar.color_palette.findChildren(QPushButton)[-1]
        self.assertGreater(custom.geometry().top(), swatch_bottom)

    def test_color_value_uses_the_selected_color_and_compact_width(self):
        self.overlay._choose_color(QColor("#19be6b"))

        self.assertEqual(
            self.overlay.toolbar.color_button.display_color, QColor("#19be6b")
        )
        self.assertLess(self.overlay.toolbar.color_button.width(), 132)

    def test_toolbar_buttons_are_vertically_centered_at_one_height(self):
        self.overlay.show()
        self.overlay.toolbar.show()
        self.app.processEvents()
        buttons = self.overlay.toolbar.findChildren(
            QPushButton, "", Qt.FindDirectChildrenOnly
        )

        self.assertTrue(buttons)
        self.assertEqual({button.height() for button in buttons}, {38})
        self.overlay.toolbar._center_buttons()
        self.assertEqual(self.overlay.toolbar.height(), 50)
        top_gaps = {button.geometry().top() for button in buttons}
        bottom_gaps = {
            self.overlay.toolbar.height() - button.geometry().bottom() - 1
            for button in buttons
        }
        self.assertEqual(top_gaps, bottom_gaps)
        self.assertGreaterEqual(next(iter(top_gaps)), 5)

    def test_existing_text_ignores_click_and_can_be_dragged(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = {
            "kind": "text",
            "start": QPoint(80, 90),
            "end": QPoint(80, 90),
            "color": QColor("#ffffff"),
            "width": 4.0,
            "font_size": 20.0,
            "size": QSize(180, 38),
            "text": "可移动文字",
        }
        self.overlay._annotations.append(annotation)

        QTest.mouseClick(self.overlay, Qt.LeftButton, pos=QPoint(100, 105))
        self.assertEqual(annotation["start"], QPoint(80, 90))
        self.assertIs(self.overlay._active_annotation, annotation)
        self.assertEqual(self.overlay.toolbar.width_spin.value(), 4)
        self.assertEqual(self.overlay.toolbar.font_size_spin.value(), 20)

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(100, 105))
        self.overlay._move_text_annotation(QPoint(150, 145))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(150, 145))

        self.assertEqual(annotation["start"], QPoint(130, 130))

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(150, 145))
        self.overlay._move_text_annotation(QPoint(900, 145))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(900, 145))

        self.assertEqual(
            annotation["start"].x() + annotation["size"].width() - 1,
            self.overlay.selection.right(),
        )

    def test_clicking_shape_selects_it_and_syncs_editable_properties(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = {
            "kind": "arrow",
            "start": QPoint(80, 90),
            "end": QPoint(240, 190),
            "color": QColor("#19be6b"),
            "width": 9.0,
        }
        self.overlay._annotations.append(annotation)

        QTest.mouseClick(self.overlay, Qt.LeftButton, pos=QPoint(160, 140))

        self.assertIs(self.overlay._active_annotation, annotation)
        self.assertEqual(self.overlay._color, QColor("#19be6b"))
        self.assertEqual(self.overlay.toolbar.width_spin.value(), 9)
        self.overlay.toolbar.width_spin.setValue(12)
        self.overlay._choose_color(QColor("#409eff"))
        self.assertEqual(annotation["width"], 12)
        self.assertEqual(annotation["color"], QColor("#409eff"))

    def test_dragging_selected_shape_moves_it_without_finishing_capture(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = new_annotation(
            "arrow", QPoint(80, 90), QPoint(240, 190), self.overlay._color, 6
        )
        self.overlay._annotations.append(annotation)
        completed = []
        self.overlay.completed.connect(lambda: completed.append(True))

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(160, 140))
        QTest.mouseMove(self.overlay, QPoint(200, 170))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(200, 170))

        self.assertEqual(annotation["start"], QPoint(120, 120))
        self.assertEqual(annotation["end"], QPoint(280, 220))
        self.assertEqual(completed, [])

    def test_delete_key_removes_the_selected_annotation(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = new_annotation(
            "rect", QPoint(80, 90), QPoint(240, 190), self.overlay._color, 6
        )
        self.overlay._annotations.append(annotation)
        self.overlay._select_annotation(annotation)

        QTest.keyClick(self.overlay, Qt.Key_Delete)

        self.assertEqual(self.overlay._annotations, [])
        self.assertIsNone(self.overlay._active_annotation)

    def test_selected_shape_can_be_resized_from_its_anchor(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = new_annotation(
            "rect", QPoint(80, 90), QPoint(240, 190), self.overlay._color, 6
        )
        self.overlay._annotations.append(annotation)
        self.overlay._select_annotation(annotation)

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(240, 190))
        QTest.mouseMove(self.overlay, QPoint(320, 250))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(320, 250))

        self.assertEqual(annotation["start"], QPoint(80, 90))
        self.assertEqual(annotation["end"], QPoint(320, 250))

    def test_double_clicking_shape_does_not_finish_capture(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = new_annotation(
            "rect", QPoint(80, 90), QPoint(240, 190), self.overlay._color, 6
        )
        self.overlay._annotations.append(annotation)
        completed = []
        self.overlay.completed.connect(lambda: completed.append(True))

        QTest.mouseDClick(self.overlay, Qt.LeftButton, pos=QPoint(80, 140))

        self.assertIs(self.overlay._active_annotation, annotation)
        self.assertEqual(completed, [])

    def test_font_list_is_exempt_from_frozen_canvas_input_lock(self):
        view = self.overlay.toolbar.font_combo.view()

        self.assertTrue(self.overlay._is_control_event_target(view))
        self.assertTrue(self.overlay._is_control_event_target(view.viewport()))
        self.assertFalse(self.overlay._is_control_event_target(self.overlay))

    @unittest.skipUnless(
        platform.system() == "Darwin",
        "macOS-only: verifies native scroll routing through a visible font "
        "popup; on Windows the QComboBox popup is a native window whose "
        "internal view() is not reported visible in CI",
    )
    def test_visible_font_popup_accepts_native_scroll_routing(self):
        self.overlay.show()
        self.overlay.toolbar.font_panel.show()
        self.overlay.toolbar.font_combo.showPopup()
        self.overlay._install_input_lock()
        self.app.processEvents()

        self.assertTrue(self.overlay.toolbar.font_combo.view().isVisible())
        self.assertFalse(
            self.overlay.eventFilter(self.overlay.toolbar, QEvent(QEvent.Wheel))
        )
        self.assertEqual(
            self.overlay.toolbar.font_combo.view().verticalScrollBar().objectName(),
            "screenshotFontScrollBar",
        )
        scroll_bar = self.overlay.toolbar.font_combo.view().verticalScrollBar()
        self.assertEqual(
            self.overlay.toolbar.font_combo.view().frameShape(), QFrame.NoFrame
        )
        self.assertIn("border: 0", scroll_bar.styleSheet())
        self.assertIn("outline: 0", scroll_bar.styleSheet())
        scroll_bar.setValue(scroll_bar.minimum())
        wheel = QWheelEvent(
            QPointF(20, 20),
            QPointF(
                self.overlay.toolbar.font_combo.view().mapToGlobal(QPoint(20, 20))
            ),
            QPoint(),
            QPoint(0, -120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(
            self.overlay.toolbar.font_combo.view().viewport(), wheel
        )
        self.assertGreater(scroll_bar.value(), scroll_bar.minimum())
        self.overlay.toolbar.font_combo.hidePopup()

    def test_font_scrollbar_is_fully_custom_painted_without_white_frame(self):
        scroll_bar = ScreenshotScrollBar(Qt.Vertical)
        scroll_bar.resize(12, 180)
        scroll_bar.setRange(0, 100)
        scroll_bar.setPageStep(20)
        scroll_bar.show()
        self.app.processEvents()

        image = scroll_bar.grab().toImage()
        for point in (QPoint(0, 0), QPoint(11, 0), QPoint(0, 179), QPoint(11, 179)):
            self.assertNotEqual(image.pixelColor(point), QColor(Qt.white))
        scroll_bar.close()

    def test_selection_handles_use_directional_resize_cursors(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        expected = {
            "tl": Qt.SizeFDiagCursor,
            "t": Qt.SizeVerCursor,
            "tr": Qt.SizeBDiagCursor,
            "r": Qt.SizeHorCursor,
            "br": Qt.SizeFDiagCursor,
            "b": Qt.SizeVerCursor,
            "bl": Qt.SizeBDiagCursor,
            "l": Qt.SizeHorCursor,
        }

        for handle, cursor in expected.items():
            self.overlay._refresh_hover_cursor(
                handle_points(self.overlay.selection)[handle]
            )
            self.assertEqual(self.overlay.cursor().shape(), cursor)

    def test_resizing_selection_preserves_existing_annotations(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        annotation = new_annotation(
            "rect",
            QPoint(150, 150),
            QPoint(240, 220),
            self.overlay._color,
            self.overlay._width,
        )
        self.overlay._annotations.append(annotation)

        QTest.mousePress(
            self.overlay,
            Qt.LeftButton,
            pos=handle_points(self.overlay.selection)["br"],
        )
        self.overlay.selection = resize_selection(
            self.overlay._selection_start,
            self.overlay._handle,
            QPoint(550, 450),
            self.overlay.rect(),
        )
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(550, 450))

        self.assertEqual(self.overlay._annotations, [annotation])

    def test_empty_selection_can_still_be_moved(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        self.overlay._select_tool("", False)

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(300, 250))
        QTest.mouseMove(self.overlay, QPoint(350, 280))

        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(350, 280))

        self.assertEqual(self.overlay.selection.topLeft(), QPoint(150, 130))

    def test_moving_selection_uses_pixels_from_the_new_screen_region(self):
        self.overlay.resize(120, 60)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#ff4d4f"))
        painter = QPainter(self.overlay._desktop)
        painter.fillRect(QRect(60, 0, 60, 60), QColor("#409eff"))
        painter.end()
        self.overlay.selection = QRect(0, 0, 40, 40)

        self.overlay._committed_annotation_layer()
        self.overlay.selection = QRect(70, 0, 40, 40)

        rendered = self.overlay._render_selection().toImage()
        self.assertEqual(rendered.pixelColor(20, 20), QColor("#409eff"))

    def test_toolbar_and_option_panels_use_the_standard_arrow_cursor(self):
        self.assertEqual(self.overlay.toolbar.cursor().shape(), Qt.ArrowCursor)
        for panel in (
            self.overlay.toolbar.color_palette,
            self.overlay.toolbar.width_panel,
            self.overlay.toolbar.font_size_panel,
            self.overlay.toolbar.font_panel,
        ):
            self.assertEqual(panel.cursor().shape(), Qt.ArrowCursor)

    def test_annotations_lock_selection_until_the_last_annotation_is_undone(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        annotation = new_annotation(
            "rect",
            QPoint(150, 150),
            QPoint(240, 220),
            self.overlay._color,
            self.overlay._width,
        )
        self.overlay._annotations.append(annotation)
        original = QRect(self.overlay.selection)

        QTest.mousePress(
            self.overlay,
            Qt.LeftButton,
            pos=handle_points(self.overlay.selection)["br"],
        )
        QTest.mouseMove(self.overlay, QPoint(650, 500))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(650, 500))
        self.assertEqual(self.overlay.selection, original)

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(300, 250))
        QTest.mouseMove(self.overlay, QPoint(360, 290))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(360, 290))
        self.assertEqual(self.overlay.selection, original)

        self.overlay._undo()
        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(300, 250))
        QTest.mouseMove(self.overlay, QPoint(360, 290))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(360, 290))
        self.assertEqual(self.overlay.selection.topLeft(), QPoint(160, 140))

    def test_undo_after_element_move_restores_position_instead_of_deleting(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        annotation = new_annotation(
            "rect",
            QPoint(150, 150),
            QPoint(240, 220),
            self.overlay._color,
            self.overlay._width,
        )

        # Commit a drawn annotation so an "add" undo step is recorded.
        self.overlay._current = annotation
        self.overlay._drag_mode = "annotate"
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(240, 220)
        self.overlay.mouseReleaseEvent(release)
        self.assertIn(annotation, self.overlay._annotations)

        # Move the element by (80, 80).
        self.overlay._active_annotation = annotation
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(180, 180)
        self.overlay._begin_element_move(annotation)
        self.overlay._move_active_annotation(QPoint(260, 260))
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(260, 260)
        self.overlay.mouseReleaseEvent(release)
        self.assertEqual(annotation["start"], QPoint(230, 230))

        # Undo must revert the move, not delete the annotation.
        self.overlay._undo()
        self.assertIn(annotation, self.overlay._annotations)
        self.assertEqual(annotation["start"], QPoint(150, 150))

        # A second undo removes the drawn annotation.
        self.overlay._undo()
        self.assertNotIn(annotation, self.overlay._annotations)

    def test_undo_after_element_resize_restores_original_geometry(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        annotation = new_annotation(
            "rect",
            QPoint(150, 150),
            QPoint(240, 220),
            self.overlay._color,
            self.overlay._width,
        )
        self.overlay._annotations.append(annotation)
        self.overlay._active_annotation = annotation
        self.overlay._drag_mode = "resize_element"
        self.overlay._handle = "bottom_right"
        self.overlay._drag_start = QPoint(240, 220)
        self.overlay._begin_element_resize(annotation)
        source = QRect(self.overlay._element_bounds_start)
        target = source.adjusted(0, 0, 60, 40)
        self.overlay._resize_preview_bounds = target
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(target.bottomRight())
        self.overlay.mouseReleaseEvent(release)
        self.assertEqual(annotation["end"], QPoint(300, 260))

        self.overlay._undo()
        self.assertIn(annotation, self.overlay._annotations)
        self.assertEqual(annotation["start"], QPoint(150, 150))
        self.assertEqual(annotation["end"], QPoint(240, 220))

    def test_undo_after_erase_restores_original_annotations(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(40, 160), QPoint(40, 160), QColor("#ff4d4f"), 6
        )
        append_brush_points(pen, QPoint(700, 160))
        self.overlay._annotations.append(pen)
        self.overlay._current = new_annotation(
            "eraser",
            QPoint(360, 160),
            QPoint(360, 160),
            QColor(Qt.white),
            6,
        )
        append_brush_points(self.overlay._current, QPoint(440, 160))
        self.overlay._drag_mode = "annotate"
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(440, 160)
        self.overlay.mouseReleaseEvent(release)
        self.assertEqual(len(self.overlay._annotations), 2)

        self.overlay._undo()
        self.assertEqual(len(self.overlay._annotations), 1)
        self.assertIs(self.overlay._annotations[0], pen)

    def test_selection_handles_are_not_painted_after_annotation_is_added(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        self.overlay._annotations.append(
            new_annotation(
                "rect",
                QPoint(150, 150),
                QPoint(240, 220),
                self.overlay._color,
                self.overlay._width,
            )
        )

        with patch.object(self.overlay, "_paint_handles") as paint_handles:
            self.overlay.render(QPixmap(self.overlay.size()))

        paint_handles.assert_not_called()

    def test_dragging_from_an_existing_element_starts_the_active_tool(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        existing = new_annotation(
            "rect",
            QPoint(150, 150),
            QPoint(240, 220),
            self.overlay._color,
            self.overlay._width,
        )
        self.overlay._annotations.append(existing)
        self.overlay._select_tool("arrow")

        with patch.object(
            self.overlay,
            "_annotation_at",
            wraps=self.overlay._annotation_at,
        ) as annotation_at:
            QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(150, 180))
            QTest.mouseMove(self.overlay, QPoint(260, 260))
            QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(260, 260))

        self.assertEqual(len(self.overlay._annotations), 2)
        self.assertEqual(self.overlay._annotations[-1]["kind"], "arrow")
        self.assertEqual(self.overlay._annotations[-1]["start"], QPoint(150, 180))
        annotation_at.assert_not_called()

    def test_committed_annotations_are_not_repainted_on_every_frame(self):
        self.overlay.selection = QRect(100, 100, 400, 300)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        for offset in range(120):
            self.overlay._annotations.append(
                new_annotation(
                    "rect",
                    QPoint(110 + offset, 120),
                    QPoint(140 + offset, 150),
                    self.overlay._color,
                    self.overlay._width,
                )
            )

        with patch.object(
            self.overlay,
            "_paint_annotation",
            wraps=self.overlay._paint_annotation,
        ) as paint_annotation:
            first_frame = QPixmap(self.overlay.size())
            self.overlay.render(first_frame)
            first_frame_calls = paint_annotation.call_count
            second_frame = QPixmap(self.overlay.size())
            self.overlay.render(second_frame)

        self.assertEqual(first_frame_calls, len(self.overlay._annotations))
        self.assertEqual(paint_annotation.call_count, first_frame_calls)

    def test_mosaic_samples_annotations_that_were_drawn_before_it(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        pen = new_annotation(
            "pen", QPoint(20, 45), QPoint(20, 45), QColor("#ff0000"), 20
        )
        append_brush_points(pen, QPoint(100, 45))
        mosaic = new_annotation(
            "mosaic", QPoint(20, 45), QPoint(20, 45), QColor(Qt.black), 8
        )
        append_brush_points(mosaic, QPoint(100, 45))
        self.overlay._annotations.extend((pen, mosaic))
        self.overlay._invalidate_annotation_layer()

        result = self.overlay._committed_annotation_layer().toImage()
        center = result.pixelColor(60, 45)

        self.assertGreater(center.red(), center.blue())

    def test_mosaic_composite_is_cached_between_pointer_frames(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        layer = self.overlay._committed_annotation_layer()

        first = self.overlay._annotation_composite(layer)
        second = self.overlay._annotation_composite(layer)

        self.assertIs(first, second)
        self.overlay._invalidate_annotation_layer()
        rebuilt_layer = self.overlay._committed_annotation_layer()
        rebuilt = self.overlay._annotation_composite(rebuilt_layer)
        self.assertIsNot(rebuilt, first)

    def test_eraser_restores_the_frozen_desktop_under_annotations(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#0055ff"))
        pen = new_annotation(
            "pen", QPoint(20, 45), QPoint(20, 45), QColor("#ff0000"), 20
        )
        append_brush_points(pen, QPoint(100, 45))
        eraser = new_annotation(
            "eraser", QPoint(60, 45), QPoint(60, 45), QColor(Qt.transparent), 8
        )
        self.overlay._annotations.extend((pen, eraser))
        self.overlay._invalidate_annotation_layer()

        result = self.overlay._render_selection().toImage()

        self.assertEqual(result.pixelColor(60, 45), QColor("#0055ff"))
        self.assertEqual(result.pixelColor(30, 45), QColor("#ff0000"))

    def test_eraser_clears_annotation_pixels_instead_of_repainting_background(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#2166cc"))
        pen = new_annotation(
            "pen", QPoint(10, 45), QPoint(10, 45), QColor("#ff4d4f"), 24
        )
        append_brush_points(pen, QPoint(110, 45))
        eraser = new_annotation(
            "eraser", QPoint(60, 45), QPoint(60, 45), QColor(Qt.transparent), 8
        )
        self.overlay._annotations.extend((pen, eraser))
        self.overlay._invalidate_annotation_layer()

        annotation_layer = self.overlay._committed_annotation_layer().toImage()

        self.assertEqual(annotation_layer.pixelColor(60, 45).alpha(), 0)
        self.assertGreater(annotation_layer.pixelColor(30, 45).alpha(), 0)

    def test_eraser_has_a_hard_square_edge_and_leaves_no_blended_pixels(self):
        self.overlay.resize(120, 90)
        self.overlay.selection = QRect(0, 0, 120, 90)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#2166cc"))
        pen = new_annotation(
            "pen", QPoint(10, 45), QPoint(10, 45), QColor("#ff4d4f"), 24
        )
        append_brush_points(pen, QPoint(110, 45))
        eraser = new_annotation(
            "eraser", QPoint(60, 45), QPoint(60, 45), QColor(Qt.transparent), 8
        )
        self.overlay._annotations.extend((pen, eraser))
        self.overlay._invalidate_annotation_layer()

        result = self.overlay._render_selection().toImage()

        for y in range(34, 57):
            for x in range(49, 72):
                self.assertEqual(result.pixelColor(x, y), QColor("#2166cc"))

    def test_element_resize_dirty_region_covers_old_selection_handles(self):
        self.overlay.selection = QRect(20, 20, 600, 400)
        annotation = new_annotation(
            "arrow", QPoint(120, 100), QPoint(120, 260), QColor("#ff4d4f"), 1
        )
        self.overlay._annotations.append(annotation)
        self.overlay._active_annotation = annotation
        self.overlay._drag_mode = "resize_element"

        dirty = self.overlay._active_draw_region()

        for point in handle_points(self.overlay._editable_annotation_bounds()).values():
            handle_rect = QRect(point.x() - 4, point.y() - 4, 8, 8)
            self.assertTrue(dirty.contains(handle_rect))

    def test_resized_preview_dirty_region_covers_every_changed_pixel(self):
        self.overlay.selection = QRect(20, 20, 800, 540)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        annotation = new_annotation(
            "rect", QPoint(100, 100), QPoint(200, 200), QColor("#ff4d4f"), 4
        )
        self.overlay._annotations.append(annotation)
        self.overlay._active_annotation = annotation
        self.overlay._drag_mode = "resize_element"
        self.overlay._handle = "br"
        self.overlay._begin_element_resize(annotation)
        before = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        before.fill(Qt.transparent)
        self.overlay.render(before)
        old_region = self.overlay._active_preview_region()

        self.overlay._resize_preview_bounds = QRect(100, 100, 401, 401)
        after = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        after.fill(Qt.transparent)
        self.overlay.render(after)
        dirty = old_region.united(self.overlay._active_preview_region())

        missed = []
        for y in range(before.height()):
            for x in range(before.width()):
                if before.pixel(x, y) != after.pixel(x, y) and not dirty.contains(
                    QPoint(x, y)
                ):
                    missed.append(QPoint(x, y))
                    if len(missed) == 5:
                        break
            if len(missed) == 5:
                break
        self.assertEqual(missed, [])

    def test_large_rectangle_preview_repaints_only_its_outline(self):
        self.overlay.resize(1920, 1080)
        self.overlay.selection = QRect(0, 0, 1920, 1080)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        rectangle = new_annotation(
            "rect", QPoint(10, 10), QPoint(1900, 1060), QColor("#ff4d4f"), 4
        )
        self.overlay._annotations.append(rectangle)
        self.overlay._active_annotation = rectangle
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(10, 10)

        self.overlay._begin_element_move(rectangle)

        region = self.overlay._active_preview_region()
        dirty_area = sum(rect.width() * rect.height() for rect in region)
        self.assertLess(dirty_area, self.overlay.width() * self.overlay.height() // 4)

    def test_flat_ellipse_resize_dirty_region_covers_every_changed_pixel(self):
        self.overlay.resize(900, 600)
        self.overlay.selection = QRect(0, 0, 900, 600)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        ellipse = new_annotation(
            "ellipse", QPoint(50, 250), QPoint(850, 270), QColor("#ff4d4f"), 4
        )
        self.overlay._annotations.append(ellipse)
        self.overlay._active_annotation = ellipse
        self.overlay._drag_mode = "resize_element"
        self.overlay._handle = "b"
        self.overlay._begin_element_resize(ellipse)
        before = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        before.fill(Qt.transparent)
        self.overlay.render(before)
        old_region = self.overlay._active_preview_region()

        self.overlay._resize_preview_bounds = QRect(50, 240, 801, 61)
        after = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        after.fill(Qt.transparent)
        self.overlay.render(after)
        dirty = old_region.united(self.overlay._active_preview_region())

        missed = []
        for y in range(before.height()):
            for x in range(before.width()):
                if before.pixel(x, y) != after.pixel(x, y) and not dirty.contains(
                    QPoint(x, y)
                ):
                    missed.append(QPoint(x, y))
                    if len(missed) == 5:
                        break
            if len(missed) == 5:
                break
        self.assertEqual(missed, [])

    def test_element_edit_recomposes_only_the_affected_annotation_region(self):
        self.overlay.resize(900, 600)
        self.overlay.selection = QRect(20, 20, 840, 540)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        for row in range(10):
            for column in range(20):
                left = 30 + column * 40
                top = 30 + row * 45
                self.overlay._annotations.append(
                    new_annotation(
                        "rect",
                        QPoint(left, top),
                        QPoint(left + 18, top + 18),
                        QColor("#409eff"),
                        2,
                    )
                )
        active = new_annotation(
            "arrow", QPoint(100, 520), QPoint(170, 520), QColor("#ff4d4f"), 6
        )
        self.overlay._annotations.append(active)
        self.overlay._committed_annotation_layer()
        self.overlay._active_annotation = active
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(130, 520)
        self.overlay._element_start = active.copy()
        self.overlay._element_bounds_start = self.overlay._editable_annotation_bounds()
        old_region = self.overlay._active_draw_region()

        with patch.object(
            self.overlay,
            "_paint_annotation",
            wraps=self.overlay._paint_annotation,
        ) as paint_annotation:
            self.overlay._move_active_annotation(QPoint(230, 520))
            dirty = old_region.united(self.overlay._active_draw_region())
            self.overlay._refresh_annotation_layer_region(dirty)

        layer = self.overlay._committed_annotation_layer().toImage()
        self.assertEqual(layer.pixelColor(115, 500).alpha(), 0)
        self.assertGreater(layer.pixelColor(215, 500).alpha(), 0)
        self.assertLess(paint_annotation.call_count, 20)

    def test_vector_drag_previews_without_rebuilding_a_long_pen(self):
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        annotation = new_annotation(
            "pen", QPoint(40, 80), QPoint(40, 80), QColor("#ff4d4f"), 4
        )
        annotation["points"] = [QPoint(40 + index, 80) for index in range(600)]
        annotation["start"] = QPoint(annotation["points"][0])
        annotation["end"] = QPoint(annotation["points"][-1])
        annotation["_point_bounds"] = QRect(
            annotation["points"][0], annotation["points"][-1]
        ).normalized()
        annotation["_point_bounds_count"] = len(annotation["points"])
        self.overlay._annotations.append(annotation)
        self.overlay._committed_annotation_layer()
        self.overlay._active_annotation = annotation
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(180, 80)
        self.overlay._begin_element_move(annotation)
        original_points = annotation["points"]
        original_revision = annotation["_geometry_revision"]

        self.overlay._move_active_annotation(QPoint(220, 100))

        self.assertIs(annotation["points"], original_points)
        self.assertEqual(annotation["_geometry_revision"], original_revision)
        self.assertEqual(self.overlay._drag_preview_offset, QPoint(40, 20))
        self.assertFalse(self.overlay._drag_base_layer.isNull())
        self.assertTrue(self.overlay._drag_preview_tiles)
        self.assertFalse(self.overlay._active_preview_region().isEmpty())

        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(220, 100)
        self.overlay.mouseReleaseEvent(release)

        self.assertEqual(annotation["start"], QPoint(80, 100))
        self.assertEqual(annotation["_geometry_revision"], original_revision + 1)
        self.assertIsNone(self.overlay._drag_preview_annotation)
        self.assertTrue(self.overlay._drag_preview_layer.isNull())
        self.assertEqual(self.overlay._drag_preview_tiles, [])
        self.assertTrue(self.overlay._drag_base_layer.isNull())

        with patch.object(self.overlay, "_paint_annotation") as paint_annotation:
            self.overlay._committed_annotation_layer()
        self.assertFalse(paint_annotation.called)

    def test_fast_drag_scene_matches_the_regular_composition_pixel_for_pixel(self):
        self.overlay.selection = QRect(40, 40, 760, 480)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        pen = new_annotation(
            "pen", QPoint(80, 180), QPoint(80, 180), QColor("#ff4d4f"), 6
        )
        append_brush_points(pen, QPoint(700, 300))
        self.overlay._current = pen
        self.overlay._drag_mode = "annotate"
        self.overlay._begin_current_stroke_cache()
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(700, 300)
        self.overlay.mouseReleaseEvent(release)
        self.overlay.toolbar.hide()
        self.overlay.selection_options.hide()
        self.overlay._active_annotation = pen
        self.overlay._drag_mode = "move_element"
        self.overlay._drag_start = QPoint(300, 220)
        self.overlay._begin_element_move(pen)
        self.overlay._drag_preview_offset = QPoint(30, 20)

        fast = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        fast.fill(Qt.transparent)
        self.overlay.render(fast)
        scene = QPixmap(self.overlay._drag_scene_layer)
        self.overlay._drag_scene_layer = QPixmap()
        regular = QImage(self.overlay.size(), QImage.Format_ARGB32_Premultiplied)
        regular.fill(Qt.transparent)
        self.overlay.render(regular)
        self.overlay._drag_scene_layer = scene

        self.assertEqual(fast, regular)

    def test_fast_pen_drag_keeps_the_stroke_continuous_on_retina_dpr(self):
        self.overlay._dpr = 2.0
        self.overlay.selection = QRect(0, 0, 800, 500)
        self.overlay._desktop = QPixmap(self.overlay.size())
        self.overlay._desktop.fill(QColor("#202124"))
        self.overlay._color = QColor("#ff0000")
        self.overlay._width = 4
        self.overlay._select_tool("pen")
        press = Mock()
        press.button.return_value = Qt.LeftButton
        press.position.return_value = QPointF(40, 60)
        self.overlay.mousePressEvent(press)
        for x, y in [(260, 90), (500, 140), (760, 240), (760, 480)]:
            move = Mock()
            move.position.return_value = QPointF(x, y)
            self.overlay.mouseMoveEvent(move)
        release = Mock()
        release.button.return_value = Qt.LeftButton
        release.position.return_value = QPointF(760, 480)
        self.overlay.mouseReleaseEvent(release)
        self.overlay.toolbar.hide()
        self.overlay.selection_options.hide()

        points = self.overlay._annotations[-1]["points"]
        self.assertGreater(len(points), 64)
        image = self.overlay._committed_annotation_layer().toImage()
        gaps = 0
        for index in range(1, len(points)):
            a, b = points[index - 1], points[index]
            midpoint = QPoint((a.x() + b.x()) // 2, (a.y() + b.y()) // 2)
            physical_x = round(midpoint.x() * self.overlay._dpr)
            physical_y = round(midpoint.y() * self.overlay._dpr)
            if (
                0 <= physical_x < image.width()
                and 0 <= physical_y < image.height()
                and image.pixelColor(physical_x, physical_y).alpha() < 128
            ):
                gaps += 1
        self.assertEqual(gaps, 0)

    def test_clicking_a_detected_window_selects_its_region(self):
        candidate = QRect(120, 80, 500, 360)
        self.overlay._window_candidates = [candidate]

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(200, 160))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(200, 160))

        self.assertEqual(self.overlay.selection, candidate)

    def test_keep_main_mode_includes_current_process_in_window_detection(self):
        overlay = ScreenshotOverlay(include_app_window=True)
        overlay._virtual = QRect(0, 0, 900, 600)
        shot = QPixmap(900, 600)
        shot.fill(Qt.black)

        with patch(
            "fuzztoolbox.tools.screenshot.overlay.enumerate_window_rects",
            return_value=[],
        ) as enumerate_rects, patch(
            "fuzztoolbox.tools.screenshot.overlay._raise_window_level"
        ):
            overlay._show_overlay([(overlay._virtual, shot)])

        enumerate_rects.assert_called_once_with(include_current_process=True)
        overlay._remove_input_lock()
        overlay.close()
        overlay.deleteLater()

    def test_frontmost_window_wins_when_windows_overlap(self):
        front_window = QRect(100, 80, 700, 460)
        hidden_smaller_window = QRect(300, 200, 240, 180)
        self.overlay._window_candidates = [front_window, hidden_smaller_window]

        self.assertEqual(
            self.overlay._window_at(QPoint(400, 260)), front_window
        )

    def test_clicking_desktop_wallpaper_selects_the_current_screen(self):
        screen = QRect(0, 0, 900, 600)
        self.overlay._window_candidates = [QRect(100, 80, 300, 240)]
        self.overlay._screen_candidates = [screen]

        QTest.mousePress(self.overlay, Qt.LeftButton, pos=QPoint(700, 500))
        QTest.mouseRelease(self.overlay, Qt.LeftButton, pos=QPoint(700, 500))

        self.assertEqual(self.overlay.selection, screen)

    def test_space_selects_the_current_screen(self):
        screen = QRect(0, 0, 900, 600)
        self.overlay._screen_candidates = [screen]
        self.overlay._cursor_pos = QPoint(450, 300)

        QTest.keyClick(self.overlay, Qt.Key_Space)

        self.assertEqual(self.overlay.selection, screen)

    def test_zoom_keyboard_shortcuts_are_consumed(self):
        for key in (Qt.Key_Plus, Qt.Key_Minus, Qt.Key_Equal, Qt.Key_0):
            event = QKeyEvent(QEvent.KeyPress, key, Qt.MetaModifier)

            self.overlay.keyPressEvent(event)

            self.assertTrue(event.isAccepted())

    def test_native_gestures_are_consumed_by_the_overlay(self):
        event = QEvent(QEvent.NativeGesture)

        handled = self.overlay.event(event)

        self.assertTrue(handled)
        self.assertTrue(event.isAccepted())

    def test_screenshot_session_blocks_zoom_events_on_child_widgets(self):
        self.overlay._install_input_lock()
        event_types = (
            QEvent.Wheel,
            QEvent.NativeGesture,
            QEvent.Gesture,
            QEvent.TouchUpdate,
        )

        for event_type in event_types:
            event = QEvent(event_type)
            self.assertTrue(self.overlay.eventFilter(self.overlay.toolbar, event))
            self.assertTrue(event.isAccepted())

        self.overlay._remove_input_lock()
        self.assertFalse(self.overlay._input_lock_installed)

    def test_frozen_desktop_overlay_cannot_be_resized_from_its_edges(self):
        geometry = QRect(-300, 40, 1600, 900)

        self.overlay._lock_overlay_geometry(geometry)

        self.assertEqual(self.overlay.pos(), geometry.topLeft())
        self.assertEqual(self.overlay.size(), geometry.size())
        self.assertEqual(self.overlay.minimumSize(), geometry.size())
        self.assertEqual(self.overlay.maximumSize(), geometry.size())

    def test_macos_dock_fallback_supports_bottom_and_side_docks(self):
        geometry = QRect(0, 0, 1440, 900)

        bottom = macos_dock_regions(geometry, QRect(0, 30, 1440, 810))
        left = macos_dock_regions(geometry, QRect(80, 30, 1360, 870))

        self.assertEqual(bottom, [QRect(0, 840, 1440, 60)])
        self.assertEqual(left, [QRect(0, 0, 80, 900)])

    def test_save_uses_the_native_dialog_with_a_timestamped_name(self):
        pixmap = QPixmap(10, 10)
        pixmap.fill(Qt.white)
        self.overlay._render_selection = Mock(return_value=pixmap)

        with patch("fuzztoolbox.tools.screenshot.overlay._raise_window_level"):
            self.overlay._save()
            self.app.processEvents()

        self.assertIsNotNone(self.overlay._save_dialog)
        self.assertTrue(self.overlay._save_dialog.isVisible())
        self.assertFalse(
            self.overlay._save_dialog.testOption(QFileDialog.DontUseNativeDialog)
        )
        self.assertRegex(
            self.overlay._save_dialog.selectedFiles()[0],
            r"截图_\d{4}-\d{2}-\d{2}_\d{6}\.png$",
        )

    def test_failed_save_keeps_the_capture_session_open(self):
        pixmap = Mock()
        pixmap.save.return_value = False

        with patch(
            "fuzztoolbox.tools.screenshot.overlay.QMessageBox.critical"
        ) as critical:
            self.overlay._save_to_path(pixmap, "/not-writable/截图")

        pixmap.save.assert_called_once_with("/not-writable/截图.png", "PNG")
        critical.assert_called_once()
        self.assertFalse(self.overlay._closing)


if __name__ == "__main__":
    unittest.main()
