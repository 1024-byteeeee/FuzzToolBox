"""Unicode-aware text statistics using only the Python standard library."""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TextStatistics:
    characters: int
    non_whitespace_characters: int
    word_units: int
    words: int
    cjk_characters: int
    digits: int
    whitespace: int
    lines: int
    non_empty_lines: int
    blank_lines: int
    paragraphs: int
    sentences: int
    utf8_bytes: int
    utf16_bytes: int


def _is_cjk(character):
    value = ord(character)
    return (
        0x3400 <= value <= 0x4DBF
        or 0x4E00 <= value <= 0x9FFF
        or 0xF900 <= value <= 0xFAFF
        or 0x20000 <= value <= 0x3134F
        or 0x3040 <= value <= 0x30FF
        or 0xAC00 <= value <= 0xD7AF
    )


def _word_groups(text):
    groups = 0
    inside = False
    for character in text:
        category = unicodedata.category(character)
        is_word = not _is_cjk(character) and (category[0] in {"L", "N", "M"} or character in {"_", "'", "’"})
        if is_word and not inside:
            groups += 1
        inside = is_word
    return groups


def analyze_text(text):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n") if normalized else []
    cjk = sum(_is_cjk(character) for character in normalized)
    words = _word_groups(normalized)
    non_empty_lines = sum(bool(line.strip()) for line in lines)
    paragraphs = len([part for part in re.split(r"\n\s*\n+", normalized.strip()) if part.strip()]) if normalized.strip() else 0
    sentences = len([part for part in re.split(r"[.!?。！？…]+", normalized.strip()) if part.strip()]) if normalized.strip() else 0
    return TextStatistics(
        characters=len(normalized),
        non_whitespace_characters=sum(not character.isspace() for character in normalized),
        word_units=cjk + words,
        words=words,
        cjk_characters=cjk,
        digits=sum(character.isdigit() for character in normalized),
        whitespace=sum(character.isspace() for character in normalized),
        lines=len(lines),
        non_empty_lines=non_empty_lines,
        blank_lines=len(lines) - non_empty_lines,
        paragraphs=paragraphs,
        sentences=sentences,
        utf8_bytes=len(normalized.encode("utf-8")),
        utf16_bytes=len(normalized.encode("utf-16-le")),
    )


def format_report(stats):
    return "\n".join(
        (
            "文本统计报告",
            f"字数：{stats.word_units}",
            f"字符数：{stats.characters}",
            f"非空白字符：{stats.non_whitespace_characters}",
            f"单词数：{stats.words}",
            f"中日韩字符：{stats.cjk_characters}",
            f"数字：{stats.digits}",
            f"空白字符：{stats.whitespace}",
            f"行数：{stats.lines}",
            f"非空行：{stats.non_empty_lines}",
            f"空白行：{stats.blank_lines}",
            f"段落数：{stats.paragraphs}",
            f"句子数：{stats.sentences}",
            f"UTF-8 字节数：{stats.utf8_bytes:,} 字节",
            f"UTF-16 LE 字节数：{stats.utf16_bytes:,} 字节",
        )
    )
