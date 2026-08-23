import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.device_info.collector import DeviceReport, InfoSection
from fuzztoolbox.tools.device_info.page import (
    DeviceInfoPage,
    DeviceInfoWorker,
    collect_screen_section,
)


class DeviceInfoPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_screen_information_comes_from_qt_display_api(self):
        section = collect_screen_section()

        self.assertEqual(section.title, "显示器")
        self.assertTrue(section.rows)
        self.assertIn("逻辑", section.rows[0][1])
        self.assertIn("像素比", section.rows[0][1])

    def test_loaded_report_renders_cards_and_enables_copy(self):
        page = DeviceInfoPage()
        page._loaded(DeviceReport((InfoSection("设备概览", (("设备名称", "Example"),)),)))

        self.assertIsNotNone(page.report)
        self.assertGreaterEqual(page.sections_layout.count(), 2)
        self.assertTrue(page.copy_button.isEnabled())
        self.assertIn("实时更新中", page.status.text())
        page.deleteLater()

    def test_refresh_updates_values_in_place_without_rebuilding_cards(self):
        page = DeviceInfoPage()
        first = DeviceReport((
            InfoSection("处理器", (("当前使用率", "10.0%"),)),
            InfoSection("内存", (("使用率", "50.0%"),)),
        ))
        page._loaded(first)
        panels = [
            page.sections_layout.itemAt(index).widget()
            for index in range(page.sections_layout.count())
        ]
        value_labels = list(page._value_labels)

        second = DeviceReport((
            InfoSection("处理器", (("当前使用率", "23.0%"),)),
            InfoSection("内存", (("使用率", "51.0%"),)),
        ))
        page._loaded(second)

        # 结构不变时复用原有卡片与标签，避免刷新闪烁。
        self.assertEqual(
            panels,
            [
                page.sections_layout.itemAt(index).widget()
                for index in range(page.sections_layout.count())
            ],
        )
        self.assertEqual(value_labels, page._value_labels)
        self.assertEqual(page._value_labels[0].text(), "23.0%")
        self.assertEqual(page._value_labels[1].text(), "51.0%")
        page.deleteLater()

    def test_structure_change_rebuilds_cards(self):
        page = DeviceInfoPage()
        page._render(DeviceReport((InfoSection("磁盘 1 · C:", (("总容量", "1 GB"),)),)))
        self.assertEqual(page.sections_layout.count(), 1)

        page._render(DeviceReport((
            InfoSection("磁盘 1 · C:", (("总容量", "1 GB"),)),
            InfoSection("磁盘 2 · D:", (("总容量", "2 GB"),)),
        )))
        self.assertEqual(page.sections_layout.count(), 2)
        page.deleteLater()

    def test_prepare_close_stops_auto_refresh_and_returns_ready_when_idle(self):
        page = DeviceInfoPage()
        page._refresh_timer.start()
        self.assertTrue(page.prepare_close(lambda: None))
        self.assertFalse(page._refresh_timer.isActive())
        page.deleteLater()

    def test_first_refresh_shows_skeleton_until_report_arrives(self):
        from PySide6.QtWidgets import QLabel

        page = DeviceInfoPage()
        with patch.object(DeviceInfoWorker, "start"):
            page.refresh()
        # 首次加载期间用骨架卡片占位，还没有任何真实数值标签。
        self.assertGreaterEqual(page.sections_layout.count(), 3)
        self.assertIsNone(page.report)
        self.assertEqual(page._value_labels, [])
        self.assertFalse([
            label
            for index in range(page.sections_layout.count())
            for label in page.sections_layout.itemAt(index).widget().findChildren(QLabel)
            if label.objectName() == "deviceInfoValue"
        ])

        page._loaded(DeviceReport((InfoSection("设备概览", (("设备名称", "Example"),)),)))
        self.assertIsNotNone(page.report)
        self.assertEqual(page.sections_layout.count(), 2)
        self.assertEqual(page._value_labels[0].text(), "Example")
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
