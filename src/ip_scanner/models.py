from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ScanConfig:
    method: str = "tcp"
    timeout: float = 0.5
    retries: int = 0
    concurrency: int = 256
    ports: List[int] = field(default_factory=lambda: [22, 80, 443, 445, 3389, 8080])
    resolve_hostname: bool = False
    include_dead: bool = False

    def validate(self) -> None:
        if self.method not in {"tcp", "ping"}:
            raise ValueError("扫描方式必须是 tcp 或 ping")
        if not 0.05 <= self.timeout <= 30:
            raise ValueError("超时时间必须在 0.05 到 30 秒之间")
        if not 1 <= self.concurrency <= 4096:
            raise ValueError("并发数必须在 1 到 4096 之间")
        if not 0 <= self.retries <= 5:
            raise ValueError("重试次数必须在 0 到 5 之间")
        if self.method == "tcp" and not self.ports:
            raise ValueError("TCP 扫描至少需要一个端口")
        if any(port < 1 or port > 65535 for port in self.ports):
            raise ValueError("端口必须在 1 到 65535 之间")


@dataclass
class ScanResult:
    ip: str
    is_alive: bool
    method: str
    response_time_ms: Optional[float] = None
    hostname: Optional[str] = None
    mac: Optional[str] = None
    open_ports: List[int] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScanProgress:
    scanned: int
    total: int
    alive: int
    elapsed_seconds: float

    @property
    def rate(self) -> float:
        return self.scanned / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0
