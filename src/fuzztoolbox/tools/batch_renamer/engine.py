"""Pure rename planning, validation, transactional execution, and undo."""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RuleKind(Enum):
    REPLACE = "replace"
    REGEX = "regex"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    NUMBER = "number"
    CASE = "case"
    REMOVE = "remove"


@dataclass(frozen=True)
class RenameRule:
    kind: RuleKind
    first: str = ""
    second: str = ""


@dataclass(frozen=True)
class RenameItem:
    source: Path
    target: Path
    selected: bool = True
    error: str = ""

    @property
    def changed(self) -> bool:
        return self.source.name != self.target.name

    @property
    def ready(self) -> bool:
        return self.selected and self.changed and not self.error


@dataclass(frozen=True)
class RenamePlan:
    items: tuple[RenameItem, ...]

    @property
    def errors(self) -> tuple[RenameItem, ...]:
        return tuple(item for item in self.items if item.selected and item.error)

    @property
    def ready_items(self) -> tuple[RenameItem, ...]:
        return tuple(item for item in self.items if item.ready)


@dataclass(frozen=True)
class RenameReceipt:
    mappings: tuple[tuple[Path, Path], ...]


class RenameError(RuntimeError):
    pass


_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_INVALID_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def transform_name(
    filename: str,
    rules: tuple[RenameRule, ...],
    index: int,
    *,
    preserve_extension: bool = True,
) -> str:
    path = Path(filename)
    suffix = path.suffix if preserve_extension else ""
    value = path.stem if suffix else filename
    for rule in rules:
        if rule.kind is RuleKind.REPLACE:
            value = value.replace(rule.first, rule.second)
        elif rule.kind is RuleKind.REGEX:
            value = re.sub(rule.first, rule.second, value)
        elif rule.kind is RuleKind.PREFIX:
            value = f"{rule.first}{value}"
        elif rule.kind is RuleKind.SUFFIX:
            value = f"{value}{rule.first}"
        elif rule.kind is RuleKind.NUMBER:
            start = _integer(rule.first, 1)
            width = max(1, min(12, _integer(rule.second, 3)))
            value = f"{value}_{start + index:0{width}d}"
        elif rule.kind is RuleKind.CASE:
            value = _convert_case(value, rule.first)
        elif rule.kind is RuleKind.REMOVE:
            start = max(0, _integer(rule.first, 0))
            count = max(0, _integer(rule.second, 1))
            value = value[:start] + value[start + count :]
    return f"{value}{suffix}"


def build_plan(
    sources: list[Path],
    rules: tuple[RenameRule, ...],
    *,
    selected: set[Path] | None = None,
    preserve_extension: bool = True,
) -> RenamePlan:
    normalized_sources = tuple(Path(source) for source in sources)
    selected_sources = set(normalized_sources) if selected is None else selected
    provisional = []
    selected_index = 0
    for source in normalized_sources:
        enabled = source in selected_sources
        try:
            name = transform_name(
                source.name,
                rules,
                selected_index,
                preserve_extension=preserve_extension,
            )
            error = validate_filename(name) if enabled else ""
        except (ValueError, re.error) as exc:
            name = source.name
            error = f"规则错误：{exc}" if enabled else ""
        provisional.append(RenameItem(source, source.with_name(name), enabled, error))
        if enabled:
            selected_index += 1
    return RenamePlan(_validate_collisions(tuple(provisional)))


def validate_filename(name: str) -> str:
    if not name or name in {".", ".."}:
        return "文件名不能为空"
    if _INVALID_CHARACTERS.search(name):
        return "包含跨平台不允许的字符"
    if name.endswith((" ", ".")):
        return "文件名不能以空格或句点结尾"
    if Path(name).stem.upper() in _WINDOWS_RESERVED:
        return "属于 Windows 保留名称"
    if len(os.fsencode(name)) > 255:
        return "文件名超过 255 字节"
    return ""


def execute_plan(plan: RenamePlan) -> RenameReceipt:
    if plan.errors:
        raise RenameError("重命名计划仍存在冲突")
    items = plan.ready_items
    if not items:
        raise RenameError("没有需要重命名的文件")
    _revalidate(items)
    staged: list[tuple[RenameItem, Path]] = []
    completed: list[tuple[RenameItem, Path]] = []
    try:
        for item in items:
            temporary = _temporary_path(item.source)
            item.source.replace(temporary)
            staged.append((item, temporary))
        for item, temporary in staged:
            temporary.replace(item.target)
            completed.append((item, temporary))
    except OSError as exc:
        _rollback(items, staged, completed)
        raise RenameError(f"重命名失败，已自动回滚：{exc}") from exc
    return RenameReceipt(tuple((item.source, item.target) for item in items))


def undo_receipt(receipt: RenameReceipt) -> RenameReceipt:
    reverse = RenamePlan(
        tuple(RenameItem(current, original) for original, current in receipt.mappings)
    )
    return execute_plan(reverse)


def _validate_collisions(items: tuple[RenameItem, ...]) -> tuple[RenameItem, ...]:
    selected_sources = {_path_key(item.source): item.source for item in items if item.selected}
    target_counts: dict[tuple[str, str], int] = {}
    for item in items:
        if item.selected:
            key = _path_key(item.target)
            target_counts[key] = target_counts.get(key, 0) + 1
    validated = []
    for item in items:
        error = item.error
        if item.selected and not error:
            target_key = _path_key(item.target)
            if target_counts[target_key] > 1:
                error = "新名称与批次中的其他文件重复"
            elif item.target.exists() and target_key not in selected_sources:
                error = "目标文件已经存在"
            elif not item.source.exists():
                error = "源文件不存在"
            elif not item.source.is_file():
                error = "当前版本只支持文件"
        validated.append(RenameItem(item.source, item.target, item.selected, error))
    return tuple(validated)


def _revalidate(items: tuple[RenameItem, ...]) -> None:
    sources = {_path_key(item.source) for item in items}
    for item in items:
        if not item.source.is_file():
            raise RenameError(f"源文件已不存在：{item.source.name}")
        if item.target.exists() and _path_key(item.target) not in sources:
            raise RenameError(f"目标文件已存在：{item.target.name}")


def _rollback(items, staged, completed) -> None:
    recovery: list[tuple[RenameItem, Path]] = []
    completed_items = {item for item, _temporary in completed}
    for item, temporary in reversed(completed):
        if item.target.exists():
            rescue = _temporary_path(item.target)
            item.target.replace(rescue)
            recovery.append((item, rescue))
    for item, temporary in staged:
        if item not in completed_items and temporary.exists():
            recovery.append((item, temporary))
    for item, temporary in recovery:
        if temporary.exists():
            temporary.replace(item.source)


def _temporary_path(path: Path) -> Path:
    while True:
        candidate = path.with_name(f".fuzztoolbox-rename-{uuid.uuid4().hex}.tmp")
        if not candidate.exists():
            return candidate


def _path_key(path: Path) -> tuple[str, str]:
    parent = unicodedata.normalize("NFC", str(path.parent)).casefold()
    name = unicodedata.normalize("NFC", path.name).casefold()
    return parent, name


def _integer(value: str, default: int) -> int:
    return int(value.strip()) if value.strip() else default


def _convert_case(value: str, mode: str) -> str:
    if mode == "upper":
        return value.upper()
    if mode == "lower":
        return value.lower()
    if mode == "title":
        return value.title()
    if mode == "capitalize":
        return value[:1].upper() + value[1:].lower()
    return value
