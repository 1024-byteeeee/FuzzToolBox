"""Local brute-force password strength estimation."""

import math
import string
from dataclasses import dataclass
from decimal import Decimal, localcontext

GUESSES_PER_SECOND = 10_000_000_000
MAX_SCORE_ENTROPY = 128.0


@dataclass(frozen=True)
class PasswordStrength:
    length: int
    charset_size: int
    entropy: float
    score: int
    crack_time: str
    average_guesses: int


def infer_charset_size(password: str) -> int:
    """Infer the brute-force character pool from character classes in use."""
    size = 0
    if any(character in string.ascii_lowercase for character in password):
        size += 26
    if any(character in string.ascii_uppercase for character in password):
        size += 26
    if any(character in string.digits for character in password):
        size += 10
    if any(character in string.punctuation for character in password):
        size += len(string.punctuation)
    if any(character in string.whitespace for character in password):
        size += 1

    known = set(string.ascii_letters + string.digits + string.punctuation + string.whitespace)
    size += len({character for character in password if character not in known})
    return size


def format_crack_time(average_guesses: int, rate: int = GUESSES_PER_SECOND) -> str:
    if average_guesses <= 0:
        return "立即"
    if rate <= 0:
        raise ValueError("破解速度必须大于 0")
    if average_guesses < rate:
        seconds = average_guesses / rate
        if seconds < 0.001:
            return "少于 1 毫秒"
        return f"{seconds:.3g} 秒"

    units = (
        ("万亿年", 31_557_600 * 1_000_000_000_000),
        ("亿年", 31_557_600 * 100_000_000),
        ("万年", 31_557_600 * 10_000),
        ("年", 31_557_600),
        ("天", 86_400),
        ("小时", 3_600),
        ("分钟", 60),
        ("秒", 1),
    )
    for label, seconds_per_unit in units:
        denominator = rate * seconds_per_unit
        if average_guesses >= denominator:
            with localcontext() as context:
                context.prec = 3
                value = Decimal(average_guesses) / Decimal(denominator)
                rendered = format(value, "f") if value.adjusted() <= 6 else f"{value:.2E}"
                return f"约 {rendered} {label}"
    return "少于 1 秒"


def analyze_password(password: str) -> PasswordStrength:
    length = len(password)
    charset_size = infer_charset_size(password)
    if not length or not charset_size:
        return PasswordStrength(0, 0, 0.0, 0, "立即", 0)

    entropy = length * math.log2(charset_size)
    search_space = pow(charset_size, length)
    average_guesses = max(1, search_space // 2)
    score = min(100, max(0, round(entropy / MAX_SCORE_ENTROPY * 100)))
    return PasswordStrength(
        length=length,
        charset_size=charset_size,
        entropy=entropy,
        score=score,
        crack_time=format_crack_time(average_guesses),
        average_guesses=average_guesses,
    )
