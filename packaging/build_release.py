"""Build the self-contained FuzzToolBox application on the current OS."""

import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from dmg_layout import create_styled_dmg

from fuzztoolbox import __version__

PROJECT_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = PROJECT_DIR / "build"
RELEASE_DIR = BUILD_DIR / "releases"
APP_NAME = "FuzzToolBox"

# Pages are imported on demand by the desktop shell.  Keep their modules in
# frozen builds even though the imports are intentionally not executed during
# startup (PyInstaller cannot infer string-based lazy imports on its own).
LAZY_TOOL_MODULES = (
    "fuzztoolbox.tools.device_info.page",
    "fuzztoolbox.tools.ip_scanner.page",
    "fuzztoolbox.tools.ip_lookup.page",
    "fuzztoolbox.tools.subnet_calculator.page",
    "fuzztoolbox.tools.subnet_mask_inverse.page",
    "fuzztoolbox.tools.uuid_generator.page",
    "fuzztoolbox.tools.token_generator.page",
    "fuzztoolbox.tools.json_formatter.page",
    "fuzztoolbox.tools.docker_compose_converter.page",
    "fuzztoolbox.tools.text_comparer.page",
    "fuzztoolbox.tools.text_statistics.page",
    "fuzztoolbox.tools.lorem_ipsum.page",
    "fuzztoolbox.tools.ipv4_converter.page",
    "fuzztoolbox.tools.qr_generator.page",
    "fuzztoolbox.tools.wifi_qr_generator.page",
    "fuzztoolbox.tools.color_picker.page",
    "fuzztoolbox.tools.screenshot.page",
    "fuzztoolbox.tools.roman_numeral.page",
    "fuzztoolbox.tools.password_strength.page",
    "fuzztoolbox.tools.random_port.page",
    "fuzztoolbox.tools.timer.page",
    "fuzztoolbox.tools.datetime_converter.page",
)


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


SIGN_IDENTITY = "FuzzToolBox Code Signing"
SIGN_PASSWORD = "fuzztoolbox"


def ensure_stable_signing_identity() -> tuple:
    """Create (once) a stable self-signed codesign certificate.

    macOS TCC grants (e.g. screen recording) are tied to the signing
    identity. Ad-hoc signatures change every build and reset the grants,
    so we sign with a persistent self-signed certificate instead.
    """
    cert_dir = PROJECT_DIR / "packaging" / "codesign"
    keychain = cert_dir / "codesign.keychain-db"
    p12 = cert_dir / "cert.p12"

    check = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning", str(keychain)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check.returncode == 0 and SIGN_IDENTITY in check.stdout:
        subprocess.run(
            ["security", "unlock-keychain", "-p", SIGN_PASSWORD, str(keychain)],
            check=True,
            timeout=60,
        )
        _add_keychain_to_search_list(keychain)
        return SIGN_IDENTITY, keychain

    cert_dir.mkdir(parents=True, exist_ok=True)
    if not p12.exists():
        key = cert_dir / "key.pem"
        cert = cert_dir / "cert.pem"
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert), "-days", "3650",
                "-nodes", "-subj", f"/CN={SIGN_IDENTITY}",
                "-addext", "keyUsage=digitalSignature",
                "-addext", "extendedKeyUsage=codeSigning",
            ],
            check=True,
            capture_output=True,
        )
        # Legacy 3DES/SHA1 PKCS12 so macOS `security import` accepts it.
        subprocess.run(
            [
                "openssl", "pkcs12", "-export", "-out", str(p12),
                "-inkey", str(key), "-in", str(cert),
                "-passout", f"pass:{SIGN_PASSWORD}",
                "-keypbe", "PBE-SHA1-3DES", "-certpbe", "PBE-SHA1-3DES",
                "-macalg", "sha1",
            ],
            check=True,
            capture_output=True,
        )
    if not keychain.exists():
        subprocess.run(
            ["security", "create-keychain", "-p", SIGN_PASSWORD, str(keychain)],
            check=True,
            timeout=60,
        )
    subprocess.run(
        ["security", "unlock-keychain", "-p", SIGN_PASSWORD, str(keychain)],
        check=True,
        timeout=60,
    )
    subprocess.run(
        [
            "security", "import", str(p12), "-k", str(keychain),
            "-P", SIGN_PASSWORD, "-T", "/usr/bin/codesign",
        ],
        check=True,
        timeout=90,
    )
    # No `security add-trusted-cert` here: it routes through Security Server
    # and can block forever on headless CI (no GUI session to answer the
    # authorization prompt), even for the user domain.  Trust settings are
    # not required for codesign to produce a signature and do not transfer
    # between machines anyway, so the step is skipped entirely.
    subprocess.run(
        [
            "security", "set-key-partition-list", "-S",
            "apple-tool:,apple:,codesign:", "-s", "-k", SIGN_PASSWORD,
            str(keychain),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    _add_keychain_to_search_list(keychain)
    return SIGN_IDENTITY, keychain


def _add_keychain_to_search_list(keychain: Path) -> None:
    """Add the codesign keychain to the user keychain search list so that
    `codesign` can locate the identity without the deprecated --keychain."""
    current = subprocess.run(
        ["security", "list-keychains", "-d", "user"],
        capture_output=True,
        text=True,
    )
    existing = [path.strip().strip('"') for path in current.stdout.splitlines()]
    target = str(keychain)
    if target in existing:
        return
    subprocess.run(
        ["security", "list-keychains", "-d", "user", "-s", target, *existing],
        check=True,
    )


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
    assets = PROJECT_DIR / "src" / "fuzztoolbox" / "assets"
    styles = PROJECT_DIR / "src" / "fuzztoolbox" / "styles"
    runtime_scripts = PROJECT_DIR / "src" / "fuzztoolbox" / "runtime_scripts"
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
        f"{assets}{os.pathsep}fuzztoolbox/assets",
        "--add-data",
        f"{styles}{os.pathsep}fuzztoolbox/styles",
        "--add-data",
        f"{runtime_scripts}{os.pathsep}fuzztoolbox/runtime_scripts",
    ]
    for module in LAZY_TOOL_MODULES:
        command.extend(["--hidden-import", module])
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
        ensure_stable_signing_identity()
        subprocess.run(
            [
                "/usr/bin/codesign", "--force", "--deep", "--sign",
                SIGN_IDENTITY, str(built_path),
            ],
            check=True,
        )
        release_path = RELEASE_DIR / f"{APP_NAME}-v{__version__}-{label}-{arch}.dmg"
        create_styled_dmg(built_path, release_path, APP_NAME)
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
