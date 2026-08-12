"""Standard-library IP information queries and connectivity checks."""

from __future__ import annotations

import ipaddress
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.request import Request, urlopen


USER_AGENT = "FuzzToolBox/2.1 IP-Lookup"
@dataclass
class SourceResult:
    source: str
    fields: Dict[str, object] = field(default_factory=dict)
    error: str = ""


@dataclass
class LookupReport:
    ip: str
    classification: str
    ptr: str = ""
    current_ipv4: str = ""
    current_ipv6: str = ""
    sources: List[SourceResult] = field(default_factory=list)

    def merged(self, key: str):
        for source in self.sources:
            value = source.fields.get(key)
            if value not in (None, ""):
                return value
        return None


def parse_public_ip(value: str) -> str:
    address = ipaddress.ip_address(value.strip())
    if not address.is_global:
        raise ValueError("请输入公网 IPv4 或 IPv6 地址")
    return str(address)


def classify_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    labels = [f"IPv{address.version}"]
    for matched, label in (
        (address.is_private, "私有地址"),
        (address.is_loopback, "回环地址"),
        (address.is_link_local, "链路本地"),
        (address.is_multicast, "组播地址"),
        (address.is_reserved, "保留地址"),
        (address.is_unspecified, "未指定地址"),
    ):
        if matched:
            labels.append(label)
    if len(labels) == 1:
        labels.append("公网地址" if address.is_global else "特殊用途地址")
    return " · ".join(labels)


def _read_json(url: str, timeout: float = 5.0) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_public_ip(version: int, timeout: float = 4.0) -> Optional[str]:
    url = (
        "https://api.ipify.org?format=json"
        if version == 4
        else "https://api6.ipify.org?format=json"
    )
    try:
        value = _read_json(url, timeout).get("ip", "")
        address = ipaddress.ip_address(value)
        return str(address) if address.version == version and address.is_global else None
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def discover_public_ips() -> tuple:
    with ThreadPoolExecutor(max_workers=2) as executor:
        ipv4 = executor.submit(discover_public_ip, 4)
        ipv6 = executor.submit(discover_public_ip, 6)
        return ipv4.result() or "", ipv6.result() or ""


def _ipwhois(ip: str) -> SourceResult:
    data = _read_json(f"https://ipwho.is/{ip}")
    if not data.get("success", True):
        raise ValueError(str(data.get("message", "查询失败")))
    connection = data.get("connection") or {}
    return SourceResult(
        "ipwho.is",
        {
            "country": data.get("country"),
            "region": data.get("region"),
            "city": data.get("city"),
            "asn": connection.get("asn"),
            "isp": connection.get("isp"),
            "org": connection.get("org"),
        },
    )


def _ipapi_co(ip: str) -> SourceResult:
    data = _read_json(f"https://ipapi.co/{ip}/json/")
    if data.get("error"):
        raise ValueError(str(data.get("reason", "查询失败")))
    return SourceResult(
        "ipapi.co",
        {
            "country": data.get("country_name"),
            "region": data.get("region"),
            "city": data.get("city"),
            "asn": data.get("asn"),
            "isp": data.get("org"),
            "org": data.get("org"),
        },
    )


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def lookup(ip: str) -> LookupReport:
    normalized = parse_public_ip(ip)
    report = LookupReport(normalized, classify_ip(normalized), reverse_dns(normalized))
    providers = [_ipwhois, _ipapi_co]
    for provider in providers:
        try:
            report.sources.append(provider(normalized))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            report.sources.append(SourceResult(provider.__name__.lstrip("_"), error=str(exc)))
    return report
