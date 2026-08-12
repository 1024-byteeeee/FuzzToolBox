"""Load external QSS resources and apply named widget styles."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
STYLE_DIR = PACKAGE_ROOT / "styles"
ASSET_DIR = PACKAGE_ROOT / "assets"
_BLOCK_PATTERN = re.compile(
    r"/\*\s*@style\s+([^\s]+)\s*\n(.*?)\n@endstyle\s*\*/", re.DOTALL
)


@lru_cache(maxsize=1)
def _catalog() -> dict[str, str]:
    text = (STYLE_DIR / "catalog.qss").read_text(encoding="utf-8")
    return {key: value.strip() for key, value in _BLOCK_PATTERN.findall(text)}


@lru_cache(maxsize=None)
def load_qss(name: str) -> str:
    """Return a complete QSS resource with packaged asset placeholders resolved."""
    text = (STYLE_DIR / name).read_text(encoding="utf-8")
    return text.replace("%ASSET_DIR%", ASSET_DIR.as_posix())


def style_text(key: str, **values: Any) -> str:
    """Return a named catalog style, optionally substituting dynamic values."""
    try:
        template = _catalog()[key]
    except KeyError as exc:
        raise KeyError(f"Unknown widget style: {key}") from exc
    return template.format_map(values) if values else template


def apply_style(widget: Any, key: str, **values: Any) -> None:
    """Apply a named external style to a widget."""
    widget.setStyleSheet(style_text(key, **values))


def clear_style(widget: Any) -> None:
    """Remove a temporary local style so the application theme is inherited again."""
    widget.setStyleSheet("")


def set_style_state(widget: Any, state: str) -> None:
    """Update a dynamic QSS property and immediately repolish its widget."""
    widget.setProperty("styleState", state)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
