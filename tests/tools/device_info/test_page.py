import unittest

from PySide6.QtWidgets import QApplication

from fuzztoolbox.tools.device_info.collector import DeviceReport, InfoSection
from fuzztoolbox.tools.device_info.page import DeviceInfoPage, collect_screen_section


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
        self.assertEqual(page.status.text(), "设备信息已更新")
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
