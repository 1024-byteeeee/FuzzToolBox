"""Pure QR generation logic, kept independent from Qt for easy testing."""

from io import BytesIO

import segno


ERROR_LEVELS = ("L", "M", "Q", "H")


def generate_qr_png(
    text: str,
    foreground: str = "#000000",
    background: str = "#ffffff",
    error_level: str = "M",
    scale: int = 12,
) -> bytes:
    if not text:
        raise ValueError("请输入需要生成二维码的文本")
    level = error_level.upper()
    if level not in ERROR_LEVELS:
        raise ValueError("不支持的二维码容错率")
    if foreground.casefold() == background.casefold():
        raise ValueError("前景色和背景色不能相同")
    try:
        qr = segno.make_qr(text, error=level, boost_error=False)
    except (ValueError, segno.DataOverflowError) as exc:
        raise ValueError(f"文本内容超出二维码容量：{exc}") from exc
    output = BytesIO()
    qr.save(
        output,
        kind="png",
        scale=max(1, scale),
        border=4,
        dark=foreground,
        light=background,
    )
    return output.getvalue()

