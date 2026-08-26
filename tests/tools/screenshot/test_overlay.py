import platform
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QFrame,
    QPushButton,
)

from fuzztoolbox.tools.screenshot.annotations import (
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

    def test_mosaic_uses_a_hollow_brush_cursor(self):
        self.overlay._select_tool("mosaic")

        self.assertFalse(self.overlay.cursor().pixmap().isNull())

    def test_width_slider_and_number_input_stay_synchronized(self):
        self.overlay.toolbar.width_slider.setValue(170)

        self.assertEqual(self.overlay.toolbar.width_spin.value(), 17)
        self.assertEqual(self.overlay._width, 17)
        self.assertEqual(self.overlay.toolbar.width_button.text(), "粗细 17")

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
