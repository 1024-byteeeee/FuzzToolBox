import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

NAMESPACES = {
    "dns": uuid.NAMESPACE_DNS,
    "url": uuid.NAMESPACE_URL,
    "oid": uuid.NAMESPACE_OID,
    "x500": uuid.NAMESPACE_X500,
}


@dataclass(frozen=True)
class UUIDFormat:
    uppercase: bool = False
    hyphens: bool = True
    braces: bool = False


class UUID7Generator:
    """Generate monotonically increasing RFC 9562 UUIDv7 values."""

    _PAYLOAD_MASK = (1 << 74) - 1
    _RAND_B_MASK = (1 << 62) - 1

    def __init__(self):
        self._lock = threading.Lock()
        self._last_timestamp = -1
        self._last_payload = -1

    def generate(self, timestamp_ms: Optional[int] = None) -> uuid.UUID:
        now = int(time.time_ns() // 1_000_000) if timestamp_ms is None else timestamp_ms
        if not 0 <= now < (1 << 48):
            raise ValueError("UUID v7 时间戳超出有效范围")
        with self._lock:
            timestamp = max(now, self._last_timestamp)
            if timestamp > self._last_timestamp:
                payload = secrets.randbits(74)
            else:
                payload = self._last_payload + 1
                if payload > self._PAYLOAD_MASK:
                    timestamp += 1
                    payload = secrets.randbits(74)
            self._last_timestamp = timestamp
            self._last_payload = payload

        rand_a = payload >> 62
        rand_b = payload & self._RAND_B_MASK
        value = (
            (timestamp << 80)
            | (7 << 76)
            | (rand_a << 64)
            | (0b10 << 62)
            | rand_b
        )
        return uuid.UUID(int=value)


def resolve_namespace(value: str) -> uuid.UUID:
    normalized = value.strip().casefold()
    if normalized in NAMESPACES:
        return NAMESPACES[normalized]
    try:
        return uuid.UUID(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError("请输入有效的命名空间 UUID") from exc


def format_uuid(value: uuid.UUID, options: UUIDFormat = UUIDFormat()) -> str:
    text = str(value) if options.hyphens else value.hex
    if options.uppercase:
        text = text.upper()
    if options.braces:
        text = "{" + text + "}"
    return text


def generate_uuids(
    version: int,
    count: int = 1,
    *,
    namespace: Optional[str] = None,
    name: Optional[str] = None,
    formatter: UUIDFormat = UUIDFormat(),
    uuid7_generator: Optional[UUID7Generator] = None,
) -> list[str]:
    if version not in {1, 3, 4, 5, 7}:
        raise ValueError("不支持的 UUID 版本")
    if not 1 <= count <= 100_000:
        raise ValueError("生成数量必须在 1 到 100000 之间")
    resolved_namespace = None
    if version in {3, 5}:
        if not name:
            raise ValueError("UUID v3/v5 必须填写名称")
        resolved_namespace = resolve_namespace(namespace or "")
    generator7 = uuid7_generator or UUID7Generator()

    values: Iterable[uuid.UUID]
    if version == 1:
        values = (uuid.uuid1() for _ in range(count))
    elif version == 3:
        values = (uuid.uuid3(resolved_namespace, name) for _ in range(count))
    elif version == 4:
        values = (uuid.uuid4() for _ in range(count))
    elif version == 5:
        values = (uuid.uuid5(resolved_namespace, name) for _ in range(count))
    else:
        values = (generator7.generate() for _ in range(count))
    return [format_uuid(value, formatter) for value in values]
