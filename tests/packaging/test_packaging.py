import unittest
import struct
import xml.etree.ElementTree as ET
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
        self.assertIn('shutil.which("sync")', layout)
        self.assertIn('"detach", "-force", device', layout)

    def test_macos_dmg_background_is_full_size_and_solid(self):
        background = PROJECT_DIR / "packaging" / "dmg-background.svg"
        root = ET.parse(background).getroot()
        self.assertEqual((root.get("width"), root.get("height")), ("720", "440"))
        children = list(root)
        self.assertEqual(len(children), 1)
        self.assertTrue(children[0].tag.endswith("rect"))
        self.assertEqual(children[0].get("width"), "720")
        self.assertEqual(children[0].get("height"), "440")

        layout = (PROJECT_DIR / "packaging" / "dmg_layout.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FINDER_DPI = 72", layout)
        self.assertIn("image.setDotsPerMeterX(dots_per_meter)", layout)
        self.assertIn("image.setDotsPerMeterY(dots_per_meter)", layout)

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
