"""Cross-platform device information collector and page."""

from .collector import DeviceReport, InfoSection, collect_device_info

__all__ = ["DeviceReport", "InfoSection", "collect_device_info"]
