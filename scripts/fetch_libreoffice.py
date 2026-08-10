"""Download and stage the official LibreOffice conversion runtime."""

import hashlib
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional


VERSION = "26.2.4"
PROJECT_DIR = Path(__file__).resolve().parent.parent
ARCH = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"
TARGET = PROJECT_DIR / "vendor" / "libreoffice" / f"{platform.system()}-{ARCH}"
MAC_SHA256 = {
    "arm64": "64e0ad05564554eeee639d49b08b20908a38d4722ec95f1620d05c99bcbe9fb1",
}
WINDOWS_SHA256 = {
    "x86_64": "202f26cda071c5aa4996a5a28412fddceb3891dceb0366982c62650456c0730f",
}


def _download(url: str, target: Path) -> None:
    print(f"Downloading LibreOffice {VERSION} from The Document Foundation...")
    with urllib.request.urlopen(url) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, 1024 * 1024)


def _verify(path: Path, expected: Optional[str]) -> None:
    if not expected:
        return
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise SystemExit("LibreOffice download checksum mismatch")


def _stage_macos(work: Path) -> None:
    upstream_arch = "aarch64" if ARCH == "arm64" else "x86-64"
    image = work / "LibreOffice.dmg"
    url = (
        f"https://download.documentfoundation.org/libreoffice/stable/{VERSION}/mac/"
        f"{upstream_arch}/LibreOffice_{VERSION}_MacOS_{upstream_arch}.dmg"
    )
    _download(url, image)
    _verify(image, MAC_SHA256.get(ARCH))
    mount = work / "mount"
    mount.mkdir()
    subprocess.run(
        ["/usr/bin/hdiutil", "attach", str(image), "-nobrowse", "-readonly", "-mountpoint", str(mount)],
        check=True,
    )
    try:
        shutil.copytree(mount / "LibreOffice.app", TARGET / "LibreOffice.app", symlinks=True)
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=True)


def _stage_windows(work: Path) -> None:
    if ARCH != "x86_64":
        raise SystemExit("The bundled Windows LibreOffice runtime currently requires x86-64")
    installer = work / "LibreOffice.msi"
    url = (
        f"https://download.documentfoundation.org/libreoffice/stable/{VERSION}/win/x86_64/"
        f"LibreOffice_{VERSION}_Win_x86-64.msi"
    )
    _download(url, installer)
    _verify(installer, WINDOWS_SHA256.get(ARCH))
    extracted = work / "extracted"
    subprocess.run(
        ["msiexec", "/a", str(installer), "/qn", f"TARGETDIR={extracted}"],
        check=True,
    )
    program = next(extracted.rglob("program/soffice.exe"), None)
    if program is None:
        raise SystemExit("LibreOffice administrative install did not contain soffice.exe")
    shutil.copytree(program.parent.parent, TARGET, dirs_exist_ok=True)


def main() -> None:
    expected = (
        TARGET / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
        if platform.system() == "Darwin"
        else TARGET / "program" / "soffice.exe"
    )
    if expected.is_file():
        print(f"Bundled LibreOffice is already staged: {expected}")
        return
    if platform.system() not in {"Darwin", "Windows"}:
        raise SystemExit(f"Unsupported platform: {platform.system()}")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="fuzztoolbox-libreoffice-") as work:
        if platform.system() == "Darwin":
            _stage_macos(Path(work))
        else:
            _stage_windows(Path(work))
    if not expected.is_file():
        raise SystemExit("LibreOffice staging failed")
    print(f"Staged bundled LibreOffice: {expected}")


if __name__ == "__main__":
    main()
