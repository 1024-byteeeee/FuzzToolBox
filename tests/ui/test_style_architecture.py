import re
import unittest
from pathlib import Path

from fuzztoolbox.ui.style_loader import (
    STYLE_DIR,
    current_theme,
    load_qss,
    set_theme,
    style_text,
    theme_color,
)


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "fuzztoolbox"


class StyleArchitectureTests(unittest.TestCase):
    def test_python_ui_modules_do_not_embed_widget_styles(self):
        allowed = {
            SOURCE_ROOT / "ui" / "main_window.py",
            SOURCE_ROOT / "ui" / "style_loader.py",
        }
        offenders = []
        for path in SOURCE_ROOT.rglob("*.py"):
            if path in allowed:
                continue
            if "setStyleSheet" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(SOURCE_ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_all_named_style_references_exist(self):
        pattern = re.compile(r'apply_style\([^\n]*?"([^"]+)"')
        missing = []
        for path in SOURCE_ROOT.rglob("*.py"):
            for key in pattern.findall(path.read_text(encoding="utf-8")):
                try:
                    style_text(key)
                except KeyError:
                    missing.append(f"{path.relative_to(SOURCE_ROOT)}: {key}")
        self.assertEqual(missing, [])

    def test_external_theme_and_catalog_are_packaged_resources(self):
        self.assertTrue((STYLE_DIR / "base.qss").is_file())
        self.assertTrue((STYLE_DIR / "catalog.qss").is_file())
        self.assertIn("QWidget {", load_qss("base.qss"))
        self.assertNotIn("%ASSET_DIR%", load_qss("base.qss"))

    def test_dark_theme_resolves_qss_and_custom_paint_colors(self):
        try:
            set_theme("dark")
            stylesheet = load_qss("base.qss")
            self.assertEqual(current_theme(), "dark")
            self.assertIn("#111827", stylesheet)
            self.assertIn("#edf2f7", stylesheet)
            self.assertIn("chevron-down-dark.svg", stylesheet)
            self.assertEqual(theme_color("surface"), "#182230")
            self.assertIn("#182230", style_text("ui.components:57"))
            self.assertIn("#1b3025", stylesheet)
            self.assertNotIn("#f0faf4", stylesheet)
        finally:
            set_theme("light")

    def test_light_theme_remains_the_default_visual_contract(self):
        set_theme("light")
        stylesheet = load_qss("base.qss")
        self.assertIn("#f5f7fa", stylesheet)
        self.assertNotIn("-dark.svg", stylesheet)
        self.assertEqual(theme_color("text"), "#303133")


if __name__ == "__main__":
    unittest.main()
