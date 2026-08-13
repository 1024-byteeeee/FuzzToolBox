import math
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QEasingCurve, QRect, Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication, QImage, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QTableView,
)

from fuzztoolbox.ui.main_window import (
    FOOTER_COPYRIGHT,
    THEME_MODES,
    WINDOWS_APP_ID,
    MainWindow,
    configure_windows_app_id,
    restore_window_placement,
    show_main_window,
)
from fuzztoolbox.tools.ip_scanner.page import ResultModel, ScanWorker
from fuzztoolbox.tools.ip_scanner.models import ScanConfig
from fuzztoolbox.ui.home_page import ToolboxHomePage
from fuzztoolbox.ui.home_page import ThemeToggleButton
from fuzztoolbox.ui.line_number_editor import LineNumberEditor
from fuzztoolbox.ui.theme import STYLE
from fuzztoolbox.tools.ip_scanner.models import ScanResult
from fuzztoolbox.core.network_info import NetworkInfo
from fuzztoolbox.tools.subnet_calculator.calculator import FLSMPlan, parse_network
from fuzztoolbox.tools.subnet_calculator.page import FETCH_BATCH_SIZE, SubnetResultModel
from fuzztoolbox.ui.tool_registry import TOOLS, filter_tools
from fuzztoolbox.ui.components import (
    ComboItemDelegate,
    ComboListView,
    GridCellDelegate,
    configure_combo,
    configure_table,
)


class ResultModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_app_id_is_registered_for_taskbar_icon(self):
        shell32 = Mock()
        windll = Mock(shell32=shell32)
        with patch("fuzztoolbox.ui.main_window.sys.platform", "win32"), patch(
            "fuzztoolbox.ui.main_window.ctypes.windll", windll, create=True
        ):
            configure_windows_app_id()

        shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            WINDOWS_APP_ID
        )

    def test_windows_main_window_is_shown_exactly_once(self):
        window = Mock()
        window.centralWidget.return_value = None
        window._start_maximized = False
        show_main_window(window)

        window.ensurePolished.assert_called_once_with()
        window.show.assert_called_once_with()
        window.showMaximized.assert_not_called()
        window.hide.assert_not_called()
        window.setAttribute.assert_not_called()
        window.setWindowOpacity.assert_not_called()

    def test_maximized_window_is_mapped_maximized_without_normal_show(self):
        window = Mock()
        window.centralWidget.return_value = None
        window._start_maximized = True
        show_main_window(window)

        window.showMaximized.assert_called_once_with()
        window.show.assert_not_called()

    def test_tiny_saved_geometry_is_replaced_before_first_show(self):
        window = Mock()
        window.rect.return_value = QRect(0, 0, 1180, 760)
        settings = Mock()
        settings.value.side_effect = lambda key, *args, **kwargs: {
            "window/normalGeometry": QRect(50, 50, 320, 240),
            "window/maximized": False,
            "window/geometry": None,
        }.get(key)
        screen = Mock()
        screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)

        with patch(
            "fuzztoolbox.ui.main_window.QGuiApplication.screens", return_value=[screen]
        ), patch(
            "fuzztoolbox.ui.main_window.QGuiApplication.primaryScreen",
            return_value=screen,
        ):
            restored = restore_window_placement(window, settings)

        self.assertFalse(restored)
        window.resize.assert_called_once_with(1180, 760)
        window.move.assert_called_once()

    def test_visible_full_size_saved_geometry_is_preserved(self):
        window = Mock()
        settings = Mock()
        normal_geometry = QRect(80, 60, 1180, 760)
        settings.value.side_effect = lambda key, *args, **kwargs: {
            "window/normalGeometry": normal_geometry,
            "window/maximized": True,
            "window/geometry": None,
        }.get(key)
        screen = Mock()
        screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)

        with patch(
            "fuzztoolbox.ui.main_window.QGuiApplication.screens", return_value=[screen]
        ):
            restored = restore_window_placement(window, settings)

        self.assertTrue(restored)
        window.setGeometry.assert_called_once_with(normal_geometry)
        self.assertTrue(window._start_maximized)
        window.resize.assert_not_called()
        window.move.assert_not_called()

    def test_scan_worker_cancel_reaches_scanner_and_force_cancels_task(self):
        worker = ScanWorker("192.0.2.1", ScanConfig(), NetworkInfo())
        worker.scanner = Mock()
        worker.scan_task = Mock()
        worker.scan_task.done.return_value = False
        worker.loop = Mock()
        worker.loop.call_soon_threadsafe.side_effect = lambda callback: callback()

        worker.cancel(force=True)

        worker.scanner.cancel.assert_called_once_with()
        worker.scan_task.cancel.assert_called_once_with()
        self.assertTrue(worker._cancel_requested.is_set())

    def test_detail_update_replaces_existing_ip_without_adding_a_row(self):
        model = ResultModel()
        model.add_batch(
            [
                ScanResult(
                    ip="192.168.1.20",
                    is_alive=True,
                    method="ping",
                    details_pending=True,
                )
            ]
        )
        model.add_batch(
            [
                ScanResult(
                    ip="192.168.1.20",
                    is_alive=True,
                    method="ping",
                    hostname="printer.local",
                    mac="00:11:22:33:44:55",
                )
            ]
        )

        self.assertEqual(model.rowCount(), 1)
        self.assertEqual(model.results[0].hostname, "printer.local")
        self.assertEqual(model.results[0].mac, "00:11:22:33:44:55")

    def test_tool_registry_filters_by_keyword_and_category(self):
        self.assertEqual(filter_tools(TOOLS, "Ping")[0].id, "ip-scanner")
        self.assertEqual(filter_tools(TOOLS, category="网络工具")[0].id, "ip-scanner")
        self.assertEqual(filter_tools(TOOLS, "JSON")[0].id, "json-formatter")
        self.assertEqual(filter_tools(TOOLS, "GUID")[0].id, "uuid-generator")
        self.assertEqual(filter_tools(TOOLS, "十六进制")[0].id, "ipv4-converter")
        self.assertEqual(filter_tools(TOOLS, "二维码")[0].id, "qr-generator")
        self.assertEqual(filter_tools(TOOLS, "SSID")[0].id, "wifi-qr-generator")
        self.assertEqual(filter_tools(TOOLS, "色轮")[0].id, "color-picker")
        self.assertEqual(filter_tools(TOOLS, "ASN")[0].id, "ip-lookup")
        self.assertEqual(filter_tools(TOOLS, "罗马")[0].id, "roman-numeral")
        self.assertEqual(filter_tools(TOOLS, "熵")[0].id, "password-strength")
        self.assertEqual(filter_tools(TOOLS, "随机端口")[0].id, "random-port")
        self.assertEqual(filter_tools(TOOLS, "倒计时")[0].id, "timer")
        self.assertEqual(filter_tools(TOOLS, "Unified")[0].id, "text-comparer")
        self.assertEqual(filter_tools(TOOLS, "字数")[0].id, "text-statistics")
        self.assertEqual(filter_tools(TOOLS, "时间戳")[0].id, "datetime-converter")

    def test_every_tool_has_a_unique_existing_svg_icon(self):
        assets = Path(__file__).resolve().parents[2] / "src" / "fuzztoolbox" / "assets"
        icons = [tool.icon for tool in TOOLS]
        self.assertEqual(len(icons), len(set(icons)))
        for icon in icons:
            self.assertTrue(icon.startswith("tool-"))
            self.assertTrue(icon.endswith(".svg"))
            self.assertTrue((assets / icon).is_file())

    def test_subnet_model_loads_huge_ipv6_plan_progressively(self):
        model = SubnetResultModel()
        model.set_flsm(FLSMPlan(parse_network("2001:db8::/32"), 64))
        self.assertEqual(model.total, 1 << 32)
        self.assertEqual(model.rowCount(), FETCH_BATCH_SIZE)
        self.assertTrue(model.canFetchMore())
        model.fetchMore()
        self.assertEqual(model.rowCount(), FETCH_BATCH_SIZE * 2)
        row = model.jump_to_index(model.total - 1)
        self.assertLessEqual(model.rowCount(), FETCH_BATCH_SIZE)
        self.assertEqual(
            model.data(model.index(row, 2)), "2001:db8:ffff:ffff::/64"
        )

    def test_common_combo_and_table_interactions_are_applied(self):
        combo = QComboBox()
        configure_combo(combo)
        self.assertIsInstance(combo.view(), ComboListView)
        self.assertIsInstance(combo.view().itemDelegate(), ComboItemDelegate)
        self.assertIn("background: transparent", combo.view().styleSheet())
        self.assertIn("border-radius: 8px", combo.view().styleSheet())
        self.assertIn("QListView::item:hover", combo.view().styleSheet())
        self.assertIn("background: transparent", combo.view().viewport().styleSheet())
        self.assertTrue(combo.view().window().property("fuzztoolboxPopupPrepared"))
        self.assertEqual(combo.view().window().objectName(), "comboPopupContainer")
        self.assertIn("QFrame#comboPopupContainer", combo.view().window().styleSheet())
        self.assertIn("border-radius: 8px", combo.view().window().styleSheet())

        table = QTableView()
        configure_table(table)
        self.assertIsInstance(table.itemDelegate(), GridCellDelegate)
        self.assertEqual(table.selectionBehavior(), QTableView.SelectItems)

    def test_line_number_editor_resizes_gutter_and_marks_error_line(self):
        editor = LineNumberEditor()
        initial_width = editor.line_number_area_width()
        editor.setPlainText("\n".join(str(index) for index in range(120)))
        self.app.processEvents()
        self.assertEqual(editor.blockCount(), 120)
        self.assertGreater(editor.line_number_area_width(), initial_width)
        editor.set_error_line(100)
        self.assertEqual(editor._error_line, 100)
        editor.clear_error_line()
        self.assertIsNone(editor._error_line)
        editor.close()

    def test_subnet_page_keeps_return_button_available_and_shows_network(self):
        from fuzztoolbox.tools.subnet_calculator.page import SubnetCalculatorPage

        info = NetworkInfo(
            interface="Ethernet",
            ip="192.168.8.42",
            prefix_length=24,
            gateway="192.168.8.1",
        )
        page = SubnetCalculatorPage(info)
        page.resize(1180, 760)
        page.show()
        self.app.processEvents()

        self.assertTrue(page.reset_window_button.isEnabled())
        self.assertIn("本机网络  Ethernet", page.network_label.text())
        self.assertIn("IP 192.168.8.42", page.network_label.text())
        self.assertEqual(page.input_layout.columnMinimumWidth(0), 78)
        self.assertEqual(page.input_layout.columnStretch(1), 3)
        self.assertTrue(page.base_network_label.alignment() & Qt.AlignRight)
        self.assertGreaterEqual(page.table.columnWidth(2), 150)
        for column in (4, 5, 6):
            self.assertGreaterEqual(page.table.columnWidth(column), 125)

        page.base_network.setText("2001:db8::/32")
        page.flsm_value.setText("64")
        page.calculate()
        page.locate_ip.setText("2001:db8:ffff:ffff::1")
        page.locate()
        self.assertGreater(page.model.window_start, 0)
        page.return_to_start()
        self.assertEqual(page.model.window_start, 0)
        self.assertEqual(page.table.currentIndex().row(), 0)
        self.assertTrue(page.reset_window_button.isEnabled())
        page.close()

    def test_home_page_search_hides_unmatched_tool(self):
        page = ToolboxHomePage()
        page.search.setText("绝对不存在的工具名称")
        self.app.processEvents()
        self.assertTrue(page.cards["ip-scanner"].isHidden())
        self.assertEqual(page.empty_label.text(), "没有找到匹配的工具")

    def test_ipv4_converter_presents_grouped_cards_and_inline_errors(self):
        from fuzztoolbox.tools.ipv4_converter.page import IPv4ConverterPage

        page = IPv4ConverterPage(NetworkInfo(ip="192.168.1.10", prefix_length=24))
        self.assertFalse(hasattr(page, "table"))
        self.assertFalse(hasattr(page, "copy_selected_button"))
        self.assertEqual(page.hero_value.text(), "192.168.1.10")
        self.assertEqual([label.text() for label in page.octet_labels], ["192", "168", "1", "10"])
        self.assertEqual(page.result_cards["十六进制"].value, "0xC0A8010A")
        self.assertIn(".", page.result_cards["二进制"].value)
        page.result_cards["IPv6（简写）"].copy_button.click()
        self.assertEqual(QGuiApplication.clipboard().text(), "::ffff:192.168.1.10")
        self.assertEqual(page.result_cards["IPv6（简写）"].copy_button.text(), "已复制")
        page.resize(760, 700)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._result_columns, 1)
        page.resize(760, 430)
        self.app.processEvents()
        self.assertGreater(page.scroll_area.verticalScrollBar().maximum(), 0)
        page.input.setText("999.1.1.1")
        page.convert()
        self.assertIn("无法转换", page.result_state.text())
        self.assertFalse(page.copy_all_button.isEnabled())
        page.resize(1100, 760)
        self.app.processEvents()
        self.assertLessEqual(page.network_label.height(), page.network_label.sizeHint().height() + 2)
        self.assertLessEqual(page.input.parentWidget().height(), 100)
        page.close()

    def test_password_strength_eye_action_toggles_visibility(self):
        from PySide6.QtWidgets import QLineEdit
        from fuzztoolbox.tools.password_strength.page import PasswordStrengthPage

        page = PasswordStrengthPage()
        self.assertEqual(page.password_input.echoMode(), QLineEdit.Password)
        self.assertEqual(page.visibility_action.text(), "显示密码")
        page.visibility_action.trigger()
        self.assertEqual(page.password_input.echoMode(), QLineEdit.Normal)
        self.assertEqual(page.visibility_action.text(), "隐藏密码")
        page.visibility_action.trigger()
        self.assertEqual(page.password_input.echoMode(), QLineEdit.Password)

    def test_timer_inputs_validate_ranges_and_include_milliseconds(self):
        from PySide6.QtWidgets import QAbstractSpinBox
        from fuzztoolbox.tools.timer.page import TimerPage

        page = TimerPage()
        self.assertEqual(
            (
                page.hours.value(),
                page.minutes.value(),
                page.seconds.value(),
                page.milliseconds.value(),
            ),
            (1, 0, 2, 4),
        )
        self.assertEqual(page.selected_seconds(), 3602.004)
        self.assertEqual(page.display.text(), "01:00:02.004")
        self.assertEqual((page.hours.minimum(), page.hours.maximum()), (0, 99))
        self.assertEqual((page.minutes.minimum(), page.minutes.maximum()), (0, 59))
        self.assertEqual((page.seconds.minimum(), page.seconds.maximum()), (0, 59))
        self.assertEqual(
            (page.milliseconds.minimum(), page.milliseconds.maximum()), (0, 999)
        )
        for field in (page.hours, page.minutes, page.seconds, page.milliseconds):
            self.assertEqual(field.alignment(), Qt.AlignCenter)
            self.assertEqual(field.lineEdit().alignment(), Qt.AlignCenter)
            self.assertEqual(field.buttonSymbols(), QAbstractSpinBox.NoButtons)

        page.hours.setValue(0)
        page.minutes.setValue(0)
        page.seconds.setValue(0)
        page.milliseconds.setValue(0)
        self.assertEqual(page.timer_state.duration, 0)
        self.assertEqual(page.display.text(), "00:00:00.000")
        self.assertEqual(
            {shortcut.key().toString() for shortcut in page.control_shortcuts},
            {"Space", "Return", "Enter"},
        )
        page.milliseconds.setValue(1)
        self.assertEqual(page.selected_seconds(), 0.001)
        self.assertEqual(page.display.text(), "00:00:00.001")

        page.set_mode("stopwatch")
        self.assertTrue(page.stopwatch_mode_button.isChecked())
        self.assertFalse(page.countdown_mode_button.isChecked())
        self.assertTrue(page.progress.isHidden())
        self.assertTrue(all(card.isHidden() for card in page.time_input_cards))
        self.assertEqual(page.display.text(), "00:00:00.000")
        self.assertTrue(page.pause_button.isHidden())
        self.assertFalse(page.stopwatch_tip.isHidden())
        self.assertEqual(page.stopwatch_tip.text(), "Tips：空格 & 回车均可控制开始按钮")
        self.assertEqual(page.start_button.text(), "开始")
        self.assertEqual(page.start_button.property("styleState"), "idle")
        page.start()
        self.assertEqual(page.start_button.text(), "暂停")
        page.handle_space_shortcut()
        self.assertEqual(page.start_button.text(), "继续")
        page.handle_space_shortcut()
        self.assertEqual(page.start_button.text(), "暂停")
        self.assertEqual(page.start_button.property("styleState"), "running")
        page.start()
        self.assertEqual(page.start_button.text(), "继续")
        self.assertEqual(page.start_button.property("styleState"), "paused")
        page.start()
        self.assertEqual(page.start_button.text(), "暂停")

    def test_main_window_navigates_between_home_and_scanner(self):
        with patch("fuzztoolbox.tools.ip_scanner.page.get_network_info") as network_info:
            network_info.return_value.scan_range = None
            network_info.return_value.cidr = None
            network_info.return_value.display_text.return_value = "未知"
            window = MainWindow()
        window.resize(1000, 700)
        window.show()
        self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.home_page)
        self.assertTrue(window.top_bar.isHidden())
        self.assertEqual(window.home_page.title.text(), "Fuzz Tool Box")
        window.open_tool("ip-scanner")
        self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.ip_scanner_page)
        self.assertFalse(window.top_bar.isHidden())
        self.assertFalse(window.back_button.isHidden())
        self.assertEqual(window.back_button.text(), "←  返回主页")
        self.assertFalse(window.page_icon.pixmap().isNull())
        self.assertGreater(
            window.back_button.geometry().center().x(),
            window.page_title.geometry().center().x(),
        )
        table = window.ip_scanner_page.table
        column_width = sum(
            table.horizontalHeader().sectionSize(index)
            for index in range(table.model().columnCount())
        )
        self.assertEqual(column_width, table.viewport().width())
        window.open_tool("subnet-calculator")
        self.assertIs(window.pages.currentWidget(), window.subnet_calculator_page)
        self.assertIn("子网划分计算器", window.page_title.text())
        window.open_tool("uuid-generator")
        self.assertIs(window.pages.currentWidget(), window.uuid_generator_page)
        self.assertIn("UUID 生成器", window.page_title.text())
        window.open_tool("roman-numeral")
        self.assertIs(window.pages.currentWidget(), window.roman_numeral_page)
        self.assertIn("罗马数字转换器", window.page_title.text())
        window.open_tool("password-strength")
        self.assertIs(window.pages.currentWidget(), window.password_strength_page)
        self.assertIn("密码强度分析器", window.page_title.text())
        window.open_tool("random-port")
        self.assertIs(window.pages.currentWidget(), window.random_port_page)
        self.assertIn("随机端口生成器", window.page_title.text())
        window.open_tool("timer")
        self.assertIs(window.pages.currentWidget(), window.timer_page)
        self.assertIn("计时器", window.page_title.text())
        window.open_tool("text-statistics")
        self.assertIs(window.pages.currentWidget(), window.text_statistics_page)
        self.assertIn("文本统计工具", window.page_title.text())
        window.open_tool("ipv4-converter")
        self.assertIs(window.pages.currentWidget(), window.ipv4_converter_page)
        self.assertIn("IPv4 地址转换器", window.page_title.text())
        self.assertIn("本机网络", window.ipv4_converter_page.network_label.text())
        window.open_tool("qr-generator")
        self.assertIs(window.pages.currentWidget(), window.qr_generator_page)
        self.assertIn("二维码生成器", window.page_title.text())
        window.open_tool("wifi-qr-generator")
        self.assertIs(window.pages.currentWidget(), window.wifi_qr_generator_page)
        self.assertIn("WiFi 二维码生成器", window.page_title.text())
        window.open_tool("color-picker")
        self.assertIs(window.pages.currentWidget(), window.color_picker_page)
        self.assertIn("取色器", window.page_title.text())
        window.show_home()
        self.assertIs(window.pages.currentWidget(), window.home_page)
        self.assertTrue(window.top_bar.isHidden())
        window.close()

    def test_macos_close_hides_window_and_explicit_quit_cleans_up(self):
        with patch("fuzztoolbox.tools.ip_scanner.page.get_network_info") as network_info:
            network_info.return_value.scan_range = None
            network_info.return_value.cidr = None
            network_info.return_value.display_text.return_value = "未知"
            window = MainWindow()
        window.show()
        self.app.processEvents()
        window.ip_scanner_page.prepare_close = Mock(return_value=True)
        window.ip_lookup_page.prepare_close = Mock(return_value=True)

        with patch("fuzztoolbox.ui.main_window.sys.platform", "darwin"):
            close_event = QCloseEvent()
            window.closeEvent(close_event)
            self.assertFalse(close_event.isAccepted())
            self.assertTrue(window.isHidden())
            window.ip_scanner_page.prepare_close.assert_not_called()

            window.restore_from_application_activation(Qt.ApplicationActive)
            self.assertTrue(window.isVisible())

            with patch("fuzztoolbox.ui.main_window.QTimer.singleShot") as single_shot:
                window.request_application_quit()
                self.assertTrue(window._application_quitting)
                window.ip_scanner_page.prepare_close.assert_called_once()
                window.ip_lookup_page.prepare_close.assert_called_once()
                single_shot.assert_called_once()
        window.hide()

    def test_labels_use_transparent_background(self):
        self.assertIn("QLabel { background: transparent; }", STYLE)

    def test_spinbox_hover_controls_stay_inside_the_frame(self):
        self.assertIn("subcontrol-origin: padding", STYLE)
        self.assertIn("margin-right: 1px", STYLE)
        self.assertIn("margin-top: 1px", STYLE)
        self.assertIn("margin-bottom: 1px", STYLE)
        self.assertNotIn("subcontrol-origin: border; width: 25px", STYLE)
        self.assertIn("QCheckBox { background: transparent;", STYLE)
        self.assertIn("QCheckBox::indicator:unchecked", STYLE)
        self.assertIn("QCheckBox::indicator:checked", STYLE)
        self.assertNotIn("%CHECKBOX_", STYLE)

    def test_every_button_role_has_hover_and_pressed_feedback(self):
        for selector in (
            "QPushButton:hover",
            "QPushButton:pressed",
            "QPushButton#secondary:hover",
            "QPushButton#secondary:pressed",
            "QPushButton#neutral:hover",
            "QPushButton#neutral:pressed",
            "QPushButton#danger:hover",
            "QPushButton#danger:pressed",
            "QPushButton#categoryButton:hover",
            "QPushButton#categoryButton:pressed",
        ):
            self.assertIn(selector, STYLE)

    def test_back_button_is_green_outline_and_returns_home(self):
        self.assertIn("QPushButton#backButton {", STYLE)
        self.assertIn("background: transparent; color: #27ae60", STYLE)

    def test_footer_copyright_is_english_only(self):
        self.assertEqual(FOOTER_COPYRIGHT, "© 2026 1024_byteeeee. All rights reserved.")
        self.assertNotIn("版权所有", FOOTER_COPYRIGHT)

    def test_theme_modes_have_stable_labels(self):
        self.assertEqual(THEME_MODES, ("system", "light", "dark"))

    def test_theme_toggle_icon_uses_smooth_hover_animation(self):
        button = ThemeToggleButton()
        self.assertEqual(button.iconSize(), ThemeToggleButton.NORMAL_ICON_SIZE)
        self.assertGreater(
            ThemeToggleButton.HOVER_ICON_SIZE.width(),
            ThemeToggleButton.NORMAL_ICON_SIZE.width(),
        )
        self.assertEqual(button._icon_animation.duration(), 160)
        self.assertEqual(button._icon_animation.easingCurve().type(), QEasingCurve.InOutCubic)

    def test_named_uuid_versions_use_one_deterministic_result(self):
        from fuzztoolbox.tools.uuid_generator.page import UUIDGeneratorPage

        page = UUIDGeneratorPage()
        page.version.setCurrentIndex(page.version.findData(5))
        self.assertEqual(page.count.value(), 1)
        self.assertFalse(page.count.isEnabled())
        self.assertIn("确定性", page.count.toolTip())
        page.version.setCurrentIndex(page.version.findData(4))
        self.assertTrue(page.count.isEnabled())

    def test_wifi_qr_open_network_disables_password_and_can_preview(self):
        from fuzztoolbox.tools.wifi_qr_generator.page import WiFiQRGeneratorPage

        page = WiFiQRGeneratorPage()
        page.ssid.setText("Guest WiFi")
        page.security.setCurrentIndex(page.security.findData("nopass"))
        page.generate()
        self.assertFalse(page.password.isEnabled())
        self.assertFalse(page.show_password.isEnabled())
        self.assertTrue(page.png_data.startswith(b"\x89PNG"))
        page.security.setCurrentIndex(page.security.findData("WPA"))
        self.assertTrue(page.password.isEnabled())

    def test_qr_color_dialog_initializes_before_first_interaction(self):
        from fuzztoolbox.tools.qr_generator.components import ColorButton

        button = ColorButton("#409EFF", "选择颜色")
        self.assertTrue(button._dialog.testOption(QColorDialog.DontUseNativeDialog))
        self.assertEqual(button._dialog.windowTitle(), "选择颜色")
        with patch.object(button._dialog, "exec", return_value=QDialog.Rejected), patch(
            "fuzztoolbox.tools.qr_generator.components.QTimer.singleShot"
        ) as single_shot:
            button.choose_color()
        self.assertEqual(button._dialog.currentColor().name(), "#409eff")
        callback = single_shot.call_args.args[1]
        callback()
        self.assertEqual(button._dialog.currentColor().name(), "#409eff")
        button.close()

    def test_color_picker_keeps_rgb_and_all_outputs_in_sync(self):
        from fuzztoolbox.tools.color_picker.page import ColorPickerPage

        page = ColorPickerPage()
        self.assertEqual(page.alpha.value(), 100)
        self.assertEqual(page.opacity_slider.value(), 100)
        self.assertEqual(page.outputs["hex"].text(), "#409EFF")
        page.red.setValue(255)
        page.green.setValue(0)
        page.blue.setValue(128)
        page.alpha.setValue(50)
        self.app.processEvents()

        self.assertEqual(page.outputs["hex"].text(), "#FF008080")
        self.assertEqual(page.outputs["rgb"].text(), "rgb(255 0 128 / 50%)")
        self.assertEqual(set(page.outputs), {"hex", "rgb", "hsl", "hwb", "lch", "cmyk"})
        self.assertEqual(page.opacity_slider.value(), 50)
        self.assertLessEqual(page.red.width(), 82)
        page.opacity_slider.setValue(25)
        self.assertEqual(page.alpha.value(), 25)
        self.assertTrue(page.outputs["hsl"].text().endswith("/ 25%)"))
        page.copy_all()
        self.assertIn("HEX: #FF008040", self.app.clipboard().text())
        self.assertIn("CMYK: device-cmyk(", self.app.clipboard().text())
        page.close()

    def test_color_picker_sv_drag_does_not_move_hue_indicator(self):
        from PySide6.QtCore import QPointF

        from fuzztoolbox.tools.color_picker.page import ColorPickerPage

        page = ColorPickerPage()
        page.wheel.resize(520, 520)
        page.wheel._hue = 217.35
        _center, _radius, _ring_width, square = page.wheel._geometry()
        page.wheel._drag_target = "sv"
        page.wheel._update_from_point(QPointF(square.center().x(), square.center().y()))
        self.app.processEvents()

        self.assertEqual(page.wheel._hue, 217.35)
        page.close()

    def test_color_wheel_uses_antialiased_vector_gradient(self):
        from fuzztoolbox.tools.color_picker.color_wheel import ColorWheel

        wheel = ColorWheel()
        wheel.resize(360, 360)
        image = QImage(360, 360, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        wheel.render(image)

        center, outer_radius, ring_width, _square = wheel._geometry()
        radius = outer_radius - ring_width / 2
        red = image.pixelColor(round(center.x() + radius), round(center.y()))
        green = image.pixelColor(
            round(center.x() + math.cos(math.radians(120)) * radius),
            round(center.y() - math.sin(math.radians(120)) * radius),
        )
        self.assertGreater(red.red(), 240)
        self.assertLess(red.green(), 25)
        self.assertGreater(green.green(), 220)
        self.assertFalse(hasattr(wheel, "_wheel_image"))
        wheel.close()

    def test_ip_lookup_has_named_input_default_ip_and_progress_animation(self):
        from fuzztoolbox.tools.ip_lookup.page import IPLookupPage

        page = IPLookupPage()
        self.assertEqual(page.ip_label.text(), "IP 地址")
        self.assertTrue(page.progress.isHidden())
        self.assertEqual(page.progress.minimum(), 0)
        self.assertEqual(page.progress.maximum(), 0)

        page._public_ip_pending = True
        with patch.object(page, "start_lookup") as start_lookup:
            page._set_public_ip("8.8.8.8", "2001:4860:4860::8888")
        self.assertEqual(page.ip_input.text(), "8.8.8.8")
        start_lookup.assert_called_once_with()
        self.assertEqual(page.result_card.objectName(), "ipLookupResultCard")

        page._public_ip_pending = True
        page.ip_input.setEnabled(False)
        page.query_button.setEnabled(False)
        page._public_ip_timed_out()
        self.assertTrue(page.ip_input.isEnabled())
        self.assertTrue(page.query_button.isEnabled())
        self.assertIn("30 秒", page.status.text())
        page.close()

    def test_ip_lookup_refreshes_each_time_the_page_is_opened(self):
        from fuzztoolbox.tools.ip_lookup.page import IPLookupPage

        page = IPLookupPage()
        page._load_public_ip = Mock()
        page.show()
        self.app.processEvents()
        page.hide()
        self.app.processEvents()
        page.show()
        self.app.processEvents()

        self.assertEqual(page._load_public_ip.call_count, 2)
        page.close()

    def test_ip_lookup_disables_input_for_the_whole_query(self):
        from fuzztoolbox.tools.ip_lookup.page import IPLookupPage, LookupWorker

        page = IPLookupPage()
        page.ip_input.setText("8.8.8.8")
        with patch.object(LookupWorker, "start"):
            page.start_lookup()
        self.assertFalse(page.ip_input.isEnabled())
        self.assertFalse(page.query_button.isEnabled())
        self.assertFalse(page.my_ip_button.isEnabled())

        page._lookup_finished()
        self.assertTrue(page.ip_input.isEnabled())
        self.assertTrue(page.query_button.isEnabled())
        self.assertTrue(page.my_ip_button.isEnabled())
        page.close()

    def test_ip_lookup_has_a_button_to_refresh_the_public_ip(self):
        from fuzztoolbox.tools.ip_lookup.page import IPLookupPage

        page = IPLookupPage()
        self.assertEqual(page.my_ip_button.text(), "查询当前公网 IP")
        self.assertEqual(page.my_ip_button.objectName(), "secondary")
        page.close()

    def test_ip_lookup_presents_grouped_cards_loading_and_copy_feedback(self):
        from fuzztoolbox.tools.ip_lookup.page import IPLookupPage
        from fuzztoolbox.tools.ip_lookup.service import LookupReport, SourceResult

        page = IPLookupPage()
        page._show_loading_state()
        self.assertTrue(page.loading_timer.isActive())
        self.assertIn("正在整理", page.result_state.text())
        report = LookupReport(
            ip="8.8.8.8",
            classification="IPv4 · 公网地址",
            ptr="dns.google",
            current_ipv4="1.1.1.1",
            sources=[SourceResult("test", {
                "country": "United States", "region": "California", "city": "Mountain View",
                "asn": "AS15169", "isp": "Google LLC", "org": "Google",
            })],
        )
        page._show_report(report)
        self.assertFalse(page.result_state.isVisibleTo(page))
        self.assertEqual(page.hero_ip.text(), "8.8.8.8")
        self.assertEqual(page.version_badge.text(), "IPv4")
        self.assertEqual(page.result_values["ptr"].value, "dns.google")
        page.result_values["asn"].copy_button.click()
        self.assertEqual(QGuiApplication.clipboard().text(), "AS15169")
        self.assertEqual(page.result_values["asn"].copy_button.text(), "已复制")
        page._load_public_ip = Mock()
        page.resize(760, 700)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._result_columns, 1)
        page._show_error("服务暂不可用")
        self.assertIn("服务暂不可用", page.result_state.text())
        self.assertFalse(page.copy_button.isEnabled())
        page.close()

    def test_token_generator_defaults_and_actions(self):
        from fuzztoolbox.tools.token_generator.generator import MAX_LENGTH
        from fuzztoolbox.tools.token_generator.page import TokenGeneratorPage

        page = TokenGeneratorPage()
        self.assertEqual(page.length.value(), 64)
        self.assertEqual(page.length.maximum(), MAX_LENGTH)
        self.assertTrue(page.lowercase.isChecked())
        self.assertTrue(page.uppercase.isChecked())
        self.assertTrue(page.digits.isChecked())
        self.assertFalse(page.symbols.isChecked())
        self.assertEqual(page.generate_button.text(), "生成 Token")
        self.assertEqual(page.copy_button.text(), "复制")
        self.assertEqual(len(page.current_token), 64)
        page.close()

    def test_datetime_converter_supports_units_timezones_and_copyable_results(self):
        from fuzztoolbox.tools.datetime_converter.page import DateTimeConverterPage

        page = DateTimeConverterPage()
        self.assertEqual(page.mode.currentData(), "datetime")
        self.assertTrue(page._live_preview)
        self.assertEqual(page.resume_live_button.text(), "恢复实时更新")
        self.assertFalse(page.resume_live_button.isEnabled())
        self.assertRegex(page.input.text(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")
        self.assertGreaterEqual(len(page.result_rows), 15)
        self.assertFalse(hasattr(page, "table"))
        self.assertFalse(hasattr(page, "copy_selected_button"))
        self.assertIn("ISO 8601", page.result_cards)
        page.resize(760, 700)
        page.show()
        self.app.processEvents()
        self.assertEqual(page._card_columns, 1)
        page.resize(1100, 700)
        self.app.processEvents()
        self.assertEqual(page._card_columns, 2)
        first_microseconds = dict(page.result_rows)["Unix 时间戳（微秒）"]
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            QTest.qWait(50)
            if dict(page.result_rows)["Unix 时间戳（微秒）"] != first_microseconds:
                break
        self.assertNotEqual(dict(page.result_rows)["Unix 时间戳（微秒）"], first_microseconds)
        page.mode.setCurrentIndex(page.mode.findData("timestamp"))
        page.input.setText("0")
        page.unit.setCurrentIndex(page.unit.findData("seconds"))
        page.timezone.setCurrentIndex(page.timezone.findData("UTC"))
        page.convert()
        self.assertFalse(page._live_preview)
        self.assertTrue(page.resume_live_button.isEnabled())
        rows = dict(page.result_rows)
        self.assertEqual(rows["ISO 8601"], "1970-01-01T00:00:00+00:00")
        self.assertEqual(rows["Unix 时间戳（微秒）"], "0")

        page.mode.setCurrentIndex(page.mode.findData("datetime"))
        self.assertFalse(page.unit.isEnabled())
        page.timezone.setCurrentIndex(page.timezone.findData("custom"))
        self.assertTrue(page.offset.isVisibleTo(page))
        page.offset.setText("UTC+08:00")
        page.input.setText("2026-04-13 17:00:00")
        page.convert()
        self.assertEqual(dict(page.result_rows)["Unix 时间戳（秒）"], "1776070800")
        page.result_cards["ISO 8601"].copy_button.click()
        self.assertEqual(QGuiApplication.clipboard().text(), dict(page.result_rows)["ISO 8601"])
        self.assertEqual(page.result_cards["ISO 8601"].copy_button.text(), "已复制")
        page.copy_all()
        self.assertIn("RFC 3339:", QGuiApplication.clipboard().text())
        page.resume_live_button.click()
        self.assertTrue(page._live_preview)
        self.assertFalse(page.resume_live_button.isEnabled())
        self.assertEqual(page.mode.currentData(), "datetime")
        self.assertEqual(page.timezone.currentData(), "local")
        self.assertTrue(page.live_timer.isActive())
        page.close()

    def test_json_formatter_page_formats_valid_input_and_locates_errors(self):
        from fuzztoolbox.tools.json_formatter.page import JSONFormatterPage

        page = JSONFormatterPage()
        self.assertIsInstance(page.input, LineNumberEditor)
        self.assertIsInstance(page.output, LineNumberEditor)
        self.assertEqual(page.indent.currentData(), 2)
        self.assertEqual(page.input_highlighter.language, "json")
        self.assertEqual(page.output_highlighter.language, "json")
        page.input.setPlainText('{"名称":"工具箱","ok":true,"count":12}')
        page.input_highlighter.rehighlight()
        input_colors = {
            item.format.foreground().color().name()
            for item in page.input.document().firstBlock().layout().formats()
        }
        self.assertIn("#1769aa", input_colors)
        self.assertIn("#16825d", input_colors)
        self.assertIn("#7b3fb2", input_colors)
        self.assertIn("#b15c00", input_colors)
        page.format()
        self.assertIn('"名称": "工具箱"', page.output.toPlainText())
        self.assertIn("格式化成功", page.status.text())
        page.output_highlighter.rehighlight()
        block = page.output.document().firstBlock()
        highlighted_output = False
        while block.isValid():
            highlighted_output = highlighted_output or bool(block.layout().formats())
            block = block.next()
        self.assertTrue(highlighted_output)

        page.input.setPlainText('{\n  "ok": tru\n}')
        page.validate()
        self.assertIn("第 2 行", page.status.text())
        self.assertEqual(page.input.textCursor().position(), 10)
        self.assertEqual(page.input._error_line, 2)
        page.input.insertPlainText("e")
        self.assertIsNone(page.input._error_line)
        page.close()

    def test_json_formatter_live_validation_does_not_move_the_cursor(self):
        from fuzztoolbox.tools.json_formatter.page import JSONFormatterPage

        page = JSONFormatterPage()
        invalid = '{\n  "name": "tool",\n  "enabled": tru\n}'
        page.input.setPlainText(invalid)
        cursor = page.input.textCursor()
        cursor.setPosition(2)
        page.input.setTextCursor(cursor)
        page.validate_live()
        self.assertEqual(page.input.textCursor().position(), 2)
        self.assertEqual(page.input._error_line, 3)
        self.assertIn("第 3 行", page.status.text())

        page.input.setPlainText('{"enabled": true}')
        page.validate_live()
        self.assertIsNone(page.input._error_line)
        self.assertIn("实时校验通过", page.status.text())
        page.close()

    def test_text_comparer_highlights_changes_and_switches_diff_modes(self):
        from fuzztoolbox.tools.text_comparer.page import TextComparerPage

        page = TextComparerPage()
        self.assertIsInstance(page.left, LineNumberEditor)
        self.assertIsInstance(page.right, LineNumberEditor)
        self.assertGreaterEqual(page.language.count(), 25)
        page.left.setPlainText('#include <iostream>\nstd::cout << "ready";')
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            QTest.qWait(50)
            if page.left_highlighter.language == "cpp":
                break
        self.assertEqual(page.left_highlighter.language, "cpp")
        self.assertTrue(page.left.document().firstBlock().layout().formats())
        page.left.clear()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            QTest.qWait(50)
            if page.left_highlighter.language == "text":
                break
        self.assertEqual(page.left_highlighter.language, "text")
        page.language.setCurrentIndex(page.language.findData("cpp"))
        self.assertEqual(page.left_highlighter.language, "cpp")
        self.assertEqual(page.patch_highlighter.language, "cpp")
        page.left.setPlainText('#include <iostream>\nint main() { return 0; }')
        page.left_highlighter.rehighlight()
        self.assertTrue(page.left.document().firstBlock().layout().formats())
        one_digit_edit = page._context_edit_width(page.context_lines.width())
        page.context_lines.setValue(20)
        self.app.processEvents()
        two_digit_width = page.context_lines.width()
        two_digit_edit = page._context_edit_width(two_digit_width)
        self.assertGreaterEqual(
            two_digit_edit,
            page.context_lines.fontMetrics().horizontalAdvance("20") + 8,
        )
        page.context_lines.setValue(9)
        self.app.processEvents()
        self.assertGreaterEqual(
            one_digit_edit,
            page.context_lines.fontMetrics().horizontalAdvance("9"),
        )
        page.show()
        page.context_lines.setFocus()
        self.app.processEvents()
        line_edit = page.context_lines.findChild(QLineEdit)
        QTest.mouseClick(line_edit, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(line_edit.selectedText(), "9")
        QTest.keyClicks(page.context_lines, "20")
        self.assertEqual(page.context_lines.text(), "20")
        QTest.keyClick(page.context_lines, Qt.Key_Return)
        self.assertEqual(page.context_lines.value(), 20)
        self.assertAlmostEqual(page.context_lines.width(), two_digit_width, delta=2)
        page.left.setPlainText("one\nold\nend")
        page.right.setPlainText("one\nnew\nadded\nend")
        page.compare()
        self.assertIn("新增 1 行", page.status.text())
        self.assertIn("修改 1 行", page.status.text())
        self.assertTrue(page.left._decorations)
        self.assertTrue(page.right._decorations)
        self.assertIn("selection-background-color: rgba(64, 158, 255, 82)", page.left.styleSheet())
        page.left.moveCursor(QTextCursor.NextBlock)
        last_selection = page.left.extraSelections()[-1]
        last_format = last_selection.format
        self.assertIn(
            last_format.background().color().name(),
            ("#fff0bf", "#f1b8b8", "#4a3d22", "#63343c"),
        )

        page.mode.setCurrentIndex(page.mode.findData("unified"))
        self.assertIs(page.stack.currentWidget(), page.patch_output)
        self.assertIn("--- 原始文本", page.patch_output.toPlainText())
        self.assertTrue(page.patch_output._decorations)
        self.assertTrue(page.patch_output._line_markers)
        self.assertTrue(page.patch_output._highlight_read_only_line)
        self.assertEqual(
            len(page.patch_output.extraSelections()),
            len(page.patch_output._decorations) + 1,
        )
        current_line_selection = page.patch_output.extraSelections()[-1]
        current_line_format = current_line_selection.format
        self.assertEqual(current_line_format.background().color().alpha(), 54)
        self.assertNotIn("■", "".join(label.text() for label in page.legend.findChildren(QLabel)))
        self.assertFalse(page.copy_button.isHidden())

        page.mode.setCurrentIndex(page.mode.findData("context"))
        self.assertIn("***************", page.patch_output.toPlainText())
        self.assertTrue(page.patch_output._decorations)
        self.assertIn("#d79a20", page.patch_output._line_markers.values())

        page.left.setPlainText("one\n\nend")
        page.right.setPlainText("one\nadded\nend")
        page.compare()
        self.assertEqual(page.left._empty_line_markers, {2: "#d79a20"})
        page.mode.setCurrentIndex(page.mode.findData("unified"))
        page.left.setPlainText("one\nend")
        page.right.setPlainText("one\n\nend")
        page.compare()
        self.assertIn("#35a35a", page.patch_output._empty_line_markers.values())
        page.close()

    def test_text_statistics_page_updates_live_and_reports_selection(self):
        from fuzztoolbox.tools.text_statistics.page import TextStatisticsPage

        page = TextStatisticsPage()
        self.assertIsInstance(page.input, LineNumberEditor)
        page.input.setPlainText("你好 OpenAI\n第二行")
        deadline = time.monotonic() + 2
        while page.stats.lines != 2 and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertEqual(page.stats.lines, 2)
        self.assertEqual(page.stats.words, 1)
        self.assertEqual(page.values["word_units"].text(), "6")
        self.assertEqual(page.values["utf8_bytes"].text(), "23 字节")
        page.input.setPlainText('#include <iostream>\nstd::cout << "ok";')
        deadline = time.monotonic() + 2
        while page.syntax_highlighter.language != "cpp" and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertEqual(page.syntax_highlighter.language, "cpp")
        self.assertTrue(page.input.document().firstBlock().layout().formats())
        page.language.setCurrentIndex(page.language.findData("python"))
        self.assertEqual(page.syntax_highlighter.language, "python")
        page.input.setPlainText("你好 OpenAI\n第二行")
        deadline = time.monotonic() + 2
        while page.stats.lines != 2 and time.monotonic() < deadline:
            QTest.qWait(20)
        cursor = page.input.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(2, QTextCursor.KeepAnchor)
        page.input.setTextCursor(cursor)
        self.assertIn("2 字符", page.selection_status.text())
        page.close()


if __name__ == "__main__":
    unittest.main()
