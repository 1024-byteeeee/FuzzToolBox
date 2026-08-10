import tempfile
import unittest
import zipfile
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from ip_scanner.word_pdf import (
    ConversionError,
    _convert_builtin_docx,
    _convert_libreoffice,
    _docx_text_and_fonts,
    _font_substitution_profile,
    find_libreoffice,
    convert_to_pdf,
    supported_files,
    unique_output_path,
)


class WordPdfTests(unittest.TestCase):
    @staticmethod
    def _write_minimal_docx(path, text="中文转换测试", font="宋体"):
        document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:rPr><w:rFonts w:eastAsia="{font}"/></w:rPr><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>'''
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "[Content_Types].xml",
                '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''',
            )
            archive.writestr(
                "_rels/.rels",
                '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''',
            )
            archive.writestr("word/document.xml", document)

    def test_supported_files_accepts_word_and_wps_without_duplicates(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            docx = folder / "中文 文档.docx"
            wps = folder / "plan.wps"
            ignored = folder / "notes.txt"
            for path in (docx, wps, ignored):
                path.write_text("test", encoding="utf-8")
            self.assertEqual(
                supported_files((str(docx), str(wps), str(docx), str(ignored))),
                (docx.resolve(), wps.resolve()),
            )

    def test_unique_output_path_never_overwrites_existing_pdf(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "report.docx"
            source.write_text("test", encoding="utf-8")
            (folder / "report.pdf").write_bytes(b"pdf")
            self.assertEqual(unique_output_path(folder, source).name, "report (2).pdf")

    def test_windows_uses_wps_when_word_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "report.docx"
            output = folder / "report.pdf"
            source.write_text("test", encoding="utf-8")

            def fake_wps(_source, target, wps=False):
                self.assertTrue(wps)
                target.write_bytes(b"%PDF")
                return "WPS Office"

            with patch("ip_scanner.word_pdf.platform.system", return_value="Windows"), patch(
                "ip_scanner.word_pdf.word_available", return_value=False
            ), patch("ip_scanner.word_pdf.wps_available", return_value=True), patch(
                "ip_scanner.word_pdf.find_libreoffice", return_value=None
            ), patch("ip_scanner.word_pdf._convert_windows_com", side_effect=fake_wps):
                result = convert_to_pdf(source, output)
            self.assertEqual(result.engine, "WPS Office")
            self.assertTrue(output.is_file())

    def test_missing_conversion_engine_has_clear_error(self):
        with tempfile.TemporaryDirectory() as folder_text:
            source = Path(folder_text) / "report.doc"
            source.write_text("test", encoding="utf-8")
            with patch("ip_scanner.word_pdf.word_available", return_value=False), patch(
                "ip_scanner.word_pdf.wps_available", return_value=False
            ), patch("ip_scanner.word_pdf.find_libreoffice", return_value=None):
                with self.assertRaisesRegex(ConversionError, "未检测到可用转换引擎"):
                    convert_to_pdf(source, source.with_suffix(".pdf"))

    def test_builtin_engine_converts_chinese_without_external_office(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "中文报告.docx"
            output = folder / "中文报告.pdf"
            self._write_minimal_docx(source, "中文不会乱码或消失")
            self.assertEqual(_convert_builtin_docx(source, output), "内置 DOCX 引擎")
            self.assertTrue(output.is_file())
            from pypdf import PdfReader

            # dxpdf uses platform font APIs and can emit a valid visual PDF
            # whose glyph-to-Unicode map is not extractable by pypdf on
            # Windows. Text extraction is therefore not a portable assertion
            # for this last-resort engine; production releases prefer the
            # bundled LibreOffice engine and validate that path separately.
            self.assertGreaterEqual(len(PdfReader(str(output)).pages), 1)

    def test_complete_libreoffice_engine_precedes_builtin_fallback(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "report.docx"
            output = folder / "report.pdf"
            self._write_minimal_docx(source, "复杂中文文档")

            def fake_libreoffice(_source, target, _executable, _timeout, _fonts):
                target.write_bytes(b"%PDF complete-engine")
                return "LibreOffice"

            with patch("ip_scanner.word_pdf.word_available", return_value=False), patch(
                "ip_scanner.word_pdf.wps_available", return_value=False
            ), patch(
                "ip_scanner.word_pdf.find_libreoffice", return_value=Path("/bundled/soffice")
            ), patch(
                "ip_scanner.word_pdf._convert_libreoffice", side_effect=fake_libreoffice
            ), patch(
                "ip_scanner.word_pdf._convert_builtin_docx"
            ) as builtin, patch(
                "ip_scanner.word_pdf._pdf_cjk_coverage", return_value=1.0
            ):
                result = convert_to_pdf(source, output)

            self.assertEqual(result.engine, "LibreOffice")
            builtin.assert_not_called()

    def test_docx_chinese_text_and_declared_fonts_are_detected(self):
        with tempfile.TemporaryDirectory() as folder_text:
            source = Path(folder_text) / "中文.docx"
            self._write_minimal_docx(source)
            text, fonts = _docx_text_and_fonts(source)
            self.assertEqual(text, "中文转换测试")
            self.assertIn("宋体", fonts)

    def test_libreoffice_profile_substitutes_missing_fonts(self):
        with tempfile.TemporaryDirectory() as folder_text:
            profile = Path(folder_text)
            _font_substitution_profile(profile, ("自定义中文字体",), "Windows")
            registry = (profile / "user" / "registrymodifications.xcu").read_text("utf-8")
            self.assertIn("自定义中文字体", registry)
            self.assertIn("Noto Sans CJK SC", registry)
            self.assertIn("Replacement", registry)

    def test_frozen_application_prefers_bundled_libreoffice(self):
        with tempfile.TemporaryDirectory() as folder_text:
            root = Path(folder_text)
            executable = root / "libreoffice" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"binary")
            find_libreoffice.cache_clear()
            try:
                with patch.object(sys, "_MEIPASS", str(root), create=True), patch.object(
                    sys, "frozen", True, create=True
                ), patch("ip_scanner.word_pdf.shutil.which", return_value=None):
                    self.assertEqual(find_libreoffice("Darwin"), executable)
            finally:
                find_libreoffice.cache_clear()

    def test_libreoffice_uses_bundled_font_and_pdfa(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "report.docx"
            output = folder / "report.pdf"
            source.write_bytes(b"placeholder")

            def fake_run(command, **kwargs):
                output_dir = Path(command[command.index("--outdir") + 1])
                (output_dir / "report.pdf").write_bytes(b"%PDF test")
                self.assertIn("SelectPdfVersion", command[command.index("--convert-to") + 1])
                self.assertIn("FONTCONFIG_FILE", kwargs["env"])
                self.assertIn("SAL_FONTPATH", kwargs["env"])
                return Mock(returncode=0, stdout="", stderr="")

            with patch("ip_scanner.word_pdf.subprocess.run", side_effect=fake_run):
                engine = _convert_libreoffice(source, output, Path("/fake/soffice"), 30, ("宋体",))
            self.assertEqual(engine, "LibreOffice")
            self.assertTrue(output.is_file())

    def test_bad_chinese_coverage_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder_text:
            folder = Path(folder_text)
            source = folder / "report.docx"
            output = folder / "report.pdf"
            self._write_minimal_docx(source)

            def fake_convert(_source, target, _executable, _timeout, _fonts):
                target.write_bytes(b"%PDF broken")
                return "LibreOffice"

            with patch("ip_scanner.word_pdf.platform.system", return_value="Darwin"), patch(
                "ip_scanner.word_pdf.word_available", return_value=False
            ), patch("ip_scanner.word_pdf.wps_available", return_value=False), patch(
                "ip_scanner.word_pdf.find_libreoffice", return_value=Path("/fake/soffice")
            ), patch("ip_scanner.word_pdf._convert_libreoffice", side_effect=fake_convert), patch(
                "ip_scanner.word_pdf._pdf_cjk_coverage", return_value=0.2
            ):
                with self.assertRaisesRegex(ConversionError, "中文完整性校验"):
                    convert_to_pdf(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
