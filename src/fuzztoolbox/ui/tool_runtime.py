"""Lifecycle registry for loaded tool pages and their background activity."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from .tool_registry import ToolDefinition


class ToolRuntimeState(Enum):
    LOADED = "loaded"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ToolActivity:
    active: bool = False
    detail: str = "页面已加载，当前没有后台任务"

    @classmethod
    def running(cls, detail: str) -> ToolActivity:
        return cls(True, detail)


@dataclass(frozen=True)
class ToolRuntimeSnapshot:
    tool_id: str
    name: str
    icon: str
    state: ToolRuntimeState
    detail: str

    @property
    def active(self) -> bool:
        return self.state is not ToolRuntimeState.LOADED


class PageDisposer(Protocol):
    def __call__(self, tool_id: str, page: QWidget) -> None: ...


class ToolRuntimeManager(QObject):
    """Own loaded page registrations and coordinate safe asynchronous teardown."""

    changed = Signal()

    def __init__(
        self,
        tools: tuple[ToolDefinition, ...],
        disposer: PageDisposer,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._definitions = {tool.id: tool for tool in tools}
        self._disposer = disposer
        self._pages: dict[str, QWidget] = {}
        self._closing: set[str] = set()
        self._close_all_callbacks: list[Callable[[], None]] = []
        self._batch_closing = False

    @property
    def loaded_count(self) -> int:
        return len(self._pages)

    @property
    def active_count(self) -> int:
        return sum(snapshot.active for snapshot in self.snapshots())

    def register(self, tool_id: str, page: QWidget) -> None:
        current = self._pages.get(tool_id)
        if current is page:
            return
        if current is not None:
            raise ValueError(f"工具页面已经注册：{tool_id}")
        if tool_id not in self._definitions:
            raise KeyError(f"未知工具：{tool_id}")
        self._pages[tool_id] = page
        self.changed.emit()

    def page(self, tool_id: str) -> QWidget | None:
        return self._pages.get(tool_id)

    def snapshots(self) -> tuple[ToolRuntimeSnapshot, ...]:
        snapshots = []
        for tool_id, page in self._pages.items():
            tool = self._definitions[tool_id]
            if tool_id in self._closing:
                state = ToolRuntimeState.STOPPING
                detail = "正在安全结束后台活动并释放工具…"
            else:
                activity = self._page_activity(page)
                state = (
                    ToolRuntimeState.RUNNING
                    if activity.active
                    else ToolRuntimeState.LOADED
                )
                detail = activity.detail
            snapshots.append(
                ToolRuntimeSnapshot(tool_id, tool.name, tool.icon, state, detail)
            )
        return tuple(snapshots)

    def request_close(self, tool_id: str) -> bool:
        page = self._pages.get(tool_id)
        if page is None or tool_id in self._closing:
            return False
        self._closing.add(tool_id)
        self.changed.emit()
        self._advance_close(tool_id, page)
        return True

    def request_close_all(self, on_finished=None) -> bool:
        if not self._pages:
            return True
        if on_finished is not None:
            self._close_all_callbacks.append(on_finished)
        self._batch_closing = True
        try:
            for tool_id in tuple(self._pages):
                self.request_close(tool_id)
        finally:
            self._batch_closing = False
        if self._pages:
            return False
        if on_finished is not None:
            self._close_all_callbacks.remove(on_finished)
        return True

    def _advance_close(self, tool_id: str, page: QWidget) -> None:
        if self._pages.get(tool_id) is not page or tool_id not in self._closing:
            return
        prepare_close = getattr(page, "prepare_close", None)
        if prepare_close is not None:
            ready = prepare_close(
                lambda: QTimer.singleShot(
                    0, lambda: self._advance_close(tool_id, page)
                )
            )
            if not ready:
                return
        self._pages.pop(tool_id, None)
        self._closing.discard(tool_id)
        self._disposer(tool_id, page)
        self.changed.emit()
        self._notify_close_all_if_ready()

    def _notify_close_all_if_ready(self) -> None:
        if self._batch_closing or self._pages or not self._close_all_callbacks:
            return
        callbacks, self._close_all_callbacks = self._close_all_callbacks, []
        for callback in callbacks:
            callback()

    @staticmethod
    def _page_activity(page: QWidget) -> ToolActivity:
        provider = getattr(page, "runtime_activity", None)
        if provider is None:
            return ToolActivity()
        activity = provider()
        if not isinstance(activity, ToolActivity):
            raise TypeError("runtime_activity() 必须返回 ToolActivity")
        return activity
