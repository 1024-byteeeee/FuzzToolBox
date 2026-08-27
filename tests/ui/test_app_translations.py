from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QLineEdit

from fuzztoolbox.app import _install_chinese_translations


class ChineseTranslationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qt_standard_context_menu_is_chinese(self) -> None:
        """Every editable input's built-in context menu must show Chinese
        actions (剪切/复制/粘贴/删除/全选) app-wide."""
        _install_chinese_translations(self.app)
        edit = QLineEdit()
        edit.setText("abc")
        menu = edit.createStandardContextMenu()
        if menu is None:
            self.skipTest("standard context menu unavailable in this platform")
        try:
            texts = [action.text() for action in menu.actions()]
        finally:
            menu.deleteLater()
            edit.deleteLater()
        for keyword in ("剪切", "复制", "粘贴", "删除", "全选"):
            self.assertTrue(
                any(keyword in text for text in texts),
                f"expected Chinese action containing {keyword!r}, got {texts!r}",
            )


if __name__ == "__main__":
    unittest.main()
