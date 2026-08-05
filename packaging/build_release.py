"""Build a self-contained, single-file IP-Scanner executable on the current OS."""

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
        "--onefile",
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
    if system == "Darwin":
        # A macOS .app is a directory bundle. Console mode intentionally produces
        # one Mach-O file; the program itself still opens the PySide GUI.
        pass
    elif system == "Windows":
        command[3:3] = [
            "--windowed",
            "--version-file",
            str(PROJECT_DIR / "packaging" / "windows_version_info.txt"),
        ]
    subprocess.run(command, cwd=PROJECT_DIR, env=environment, check=True)

    label = platform_label()
    arch = normalized_architecture()
    suffix = ".exe" if system == "Windows" else ""
    built_path = BUILD_DIR / f"IP-Scanner{suffix}"
    release_path = RELEASE_DIR / f"IP-Scanner-{label}-{arch}{suffix}"
    if not built_path.is_file():
        raise SystemExit(f"PyInstaller did not create the expected executable: {built_path}")

    if system == "Darwin":
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(built_path)],
            check=True,
        )

    if release_path.exists():
        release_path.unlink()
    shutil.copy2(built_path, release_path)
    if system != "Windows":
        release_path.chmod(release_path.stat().st_mode | 0o111)
    print(f"Built self-contained executable: {built_path}")
    print(f"Built release executable: {release_path}")
    return release_path


if __name__ == "__main__":
    build()
