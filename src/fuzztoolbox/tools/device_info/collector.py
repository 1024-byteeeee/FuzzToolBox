import json
import platform
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import psutil

from ...core.network_info import _powershell_script_command, get_network_info
from ...core.subprocess_utils import hidden_subprocess_kwargs


Rows = Tuple[Tuple[str, str], ...]

# 设备型号、CPU 型号等静态硬件信息在实时刷新之间保持不变。
# 缓存探测结果，避免每次刷新都重新启动 system_profiler / PowerShell。
_HARDWARE_CACHE = {}

WINDOWS_DRIVE_MOUNT = re.compile(r"^[A-Za-z]:\\?$")
# macOS 的 VM / Preboot / Data 等系统内部卷对用户没有意义，统一隐藏。
MACOS_HIDDEN_MOUNT_PREFIX = "/System/Volumes/"


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


def _windows_uptime() -> Optional[float]:
    """通过 GetTickCount64 读取 Windows 运行时长。

    该计数器在系统睡眠/休眠期间停止计数，返回的是真实活跃时长。
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetTickCount64.restype = ctypes.c_uint64
        return kernel32.GetTickCount64() / 1000.0
    except (AttributeError, OSError, ValueError):
        return None


def system_uptime(system: str = None) -> float:
    """计算系统真实运行时长（不包含睡眠/休眠时间）。

    直接用 time.time() - psutil.boot_time() 得到的是墙钟差值，
    会把合盖睡眠的时间也算进运行时长，导致显示值明显偏大。
    这里优先使用各平台不计入睡眠时间的单调时钟：
    macOS 的 CLOCK_UPTIME_RAW、Windows 的 GetTickCount64。
    """
    system = system or platform.system()
    if system == "Windows":
        tick_uptime = _windows_uptime()
        if tick_uptime is not None:
            return tick_uptime
    clock_id = getattr(time, "CLOCK_UPTIME_RAW", None)
    if clock_id is not None:
        try:
            return time.clock_gettime(clock_id)
        except (OSError, ValueError):
            pass
    return max(0.0, time.time() - psutil.boot_time())


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
    data = _run_json(_powershell_script_command("get_device_hardware.ps1"), timeout=12.0)
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


def _windows_system_status() -> dict:
    """一次 PowerShell 调用同时读取 CPU 负载与各盘符卷标。

    psutil.cpu_percent 依赖进程内两次采样的差值，在部分 Windows 环境
    （尤其是 PyInstaller 打包后的窗口进程）中会持续返回 0%。
    Win32_Processor.LoadPercentage 由系统性能计数器直接提供，始终有效。
    """
    data = _run_json(_powershell_script_command("get_system_status.ps1"), timeout=10.0)
    load = data.get("LoadPercentage")
    try:
        load_percentage = float(load)
    except (TypeError, ValueError):
        load_percentage = None
    volumes = data.get("Volumes") or []
    if isinstance(volumes, dict):
        volumes = [volumes]
    labels = {}
    for item in volumes:
        drive = str(item.get("DriveLetter") or "").strip()
        label = str(item.get("Label") or "").strip()
        if drive:
            labels[drive.rstrip("\\").upper()] = label
    return {"load_percentage": load_percentage, "labels": labels}


def _cpu_usage(system: str, windows_status: Optional[dict]) -> float:
    if system == "Windows" and windows_status and windows_status["load_percentage"] is not None:
        return windows_status["load_percentage"]
    return psutil.cpu_percent(interval=0.1)


def _disk_label(partition, system: str) -> str:
    mountpoint = partition.mountpoint
    if system == "Windows":
        # Windows 的卷标由 PowerShell 脚本统一补充，这里只展示盘符。
        return mountpoint.rstrip("\\") or mountpoint
    if mountpoint == "/":
        return "系统磁盘（/）"
    name = Path(mountpoint).name
    return f"{name}（{mountpoint}）" if name else mountpoint


def _visible_partitions(system: str):
    try:
        partitions = psutil.disk_partitions(all=False)
    except (OSError, PermissionError, NotImplementedError):
        return []
    visible = []
    seen_mounts = set()
    for partition in partitions:
        mountpoint = partition.mountpoint
        if mountpoint in seen_mounts:
            continue
        if system == "Windows":
            # 仅保留盘符根目录（C:\、D:\），排除卷 GUID 挂载点和隐藏分区。
            if not WINDOWS_DRIVE_MOUNT.match(mountpoint):
                continue
        elif system == "Darwin":
            if mountpoint.startswith(MACOS_HIDDEN_MOUNT_PREFIX):
                continue
        elif mountpoint.startswith(("/dev", "/proc", "/sys", "/run", "/snap")):
            continue
        try:
            usage = psutil.disk_usage(mountpoint)
        except (OSError, PermissionError):
            continue
        if usage.total <= 0:
            continue
        seen_mounts.add(mountpoint)
        visible.append((partition, usage))
    return visible


def _disk_sections(system: str, windows_status: Optional[dict]) -> Tuple[InfoSection, ...]:
    partitions = _visible_partitions(system)
    labels = (windows_status or {}).get("labels", {}) if system == "Windows" else {}
    sections = []
    for index, (partition, usage) in enumerate(partitions, start=1):
        label = _disk_label(partition, system)
        if system == "Windows":
            drive = partition.mountpoint.rstrip("\\").upper()
            volume_label = labels.get(drive)
            if volume_label:
                label = f"{label}（{volume_label}）"
        title = f"磁盘 {index} · {label}" if len(partitions) > 1 else f"磁盘 · {label}"
        sections.append(InfoSection(title, (
            ("总容量", format_bytes(usage.total)),
            ("已使用", format_bytes(usage.used)),
            ("可用", format_bytes(usage.free)),
            ("使用率", f"{usage.percent:.1f}%"),
        )))
    if not sections:
        sections.append(InfoSection("磁盘", (("磁盘", "未检测到"),)))
    return tuple(sections)


def _hardware(system: str) -> dict:
    if system in _HARDWARE_CACHE:
        return _HARDWARE_CACHE[system]
    if system == "Darwin":
        hardware = _mac_hardware()
    elif system == "Windows":
        hardware = _windows_hardware()
    else:
        hardware = {
            "model": platform.node() or "未检测到",
            "manufacturer": "未检测到",
            "cpu": platform.processor(),
            "gpu_rows": [],
        }
    _HARDWARE_CACHE[system] = hardware
    return hardware


def collect_device_info(system: str = None) -> DeviceReport:
    system = system or platform.system()
    hardware = _hardware(system)
    windows_status = _windows_system_status() if system == "Windows" else None
    memory = psutil.virtual_memory()
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
            ("运行时长", format_duration(system_uptime(system))),
        )),
        InfoSection("处理器", (
            ("CPU", cpu_name),
            ("物理核心", str(psutil.cpu_count(logical=False) or "未检测到")),
            ("逻辑核心", str(psutil.cpu_count(logical=True) or "未检测到")),
            ("当前频率", _frequency_text(getattr(frequency, "current", None))),
            ("最大频率", _frequency_text(getattr(frequency, "max", None))),
            ("当前使用率", f"{_cpu_usage(system, windows_status):.1f}%"),
        )),
        InfoSection("图形处理器", tuple(hardware["gpu_rows"]) or (("GPU", "未检测到"),)),
        InfoSection("内存", (
            ("总容量", format_bytes(memory.total)),
            ("已使用", format_bytes(memory.used)),
            ("可用", format_bytes(memory.available)),
            ("使用率", f"{memory.percent:.1f}%"),
        )),
        *_disk_sections(system, windows_status),
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
