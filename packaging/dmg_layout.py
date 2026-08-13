"""Create a styled macOS DMG using only bundled Python and system tools."""

import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


WINDOW_WIDTH = 720
WINDOW_HEIGHT = 440
ICON_SIZE = 112
APP_POSITION = (190, 265)
APPLICATIONS_POSITION = (530, 265)


def _detach_dmg(device: str, attempts: int = 6) -> None:
    """Detach a DMG after Finder has released its background and window state."""
    sync_command = shutil.which("sync")
    if sync_command:
        subprocess.run([sync_command], check=False)
    for attempt in range(attempts):
        result = subprocess.run(
            ["/usr/bin/hdiutil", "detach", device],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        if attempt + 1 < attempts:
            time.sleep(min(0.5 * (attempt + 1), 2.0))

    subprocess.run(
        ["/usr/bin/hdiutil", "detach", "-force", device],
        check=True,
    )


def _render_background(svg_path: Path, png_path: Path) -> None:
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication([])
    image = QImage(WINDOW_WIDTH, WINDOW_HEIGHT, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid DMG background SVG: {svg_path}")
    renderer.render(painter)
    painter.end()
    if not image.save(str(png_path), "PNG"):
        raise RuntimeError(f"Unable to render DMG background: {png_path}")
    app.quit()


def _render_background_isolated(svg_path: Path, png_path: Path) -> None:
    environment = dict(**__import__("os").environ)
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--render", str(svg_path), str(png_path)],
        check=True,
        env=environment,
    )


def create_styled_dmg(app_path: Path, output_path: Path, volume_name: str) -> None:
    """Build a compressed DMG with a deterministic Finder presentation."""
    with tempfile.TemporaryDirectory(prefix="fuzztoolbox-dmg-") as temp_text:
        temp = Path(temp_text)
        source = temp / "source"
        source.mkdir()
        shutil.copytree(app_path, source / app_path.name, symlinks=True)
        (source / "Applications").symlink_to("/Applications")
        background_dir = source / ".background"
        background_dir.mkdir()
        _render_background_isolated(
            Path(__file__).with_name("dmg-background.svg"),
            background_dir / "background.png",
        )

        read_write = temp / "layout.dmg"
        subprocess.run(
            [
                "/usr/bin/hdiutil", "create", "-volname", volume_name,
                "-srcfolder", str(source), "-ov", "-format", "UDRW",
                str(read_write),
            ],
            check=True,
        )
        attach = subprocess.run(
            ["/usr/bin/hdiutil", "attach", str(read_write), "-nobrowse", "-plist"],
            check=True,
            capture_output=True,
        )
        attachment = plistlib.loads(attach.stdout)
        entity = next(
            item for item in attachment["system-entities"] if item.get("mount-point")
        )
        mount_point = Path(entity["mount-point"])
        device = entity["dev-entry"]
        script = f'''
tell application "Finder"
  tell disk "{volume_name}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set pathbar visible of container window to false
    set the bounds of container window to {{120, 120, {120 + WINDOW_WIDTH}, {120 + WINDOW_HEIGHT}}}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to {ICON_SIZE}
    set text size of opts to 14
    set background picture of opts to file ".background:background.png"
    set position of item "{app_path.name}" to {{{APP_POSITION[0]}, {APP_POSITION[1]}}}
    set position of item "Applications" to {{{APPLICATIONS_POSITION[0]}, {APPLICATIONS_POSITION[1]}}}
    close
    open
    update without registering applications
    delay 2
  end tell
end tell
'''
        try:
            subprocess.run(["/usr/bin/osascript", "-e", script], check=True)
        finally:
            # Finder can keep the background image or .DS_Store open briefly,
            # especially on hosted macOS runners. Ask it to release the disk,
            # then retry the detach before falling back to a forced detach.
            subprocess.run(
                [
                    "/usr/bin/osascript", "-e",
                    f'tell application "Finder" to close every window whose target is disk "{volume_name}"',
                ],
                check=False,
            )
            _detach_dmg(device)
        output_path.unlink(missing_ok=True)
        subprocess.run(
            [
                "/usr/bin/hdiutil", "convert", str(read_write), "-format", "UDZO",
                "-imagekey", "zlib-level=9", "-o", str(output_path),
            ],
            check=True,
        )


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--render":
    _render_background(Path(sys.argv[2]), Path(sys.argv[3]))
