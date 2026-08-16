import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fuzztoolbox.core.network_info import NetworkInfo
from fuzztoolbox.tools.device_info import collector as collector_module
from fuzztoolbox.tools.device_info.collector import (
    DeviceReport,
    InfoSection,
    collect_device_info,
    format_bytes,
    format_duration,
)


def _partition(mountpoint, device="/dev/disk0s1", fstype="apfs"):
    return SimpleNamespace(device=device, mountpoint=mountpoint, fstype=fstype, opts="rw")


def _usage(total=512 * 1024**3, used=128 * 1024**3, free=384 * 1024**3, percent=25.0):
    return SimpleNamespace(total=total, used=used, free=free, percent=percent)


class DeviceInfoCollectorTests(unittest.TestCase):
    def setUp(self):
        collector_module._HARDWARE_CACHE.clear()

    def tearDown(self):
        collector_module._HARDWARE_CACHE.clear()

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
        battery = SimpleNamespace(percent=80, power_plugged=True)
        frequency = SimpleNamespace(current=3200, max=4000)
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_partitions",
            return_value=[_partition("/")],
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_usage", return_value=_usage()
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", return_value=frequency, create=True), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", return_value=battery, create=True
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_count", side_effect=[8, 10]), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_percent", return_value=12.5
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.boot_time", return_value=0), patch(
            "fuzztoolbox.tools.device_info.collector.time.time", return_value=3600
        ):
            report = collect_device_info("Darwin")

        titles = [section.title for section in report.sections]
        self.assertEqual(
            titles,
            ["设备概览", "处理器", "图形处理器", "内存", "磁盘 · 系统磁盘（/）", "网络", "电池"],
        )
        self.assertIn("Example Chip", report.text())
        self.assertIn("192.0.2.10", report.text())
        self.assertIn("3.20 GHz", report.text())

    @patch("fuzztoolbox.tools.device_info.collector.get_network_info")
    @patch("fuzztoolbox.tools.device_info.collector._windows_hardware")
    def test_windows_lists_every_drive_with_volume_labels(self, windows_hardware, network_info):
        windows_hardware.return_value = {
            "model": "Example PC",
            "manufacturer": "Example",
            "cpu": "Example CPU",
            "gpu_rows": [],
        }
        network_info.return_value = NetworkInfo(interface="Ethernet", ip="192.0.2.20", mac=None)
        memory = SimpleNamespace(total=16 * 1024**3, used=8 * 1024**3, available=8 * 1024**3, percent=50)
        partitions = [
            _partition("C:\\", device="C:", fstype="NTFS"),
            _partition("D:\\", device="D:", fstype="NTFS"),
            # 卷 GUID 挂载点不应出现在磁盘列表中。
            _partition("C:\\Mounts\\Data", device="E:", fstype="NTFS"),
        ]

        def fake_usage(path):
            return _usage(total=256 * 1024**3, used=64 * 1024**3, free=192 * 1024**3, percent=25.0)

        status = {"load_percentage": 37.5, "labels": {"C:": "系统", "D:": "数据"}}
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_partitions", return_value=partitions
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_usage", side_effect=fake_usage
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", return_value=None, create=True), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", return_value=None, create=True
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_count", return_value=4), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_percent", return_value=0.0
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.boot_time", return_value=0), patch(
            "fuzztoolbox.tools.device_info.collector.time.time", return_value=3600
        ), patch(
            "fuzztoolbox.tools.device_info.collector._windows_system_status", return_value=status
        ):
            report = collect_device_info("Windows")

        titles = [section.title for section in report.sections]
        self.assertIn("磁盘 1 · C:（系统）", titles)
        self.assertIn("磁盘 2 · D:（数据）", titles)
        self.assertNotIn("磁盘 3 · C:\\Mounts\\Data", titles)
        # Windows 下 CPU 使用率必须来自 WMI，而不是始终为 0 的 psutil 采样值。
        self.assertIn("当前使用率: 37.5%", report.text())

    @patch("fuzztoolbox.tools.device_info.collector.get_network_info")
    @patch("fuzztoolbox.tools.device_info.collector._windows_hardware")
    def test_windows_cpu_usage_falls_back_to_psutil_when_wmi_is_unavailable(
        self, windows_hardware, network_info
    ):
        windows_hardware.return_value = {
            "model": "Example PC",
            "manufacturer": "Example",
            "cpu": "Example CPU",
            "gpu_rows": [],
        }
        network_info.return_value = NetworkInfo()
        memory = SimpleNamespace(total=1, used=1, available=0, percent=100)
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_partitions", return_value=[]
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", side_effect=NotImplementedError, create=True
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", side_effect=AttributeError, create=True
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.cpu_count", return_value=None), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_percent", return_value=21.0
        ), patch("fuzztoolbox.tools.device_info.collector.psutil.boot_time", return_value=0), patch(
            "fuzztoolbox.tools.device_info.collector.time.time", return_value=3600
        ), patch(
            "fuzztoolbox.tools.device_info.collector._windows_system_status",
            return_value={"load_percentage": None, "labels": {}},
        ):
            report = collect_device_info("Windows")

        self.assertIn("当前使用率: 21.0%", report.text())
        self.assertIn("磁盘", [section.title for section in report.sections])

    def test_missing_optional_frequency_and_battery_are_supported(self):
        memory = SimpleNamespace(total=1, used=1, available=0, percent=100)
        with patch("fuzztoolbox.tools.device_info.collector.psutil.virtual_memory", return_value=memory), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.disk_partitions", return_value=[]
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.cpu_freq", side_effect=NotImplementedError, create=True
        ), patch(
            "fuzztoolbox.tools.device_info.collector.psutil.sensors_battery", side_effect=AttributeError, create=True
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
