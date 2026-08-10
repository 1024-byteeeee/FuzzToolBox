import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_windows_installer_uses_only_bundled_inno_resources(self):
        script = (PROJECT_DIR / "packaging" / "windows_installer.iss").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ChineseSimplified.isl", script)
        self.assertNotIn("compiler:Languages", script)


if __name__ == "__main__":
    unittest.main()
