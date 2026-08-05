"""Build a native IP-Scanner bundle and a release archive on the current OS."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = PROJECT_DIR / "build"
RELEASE_DIR = BUILD_DIR / "releases"


def normalized_architecture() -> str:
    value = platform.machine().lower()
    if value in {"amd64", "x86_64"}:
        return "x86_64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    return value or "unknown"


def platform_label() -> str:
    return {
        "Darwin": "macOS",
        "Windows": "Windows",
        "Linux": "Linux",
    }.get(platform.system(), platform.system())


def build() -> Path:
    system = platform.system()
    if system not in {"Darwin", "Windows", "Linux"}:
        raise SystemExit(f"Unsupported build platform: {system}")

    BUILD_DIR.mkdir(exist_ok=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD_DIR / ".pyinstaller-config")
    assets = PROJECT_DIR / "src" / "ip_scanner" / "assets"
    entry = PROJECT_DIR / "packaging" / "macos_entry.py"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "IP-Scanner",
        "--distpath",
        str(BUILD_DIR),
        "--workpath",
        str(BUILD_DIR / ".work"),
        "--specpath",
        str(BUILD_DIR),
        "--paths",
        str(PROJECT_DIR / "src"),
        "--add-data",
        f"{assets}{os.pathsep}ip_scanner/assets",
        str(entry),
    ]
    subprocess.run(command, cwd=PROJECT_DIR, env=environment, check=True)

    label = platform_label()
    arch = normalized_architecture()
    archive_base = RELEASE_DIR / f"IP-Scanner-{label}-{arch}"
    if system == "Darwin":
        source_name = "IP-Scanner.app"
        archive_format = "zip"
    elif system == "Windows":
        source_name = "IP-Scanner"
        archive_format = "zip"
    else:
        source_name = "IP-Scanner"
        archive_format = "gztar"

    extension = ".tar.gz" if archive_format == "gztar" else ".zip"
    archive_path = Path(f"{archive_base}{extension}")
    if archive_path.exists():
        archive_path.unlink()
    result = shutil.make_archive(
        str(archive_base),
        archive_format,
        root_dir=BUILD_DIR,
        base_dir=source_name,
    )
    print(f"Built native bundle: {BUILD_DIR / source_name}")
    print(f"Built release archive: {result}")
    return Path(result)


if __name__ == "__main__":
    build()
