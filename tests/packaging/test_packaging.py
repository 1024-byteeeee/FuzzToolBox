import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_package_exposes_only_the_gui_entry_point(self):
        config = (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[project.gui-scripts]", config)
        self.assertIn('fuzztoolbox = "fuzztoolbox.app:main"', config)
        self.assertNotIn("[project.scripts]", config)
        self.assertNotIn("fuzztoolbox-gui", config)
        self.assertFalse(
            (PROJECT_DIR / "src" / "fuzztoolbox" / "tools" / "ip_scanner" / "cli.py").exists()
        )

    def test_desktop_entry_point_defers_main_window_import_until_after_splash(self):
        script = (PROJECT_DIR / "src" / "fuzztoolbox" / "app.py").read_text(
            encoding="utf-8"
        )

        splash_position = script.index("show_splash_screen(app)")
        main_window_position = script.index("from .ui.main_window import")
        self.assertLess(splash_position, main_window_position)

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
        configure_script = (
            PROJECT_DIR / "packaging" / "scripts" / "configure_dmg.applescript"
        ).read_text(encoding="utf-8")
        close_script = (
            PROJECT_DIR / "packaging" / "scripts" / "close_dmg_window.applescript"
        ).read_text(encoding="utf-8")
        background = PROJECT_DIR / "packaging" / "dmg-background.svg"
        self.assertTrue(background.is_file())
        self.assertIn("configure_dmg.applescript", layout)
        self.assertIn("close_dmg_window.applescript", layout)
        self.assertIn("set background picture of opts", configure_script)
        self.assertIn("set position of item applicationName", configure_script)
        self.assertIn('set position of item "Applications"', configure_script)
        self.assertIn("close every window", close_script)
        self.assertIn('"-format", "UDZO"', layout)
        self.assertIn('shutil.which("sync")', layout)
        self.assertIn('"detach", "-force", device', layout)

    def test_system_scripts_are_external_resources(self):
        network_info = (
            PROJECT_DIR / "src" / "fuzztoolbox" / "core" / "network_info.py"
        ).read_text(encoding="utf-8")
        dmg_layout = (PROJECT_DIR / "packaging" / "dmg_layout.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Get-NetIPConfiguration", network_info)
        self.assertNotIn('tell application "Finder"', dmg_layout)

        runtime_scripts = (
            PROJECT_DIR / "src" / "fuzztoolbox" / "runtime_scripts" / "windows"
        )
        self.assertTrue((runtime_scripts / "get_network_info.ps1").is_file())
        self.assertTrue((runtime_scripts / "get_interface_gateway.ps1").is_file())
        self.assertTrue((runtime_scripts / "get_device_hardware.ps1").is_file())
        self.assertTrue((runtime_scripts / "get_system_status.ps1").is_file())

        device_collector = (
            PROJECT_DIR / "src" / "fuzztoolbox" / "tools" / "device_info" / "collector.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Get-CimInstance", device_collector)

    def test_runtime_scripts_are_included_in_package_and_pyinstaller(self):
        project_config = (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
        release_builder = (PROJECT_DIR / "packaging" / "build_release.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"runtime_scripts/windows/*.ps1"', project_config)
        self.assertIn("fuzztoolbox/runtime_scripts", release_builder)

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
