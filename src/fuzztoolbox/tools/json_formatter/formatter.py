"""Parse, format and compact JSON using the Python standard library."""

import json
from dataclasses import dataclass
from typing import Any, Optional, Union


Indent = Union[int, str]


@dataclass(frozen=True)
class JSONErrorDetails:
    message: str
    line: int
    column: int
    position: int

    def display(self) -> str:
        return f"第 {self.line} 行，第 {self.column} 列：{self.message}"


class JSONValidationError(ValueError):
    def __init__(self, details: JSONErrorDetails):
        self.details = details
        super().__init__(details.display())


def parse_json(source: str) -> Any:
    if not source.strip():
        raise ValueError("请输入 JSON 内容")
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        raise JSONValidationError(
            JSONErrorDetails(exc.msg, exc.lineno, exc.colno, exc.pos)
        ) from exc


def format_json(source: str, indent: Indent = 2, *, sort_keys: bool = False) -> str:
    if indent not in (2, 4, "\t"):
        raise ValueError("缩进仅支持 2 空格、4 空格或 Tab")
    return json.dumps(
        parse_json(source),
        ensure_ascii=False,
        indent=indent,
        sort_keys=sort_keys,
        allow_nan=False,
    )


def compact_json(source: str, *, sort_keys: bool = False) -> str:
    return json.dumps(
        parse_json(source),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
        allow_nan=False,
    )


def validate_json(source: str) -> Optional[JSONErrorDetails]:
    try:
        parse_json(source)
    except JSONValidationError as exc:
        return exc.details
    return None
