from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    description: str
    category: str
    icon: str
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
        icon="tool-ip-scanner.svg",
        keywords=("ip", "ping", "端口", "局域网", "主机发现"),
    ),
    ToolDefinition(
        id="ip-lookup",
        name="公网IP信息查询",
        description="查询公网 IP、Geo、ASN、ISP、组织与 PTR / rDNS。",
        category="网络工具",
        icon="tool-ip-lookup.svg",
        keywords=("ip", "geo", "asn", "isp", "ptr", "rdns", "公网", "归属地"),
    ),
    ToolDefinition(
        id="subnet-calculator",
        name="子网划分计算器",
        description="计算 IPv4/IPv6 网络信息，完成 FLSM 与 VLSM 子网规划。",
        category="网络工具",
        icon="tool-subnet-calculator.svg",
        keywords=("subnet", "cidr", "掩码", "flsm", "vlsm", "ipv4", "ipv6"),
    ),
    ToolDefinition(
        id="ipv4-converter",
        name="IPv4 地址转换器",
        description="将 IPv4 地址转换为二进制、十进制、十六进制及映射 IPv6。",
        category="网络工具",
        icon="tool-ipv4-converter.svg",
        keywords=("ipv4", "binary", "decimal", "hex", "二进制", "十六进制", "ipv6"),
    ),
    ToolDefinition(
        id="uuid-generator",
        name="UUID 生成器",
        description="生成 UUID v1、v3、v4、v5 与时间有序的 UUID v7。",
        category="开发工具",
        icon="tool-uuid-generator.svg",
        keywords=("uuid", "guid", "唯一标识", "随机", "开发"),
    ),
    ToolDefinition(
        id="token-generator",
        name="Token 生成器",
        description="使用自选字符集生成长度可配置的安全随机字符串。",
        category="开发工具",
        icon="tool-token-generator.svg",
        keywords=("token", "random", "string", "字符", "随机", "密钥", "令牌"),
    ),
    ToolDefinition(
        id="json-formatter",
        name="JSON 格式化与校验器",
        description="格式化、压缩并校验 JSON，精确定位语法错误。",
        category="开发工具",
        icon="tool-json-formatter.svg",
        keywords=("json", "格式化", "压缩", "校验", "验证", "语法", "美化"),
    ),
    ToolDefinition(
        id="docker-compose-converter",
        name="Docker Run 转 Compose",
        description="将 Docker Run 命令转换为结构清晰的 Docker Compose YAML。",
        category="开发工具",
        icon="tool-docker-compose-converter.svg",
        keywords=("docker", "run", "compose", "yaml", "容器", "转换"),
    ),
    ToolDefinition(
        id="text-comparer",
        name="文本对比工具",
        description="逐行比较两段文本，高亮增删改并生成标准 Diff。",
        category="开发工具",
        icon="tool-text-comparer.svg",
        keywords=("text", "diff", "compare", "文本", "对比", "差异", "unified", "context"),
    ),
    ToolDefinition(
        id="text-statistics",
        name="文本统计工具",
        description="实时统计字数、字符、单词、行数、段落与文本大小。",
        category="实用工具",
        icon="tool-text-statistics.svg",
        keywords=("text", "statistics", "count", "文本", "统计", "字数", "字符", "单词", "行数", "大小"),
    ),
    ToolDefinition(
        id="qr-generator",
        name="二维码生成器",
        description="将文本或网址生成可自定义颜色与容错率的二维码。",
        category="开发工具",
        icon="tool-qr-generator.svg",
        keywords=("qr", "qrcode", "二维码", "网址", "颜色", "容错"),
    ),
    ToolDefinition(
        id="wifi-qr-generator",
        name="WiFi 二维码生成器",
        description="生成可供手机扫码连接的 Wi-Fi 配置二维码。",
        category="网络工具",
        icon="tool-wifi-qr-generator.svg",
        keywords=("wifi", "wi-fi", "无线网络", "二维码", "ssid", "密码"),
    ),
    ToolDefinition(
        id="color-picker",
        name="取色器",
        description="通过色轮选取颜色，输出 HEX、RGB、HSL、HWB、LCH 与 CMYK。",
        category="开发工具",
        icon="tool-color-picker.svg",
        keywords=("color", "picker", "rgb", "hex", "hsl", "hwb", "lch", "cmyk", "色轮", "取色"),
    ),
    ToolDefinition(
        id="roman-numeral",
        name="罗马数字转换器",
        description="将罗马数字转换为数字，并将数字转换为罗马数字。",
        category="开发工具",
        icon="tool-roman-numeral.svg",
        keywords=("roman", "numeral", "罗马", "数字", "转换"),
    ),
    ToolDefinition(
        id="password-strength",
        name="密码强度分析器",
        description="分析密码的熵、字符集、评分与预计暴力破解时长。",
        category="开发工具",
        icon="tool-password-strength.svg",
        keywords=("password", "密码", "强度", "熵", "entropy", "暴力破解", "安全"),
    ),
    ToolDefinition(
        id="random-port",
        name="随机端口生成器",
        description="生成 1024–65535 范围内的随机非特权端口号。",
        category="网络工具",
        icon="tool-random-port.svg",
        keywords=("port", "random", "随机", "端口", "tcp", "udp", "开发"),
    ),
    ToolDefinition(
        id="timer",
        name="计时器",
        description="支持预设时长、暂停与继续的精准倒计时工具。",
        category="实用工具",
        icon="tool-timer.svg",
        keywords=("timer", "countdown", "计时", "倒计时", "提醒", "时间"),
    ),
    ToolDefinition(
        id="datetime-converter",
        name="日期时间转换器",
        description="在 Unix 时间戳、ISO 8601 和常用日期时间格式之间转换。",
        category="开发工具",
        icon="tool-datetime-converter.svg",
        keywords=("datetime", "timestamp", "unix", "epoch", "日期", "时间戳", "时区", "iso 8601", "rfc 3339"),
    ),
)


def filter_tools(
    tools: Iterable[ToolDefinition], query: str = "", category: str = "all"
) -> Tuple[ToolDefinition, ...]:
    return tuple(tool for tool in tools if tool.matches(query, category))
