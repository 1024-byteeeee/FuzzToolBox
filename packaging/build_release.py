"""Build a self-contained, single-file IP-Scanner executable on the current OS."""

import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from ip_scanner import __version__

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
    }.get(platform.system(), platform.system())


def build() -> Path:
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
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
        command[3:3] = [
            "--windowed",
            "--osx-bundle-identifier",
            "com.github.1024-byteeeee.ip-scanner",
        ]
    elif system == "Windows":
        command[3:3] = [
            "--onefile",
            "--windowed",
            "--version-file",
            str(PROJECT_DIR / "packaging" / "windows_version_info.txt"),
        ]
    subprocess.run(command, cwd=PROJECT_DIR, env=environment, check=True)

    label = platform_label()
    arch = normalized_architecture()
    if system == "Darwin":
        built_path = BUILD_DIR / "IP-Scanner.app"
        if not built_path.is_dir():
            raise SystemExit(f"PyInstaller did not create the expected app: {built_path}")
        plist_path = built_path / "Contents" / "Info.plist"
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
        plist["CFBundleShortVersionString"] = __version__
        plist["CFBundleVersion"] = __version__
        with plist_path.open("wb") as handle:
            plistlib.dump(plist, handle)
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(built_path)],
            check=True,
        )
        release_path = RELEASE_DIR / f"IP-Scanner-{label}-{arch}.zip"
        if release_path.exists():
            release_path.unlink()
        subprocess.run(
            [
                "/usr/bin/ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(built_path),
                str(release_path),
            ],
            check=True,
        )
    else:
        built_path = BUILD_DIR / "IP-Scanner.exe"
        release_path = RELEASE_DIR / f"IP-Scanner-{label}-{arch}.exe"
        if not built_path.is_file():
            raise SystemExit(f"PyInstaller did not create the expected executable: {built_path}")
        if release_path.exists():
            release_path.unlink()
        shutil.copy2(built_path, release_path)

    print(f"Built self-contained application: {built_path}")
    print(f"Built release artifact: {release_path}")
    return release_path


if __name__ == "__main__":
    build()
