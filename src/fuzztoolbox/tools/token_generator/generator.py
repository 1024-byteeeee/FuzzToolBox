"""Generate cryptographically secure random tokens from selected character sets."""

import secrets
import string
from typing import Iterable, Sequence


MIN_LENGTH = 1
DEFAULT_LENGTH = 64
MAX_LENGTH = 512
LOWERCASE = string.ascii_lowercase
UPPERCASE = string.ascii_uppercase
DIGITS = string.digits
SYMBOLS = string.punctuation


def unique_characters(value: str) -> str:
    """Return characters in first-seen order with duplicates removed."""
    return "".join(dict.fromkeys(value))


def _secure_shuffle(values: Sequence[str]) -> str:
    items = list(values)
    for index in range(len(items) - 1, 0, -1):
        swap_index = secrets.randbelow(index + 1)
        items[index], items[swap_index] = items[swap_index], items[index]
    return "".join(items)


def generate_token(
    length: int = DEFAULT_LENGTH,
    *,
    lowercase: bool = True,
    uppercase: bool = True,
    digits: bool = True,
    symbols: bool = False,
    custom_characters: str = "",
) -> str:
    """Generate a token containing at least one character from each selected group."""
    if isinstance(length, bool) or not isinstance(length, int):
        raise ValueError("Token 长度必须是整数")
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        raise ValueError(f"Token 长度必须在 {MIN_LENGTH}–{MAX_LENGTH} 之间")

    groups: list[str] = []
    for enabled, characters in (
        (lowercase, LOWERCASE),
        (uppercase, UPPERCASE),
        (digits, DIGITS),
        (symbols, SYMBOLS),
    ):
        if enabled:
            groups.append(characters)
    custom = unique_characters(custom_characters)
    if custom:
        groups.append(custom)
    if not groups:
        raise ValueError("请至少选择一种字符类型或输入自定义字符")
    if length < len(groups):
        raise ValueError(f"长度不能小于已启用的字符类型数量（{len(groups)}）")

    pool = unique_characters("".join(groups))
    values = [secrets.choice(group) for group in groups]
    values.extend(secrets.choice(pool) for _ in range(length - len(values)))
    return _secure_shuffle(values)
