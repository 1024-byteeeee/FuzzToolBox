"""Compare text by line and character using Python's standard-library difflib."""

import difflib
from dataclasses import dataclass
from itertools import zip_longest
from typing import Optional, Tuple


Span = Tuple[int, int]


@dataclass(frozen=True)
class AlignedLine:
    tag: str
    left_number: Optional[int]
    left_text: Optional[str]
    right_number: Optional[int]
    right_text: Optional[str]
    left_spans: Tuple[Span, ...] = ()
    right_spans: Tuple[Span, ...] = ()


@dataclass(frozen=True)
class DiffStats:
    added: int = 0
    deleted: int = 0
    modified: int = 0

    @property
    def identical(self) -> bool:
        return not (self.added or self.deleted or self.modified)


@dataclass(frozen=True)
class ComparisonResult:
    lines: Tuple[AlignedLine, ...]
    stats: DiffStats


def _character_spans(left: str, right: str) -> tuple[Tuple[Span, ...], Tuple[Span, ...]]:
    left_spans = []
    right_spans = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if tag in {"replace", "delete"} and i1 != i2:
            left_spans.append((i1, i2))
        if tag in {"replace", "insert"} and j1 != j2:
            right_spans.append((j1, j2))
    return tuple(left_spans), tuple(right_spans)


def compare_texts(left: str, right: str) -> ComparisonResult:
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    aligned = []
    added = deleted = modified = 0
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                aligned.append(
                    AlignedLine("equal", i1 + offset + 1, left_lines[i1 + offset], j1 + offset + 1, right_lines[j1 + offset])
                )
        elif tag == "delete":
            for index in range(i1, i2):
                aligned.append(AlignedLine("delete", index + 1, left_lines[index], None, None))
                deleted += 1
        elif tag == "insert":
            for index in range(j1, j2):
                aligned.append(AlignedLine("insert", None, None, index + 1, right_lines[index]))
                added += 1
        else:
            for left_item, right_item in zip_longest(range(i1, i2), range(j1, j2)):
                if left_item is None:
                    aligned.append(AlignedLine("insert", None, None, right_item + 1, right_lines[right_item]))
                    added += 1
                elif right_item is None:
                    aligned.append(AlignedLine("delete", left_item + 1, left_lines[left_item], None, None))
                    deleted += 1
                else:
                    left_value = left_lines[left_item]
                    right_value = right_lines[right_item]
                    left_spans, right_spans = _character_spans(left_value, right_value)
                    aligned.append(
                        AlignedLine(
                            "replace",
                            left_item + 1,
                            left_value,
                            right_item + 1,
                            right_value,
                            left_spans,
                            right_spans,
                        )
                    )
                    modified += 1
    return ComparisonResult(tuple(aligned), DiffStats(added, deleted, modified))


def unified_diff(left: str, right: str, context: int = 3) -> str:
    _validate_context(context)
    return "".join(
        difflib.unified_diff(
            left.splitlines(keepends=True),
            right.splitlines(keepends=True),
            fromfile="原始文本",
            tofile="修改后文本",
            n=context,
        )
    )


def context_diff(left: str, right: str, context: int = 3) -> str:
    _validate_context(context)
    return "".join(
        difflib.context_diff(
            left.splitlines(keepends=True),
            right.splitlines(keepends=True),
            fromfile="原始文本",
            tofile="修改后文本",
            n=context,
        )
    )


def _validate_context(context: int) -> None:
    if isinstance(context, bool) or not isinstance(context, int) or not 0 <= context <= 20:
        raise ValueError("上下文行数必须在 0–20 之间")
