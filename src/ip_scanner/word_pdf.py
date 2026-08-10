import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple
from xml.etree import ElementTree


SUPPORTED_SUFFIXES = {".doc", ".docx", ".wps"}
WINDOWS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
ASSET_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
BUNDLED_CJK_FONT = ASSET_FONT_DIR / "NotoSansCJKsc-Regular.otf"
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_IGNORED_FONT_NAMES = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings", "cambria math"}
_COMMON_CJK_FONTS = (
    "宋体", "新宋体", "仿宋", "仿宋_GB2312", "黑体", "楷体", "楷体_GB2312",
    "微软雅黑", "等线", "华文宋体", "华文仿宋", "华文黑体", "华文楷体",
    "SimSun", "NSimSun", "FangSong", "KaiTi", "Microsoft YaHei", "DengXian",
)


class ConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    output: Path
    engine: str


def _docx_text_and_fonts(source: Path) -> Tuple[str, Tuple[str, ...]]:
    if source.suffix.lower() != ".docx":
        return "", ()
    text_parts = []
    fonts = set()
    try:
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if not name.startswith("word/") or not name.endswith(".xml"):
                    continue
                root = ElementTree.fromstring(archive.read(name))
                for element in root.iter():
                    local_name = element.tag.rsplit("}", 1)[-1]
                    if local_name in {"t", "delText", "instrText"} and element.text:
                        text_parts.append(element.text)
                    if local_name == "rFonts":
                        for value in element.attrib.values():
                            normalized = value.strip()
                            if normalized and normalized.casefold() not in _IGNORED_FONT_NAMES:
                                fonts.add(normalized)
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError):
        return "", ()
    return "".join(text_parts), tuple(sorted(fonts))


def _pdf_cjk_coverage(pdf_path: Path, source_text: str) -> Optional[float]:
    source_characters = Counter(_CJK_PATTERN.findall(unicodedata.normalize("NFKC", source_text)))
    if not source_characters:
        return None
    try:
        from pypdf import PdfReader

        output_text = "".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    except Exception:
        return None
    output_characters = Counter(
        _CJK_PATTERN.findall(unicodedata.normalize("NFKC", output_text))
    )
    matched = sum(min(count, output_characters[character]) for character, count in source_characters.items())
    return matched / sum(source_characters.values())


def _font_substitution_profile(profile: Path, source_fonts: Sequence[str], _system: str) -> None:
    fallback = "Noto Sans CJK SC"
    names = []
    for name in (*_COMMON_CJK_FONTS, *source_fonts):
        if name not in names and name.casefold() not in _IGNORED_FONT_NAMES:
            names.append(name)
    user_dir = profile / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    nodes = []
    for index, name in enumerate(names):
        escaped_name = (
            name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        nodes.append(
            f'<node oor:name="_{index}" oor:op="replace">'
            '<prop oor:name="Always" oor:op="fuse"><value>false</value></prop>'
            f'<prop oor:name="ReplaceFont" oor:op="fuse"><value>{escaped_name}</value></prop>'
            '<prop oor:name="OnScreenOnly" oor:op="fuse"><value>false</value></prop>'
            f'<prop oor:name="SubstituteFont" oor:op="fuse"><value>{fallback}</value></prop>'
            "</node>"
        )
    registry = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Font/Substitution/FontPairs">'
        + "".join(nodes)
        + "</item>"
        '<item oor:path="/org.openoffice.Office.Common/Font/Substitution">'
        '<prop oor:name="Replacement" oor:op="fuse"><value>true</value></prop>'
        "</item></oor:items>"
    )
    (user_dir / "registrymodifications.xcu").write_text(registry, encoding="utf-8")


def _fontconfig_file(folder: Path, cache: Path) -> Path:
    config = cache / "fonts.conf"
    folder_text = str(folder).replace("&", "&amp;").replace("<", "&lt;")
    cache_text = str(cache).replace("&", "&amp;").replace("<", "&lt;")
    config.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        f"<dir>{folder_text}</dir><cachedir>{cache_text}</cachedir>"
        '<alias><family>sans-serif</family><prefer><family>Noto Sans CJK SC</family></prefer></alias>'
        "</fontconfig>",
        encoding="utf-8",
    )
    return config


