import ipaddress
import platform
import re
import socket
import subprocess
from dataclasses import dataclass, replace
from typing import List, Optional

from .subprocess_utils import hidden_subprocess_kwargs

try:
    import psutil
except ImportError:  # pragma: no cover - source-only fallback for incomplete installs
    psutil = None


RFC1918_NETWORKS = tuple(
    ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")
VIRTUAL_INTERFACE_HINTS = (
    "utun",
    "tun",
    "tap",
    "wireguard",
    "tailscale",
    "zerotier",
    "docker",
    "bridge",
    "br-",
    "br0",
    "veth",
    "virbr",
    "vmnet",
    "vbox",
    "vethernet",
    "hyper-v",
    "awdl",
    "llw",
    "loopback",
    "hamachi",
    "ppp",
)


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


def _run(args: List[str], timeout: float = 3.0) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _socket_source_ip() -> Optional[str]:
    for remote in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.2)
            sock.connect(remote)
            value = sock.getsockname()[0]
            address = ipaddress.IPv4Address(value)
            if not address.is_loopback and not address.is_unspecified:
                return value
        except (OSError, ValueError):
            pass
        finally:
            sock.close()
    return None


def _prefix_from_netmask(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{value}").prefixlen
    except (ValueError, ipaddress.NetmaskValueError):
        return None


def _normalized_mac(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = re.split("[:-]", value.strip())
    if len(parts) != 6:
        return None
    try:
        normalized = ":".join(f"{int(part, 16):02X}" for part in parts)
    except ValueError:
        return None
    return None if normalized == "00:00:00:00:00:00" else normalized


def _is_rfc1918(address: ipaddress.IPv4Address) -> bool:
    return any(address in network for network in RFC1918_NETWORKS)


def _interface_score(
    name: str,
    ip: str,
    prefix_length: Optional[int],
    is_up: bool,
    mac: Optional[str],
    preferred_ip: Optional[str],
) -> int:
    address = ipaddress.IPv4Address(ip)
    normalized_name = name.lower().replace(" ", "")
    virtual = any(hint in normalized_name for hint in VIRTUAL_INTERFACE_HINTS)
    score = 30 if is_up else -300
    if _is_rfc1918(address):
        score += 50
    elif address in CGNAT_NETWORK:
        score += 30
    elif address.is_link_local:
        score -= 80
    elif address.is_global:
        score += 20
    if preferred_ip == ip:
        score += 100 if not virtual else 20
    if re.match(r"^(?:en\d+|eth\d*|eno\d+|ens\d+|enp\w+|wlan\d*|wlp\w+)$", normalized_name):
        score += 40
    elif normalized_name in {"ethernet", "wi-fi", "wifi", "wlan"}:
        score += 40
    if virtual:
        score -= 100
    if prefix_length in {31, 32}:
        score -= 20
    if mac:
        score += 10
    return score


def _psutil_network_info() -> Optional[NetworkInfo]:
    if psutil is None:
        return None
    preferred_ip = _socket_source_ip()
    try:
        addresses_by_interface = psutil.net_if_addrs()
        stats_by_interface = psutil.net_if_stats()
    except (OSError, RuntimeError, psutil.Error):
        return None

    link_families = {
        family
        for family in (getattr(psutil, "AF_LINK", None), getattr(socket, "AF_PACKET", None))
        if family is not None
    }
    candidates = []
    for name, addresses in addresses_by_interface.items():
        mac = next(
            (
                _normalized_mac(item.address)
                for item in addresses
                if item.family in link_families and _normalized_mac(item.address)
            ),
            None,
        )
        stats = stats_by_interface.get(name)
        is_up = bool(stats.isup) if stats is not None else True
        for item in addresses:
            if item.family != socket.AF_INET:
                continue
            try:
                address = ipaddress.IPv4Address(item.address)
            except ipaddress.AddressValueError:
                continue
            if address.is_loopback or address.is_unspecified or address.is_multicast:
                continue
            prefix_length = _prefix_from_netmask(item.netmask)
            score = _interface_score(
                name, item.address, prefix_length, is_up, mac, preferred_ip
            )
            candidates.append((score, name, item.address, prefix_length, mac))

    if not candidates:
        return None
    _, name, ip, prefix_length, mac = max(candidates, key=lambda item: (item[0], item[1]))
    return NetworkInfo(interface=name, ip=ip, prefix_length=prefix_length, mac=mac)


def _gateway_for_interface(interface: str) -> Optional[str]:
    system = platform.system()
    if system == "Darwin":
        output = _run(["/sbin/route", "-n", "get", "default"])
        route_interface = re.search(r"^\s*interface:\s*(\S+)", output, re.MULTILINE)
        gateway = re.search(r"^\s*gateway:\s*(\d+(?:\.\d+){3})", output, re.MULTILINE)
        if route_interface and route_interface.group(1) == interface and gateway:
            return gateway.group(1)
    elif system == "Windows":
        escaped = interface.replace("'", "''")
        script = (
            f"$c=Get-NetIPConfiguration -InterfaceAlias '{escaped}' -ErrorAction SilentlyContinue; "
            "if ($c.IPv4DefaultGateway) {Write-Output $c.IPv4DefaultGateway.NextHop}"
        )
        output = _run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=5.0,
        ).strip()
        if re.fullmatch(r"\d+(?:\.\d+){3}", output):
            return output
    return None


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
    return NetworkInfo(ip=_socket_source_ip())


def get_network_info(include_gateway: bool = True) -> NetworkInfo:
    enumerated = _psutil_network_info()
    if enumerated is not None:
        gateway = (
            _gateway_for_interface(enumerated.interface)
            if include_gateway and enumerated.interface
            else None
        )
        return replace(enumerated, gateway=gateway)

    system = platform.system()
    if system == "Darwin":
        return _macos_network_info()
    if system == "Windows":
        return _windows_network_info()
    return _socket_fallback()
