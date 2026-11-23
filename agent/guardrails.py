"""Verify that numeric claims in assistant replies are supported by tool output."""

import logging
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)
_ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩٬٫",
    "0123456789,.",
)
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*(?P<scale>million|millions|m|thousand|thousands|k|billion|billions|b)?"
    r"(?![\w²])",
    re.IGNORECASE,
)
_WORD_BASE = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
)
_WORD_UNIT = r"one|two|three|four|five|six|seven|eight|nine"
_WORD_NUMBER_PATTERN = re.compile(
    rf"\b(?P<base>{_WORD_BASE})"
    rf"(?:[\s-]+(?P<base_unit>{_WORD_UNIT}))?"
    rf"(?:[\s-]+hundred(?:[\s-]+and)?"
    rf"(?:[\s-]+(?P<remainder>{_WORD_BASE})"
    rf"(?:[\s-]+(?P<remainder_unit>{_WORD_UNIT}))?)?)?"
    rf"(?:[\s-]+(?P<word_scale>thousand|million|billion))?\b",
    re.IGNORECASE,
)
_ENGLISH_VALUES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_ARABIC_WORD_PATTERN = re.compile(
    r"(?<!\w)(?P<base>صفر|واحد|واحدة|اثنان|اثنين|اثنتان|اثنتين|"
    r"ثلاث|ثلاثة|أربع|أربعة|اربع|اربعة|خمس|خمسة|ست|ستة|"
    r"سبع|سبعة|ثمان|ثمانية|تسع|تسعة|عشر|عشرة)"
    r"(?:\s+(?P<scale>مئة|مائة|ألف|آلاف|مليون|ملايين|مليار|مليارات))?"
    r"(?!\w)"
)
_ARABIC_VALUES = {
    "صفر": 0,
    "واحد": 1,
    "واحدة": 1,
    "اثنان": 2,
    "اثنين": 2,
    "اثنتان": 2,
    "اثنتين": 2,
    "ثلاث": 3,
    "ثلاثة": 3,
    "أربع": 4,
    "أربعة": 4,
    "اربع": 4,
    "اربعة": 4,
    "خمس": 5,
    "خمسة": 5,
    "ست": 6,
    "ستة": 6,
    "سبع": 7,
    "سبعة": 7,
    "ثمان": 8,
    "ثمانية": 8,
    "تسع": 9,
    "تسعة": 9,
    "عشر": 10,
    "عشرة": 10,
}
_ARABIC_SCALES = {
    "مئة": 100,
    "مائة": 100,
    "ألف": 1000,
    "آلاف": 1000,
    "مليون": 1_000_000,
    "ملايين": 1_000_000,
    "مليار": 1_000_000_000,
    "مليارات": 1_000_000_000,
}
_SCALE_FACTORS = {
    "k": Decimal("1000"),
    "thousand": Decimal("1000"),
    "thousands": Decimal("1000"),
    "m": Decimal("1000000"),
    "million": Decimal("1000000"),
    "millions": Decimal("1000000"),
    "b": Decimal("1000000000"),
    "billion": Decimal("1000000000"),
    "billions": Decimal("1000000000"),
}


class NumericVerification(BaseModel):
    """Outcome of checking every numeric reply claim against tool results."""

    verified: bool
    unsupported_numbers: list[str]


class NumericGuardrailError(ValueError):
    """Raised when a reply contains unsupported numeric claims."""

    def __init__(self, unsupported_numbers: Sequence[str]) -> None:
        self.unsupported_numbers = list(unsupported_numbers)
        super().__init__(
            "Reply contains numbers not present in tool outputs: "
            + ", ".join(self.unsupported_numbers)
        )


def _decimal_value(number: str, scale: str | None = None) -> Decimal | None:
    normalized = number.translate(_ARABIC_DIGITS).replace(",", "").replace("٫", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if scale:
        value *= _SCALE_FACTORS[scale.lower()]
    return value.normalize()


def numeric_claims(text: str) -> list[tuple[str, Decimal]]:
    """Extract numeral words/digits and normalize comma, K/M, and Arabic forms."""
    normalized_text = text.translate(_ARABIC_DIGITS)
    claims: list[tuple[str, Decimal]] = []
    for match in _NUMBER_PATTERN.finditer(normalized_text):
        value = _decimal_value(match.group("number"), match.group("scale"))
        if value is not None:
            claims.append((match.group(0).strip(), value))

    for pattern in (_WORD_NUMBER_PATTERN, _ARABIC_WORD_PATTERN):
        for match in pattern.finditer(text):
            if "word_scale" in match.groupdict():
                value = _ENGLISH_VALUES[match.group("base").lower()]
                if match.group("base_unit"):
                    value += _ENGLISH_VALUES[match.group("base_unit").lower()]
                if match.group("remainder"):
                    remainder = _ENGLISH_VALUES[match.group("remainder").lower()]
                    if match.group("remainder_unit"):
                        remainder += _ENGLISH_VALUES[
                            match.group("remainder_unit").lower()
                        ]
                    value = value * 100 + remainder
                elif "hundred" in match.group(0).lower():
                    value *= 100
                scale = match.group("word_scale")
                if scale:
                    value *= int(_SCALE_FACTORS[scale.lower()])
            else:
                value = _ARABIC_VALUES[match.group("base")]
                scale = match.group("scale")
                if scale:
                    value *= _ARABIC_SCALES[scale]
            claims.append((match.group(0), Decimal(value)))
    return claims


def _tool_numbers(value: Any) -> set[Decimal]:
    if isinstance(value, BaseModel):
        return _tool_numbers(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return set().union(*(_tool_numbers(item) for item in value.values()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return set().union(*(_tool_numbers(item) for item in value))
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value)).normalize()
        except InvalidOperation:
            return set()
        return {number}
    if isinstance(value, str):
        return {number for _, number in numeric_claims(value)}
    return set()


def verify_numeric_claims(
    reply: str, tool_outputs: Sequence[Any]
) -> NumericVerification:
    """Check normalized reply numbers against values/text in tool outputs."""
    supported = _tool_numbers(tool_outputs)
    unsupported = list(
        dict.fromkeys(
            original
            for original, normalized in numeric_claims(reply)
            if normalized not in supported
        )
    )
    result = NumericVerification(
        verified=not unsupported,
        unsupported_numbers=unsupported,
    )
    logger.info(
        "Checked reply numeric claims",
        extra={
            "verified": result.verified,
            "numeric_claim_count": len(numeric_claims(reply)),
            "unsupported_count": len(unsupported),
        },
    )
    return result
