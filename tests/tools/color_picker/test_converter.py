import unittest

from fuzztoolbox.tools.color_picker.converter import ColorValue


class ColorValueTests(unittest.TestCase):
    def test_formats_theme_blue_with_alpha(self):
        value = ColorValue(64, 158, 255, 80)
        self.assertEqual(value.hex, "#409EFFCC")
        self.assertEqual(value.rgb, "rgb(64 158 255 / 80%)")
        self.assertEqual(value.hsl, "hsl(210.5 100% 62.5% / 80%)")
        self.assertEqual(value.hwb, "hwb(210.5 25.1% 0% / 80%)")
        self.assertEqual(value.lch, "lch(63.1 57.2 266.7 / 80%)")
        self.assertEqual(
            value.cmyk,
            "device-cmyk(74.9% 38% 0% 0% / 80%)",
        )

    def test_opaque_output_omits_alpha(self):
        value = ColorValue(255, 0, 0)
        self.assertEqual(value.hex, "#FF0000")
        self.assertEqual(value.rgb, "rgb(255 0 0)")
        self.assertEqual(value.hsl, "hsl(0 100% 50%)")
        self.assertEqual(value.hwb, "hwb(0 0% 0%)")
        self.assertEqual(value.cmyk, "device-cmyk(0% 100% 100% 0%)")

    def test_lch_uses_css_d50_reference_conversion(self):
        # CSS Color 4 reference for sRGB red is approximately
        # lch(54.291 106.84 40.858).
        self.assertEqual(ColorValue(255, 0, 0).lch, "lch(54.3 106.9 40.9)")
        self.assertEqual(ColorValue(255, 255, 255).lch, "lch(100 0 0)")

    def test_black_cmyk_and_zero_alpha(self):
        value = ColorValue(0, 0, 0, 0)
        self.assertEqual(value.hex, "#00000000")
        self.assertEqual(value.cmyk, "device-cmyk(0% 0% 0% 100% / 0%)")

    def test_invalid_channels_are_rejected(self):
        for channels in (
            (-1, 0, 0, 100),
            (0, 256, 0, 100),
            (0, 0, 1.5, 100),
            (True, 0, 0, 100),
            (0, 0, 0, 101),
        ):
            with self.subTest(channels=channels), self.assertRaises(ValueError):
                ColorValue(*channels)


if __name__ == "__main__":
    unittest.main()
