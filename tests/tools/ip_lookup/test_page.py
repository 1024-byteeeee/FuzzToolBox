from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

import fuzztoolbox.tools.ip_lookup.page as page_module
from fuzztoolbox.tools.ip_lookup.page import IPLookupPage


class IPLookupPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_workers_are_released_after_finish_and_close_is_ready(self) -> None:
        """Closed tool pages must not leak QThread objects: after both workers
        finish, the page clears its references so prepare_close() can complete
        immediately instead of deferring (and eventually leaking memory)."""
        page = IPLookupPage()
        with patch.object(page_module, "discover_public_ips", lambda: (None, None)):
            page.show()  # showEvent auto-starts the public-IP worker
            self.app.processEvents()
            page.start_lookup()
            self.assertIsNotNone(page.worker)

            loop = QEventLoop()
            poll = QTimer()
            poll.timeout.connect(
                lambda: loop.quit()
                if page.worker is None and page.public_ip_worker is None
                else None
            )
            poll.start(20)
            QTimer.singleShot(5000, loop.quit)  # safety net on slow CI
            loop.exec()
            poll.stop()

        self.assertIsNone(page.worker)
        self.assertIsNone(page.public_ip_worker)
        self.assertTrue(page.prepare_close(lambda: None))
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
