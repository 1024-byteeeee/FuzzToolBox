import colorsys
import math
from dataclasses import dataclass


def _format_number(value: float, digits: int = 1) -> str:
    rounded = round(value, digits)
    if abs(rounded) < 10 ** (-digits):
        rounded = 0.0
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def _linear_srgb(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _lab_curve(value: float) -> float:
    delta = 6 / 29
    return value ** (1 / 3) if value > delta**3 else value / (3 * delta**2) + 4 / 29


@dataclass(frozen=True)
class ColorValue:
    red: int
    green: int
    blue: int
    alpha: int = 100

    def __post_init__(self):
        for name, value, maximum in (
            ("红色", self.red, 255),
            ("绿色", self.green, 255),
            ("蓝色", self.blue, 255),
            ("透明度", self.alpha, 100),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= maximum
            ):
                raise ValueError(f"{name}必须是 0 到 {maximum} 之间的整数")

    @property
    def _rgb_unit(self):
        return self.red / 255, self.green / 255, self.blue / 255

    @property
    def _alpha_suffix(self) -> str:
        return "" if self.alpha == 100 else f" / {self.alpha}%"

    @property
    def hex(self) -> str:
        color = f"#{self.red:02X}{self.green:02X}{self.blue:02X}"
        if self.alpha < 100:
            alpha_byte = int(self.alpha * 255 / 100 + 0.5)
            color += f"{alpha_byte:02X}"
        return color

    @property
    def rgb(self) -> str:
        return f"rgb({self.red} {self.green} {self.blue}{self._alpha_suffix})"

    @property
    def hsl(self) -> str:
        hue, lightness, saturation = colorsys.rgb_to_hls(*self._rgb_unit)
        return (
            f"hsl({_format_number(hue * 360)} "
            f"{_format_number(saturation * 100)}% "
            f"{_format_number(lightness * 100)}%{self._alpha_suffix})"
        )

    @property
    def hwb(self) -> str:
        red, green, blue = self._rgb_unit
        hue = colorsys.rgb_to_hsv(red, green, blue)[0] * 360
        whiteness = min(red, green, blue) * 100
        blackness = (1 - max(red, green, blue)) * 100
        return (
            f"hwb({_format_number(hue)} {_format_number(whiteness)}% "
            f"{_format_number(blackness)}%{self._alpha_suffix})"
        )

    @property
    def lch(self) -> str:
        red, green, blue = (_linear_srgb(channel) for channel in self._rgb_unit)
        x_d65 = 0.4124564 * red + 0.3575761 * green + 0.1804375 * blue
        y_d65 = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
        z_d65 = 0.0193339 * red + 0.1191920 * green + 0.9503041 * blue

        # Bradford-adapt XYZ from the sRGB D65 white point to CSS Lab/LCH D50.
        x_d50 = 1.0479298 * x_d65 + 0.0229468 * y_d65 - 0.0501922 * z_d65
        y_d50 = 0.0296278 * x_d65 + 0.9904345 * y_d65 - 0.0170738 * z_d65
        z_d50 = -0.0092431 * x_d65 + 0.0150551 * y_d65 + 0.7518743 * z_d65

        x = _lab_curve(x_d50 / 0.96422)
        y = _lab_curve(y_d50)
        z = _lab_curve(z_d50 / 0.82521)
        lightness = 116 * y - 16
        a = 500 * (x - y)
        b = 200 * (y - z)
        chroma = math.hypot(a, b)
        hue = math.degrees(math.atan2(b, a)) % 360 if chroma >= 0.05 else 0
        return (
            f"lch({_format_number(lightness)} {_format_number(chroma)} "
            f"{_format_number(hue)}{self._alpha_suffix})"
        )

    @property
    def cmyk(self) -> str:
        red, green, blue = self._rgb_unit
        black = 1 - max(red, green, blue)
        if black >= 1 - 1e-12:
            cyan = magenta = yellow = 0.0
        else:
            scale = 1 - black
            cyan = (1 - red - black) / scale
            magenta = (1 - green - black) / scale
            yellow = (1 - blue - black) / scale
        values = " ".join(
            f"{_format_number(channel * 100)}%"
            for channel in (cyan, magenta, yellow, black)
        )
        return f"device-cmyk({values}{self._alpha_suffix})"

    def rows(self):
        return (
            ("HEX", self.hex),
            ("RGB", self.rgb),
            ("HSL", self.hsl),
            ("HWB", self.hwb),
            ("LCH", self.lch),
            ("CMYK", self.cmyk),
        )
