import unittest

from fuzztoolbox.tools.wifi_qr_generator.generator import (
    generate_wifi_qr_png,
    make_wifi_payload,
)


class WiFiQRGeneratorTests(unittest.TestCase):
    def test_wpa_payload_escapes_special_characters_and_marks_hidden(self):
        payload = make_wifi_payload("办公室;WiFi", r"p:a\b", "WPA", True)
        self.assertEqual(payload, r"WIFI:T:WPA;S:办公室\;WiFi;P:p\:a\\b;H:true;")

    def test_open_network_omits_password(self):
        self.assertEqual(make_wifi_payload("Guest", "", "nopass"), "WIFI:T:nopass;S:Guest;;")

    def test_secured_network_requires_password(self):
        with self.assertRaisesRegex(ValueError, "密码"):
            make_wifi_payload("Office", "", "WPA")

    def test_ssid_is_required(self):
        with self.assertRaisesRegex(ValueError, "SSID"):
            make_wifi_payload("  ", "password", "WPA")

    def test_generates_png_for_wifi_configuration(self):
        data = generate_wifi_qr_png("中文网络", "secret123", "WPA", error_level="H")
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
