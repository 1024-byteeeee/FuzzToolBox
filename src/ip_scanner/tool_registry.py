from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    description: str
    category: str
    keywords: Tuple[str, ...] = ()

    def matches(self, query: str = "", category: str = "all") -> bool:
        if category != "all" and self.category != category:
            return False
        normalized = query.strip().casefold()
        if not normalized:
            return True
        searchable = " ".join(
            (self.name, self.description, self.category, *self.keywords)
        ).casefold()
        return normalized in searchable


TOOLS = (
    ToolDefinition(
        id="ip-scanner",
        name="IP Scanner",
        description="扫描指定网段，发现在线设备、主机名、MAC 地址与开放端口。",
        category="网络工具",
        keywords=("ip", "ping", "端口", "局域网", "主机发现"),
    ),
    ToolDefinition(
        id="subnet-calculator",
        name="子网划分计算器",
        description="计算 IPv4/IPv6 网络信息，完成 FLSM 与 VLSM 子网规划。",
        category="网络工具",
        keywords=("subnet", "cidr", "掩码", "flsm", "vlsm", "ipv4", "ipv6"),
    ),
)


def filter_tools(
    tools: Iterable[ToolDefinition], query: str = "", category: str = "all"
) -> Tuple[ToolDefinition, ...]:
    return tuple(tool for tool in tools if tool.matches(query, category))
