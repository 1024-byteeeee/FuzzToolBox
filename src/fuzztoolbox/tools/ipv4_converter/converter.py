from dataclasses import dataclass
import ipaddress


@dataclass(frozen=True)
class IPv4Conversion:
    ipv4: str
    binary: str
    decimal: str
    hexadecimal: str
    ipv6: str
    ipv6_short: str

    def rows(self):
        return (
            ("二进制", self.binary),
            ("十进制", self.decimal),
            ("十六进制", self.hexadecimal),
            ("IPv6", self.ipv6),
            ("IPv6（简写）", self.ipv6_short),
        )


def convert_ipv4(value: str) -> IPv4Conversion:
    text = value.strip()
    if not text:
        raise ValueError("请输入 IPv4 地址")
    if "/" in text:
        raise ValueError("请输入单个 IPv4 地址，不要包含 CIDR 前缀")
    try:
        address = ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise ValueError("请输入有效的完整 IPv4 地址") from exc

    number = int(address)
    mapped = ipaddress.IPv6Address((0xFFFF << 32) | number)
    return IPv4Conversion(
        ipv4=str(address),
        binary=".".join(f"{octet:08b}" for octet in address.packed),
        decimal=str(number),
        hexadecimal=f"0x{number:08X}",
        ipv6=mapped.exploded,
        ipv6_short=f"::ffff:{address}",
    )
