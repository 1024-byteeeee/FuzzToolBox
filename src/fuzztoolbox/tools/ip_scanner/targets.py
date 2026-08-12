import ipaddress
from dataclasses import dataclass
from typing import Iterator


MAX_IPV4 = (1 << 32) - 1


@dataclass(frozen=True)
class TargetRange:
    start: int
    end: int
    source: str

    @property
    def total(self) -> int:
        return self.end - self.start + 1

    def __iter__(self) -> Iterator[str]:
        for value in range(self.start, self.end + 1):
            yield str(ipaddress.IPv4Address(value))


def parse_target(value: str) -> TargetRange:
    text = value.strip()
    if not text:
        raise ValueError("扫描目标不能为空")

    if "-" in text:
        left, right = (part.strip() for part in text.split("-", 1))
        start = int(ipaddress.IPv4Address(left))
        end = int(ipaddress.IPv4Address(right))
        if start > end:
            raise ValueError("起始 IP 不能大于结束 IP")
        return TargetRange(start, end, text)

    if "/" in text:
        network = ipaddress.ip_network(text, strict=False)
        if network.version != 4:
            raise ValueError("当前仅支持 IPv4")
        # 网络地址和广播地址也可能是有效目标（/31、/32），保持完整 CIDR 语义。
        return TargetRange(int(network.network_address), int(network.broadcast_address), text)

    address = ipaddress.IPv4Address(text)
    return TargetRange(int(address), int(address), text)


def parse_ports(value: str):
    ports = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start < 1 or end > 65535:
                raise ValueError("端口必须在 1 到 65535 之间")
            if start > end:
                raise ValueError("端口范围起始值不能大于结束值")
            ports.update(range(start, end + 1))
        else:
            port = int(item)
            if port < 1 or port > 65535:
                raise ValueError("端口必须在 1 到 65535 之间")
            ports.add(port)
    ordered = sorted(ports)
    if not ordered or ordered[0] < 1 or ordered[-1] > 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    return ordered