@contextmanager
def _temporary_windows_font(font: Path):
    registered = False
    if platform.system() == "Windows" and font.is_file():
        try:
            import ctypes

            registered = bool(ctypes.windll.gdi32.AddFontResourceExW(str(font), 0, None))
        except (AttributeError, OSError):
            registered = False
    try:
        yield
    finally:
        if registered:
            try:
                ctypes.windll.gdi32.RemoveFontResourceExW(str(font), 0, None)
            except (AttributeError, OSError):
                pass


@contextmanager
def _temporary_document_font(font: Path):
    if platform.system() == "Windows":
        with _temporary_windows_font(font):
            yield
        return
    url = None
    core_foundation = None
    core_text = None
    registered = False
    if platform.system() == "Darwin" and font.is_file():
        try:
            import ctypes

            core_foundation = ctypes.CDLL(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            core_text = ctypes.CDLL(
                "/System/Library/Frameworks/CoreText.framework/CoreText"
            )
            core_foundation.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_long,
                ctypes.c_bool,
            ]
            core_foundation.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
            core_text.CTFontManagerRegisterFontsForURL.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            core_text.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            core_text.CTFontManagerUnregisterFontsForURL.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            core_text.CTFontManagerUnregisterFontsForURL.restype = ctypes.c_bool
            path_bytes = str(font).encode("utf-8")
            url = core_foundation.CFURLCreateFromFileSystemRepresentation(
                None, path_bytes, len(path_bytes), False
            )
            registered = bool(
                core_text.CTFontManagerRegisterFontsForURL(url, 1, None)
            )
        except (AttributeError, OSError):
            registered = False
    try:
        yield
    finally:
        if registered and core_text and url:
            core_text.CTFontManagerUnregisterFontsForURL(url, 1, None)
        if core_foundation and url:
            core_foundation.CFRelease(url)


@contextmanager
def _docx_with_cjk_fallback(source: Path):
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ElementTree.register_namespace("w", namespace)
    temporary = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        with zipfile.ZipFile(source) as source_archive, zipfile.ZipFile(
            temporary_path, "w"
        ) as target_archive:
            for item in source_archive.infolist():
                data = source_archive.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    try:
                        root = ElementTree.fromstring(data)
                        changed = False
                        for run in root.iter(f"{{{namespace}}}r"):
                            run_text = "".join(
                                node.text or ""
                                for node in run.iter(f"{{{namespace}}}t")
                            )
                            if not _CJK_PATTERN.search(run_text):
                                continue
                            run_properties = run.find(f"{{{namespace}}}rPr")
                            if run_properties is None:
                                run_properties = ElementTree.Element(f"{{{namespace}}}rPr")
                                run.insert(0, run_properties)
                            fonts = run_properties.find(f"{{{namespace}}}rFonts")
                            if fonts is None:
                                fonts = ElementTree.SubElement(
                                    run_properties, f"{{{namespace}}}rFonts"
                                )
                            for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                                fonts.set(f"{{{namespace}}}{attribute}", "Noto Sans CJK SC")
                            changed = True
                        if changed:
                            data = ElementTree.tostring(
                                root, encoding="utf-8", xml_declaration=True
                            )
                    except ElementTree.ParseError:
                        pass
                target_archive.writestr(item, data)
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def _creation_flags() -> int:
    return WINDOWS_NO_WINDOW if platform.system() == "Windows" else 0


@lru_cache(maxsize=4)
def find_libreoffice(system: Optional[str] = None) -> Optional[Path]:
    system = system or platform.system()
    candidates = []
    # PyInstaller places bundled data below _MEIPASS.  Keep the office suite
    # separate from Python modules so it is only started when conversion is
    # requested and does not affect normal application startup.
    frozen_root = getattr(sys, "_MEIPASS", None)
    resource_roots = []
    if frozen_root:
        resource_roots.append(Path(frozen_root))
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        resource_roots.extend((
            executable.parent,
            executable.parent.parent / "Resources",
        ))
    for root in resource_roots:
        if system == "Darwin":
            candidates.append(
                root / "libreoffice" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
            )
        elif system == "Windows":
            candidates.extend((
                root / "libreoffice" / "program" / "soffice.exe",
                root / "libreoffice" / "LibreOffice" / "program" / "soffice.exe",
            ))
    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))
    if system == "Darwin":
        candidates.extend(
            (
                Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
                Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
            )
        )
    elif system == "Windows":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    return next((path for path in candidates if path.is_file()), None)


