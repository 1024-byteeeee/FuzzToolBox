"""Shortcut parsing and platform-neutral identities."""

from __future__ import annotations

ALIASES = {
    "control": "ctrl",
    "option": "alt",
    "cmd": "meta",
    "command": "meta",
    "win": "meta",
    "return": "enter",
    "esc": "escape",
}

MODIFIER_NAMES = {
    "alt",
    "option",
    "ctrl",
    "control",
    "shift",
    "meta",
    "cmd",
    "command",
    "win",
}


def parse_shortcut(sequence: str) -> list[str] | None:
    """Split a user-facing shortcut while rejecting single-key bindings."""
    parts = [part.strip().lower() for part in sequence.split("+") if part.strip()]
    if len(parts) < 2:
        return None
    return parts


def canonical_shortcut(sequence: str) -> frozenset[str] | None:
    """Return an order-independent shortcut identity with aliases collapsed."""
    parts = parse_shortcut(sequence)
    if parts is None:
        return None
    normalized = normalize_shortcut_parts(parts)
    if normalized is None:
        return None
    return frozenset(normalized)


def normalize_shortcut_parts(parts: list[str]) -> list[str] | None:
    """Collapse aliases into the key names emitted by native adapters."""
    normalized = [ALIASES.get(part, part) for part in parts]
    if len(set(normalized)) != len(normalized):
        return None
    return normalized


def simple_shortcut(parts: list[str]) -> tuple[set[str], str] | None:
    """Return the native modifier/key form when a chord can use it."""
    if parts[-1] in MODIFIER_NAMES or any(
        part not in MODIFIER_NAMES for part in parts[:-1]
    ):
        return None
    return set(parts[:-1]), parts[-1]


def windows_key_code(key: str) -> int | None:
    """Translate a portable shortcut key into a Windows virtual-key code."""
    if len(key) == 1 and key.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return 0x6F + int(key[1:])
    return {
        "backspace": 0x08,
        "tab": 0x09,
        "return": 0x0D,
        "enter": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "option": 0x12,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "meta": 0x5B,
        "win": 0x5B,
        "cmd": 0x5B,
        "command": 0x5B,
        "plus": 0xBB,
        "=": 0xBB,
        "-": 0xBD,
        ",": 0xBC,
        ".": 0xBE,
        "/": 0xBF,
        "`": 0xC0,
        "[": 0xDB,
        "\\": 0xDC,
        "]": 0xDD,
        "'": 0xDE,
    }.get(key)


def windows_shortcut_supported(sequence: str) -> bool:
    """Check syntax/key support without installing a Windows hook."""
    parts = parse_shortcut(sequence)
    return bool(
        parts
        and canonical_shortcut(sequence) is not None
        and all(windows_key_code(part) is not None for part in parts)
    )


def windows_shortcut_needs_registration_probe(sequence: str) -> bool:
    """Whether RegisterHotKey can probe this shortcut for an OS conflict."""
    parts = parse_shortcut(sequence)
    return bool(parts and simple_shortcut(parts) is not None)
