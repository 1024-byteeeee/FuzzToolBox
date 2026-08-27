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
APP_POSITION = (190, 220)
APPLICATIONS_POSITION = (530, 220)
FINDER_DPI = 72
SCRIPT_DIR = Path(__file__).resolve().with_name("scripts")


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
    dots_per_meter = round(FINDER_DPI / 0.0254)
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)
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
        try:
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
        except subprocess.CalledProcessError as exc:
            # Restricted/headless macOS environments may not expose a usable
            # disk-image device, so UDRW creation or mounting can fail with
            # "Device not configured".  A flat compressed DMG remains fully
            # installable, even though Finder positioning is unavailable.
            print(f"Warning: custom DMG layout unavailable ({exc}); creating a flat DMG.")
            output_path.unlink(missing_ok=True)
            subprocess.run(
                [
                    "/usr/bin/hdiutil", "create", "-volname", volume_name,
                    "-srcfolder", str(source), "-ov", "-format", "UDZO",
                    "-imagekey", "zlib-level=9", str(output_path),
                ],
                check=True,
            )
            return
        attachment = plistlib.loads(attach.stdout)
        entity = next(
            item for item in attachment["system-entities"] if item.get("mount-point")
        )
        device = entity["dev-entry"]
        # Use the *actual* mounted volume name (mount-point basename) rather than
        # the requested volume name.  If another volume named `volume_name` is
        # already mounted, hdiutil appends " 1", " 2", … and Finder's
        # `first disk whose name is volume_name` would style the wrong (stale)
        # volume, leaving the freshly built DMG without its .DS_Store layout.
        mounted_name = Path(entity["mount-point"]).name
        if mounted_name != volume_name:
            print(
                f"Warning: volume mounted as {mounted_name!r} "
                f"(requested {volume_name!r}); using the actual mount name."
            )
        try:
            subprocess.run(
                [
                    "/usr/bin/osascript",
                    str(SCRIPT_DIR / "configure_dmg.applescript"),
                    mounted_name,
                    app_path.name,
                    str(120 + WINDOW_WIDTH),
                    str(120 + WINDOW_HEIGHT),
                    str(ICON_SIZE),
                    str(APP_POSITION[0]),
                    str(APP_POSITION[1]),
                    str(APPLICATIONS_POSITION[0]),
                    str(APPLICATIONS_POSITION[1]),
                ],
                check=True,
            )
        finally:
            # Finder can keep the background image or .DS_Store open briefly,
            # especially on hosted macOS runners. Ask it to release the disk,
            # then retry the detach before falling back to a forced detach.
            subprocess.run(
                [
                    "/usr/bin/osascript",
                    str(SCRIPT_DIR / "close_dmg_window.applescript"),
                    mounted_name,
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
