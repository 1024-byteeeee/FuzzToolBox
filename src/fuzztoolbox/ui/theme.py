"""Backward-compatible access to the external application theme."""

from .style_loader import load_qss


STYLE = load_qss("base.qss")
