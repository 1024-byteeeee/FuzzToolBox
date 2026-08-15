import json
import platform
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import psutil

from ...core.network_info import _powershell_script_command, get_network_info
from ...core.subprocess_utils import hidden_subprocess_kwargs


Rows = Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class InfoSection:
    title: str
    rows: Rows


@dataclass(frozen=True)
class DeviceReport:
    sections: Tuple[InfoSection, ...]

    def text(self) -> str:
        lines = []
        for section in self.sections:
            if lines:
                lines.append("")
            lines.append(section.title)
            lines.extend(f"{name}: {value}" for name, value in section.rows)
        return "\n".join(lines)


def format_bytes(value: int) -> str:
    amount = float(max(0, value))
    gibibyte = 1024**3
    if amount >= gibibyte:
        return f"{amount / gibibyte:.2f} GB"
    return f"{amount / 1024**2:.2f} MB"


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours or days:
        parts.append(f"{hours} 小时")
    parts.append(f"{minutes} 分钟")
    return " ".join(parts)


def _frequency_text(value) -> str:
    return f"{float(value) / 1000:.2f} GHz" if value else "未检测到"


def _run_json(command, timeout=8.0):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        return json.loads(result.stdout.lstrip("\ufeff"))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _mac_hardware():
    data = _run_json(
        ["/usr/sbin/system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "-json", "-detailLevel", "mini"]
    )
    hardware = (data.get("SPHardwareDataType") or [{}])[0]
    displays = data.get("SPDisplaysDataType") or []
    gpu_rows = []
    for item in displays:
        name = item.get("sppci_model") or item.get("_name")
        if not name:
            continue
        details = [str(name)]
        for key in ("sppci_cores", "spdisplays_vram", "sppci_vendor"):
            value = item.get(key)
            if value and str(value) not in details:
                details.append(str(value))
        gpu_rows.append((f"GPU {len(gpu_rows) + 1}", " · ".join(details)))
    return {
        "model": hardware.get("machine_model") or hardware.get("machine_name") or "未检测到",
        "manufacturer": "Apple",
        "cpu": hardware.get("chip_type") or hardware.get("cpu_type") or platform.processor(),
        "gpu_rows": gpu_rows,
    }


def _windows_hardware():
    data = _run_json(_powershell_script_command("get_device_hardware.ps1"))
    gpu = data.get("GPU") or []
    if isinstance(gpu, dict):
        gpu = [gpu]
    gpu_rows = []
    for item in gpu:
        details = [str(item.get("Name") or "未知显卡")]
        if item.get("AdapterRAM"):
            details.append(format_bytes(int(item["AdapterRAM"])))
        if item.get("DriverVersion"):
            details.append(f"驱动 {item['DriverVersion']}")
        gpu_rows.append((f"GPU {len(gpu_rows) + 1}", " · ".join(details)))
    return {
        "model": data.get("Model") or "未检测到",
        "manufacturer": data.get("Manufacturer") or "未检测到",
        "cpu": data.get("CPU") or platform.processor(),
        "gpu_rows": gpu_rows,
    }


def collect_device_info(system: str = None) -> DeviceReport:
    system = system or platform.system()
    hardware = _mac_hardware() if system == "Darwin" else _windows_hardware() if system == "Windows" else {
        "model": platform.node() or "未检测到",
        "manufacturer": "未检测到",
        "cpu": platform.processor(),
        "gpu_rows": [],
    }
    memory = psutil.virtual_memory()
    disk_root = Path.home().anchor if system == "Windows" else "/"
    disk = psutil.disk_usage(disk_root or "/")
    try:
        frequency = psutil.cpu_freq()
    except (AttributeError, NotImplementedError):
        frequency = None
    try:
        battery = psutil.sensors_battery()
    except (AttributeError, NotImplementedError):
        battery = None
    network = get_network_info(include_gateway=False)
    cpu_name = hardware.get("cpu") or platform.processor() or platform.machine()
    sections = [
        InfoSection("设备概览", (
            ("设备名称", socket.gethostname()),
            ("制造商", hardware["manufacturer"]),
            ("设备型号", hardware["model"]),
            ("操作系统", f"{platform.system()} {platform.release()}"),
            ("系统版本", platform.version()),
            ("架构", platform.machine()),
            ("运行时长", format_duration(time.time() - psutil.boot_time())),
        )),
        InfoSection("处理器", (
            ("CPU", cpu_name),
            ("物理核心", str(psutil.cpu_count(logical=False) or "未检测到")),
            ("逻辑核心", str(psutil.cpu_count(logical=True) or "未检测到")),
            ("当前频率", _frequency_text(getattr(frequency, "current", None))),
            ("最大频率", _frequency_text(getattr(frequency, "max", None))),
            ("当前使用率", f"{psutil.cpu_percent(interval=0.1):.1f}%"),
        )),
        InfoSection("图形处理器", tuple(hardware["gpu_rows"]) or (("GPU", "未检测到"),)),
        InfoSection("内存", (
            ("总容量", format_bytes(memory.total)),
            ("已使用", format_bytes(memory.used)),
            ("可用", format_bytes(memory.available)),
            ("使用率", f"{memory.percent:.1f}%"),
        )),
        InfoSection("系统盘", (
            ("总容量", format_bytes(disk.total)),
            ("已使用", format_bytes(disk.used)),
            ("可用", format_bytes(disk.free)),
            ("使用率", f"{disk.percent:.1f}%"),
        )),
        InfoSection("网络", (
            ("接口", network.interface or "未检测到"),
            ("IPv4", network.ip or "未检测到"),
            ("MAC", network.mac or "未检测到"),
        )),
    ]
    if battery:
        power = "正在充电" if battery.power_plugged else "使用电池"
        sections.append(InfoSection("电池", (("电量", f"{battery.percent:.0f}%"), ("状态", power))))
    return DeviceReport(tuple(sections))
