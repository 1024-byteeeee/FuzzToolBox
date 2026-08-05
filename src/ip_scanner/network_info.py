import ipaddress
import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class NetworkInfo:
    interface: Optional[str] = None
    ip: Optional[str] = None
    prefix_length: Optional[int] = None
    gateway: Optional[str] = None
    mac: Optional[str] = None

    @property
    def address(self) -> str:
        return self.ip or "未检测到 IPv4"

    @property
    def netmask(self) -> Optional[str]:
        if self.prefix_length is None:
            return None
        return str(ipaddress.IPv4Network(f"0.0.0.0/{self.prefix_length}").netmask)

    @property
    def cidr(self) -> Optional[str]:
        if not self.ip or self.prefix_length is None:
            return None
        network = ipaddress.IPv4Network(f"{self.ip}/{self.prefix_length}", strict=False)
        return str(network)

    @property
    def scan_range(self):
        """Return the usable host range for the detected IPv4 network."""
        if not self.ip or self.prefix_length is None:
            return None
        network = ipaddress.IPv4Network(f"{self.ip}/{self.prefix_length}", strict=False)
        if network.prefixlen <= 30:
            return str(network.network_address + 1), str(network.broadcast_address - 1)
        return str(network.network_address), str(network.broadcast_address)

    def display_text(self) -> str:
        parts = [self.interface or "未知接口", f"IP {self.address}"]
        if self.netmask:
            parts.append(f"子网掩码 {self.netmask}")
        if self.gateway:
            parts.append(f"网关 {self.gateway}")
        if self.mac:
            parts.append(f"MAC {self.mac}")
        return "  ·  ".join(parts)


def _run(args: List[str]) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                if platform.system() == "Windows"
                else 0
            ),
        )
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _prefix_from_hex_netmask(value: str) -> Optional[int]:
    try:
        number = int(value, 16)
        netmask = str(ipaddress.IPv4Address(number))
        return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    except (ValueError, ipaddress.NetmaskValueError):
        return None


def _macos_network_info() -> NetworkInfo:
    route = _run(["/sbin/route", "-n", "get", "default"])
    interface_match = re.search(r"^\s*interface:\s*(\S+)", route, re.MULTILINE)
    gateway_match = re.search(r"^\s*gateway:\s*(\S+)", route, re.MULTILINE)
    interface = interface_match.group(1) if interface_match else None
    gateway = gateway_match.group(1) if gateway_match else None
    if not interface:
        return _socket_fallback()

    details = _run(["/sbin/ifconfig", interface])
    ip_match = re.search(r"^\s*inet\s+(\d+(?:\.\d+){3})\s+netmask\s+(0x[0-9a-f]+)", details, re.MULTILINE | re.IGNORECASE)
    mac_match = re.search(r"^\s*ether\s+([0-9a-f:]+)", details, re.MULTILINE | re.IGNORECASE)
    return NetworkInfo(
        interface=interface,
        ip=ip_match.group(1) if ip_match else None,
        prefix_length=_prefix_from_hex_netmask(ip_match.group(2)) if ip_match else None,
        gateway=gateway,
        mac=mac_match.group(1).upper() if mac_match else None,
    )


def _linux_network_info() -> NetworkInfo:
    route = _run(["ip", "route", "show", "default"])
    interface_match = re.search(r"\bdev\s+(\S+)", route)
    gateway_match = re.search(r"\bvia\s+(\S+)", route)
    interface = interface_match.group(1) if interface_match else None
    if not interface:
        return _socket_fallback()
    address_text = _run(["ip", "-o", "-4", "addr", "show", "dev", interface])
    ip_match = re.search(r"\binet\s+(\d+(?:\.\d+){3})/(\d+)", address_text)
    mac_text = _run(["cat", f"/sys/class/net/{interface}/address"])
    mac = mac_text.strip().upper() or None
    return NetworkInfo(
        interface=interface,
        ip=ip_match.group(1) if ip_match else None,
        prefix_length=int(ip_match.group(2)) if ip_match else None,
        gateway=gateway_match.group(1) if gateway_match else None,
        mac=mac,
    )


def _windows_network_info() -> NetworkInfo:
    script = (
        "$c=Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -and $_.IPv4Address} "
        "| Select-Object -First 1; if ($c) {$a=$c.IPv4Address | Select-Object -First 1; "
        "$m=(Get-NetAdapter -InterfaceIndex $c.InterfaceIndex).MacAddress; "
        "Write-Output ($c.InterfaceAlias+'|'+$a.IPAddress+'|'+$a.PrefixLength+'|'"
        "+$c.IPv4DefaultGateway.NextHop+'|'+$m)}"
    )
    output = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]).strip()
    if output:
        parts = output.split("|", 4)
        if len(parts) == 5:
            try:
                prefix_length = int(parts[2])
            except ValueError:
                prefix_length = None
            return NetworkInfo(
                interface=parts[0] or None,
                ip=parts[1] or None,
                prefix_length=prefix_length,
                gateway=parts[3] or None,
                mac=parts[4].replace("-", ":").upper() or None,
            )
    return _socket_fallback()


def _socket_fallback() -> NetworkInfo:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 53))
        ip = sock.getsockname()[0]
    except OSError:
        ip = None
    finally:
        sock.close()
    return NetworkInfo(ip=ip)


def get_network_info() -> NetworkInfo:
    system = platform.system()
    if system == "Darwin":
        return _macos_network_info()
    if system == "Linux":
        return _linux_network_info()
    if system == "Windows":
        return _windows_network_info()
    return _socket_fallback()
