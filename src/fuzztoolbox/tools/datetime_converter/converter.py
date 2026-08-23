"""Exact date/time conversion using only the Python standard library."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
UNITS = {"seconds": 1, "milliseconds": 1_000, "microseconds": 1_000_000}


@dataclass(frozen=True)
class DateTimeResult:
    instant: datetime
    display: datetime

    def rows(self):
        utc = self.instant.astimezone(UTC)
        local = self.display
        seconds, micros = _unix_parts(utc)
        milliseconds = seconds * 1_000 + micros // 1_000
        microseconds = seconds * 1_000_000 + micros
        offset = local.strftime("%z")
        offset_text = "UTC" if offset == "+0000" else f"UTC{offset[:3]}:{offset[3:]}"
        iso = local.isoformat(timespec="microseconds").rstrip("0").rstrip(".")
        if local.microsecond == 0:
            iso = local.isoformat(timespec="seconds")
        return (
            ("Unix 时间戳（秒）", str(seconds)),
            ("Unix 时间戳（毫秒）", str(milliseconds)),
            ("Unix 时间戳（微秒）", str(microseconds)),
            ("ISO 8601", iso),
            ("RFC 3339", local.isoformat(timespec="milliseconds")),
            ("RFC 2822", format_datetime(local)),
            ("标准日期时间", local.strftime("%Y-%m-%d %H:%M:%S")),
            ("带毫秒日期时间", local.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]),
            ("UTC 日期时间", utc.strftime("%Y-%m-%d %H:%M:%S UTC")),
            ("HTTP 日期", format_datetime(utc, usegmt=True)),
            ("日期", local.strftime("%Y-%m-%d")),
            ("时间", local.strftime("%H:%M:%S")),
            ("年积日", local.strftime("%Y-%j")),
            ("ISO 周日期", f"{local.isocalendar().year}-W{local.isocalendar().week:02d}-{local.isocalendar().weekday}"),
            ("中文日期时间", f"{local.year}年{local.month}月{local.day}日 {local.hour:02d}时{local.minute:02d}分{local.second:02d}秒"),
            ("星期", WEEKDAYS[local.weekday()]),
            ("UTC 偏移", offset_text),
        )


def parse_timezone(value: str):
    text = value.strip().upper().replace("GMT", "UTC")
    if text in {"", "LOCAL", "本地"}:
        return None
    if text in {"UTC", "Z", "UTC+00:00", "UTC-00:00"}:
        return UTC
    match = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", text)
    if not match:
        raise ValueError("时区偏移格式应为 UTC+08:00")
    hours, minutes = int(match.group(2)), int(match.group(3) or 0)
    if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
        raise ValueError("UTC 偏移必须在 -14:00 至 +14:00 之间")
    delta = timedelta(hours=hours, minutes=minutes)
    if match.group(1) == "-":
        delta = -delta
    return timezone(delta)


def convert_timestamp(value: str, unit="auto", timezone_value="local") -> DateTimeResult:
    text = value.strip()
    if not re.fullmatch(r"[+-]?\d+", text):
        raise ValueError("时间戳必须是整数")
    raw = int(text)
    if unit == "auto":
        digits = len(text.lstrip("+-"))
        unit = "microseconds" if digits >= 16 else "milliseconds" if digits >= 13 else "seconds"
    if unit not in UNITS:
        raise ValueError("不支持的时间戳单位")
    scale = UNITS[unit]
    seconds, remainder = divmod(raw, scale)
    try:
        instant = EPOCH + timedelta(seconds=seconds, microseconds=remainder * (1_000_000 // scale))
    except OverflowError as exc:
        raise ValueError("时间戳超出支持范围（公元 1–9999 年）") from exc
    return _result(instant, timezone_value)


def convert_datetime(value: str, timezone_value="local") -> DateTimeResult:
    text = value.strip()
    if not text:
        raise ValueError("请输入日期时间")
    normalized = text[:-1] + "+00:00" if text.upper().endswith("Z") else text
    parsed = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError("请输入 ISO 8601 或 YYYY-MM-DD HH:mm:ss 格式")
    selected_tz = parse_timezone(timezone_value)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone() if selected_tz is None else parsed.replace(tzinfo=selected_tz)
    return _result(parsed.astimezone(UTC), timezone_value)


def current_result(timezone_value="local") -> DateTimeResult:
    return _result(datetime.now(UTC), timezone_value)


def _result(instant: datetime, timezone_value: str) -> DateTimeResult:
    target = parse_timezone(timezone_value)
    display = instant.astimezone() if target is None else instant.astimezone(target)
    return DateTimeResult(instant.astimezone(UTC), display)


def _unix_parts(value: datetime):
    delta = value - EPOCH
    total_seconds = delta.days * 86_400 + delta.seconds
    return total_seconds, delta.microseconds
