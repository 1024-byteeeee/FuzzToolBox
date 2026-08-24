"""Generate runtime, Windows and macOS icons from the SVG brand master."""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_DIR / "src" / "fuzztoolbox" / "assets" / "app-icon.svg"
RUNTIME_PNG = SOURCE.with_name("app-icon.png")
ICO_PATH = PROJECT_DIR / "packaging" / "FuzzToolBox.ico"
ICNS_PATH = PROJECT_DIR / "packaging" / "FuzzToolBox.icns"
WINDOWS_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(QSize(size, size), QImage.Format_RGBA8888)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Unable to encode {size}x{size} PNG")
    return bytes(data)


def write_ico(images: list[tuple[int, bytes]]) -> None:
    header_size = 6 + 16 * len(images)
    entries = []
    payload = bytearray()
    offset = header_size
    for size, png in images:
        encoded_size = 0 if size == 256 else size
        entries.append(
            struct.pack("<BBBBHHII", encoded_size, encoded_size, 0, 0, 1, 32, len(png), offset)
        )
        payload.extend(png)
        offset += len(png)
    ICO_PATH.write_bytes(
        struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + bytes(payload)
    )


def write_icns(renderer: QSvgRenderer) -> None:
    # Modern ICNS files store each representation as a PNG payload. Writing the
    # container directly also keeps icon generation reproducible on Windows.
    chunk_types = {
        16: b"icp4",
        32: b"icp5",
        64: b"icp6",
        128: b"ic07",
        256: b"ic08",
        512: b"ic09",
        1024: b"ic10",
    }
    chunks = []
    for size, chunk_type in chunk_types.items():
        png = render_png(renderer, size)
        chunks.append(chunk_type + struct.pack(">I", len(png) + 8) + png)
    body = b"".join(chunks)
    ICNS_PATH.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise SystemExit(f"Invalid SVG source: {SOURCE}")
    RUNTIME_PNG.write_bytes(render_png(renderer, 1024))
    write_ico([(size, render_png(renderer, size)) for size in WINDOWS_SIZES])
    write_icns(renderer)
    app.quit()
    print(f"Generated {RUNTIME_PNG}")
    print(f"Generated {ICO_PATH} with {len(WINDOWS_SIZES)} sizes")
    print(f"Generated {ICNS_PATH}")


if __name__ == "__main__":
    main()
