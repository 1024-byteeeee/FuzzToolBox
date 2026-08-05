"""Build a native IP-Scanner bundle and a release archive on the current OS."""

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
    if system == "Darwin":
        command[3:3] = ["--osx-bundle-identifier", "com.github.1024-byteeeee.ip-scanner"]
    elif system == "Windows":
        command[3:3] = [
            "--version-file",
            str(PROJECT_DIR / "packaging" / "windows_version_info.txt"),
        ]
    subprocess.run(command, cwd=PROJECT_DIR, env=environment, check=True)

    label = platform_label()
    arch = normalized_architecture()
    archive_base = RELEASE_DIR / f"IP-Scanner-{label}-{arch}"
    if system == "Darwin":
        source_name = "IP-Scanner.app"
        app_path = BUILD_DIR / source_name
        plist_path = app_path / "Contents" / "Info.plist"
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
        plist["CFBundleIdentifier"] = "com.github.1024-byteeeee.ip-scanner"
        plist["CFBundleShortVersionString"] = __version__
        plist["CFBundleVersion"] = __version__
        with plist_path.open("wb") as handle:
            plistlib.dump(plist, handle)
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(app_path)],
            check=True,
        )
        archive_path = Path(f"{archive_base}.zip")
        if archive_path.exists():
            archive_path.unlink()
        subprocess.run(
            [
                "/usr/bin/ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_path),
                str(archive_path),
            ],
            check=True,
        )
        print(f"Built native bundle: {app_path}")
        print(f"Built release archive: {archive_path}")
        return archive_path
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
