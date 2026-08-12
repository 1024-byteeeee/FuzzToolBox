import re
import unittest
from pathlib import Path

from fuzztoolbox.ui.style_loader import STYLE_DIR, load_qss, style_text


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


if __name__ == "__main__":
    unittest.main()
