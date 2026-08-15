from dataclasses import dataclass
import ipaddress


def _is_subnet_mask(number: int) -> bool:
    bits = f"{number:032b}"
    return "01" not in bits


@dataclass(frozen=True)
class MaskConversion:
    input_type: str
    prefix: int
    subnet_mask: str
    wildcard_mask: str
    network_bits: int
    host_bits: int
    total_addresses: int
    usable_hosts: int
    subnet_binary: str
    wildcard_binary: str

    def rows(self):
        return (
            ("子网掩码", self.subnet_mask),
            ("通配符掩码", self.wildcard_mask),
            ("CIDR 前缀", f"/{self.prefix}"),
            ("网络位数", str(self.network_bits)),
            ("主机位数", str(self.host_bits)),
            ("地址总数", f"{self.total_addresses:,}"),
            ("可用主机数", f"{self.usable_hosts:,}"),
            ("子网掩码（二进制）", self.subnet_binary),
            ("通配符掩码（二进制）", self.wildcard_binary),
        )


def convert_mask(value: str) -> MaskConversion:
    text = value.strip()
    if not text:
        raise ValueError("请输入子网掩码、通配符掩码或 CIDR 前缀")

    prefix_text = text[1:] if text.startswith("/") else text
    if prefix_text.isdecimal():
        prefix = int(prefix_text)
        if not 0 <= prefix <= 32:
            raise ValueError("CIDR 前缀必须在 /0 到 /32 之间")
        input_type = "CIDR 前缀"
    else:
        try:
            address = ipaddress.IPv4Address(text)
        except ipaddress.AddressValueError as exc:
            raise ValueError("请输入有效的 IPv4 掩码或 /0 到 /32 的 CIDR 前缀") from exc
        number = int(address)
        if _is_subnet_mask(number):
            prefix = f"{number:032b}".count("1")
            input_type = "子网掩码"
        elif _is_subnet_mask(number ^ 0xFFFFFFFF):
            prefix = f"{number ^ 0xFFFFFFFF:032b}".count("1")
            input_type = "通配符掩码"
        else:
            raise ValueError("掩码位必须连续，无法转换为有效的 CIDR 前缀")

    mask_number = ((1 << prefix) - 1) << (32 - prefix) if prefix else 0
    wildcard_number = mask_number ^ 0xFFFFFFFF
    subnet_mask = ipaddress.IPv4Address(mask_number)
    wildcard_mask = ipaddress.IPv4Address(wildcard_number)
    host_bits = 32 - prefix
    total = 1 << host_bits
    usable = total if prefix >= 31 else total - 2

    return MaskConversion(
        input_type=input_type,
        prefix=prefix,
        subnet_mask=str(subnet_mask),
        wildcard_mask=str(wildcard_mask),
        network_bits=prefix,
        host_bits=host_bits,
        total_addresses=total,
        usable_hosts=usable,
        subnet_binary=".".join(f"{octet:08b}" for octet in subnet_mask.packed),
        wildcard_binary=".".join(f"{octet:08b}" for octet in wildcard_mask.packed),
    )
