"""Build the self-contained FuzzToolBox application on the current OS."""

import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ip_scanner import __version__

PROJECT_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = PROJECT_DIR / "build"
RELEASE_DIR = BUILD_DIR / "releases"
APP_NAME = "FuzzToolBox"


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


def find_inno_setup() -> Path:
    resolved = shutil.which("ISCC.exe") or shutil.which("iscc")
    candidates = [Path(resolved)] if resolved else []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Inno Setup 6" / "ISCC.exe")
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        raise SystemExit("Inno Setup 6 is required to build the Windows installer")
    return executable


def build() -> Path:
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise SystemExit(f"Unsupported build platform: {system}")

    BUILD_DIR.mkdir(exist_ok=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    # Remove artifacts from the former product name so users never receive a
    # mixture of IP-Scanner and FuzzToolBox files after an incremental build.
    for legacy_path in (
        BUILD_DIR / "IP-Scanner",
        BUILD_DIR / "IP-Scanner.app",
        BUILD_DIR / "IP-Scanner.exe",
        BUILD_DIR / "IP-Scanner.spec",
        BUILD_DIR / ".work" / "IP-Scanner",
    ):
        if legacy_path.is_dir():
            shutil.rmtree(legacy_path)
        elif legacy_path.exists():
            legacy_path.unlink()
    for legacy_release in RELEASE_DIR.glob("IP-Scanner-*"):
        if legacy_release.is_file():
            legacy_release.unlink()
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
        "--noupx",
        "--optimize",
        "1",
        "--name",
        APP_NAME,
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
    ]
    command.append(str(entry))
    if system == "Darwin":
        command[3:3] = [
            "--windowed",
            "--osx-bundle-identifier",
            "com.github.1024-byteeeee.fuzztoolbox",
            f"--icon={PROJECT_DIR / 'packaging' / 'FuzzToolBox.icns'}",
        ]
    elif system == "Windows":
        command[3:3] = [
            "--windowed",
            "--version-file",
            str(PROJECT_DIR / "packaging" / "windows_version_info.txt"),
            f"--icon={PROJECT_DIR / 'packaging' / 'FuzzToolBox.ico'}",
            "--exclude-module",
            "PySide6.QtDBus",
            "--exclude-module",
            "PySide6.QtNetwork",
        ]
    subprocess.run(command, cwd=PROJECT_DIR, env=environment, check=True)

    label = platform_label()
    arch = normalized_architecture()
    for previous in RELEASE_DIR.glob(f"{APP_NAME}-{label}-{arch}*"):
        if previous.is_file():
            previous.unlink()
    if system == "Darwin":
        built_path = BUILD_DIR / f"{APP_NAME}.app"
        if not built_path.is_dir():
            raise SystemExit(f"PyInstaller did not create the expected app: {built_path}")
        plist_path = built_path / "Contents" / "Info.plist"
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
        plist["CFBundleShortVersionString"] = __version__
        plist["CFBundleVersion"] = __version__
        plist["CFBundleDisplayName"] = "FuzzToolBox"
        plist["CFBundleName"] = "FuzzToolBox"
        with plist_path.open("wb") as handle:
            plistlib.dump(plist, handle)
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(built_path)],
            check=True,
        )
        release_path = RELEASE_DIR / f"{APP_NAME}-{label}-{arch}.dmg"
        with tempfile.TemporaryDirectory(prefix="fuzztoolbox-dmg-") as staging_text:
            staging = Path(staging_text)
            shutil.copytree(built_path, staging / built_path.name, symlinks=True)
            (staging / "Applications").symlink_to("/Applications")
            subprocess.run(
                [
                    "/usr/bin/hdiutil",
                    "create",
                    "-volname",
                    APP_NAME,
                    "-srcfolder",
                    str(staging),
                    "-ov",
                    "-format",
                    "UDZO",
                    str(release_path),
                ],
                check=True,
            )
    else:
        built_path = BUILD_DIR / APP_NAME
        executable = built_path / f"{APP_NAME}.exe"
        if not executable.is_file():
            raise SystemExit(f"PyInstaller did not create the expected application: {executable}")
        installer_name = f"{APP_NAME}-v{__version__}-{label}-{arch}-Setup"
        release_path = RELEASE_DIR / f"{installer_name}.exe"
        if release_path.exists():
            release_path.unlink()
        subprocess.run(
            [
                str(find_inno_setup()),
                f"/DMyAppVersion={__version__}",
                f"/DInstallerBaseName={installer_name}",
                str(PROJECT_DIR / "packaging" / "windows_installer.iss"),
            ],
            cwd=PROJECT_DIR,
            check=True,
        )
        if not release_path.is_file():
            raise SystemExit(f"Inno Setup did not create the expected installer: {release_path}")

    print(f"Built self-contained application: {built_path}")
    print(f"Built release artifact: {release_path}")
    return release_path


if __name__ == "__main__":
    build()
