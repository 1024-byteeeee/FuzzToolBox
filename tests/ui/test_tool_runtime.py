from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QWidget

from fuzztoolbox.ui.tool_registry import ToolDefinition
from fuzztoolbox.ui.tool_runtime import (
    ToolActivity,
    ToolRuntimeManager,
    ToolRuntimeState,
)

TOOLS = (
    ToolDefinition("alpha", "工具 A", "", "测试", "alpha.svg"),
    ToolDefinition("beta", "工具 B", "", "测试", "beta.svg"),
)


class RuntimePage(QWidget):
    def __init__(self, *, active: bool = False, asynchronous: bool = False) -> None:
        super().__init__()
        self.active = active
        self.asynchronous = asynchronous
        self.prepare_calls = 0
        self._ready_callback = None

    def runtime_activity(self) -> ToolActivity:
        if self.active:
            return ToolActivity.running("测试任务正在运行")
        return ToolActivity()

    def prepare_close(self, on_ready) -> bool:
        self.prepare_calls += 1
        if not self.asynchronous:
            return True
        self._ready_callback = on_ready
        return False

    def finish_close(self) -> None:
        self.asynchronous = False
        callback, self._ready_callback = self._ready_callback, None
        if callback is not None:
            callback()


class ToolRuntimeManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.disposed = []
        self.runtime = ToolRuntimeManager(
            TOOLS,
            lambda tool_id, page: self.disposed.append((tool_id, page)),
        )

    def tearDown(self) -> None:
        for page in tuple(self.runtime._pages.values()):
            page.deleteLater()
        self.app.processEvents()

    def test_reports_loaded_and_running_tools(self) -> None:
        idle = RuntimePage()
        active = RuntimePage(active=True)
        self.runtime.register("alpha", idle)
        self.runtime.register("beta", active)

        snapshots = self.runtime.snapshots()

        self.assertEqual(self.runtime.loaded_count, 2)
        self.assertEqual(self.runtime.active_count, 1)
        self.assertEqual(snapshots[0].state, ToolRuntimeState.LOADED)
        self.assertEqual(snapshots[1].state, ToolRuntimeState.RUNNING)
        self.assertEqual(snapshots[1].detail, "测试任务正在运行")

    def test_closes_idle_tool_immediately(self) -> None:
        page = RuntimePage()
        self.runtime.register("alpha", page)

        self.assertTrue(self.runtime.request_close("alpha"))

        self.assertIsNone(self.runtime.page("alpha"))
        self.assertEqual(page.prepare_calls, 1)
        self.assertEqual(self.disposed, [("alpha", page)])

    def test_waits_for_asynchronous_tool_before_disposal(self) -> None:
        page = RuntimePage(active=True, asynchronous=True)
        self.runtime.register("alpha", page)

        self.assertTrue(self.runtime.request_close("alpha"))
        self.assertEqual(
            self.runtime.snapshots()[0].state,
            ToolRuntimeState.STOPPING,
        )
        self.assertEqual(self.disposed, [])

        page.finish_close()
        self.app.processEvents()

        self.assertIsNone(self.runtime.page("alpha"))
        self.assertEqual(self.disposed, [("alpha", page)])

    def test_close_all_notifies_once_after_every_tool_is_ready(self) -> None:
        immediate = RuntimePage()
        delayed = RuntimePage(active=True, asynchronous=True)
        self.runtime.register("alpha", immediate)
        self.runtime.register("beta", delayed)
        completed = []

        self.assertFalse(
            self.runtime.request_close_all(lambda: completed.append(True))
        )
        self.assertEqual([item[0] for item in self.disposed], ["alpha"])
        self.assertEqual(completed, [])

        delayed.finish_close()
        self.app.processEvents()

        self.assertEqual([item[0] for item in self.disposed], ["alpha", "beta"])
        self.assertEqual(completed, [True])

    def test_rejects_duplicate_and_unknown_registration(self) -> None:
        page = RuntimePage()
        self.runtime.register("alpha", page)
        self.runtime.register("alpha", page)

        with self.assertRaises(ValueError):
            self.runtime.register("alpha", RuntimePage())
        with self.assertRaises(KeyError):
            self.runtime.register("missing", RuntimePage())


if __name__ == "__main__":
    unittest.main()
