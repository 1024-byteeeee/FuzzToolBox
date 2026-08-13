import unittest
import struct
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_macos_release_filename_includes_version(self):
        script = (PROJECT_DIR / "packaging" / "build_release.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'f"{APP_NAME}-v{__version__}-{label}-{arch}.dmg"',
            script,
        )

    def test_macos_dmg_has_styled_finder_layout(self):
        layout = (PROJECT_DIR / "packaging" / "dmg_layout.py").read_text(
            encoding="utf-8"
        )
        background = PROJECT_DIR / "packaging" / "dmg-background.svg"
        self.assertTrue(background.is_file())
        self.assertIn("set background picture of opts", layout)
        self.assertIn('set position of item "{app_path.name}"', layout)
        self.assertIn('set position of item "Applications"', layout)
        self.assertIn('"-format", "UDZO"', layout)

    def test_windows_installer_uses_only_bundled_inno_resources(self):
        script = (PROJECT_DIR / "packaging" / "windows_installer.iss").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ChineseSimplified.isl", script)
        self.assertNotIn("compiler:Languages", script)

    def test_windows_icon_contains_taskbar_and_high_resolution_sizes(self):
        icon = (PROJECT_DIR / "packaging" / "FuzzToolBox.ico").read_bytes()
        reserved, image_type, count = struct.unpack_from("<HHH", icon)
        self.assertEqual((reserved, image_type), (0, 1))
        sizes = set()
        for index in range(count):
            width, height = struct.unpack_from("<BB", icon, 6 + index * 16)
            sizes.add((width or 256, height or 256))
        self.assertTrue({(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= sizes)

    def test_macos_and_runtime_icons_exist(self):
        self.assertGreater((PROJECT_DIR / "packaging" / "FuzzToolBox.icns").stat().st_size, 0)
        self.assertGreater(
            (PROJECT_DIR / "src" / "fuzztoolbox" / "assets" / "app-icon.png").stat().st_size,
            0,
        )


if __name__ == "__main__":
    unittest.main()