@lru_cache(maxsize=4)
def word_available(system: Optional[str] = None) -> bool:
    system = system or platform.system()
    if system == "Darwin":
        return any(
            path.is_dir()
            for path in (
                Path("/Applications/Microsoft Word.app"),
                Path.home() / "Applications/Microsoft Word.app",
            )
        )
    if system == "Windows":
        return _windows_com_available(("Word.Application",))
    return False


@lru_cache(maxsize=4)
def wps_available(system: Optional[str] = None) -> bool:
    system = system or platform.system()
    if system != "Windows":
        return False
    return _windows_com_available(("Kwps.Application", "Wps.Application"))


def _windows_com_available(program_ids: Sequence[str]) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    for program_id in program_ids:
        try:
            app = win32com.client.DispatchEx(program_id)
            app.Quit()
            return True
        except Exception:
            continue
    return False


def available_engines(system: Optional[str] = None) -> Tuple[str, ...]:
    system = system or platform.system()
    engines = []
    if word_available(system):
        engines.append("Microsoft Word")
    if wps_available(system):
        engines.append("WPS Office")
    libreoffice = find_libreoffice(system)
    if libreoffice:
        engines.append(
            "内置 LibreOffice" if "libreoffice" in {part.casefold() for part in libreoffice.parts} else "LibreOffice"
        )
    try:
        import dxpdf  # noqa: F401

        engines.append("内置 DOCX 引擎")
    except ImportError:
        pass
    return tuple(engines)


def _validate_source(source: Path) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ConversionError(f"文件不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ConversionError("仅支持 .doc、.docx 和 .wps 文件")
    return source


def _convert_windows_com(source: Path, output: Path, wps: bool = False) -> str:
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise ConversionError("Windows 转换组件未正确打包") from exc
    pythoncom.CoInitialize()
    app = None
    document = None
    try:
        program_ids = ("Kwps.Application", "Wps.Application") if wps else ("Word.Application",)
        for program_id in program_ids:
            try:
                app = win32com.client.DispatchEx(program_id)
                break
            except Exception:
                continue
        if app is None:
            raise ConversionError("未检测到可调用的 WPS Office" if wps else "未检测到 Microsoft Word")
        app.Visible = False
        with _suppress_com_property_errors():
            app.DisplayAlerts = 0
        document = app.Documents.Open(str(source), ReadOnly=True)
        document.ExportAsFixedFormat(str(output), 17)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"{'WPS' if wps else 'Word'} 转换失败：{exc}") from exc
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return "WPS Office" if wps else "Microsoft Word"


class _suppress_com_property_errors:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return True


_MAC_WORD_SCRIPT = r"""
function run(argv) {
  const source = argv[0];
  const output = argv[1];
  const word = Application('Microsoft Word');
  const wasRunning = word.running();
  word.launch();
  word.open(source);
  const document = word.activeDocument;
  try {
    document.saveAs({fileName: output, fileFormat: 'format PDF'});
  } finally {
    document.close({saving: 'no'});
    if (!wasRunning) word.quit();
  }
}
"""


def _convert_macos_word(source: Path, output: Path, timeout: int) -> str:
    result = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", _MAC_WORD_SCRIPT, str(source), str(output)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0 or not output.is_file():
        detail = result.stderr.strip() or "Microsoft Word 未生成 PDF"
        raise ConversionError(f"Word 转换失败：{detail}")
    return "Microsoft Word"


