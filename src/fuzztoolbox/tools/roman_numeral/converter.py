"""Strict conversion between integers and canonical Roman numerals."""


ROMAN_VALUES = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def integer_to_roman(value: int) -> str:
    """Convert an integer from 1 through 3999 to a canonical Roman numeral."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("请输入整数")
    if not 1 <= value <= 3999:
        raise ValueError("数字必须在 1–3999 之间")

    remainder = value
    parts = []
    for number, numeral in ROMAN_VALUES:
        count, remainder = divmod(remainder, number)
        if count:
            parts.append(numeral * count)
    return "".join(parts)


def roman_to_integer(value: str) -> int:
    """Convert a canonical Roman numeral to an integer."""
    text = value.strip().upper()
    if not text:
        raise ValueError("请输入罗马数字")
    if any(character not in "IVXLCDM" for character in text):
        raise ValueError("罗马数字只能包含 I、V、X、L、C、D、M")

    total = 0
    index = 0
    for number, numeral in ROMAN_VALUES:
        while text.startswith(numeral, index):
            total += number
            index += len(numeral)

    if index != len(text) or not 1 <= total <= 3999 or integer_to_roman(total) != text:
        raise ValueError("请输入 1–3999 范围内的规范罗马数字")
    return total
