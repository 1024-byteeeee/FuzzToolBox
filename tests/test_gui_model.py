import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QComboBox, QTableView

from ip_scanner.gui import (
    WINDOWS_APP_ID,
    MainWindow,
    ResultModel,
    STYLE,
    ToolboxHomePage,
    configure_windows_app_id,
)
from ip_scanner.models import ScanResult
from ip_scanner.network_info import NetworkInfo
from ip_scanner.subnet_calculator import FLSMPlan, parse_network
from ip_scanner.subnet_gui import FETCH_BATCH_SIZE, SubnetResultModel
from ip_scanner.tool_registry import TOOLS, filter_tools
from ip_scanner.ui_components import (
    ComboItemDelegate,
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
        with patch("ip_scanner.gui.sys.platform", "win32"), patch(
            "ip_scanner.gui.ctypes.windll", windll, create=True
        ):
            configure_windows_app_id()

        shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            WINDOWS_APP_ID
        )

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
        self.assertEqual(filter_tools(TOOLS, "JSON"), ())
        self.assertEqual(filter_tools(TOOLS, "WPS")[0].id, "word-to-pdf")
        self.assertEqual(filter_tools(TOOLS, category="文档工具")[0].id, "word-to-pdf")

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
        self.assertIsInstance(combo.view().itemDelegate(), ComboItemDelegate)

        table = QTableView()
        configure_table(table)
        self.assertIsInstance(table.itemDelegate(), GridCellDelegate)
        self.assertEqual(table.selectionBehavior(), QTableView.SelectItems)

    def test_subnet_page_keeps_return_button_available_and_shows_network(self):
        from ip_scanner.subnet_gui import SubnetCalculatorPage

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
        page.search.setText("JSON")
        self.app.processEvents()
        self.assertTrue(page.cards["ip-scanner"].isHidden())
        self.assertEqual(page.empty_label.text(), "没有找到匹配的工具")

    def test_main_window_navigates_between_home_and_scanner(self):
        with patch("ip_scanner.gui.get_network_info") as network_info:
            network_info.return_value.scan_range = None
            network_info.return_value.cidr = None
            network_info.return_value.display_text.return_value = "未知"
            window = MainWindow()
        window.resize(1000, 700)
        window.show()
        self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.home_page)
        window.open_tool("ip-scanner")
        self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.ip_scanner_page)
        self.assertFalse(window.back_button.isHidden())
        table = window.ip_scanner_page.table
        column_width = sum(
            table.horizontalHeader().sectionSize(index)
            for index in range(table.model().columnCount())
        )
        self.assertEqual(column_width, table.viewport().width())
        window.open_tool("subnet-calculator")
        self.assertIs(window.pages.currentWidget(), window.subnet_calculator_page)
        self.assertIn("子网划分计算器", window.page_title.text())
        window.open_tool("word-to-pdf")
        self.assertIs(window.pages.currentWidget(), window.word_to_pdf_page)
        self.assertIn("Word 转 PDF", window.page_title.text())
        window.show_home()
        self.assertIs(window.pages.currentWidget(), window.home_page)
        window.close()

    def test_labels_use_transparent_background(self):
        self.assertIn("QLabel { background: transparent; }", STYLE)


if __name__ == "__main__":
    unittest.main()
