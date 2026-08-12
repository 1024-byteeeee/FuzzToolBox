import unittest

from fuzztoolbox.tools.qr_generator.generator import generate_qr_png


class QRGeneratorTests(unittest.TestCase):
    def test_generates_png_for_unicode_text(self):
        data = generate_qr_png("你好，FuzzToolBox", "#123456", "#ffffff", "H")
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "请输入"):
            generate_qr_png("")

    def test_rejects_identical_colors(self):
        with self.assertRaisesRegex(ValueError, "不能相同"):
            generate_qr_png("text", "#ffffff", "#FFFFFF")

    def test_rejects_unknown_error_level(self):
        with self.assertRaisesRegex(ValueError, "容错率"):
            generate_qr_png("text", error_level="X")


if __name__ == "__main__":
    unittest.main()
