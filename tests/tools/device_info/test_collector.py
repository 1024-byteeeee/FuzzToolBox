import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fuzztoolbox.core.network_info import NetworkInfo
from fuzztoolbox.tools.device_info.collector import (
    DeviceReport,
    InfoSection,
    collect_device_info,
    format_bytes,
    format_duration,
)


class DeviceInfoCollectorTests(unittest.TestCase):
    def test_human_readable_helpers(self):
        self.assertEqual(format_bytes(512 * 1024**2), "512.00 MB")
        self.assertEqual(format_bytes(8 * 1024**3), "8.00 GB")
        self.assertEqual(format_duration(90061), "1 天 1 小时 1 分钟")

    def test_report_text_keeps_sections_and_rows(self):
        report = DeviceReport((InfoSection("处理器", (("CPU", "Example CPU"),)),))
        self.assertEqual(report.text(), "处理器\nCPU: Example CPU")

    @patch("fuzztoolbox.tools.device_info.collector.get_network_info")
    @patch("fuzztoolbox.tools.device_info.collector._mac_hardware")
    def test_collects_all_supported_sections(self, mac_hardware, network_info):
        mac_hardware.return_value = {
            "model": "Mac Example",
            "manufacturer": "Apple",
            "cpu": "Example Chip",
            "gpu_rows": [("GPU 1", "Example GPU")],
        }
        network_info.return_value = NetworkInfo(interface="en0", ip="192.0.2.10", mac="AA:BB:CC:DD:EE:FF")
        memory = SimpleNamespace(total=16 * 1024**3, used=8 * 1024**3, available=8 * 1024**3, percent=50)
        disk = SimpleNamespace(total=512 * 1024**3, used=128 * 1024**3, free=384 * 1024**3, percent=25)
        battery = SimpleNamespace(percent=80, power_plugged=True)
        frequency = SimpleNamespace(current=3200, max=4000)
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_usage", return_value=disk
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", return_value=frequency), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", return_value=battery
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_count", side_effect=[8, 10]), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_percent", return_value=12.5
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.boot_time", return_value=0), patch(
            "fuzztoolbox.tools.device_info.collector.time.time", return_value=3600
        ):
            report = collect_device_info("Darwin")

        titles = [section.title for section in report.sections]
        self.assertEqual(
            titles,
            ["设备概览", "处理器", "图形处理器", "内存", "系统盘", "网络", "电池"],
        )
        self.assertIn("Example Chip", report.text())
        self.assertIn("192.0.2.10", report.text())
        self.assertIn("3.20 GHz", report.text())

    def test_missing_optional_frequency_and_battery_are_supported(self):
        memory = SimpleNamespace(total=1, used=1, available=0, percent=100)
        disk = SimpleNamespace(total=1, used=1, free=0, percent=100)
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_usage", return_value=disk
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", side_effect=NotImplementedError
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", side_effect=AttributeError
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_count", return_value=None), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_percent", return_value=0
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.boot_time", return_value=0), patch(
            "fuzztoolbox.tools.device_info.collector.get_network_info", return_value=NetworkInfo()
        ):
            report = collect_device_info("Linux")

        self.assertNotIn("电池", [section.title for section in report.sections])
        self.assertIn("当前频率: 未检测到", report.text())


if __name__ == "__main__":
    unittest.main()