def _convert_libreoffice(
    source: Path, output: Path, executable: Path, timeout: int, source_fonts: Sequence[str] = ()
) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fuzztoolbox-lo-") as profile_text, tempfile.TemporaryDirectory(
        prefix="fuzztoolbox-pdf-"
    ) as output_text:
        profile = Path(profile_text)
        _font_substitution_profile(profile, source_fonts, platform.system())
        profile_uri = Path(profile_text).resolve().as_uri()
        environment = os.environ.copy()
        if BUNDLED_CJK_FONT.is_file():
            environment["SAL_FONTPATH"] = str(ASSET_FONT_DIR)
            environment["FONTCONFIG_FILE"] = str(_fontconfig_file(ASSET_FONT_DIR, profile))
        with _temporary_windows_font(BUNDLED_CJK_FONT):
            result = subprocess.run(
                [
                    str(executable),
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nolockcheck",
                    f"-env:UserInstallation={profile_uri}",
                    "--convert-to",
                    'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":"2"}}',
                    "--outdir",
                    output_text,
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                creationflags=_creation_flags(),
                env=environment,
            )
        generated = Path(output_text) / f"{source.stem}.pdf"
        if result.returncode != 0 or not generated.is_file():
            detail = result.stderr.strip() or result.stdout.strip() or "LibreOffice 未生成 PDF"
            raise ConversionError(f"LibreOffice 转换失败：{detail}")
        shutil.move(str(generated), str(output))
    return "LibreOffice"


def _convert_builtin_docx(source: Path, output: Path) -> str:
    if source.suffix.lower() != ".docx":
        raise ConversionError("内置转换引擎仅支持 .docx 文件")
    try:
        import dxpdf
    except ImportError as exc:
        raise ConversionError("内置 DOCX 转换引擎未正确打包") from exc
    try:
        with _temporary_document_font(BUNDLED_CJK_FONT), _docx_with_cjk_fallback(
            source
        ) as prepared_source:
            dxpdf.convert_file(str(prepared_source), str(output))
    except Exception as exc:
        raise ConversionError(f"内置 DOCX 引擎转换失败：{exc}") from exc
    if not output.is_file() or output.stat().st_size == 0:
        raise ConversionError("内置 DOCX 引擎未生成有效 PDF")
    return "内置 DOCX 引擎"


def convert_to_pdf(source, output, overwrite: bool = False, timeout: int = 120) -> ConversionResult:
    source = _validate_source(Path(source))
    source_text, source_fonts = _docx_text_and_fonts(source)
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise ConversionError(f"输出文件已存在：{output.name}")

    system = platform.system()
    attempts = []
    if source.suffix.lower() != ".wps" and word_available(system):
        attempts.append(("Microsoft Word", lambda: _convert_windows_com(source, output) if system == "Windows" else _convert_macos_word(source, output, timeout)))
    if system == "Windows" and wps_available(system):
        attempts.append(("WPS Office", lambda: _convert_windows_com(source, output, wps=True)))
    libreoffice = find_libreoffice(system)
    if libreoffice:
        attempts.append(
            (
                "LibreOffice",
                lambda: _convert_libreoffice(
                    source, output, libreoffice, timeout, source_fonts
                ),
            )
        )
    if source.suffix.lower() == ".docx":
        try:
            import dxpdf  # noqa: F401

            attempts.append(
                ("内置 DOCX 引擎", lambda: _convert_builtin_docx(source, output))
            )
        except ImportError:
            pass
    if not attempts:
        raise ConversionError(
            "未检测到可用转换引擎；DOC/WPS 文件请安装 Microsoft Word、WPS Office（Windows）或 LibreOffice"
        )

    failures = []
    for attempt_index, (name, converter) in enumerate(attempts):
        try:
            engine = converter()
            if output.is_file() and output.stat().st_size > 0:
                coverage = _pdf_cjk_coverage(output, source_text)
                if coverage is not None and coverage < 0.85:
                    message = f"中文完整性校验仅通过 {coverage:.0%}"
                    if attempt_index < len(attempts) - 1:
                        failures.append(f"{name}：{message}")
                        output.unlink()
                        continue
                    output.unlink()
                    raise ConversionError(
                        f"{message}，已阻止输出可能乱码的 PDF；请安装 Microsoft Word/WPS 或完整 LibreOffice"
                    )
                return ConversionResult(source, output, engine)
            failures.append(f"{name}：未生成有效 PDF")
        except (ConversionError, OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}：{exc}")
            if output.exists():
                output.unlink()
    raise ConversionError("；".join(failures))


def unique_output_path(folder: Path, source: Path) -> Path:
    candidate = folder / f"{source.stem}.pdf"
    index = 2
    while candidate.exists():
        candidate = folder / f"{source.stem} ({index}).pdf"
        index += 1
    return candidate


def supported_files(paths: Iterable[str]) -> Tuple[Path, ...]:
    result = []
    seen = set()
    for value in paths:
        path = Path(value).expanduser().resolve()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES and path not in seen:
            result.append(path)
            seen.add(path)
    return tuple(result)
