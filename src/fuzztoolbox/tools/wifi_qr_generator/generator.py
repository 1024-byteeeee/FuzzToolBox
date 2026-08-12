"""Wi-Fi configuration encoding and QR rendering."""

from segno import helpers

from ..qr_generator.generator import generate_qr_png


SECURITY_TYPES = ("WPA", "WEP", "nopass")


def make_wifi_payload(
    ssid: str,
    password: str = "",
    security: str = "WPA",
    hidden: bool = False,
) -> str:
    network_name = ssid.strip()
    if not network_name:
        raise ValueError("请输入 Wi-Fi 名称（SSID）")
    if security not in SECURITY_TYPES:
        raise ValueError("不支持的 Wi-Fi 加密方式")
    if security != "nopass" and not password:
        raise ValueError("请输入 Wi-Fi 密码")
    return helpers.make_wifi_data(
        ssid=network_name,
        password=None if security == "nopass" else password,
        security=security,
        hidden=hidden,
    )


def generate_wifi_qr_png(
    ssid: str,
    password: str = "",
    security: str = "WPA",
    hidden: bool = False,
    foreground: str = "#000000",
    background: str = "#ffffff",
    error_level: str = "M",
) -> bytes:
    payload = make_wifi_payload(ssid, password, security, hidden)
    return generate_qr_png(payload, foreground, background, error_level)

