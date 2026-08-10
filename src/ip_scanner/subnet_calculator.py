import ipaddress
from dataclasses import dataclass
from typing import Iterable, List, Union


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_network(value: str) -> IPNetwork:
    text = value.strip()
    if not text:
        raise ValueError("请输入 IP 地址和前缀或子网掩码")
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise ValueError("请输入有效网络，例如 192.168.1.10/24 或 2001:db8::/48") from exc


def usable_range(network: IPNetwork):
    if network.version == 6 or network.prefixlen >= network.max_prefixlen - 1:
        return network.network_address, network.broadcast_address, network.num_addresses
    return (
        network.network_address + 1,
        network.broadcast_address - 1,
        network.num_addresses - 2,
    )


def network_summary(network: IPNetwork):
    first, last, usable = usable_range(network)
    wildcard = str(network.hostmask) if network.version == 4 else "—"
    broadcast = str(network.broadcast_address) if network.version == 4 else "—"
    return {
        "IP 版本": f"IPv{network.version}",
        "规范网络": network.with_prefixlen,
        "前缀长度": f"/{network.prefixlen}",
        "子网掩码": str(network.netmask),
        "通配符掩码": wildcard,
        "网络地址": str(network.network_address),
        "广播地址": broadcast,
        "首个可用地址": str(first),
        "最后可用地址": str(last),
        "地址总数": network.num_addresses,
        "可用地址数": usable,
        "地址属性": address_scope(network),
    }


def address_scope(network: IPNetwork) -> str:
    address = network.network_address
    labels = []
    if address.is_private:
        labels.append("私有")
    if address.is_global:
        labels.append("公网")
    if address.is_loopback:
        labels.append("回环")
    if address.is_link_local:
        labels.append("链路本地")
    if address.is_multicast:
        labels.append("组播")
    if address.is_reserved:
        labels.append("保留")
    return "、".join(labels) or "普通"


@dataclass(frozen=True)
class SubnetRow:
    request_index: int
    requested_hosts: int
    network: IPNetwork

    @property
    def first(self) -> IPAddress:
        return usable_range(self.network)[0]

    @property
    def last(self) -> IPAddress:
        return usable_range(self.network)[1]

    @property
    def usable(self) -> int:
        return usable_range(self.network)[2]


@dataclass(frozen=True)
class FLSMPlan:
    network: IPNetwork
    target_prefix: int

    def __post_init__(self):
        if not self.network.prefixlen <= self.target_prefix <= self.network.max_prefixlen:
            raise ValueError(
                f"目标前缀必须在 /{self.network.prefixlen} 到 /{self.network.max_prefixlen} 之间"
            )

    @property
    def total(self) -> int:
        return 1 << (self.target_prefix - self.network.prefixlen)

    @property
    def subnet_size(self) -> int:
        return 1 << (self.network.max_prefixlen - self.target_prefix)

    def subnet_at(self, index: int) -> IPNetwork:
        if not 0 <= index < self.total:
            raise IndexError(index)
        address = int(self.network.network_address) + index * self.subnet_size
        return ipaddress.ip_network((address, self.target_prefix))

    def index_for_ip(self, value: str) -> int:
        address = ipaddress.ip_address(value.strip())
        if address.version != self.network.version or address not in self.network:
            raise ValueError("该 IP 不在当前基础网络内")
        return (int(address) - int(self.network.network_address)) // self.subnet_size


def flsm_by_count(network: IPNetwork, requested_count: int) -> FLSMPlan:
    if requested_count < 1:
        raise ValueError("子网数量必须大于 0")
    added_bits = (requested_count - 1).bit_length()
    target_prefix = network.prefixlen + added_bits
    if target_prefix > network.max_prefixlen:
        raise ValueError("基础网络无法划分出这么多子网")
    return FLSMPlan(network, target_prefix)


def parse_host_requirements(value: str) -> List[int]:
    normalized = value.replace("，", ",").replace("\n", ",")
    try:
        requirements = [int(item.strip()) for item in normalized.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("主机需求必须是用逗号或换行分隔的正整数") from exc
    if not requirements or any(item < 1 for item in requirements):
        raise ValueError("请至少输入一个大于 0 的主机需求")
    return requirements


def _prefix_for_hosts(version: int, hosts: int) -> int:
    bits = 32 if version == 4 else 128
    if version == 4:
        required_addresses = hosts if hosts <= 2 else hosts + 2
    else:
        required_addresses = hosts
    host_bits = (required_addresses - 1).bit_length()
    return bits - host_bits


def allocate_vlsm(network: IPNetwork, requirements: Iterable[int]) -> List[SubnetRow]:
    requested = list(requirements)
    if not requested or any(hosts < 1 for hosts in requested):
        raise ValueError("请至少输入一个大于 0 的主机需求")
    allocations = []
    cursor = int(network.network_address)
    limit = int(network.broadcast_address)
    ordered = sorted(enumerate(requested, start=1), key=lambda item: item[1], reverse=True)
    for request_index, hosts in ordered:
        prefix = _prefix_for_hosts(network.version, hosts)
        if prefix < network.prefixlen:
            raise ValueError(f"第 {request_index} 项需要 {hosts} 个地址，超出基础网络容量")
        size = 1 << (network.max_prefixlen - prefix)
        cursor = ((cursor + size - 1) // size) * size
        if cursor + size - 1 > limit:
            raise ValueError("基础网络剩余空间不足，无法完成 VLSM 分配")
        subnet = ipaddress.ip_network((cursor, prefix))
        allocations.append(SubnetRow(request_index, hosts, subnet))
        cursor += size
    return allocations
