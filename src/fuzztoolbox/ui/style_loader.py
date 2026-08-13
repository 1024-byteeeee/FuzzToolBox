"""Load external QSS resources and apply named widget styles."""

from __future__ import annotations

import re
import weakref
from functools import lru_cache
from pathlib import Path
from typing import Any

from .theme_colors import DARK, DARK_REPLACEMENTS, LIGHT


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
STYLE_DIR = PACKAGE_ROOT / "styles"
ASSET_DIR = PACKAGE_ROOT / "assets"
_BLOCK_PATTERN = re.compile(
    r"/\*\s*@style\s+([^\s]+)\s*\n(.*?)\n@endstyle\s*\*/", re.DOTALL
)
_theme = "light"
_callbacks: list[weakref.ReferenceType] = []


@lru_cache(maxsize=1)
def _catalog() -> dict[str, str]:
    text = (STYLE_DIR / "catalog.qss").read_text(encoding="utf-8")
    return {key: value.strip() for key, value in _BLOCK_PATTERN.findall(text)}


@lru_cache(maxsize=None)
def load_qss(name: str) -> str:
    """Return a complete QSS resource with packaged asset placeholders resolved."""
    text = (STYLE_DIR / name).read_text(encoding="utf-8")
    text = text.replace("%ASSET_DIR%", ASSET_DIR.as_posix())
    return _themed(text)


def _themed(text: str) -> str:
    if _theme != "dark":
        return text
    text = re.sub(r"background:\s*white\b", f"background: {DARK['surface']}", text)
    for source, target in DARK_REPLACEMENTS.items():
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    for name in ("chevron-down", "chevron-up", "chevron-small-down", "checkbox-unchecked", "checkbox-unchecked-hover"):
        text = text.replace(f"{name}.svg", f"{name}-dark.svg")
    return text


def style_text(key: str, **values: Any) -> str:
    """Return a named catalog style, optionally substituting dynamic values."""
    try:
        template = _catalog()[key]
    except KeyError as exc:
        raise KeyError(f"Unknown widget style: {key}") from exc
    template = template.format_map(values) if values else template
    return _themed(template)


def apply_style(widget: Any, key: str, **values: Any) -> None:
    """Apply a named external style to a widget."""
    widget.setProperty("styleKey", key)
    widget.setProperty("styleValues", values)
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


def set_theme(theme: str) -> None:
    global _theme
    _theme = "dark" if theme == "dark" else "light"
    load_qss.cache_clear()


def current_theme() -> str:
    return _theme


def theme_color(role: str) -> str:
    return (DARK if _theme == "dark" else LIGHT)[role]


def refresh_widget_styles(widgets) -> None:
    for widget in widgets:
        key = widget.property("styleKey")
        if key:
            widget.setStyleSheet(style_text(key, **(widget.property("styleValues") or {})))
        widget.update()
    alive = []
    for reference in _callbacks:
        callback = reference()
        if callback is not None:
            callback()
            alive.append(reference)
    _callbacks[:] = alive


def on_theme_changed(callback) -> None:
    _callbacks.append(weakref.WeakMethod(callback) if getattr(callback, "__self__", None) else weakref.ref(callback))
