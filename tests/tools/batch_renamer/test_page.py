import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QHeaderView, QPushButton

from fuzztoolbox.tools.batch_renamer.page import BatchRenamerPage, RuleRow
from fuzztoolbox.ui.style_loader import set_theme


class BatchRenamerPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = BatchRenamerPage()

    def tearDown(self):
        self.page.close()

    def test_file_and_rule_changes_update_preview_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "draft.txt"
            source.touch()
            self.page._add_paths([source])
            self.page.rule_rows[0].first.setText("draft")
            self.page.rule_rows[0].second.setText("release")
            self.app.processEvents()

            self.assertEqual(self.page.preview.rowCount(), 1)
            self.assertEqual(self.page.preview.item(0, 2).text(), "release.txt")
            self.assertTrue(self.page.rename_button.isEnabled())

    def test_related_options_and_workspace_panels_have_clear_spacing(self):
        self.page.resize(1200, 720)
        self.page.show()
        self.app.processEvents()

        option_gap = (
            self.page.preserve_extension.geometry().left()
            - self.page.recursive.geometry().right()
            - 1
        )
        rules = self.page.findChild(QFrame, "renameRulesPanel")
        preview = self.page.findChild(QFrame, "renamePreviewPanel")
        panel_gap = preview.geometry().left() - rules.geometry().right() - 1

        self.assertGreaterEqual(option_gap, 18)
        self.assertGreaterEqual(panel_gap, 14)

    def test_rules_surface_and_actions_are_clear_in_dark_mode(self):
        set_theme("dark")
        try:
            page = BatchRenamerPage()
            scroll = page.findChild(QFrame, "renameRulesScroll")
            row = page.findChild(RuleRow, "renameRuleRow")

            self.assertIsNotNone(scroll)
            self.assertIn("background: transparent", scroll.styleSheet())
            self.assertIn(
                "QWidget#renameRulesContent",
                page.rules_content.styleSheet(),
            )
            self.assertIn("#79bdff", row.styleSheet())
            self.assertNotIn("#526176", row.styleSheet())
            page.close()
        finally:
            set_theme("light")

    def test_preview_columns_are_responsive_and_bulk_selection_is_available(self):
        header = self.page.preview.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.Stretch)
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.Stretch)
        self.assertEqual(header.sectionResizeMode(3), QHeaderView.ResizeToContents)

        buttons = {
            button.text(): button
            for button in self.page.findChildren(QPushButton)
        }
        self.assertIn("全选", buttons)
        self.assertIn("反选", buttons)

        with tempfile.TemporaryDirectory() as directory:
            sources = []
            for name in ("first.txt", "second.txt"):
                source = Path(directory) / name
                source.touch()
                sources.append(source)
            self.page._add_paths(sources)

            self.assertEqual(
                self.page.preview.item(0, 0).textAlignment(),
                Qt.AlignCenter,
            )
            self.assertEqual(
                self.page.preview.item(0, 3).textAlignment(),
                Qt.AlignCenter,
            )
            self.assertGreaterEqual(
                self.page.preview.horizontalHeaderItem(3).sizeHint().width(),
                140,
            )

            buttons["反选"].click()
            self.assertTrue(
                all(
                    self.page.preview.item(row, 0).checkState() == Qt.Unchecked
                    for row in range(self.page.preview.rowCount())
                )
            )
            buttons["全选"].click()
            self.assertTrue(
                all(
                    self.page.preview.item(row, 0).checkState() == Qt.Checked
                    for row in range(self.page.preview.rowCount())
                )
            )


if __name__ == "__main__":
    unittest.main()
