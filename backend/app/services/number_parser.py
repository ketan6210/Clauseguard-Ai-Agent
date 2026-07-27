import math
import re
from dataclasses import dataclass


SMALL_NUMBERS = {
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
}
TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
NUMBER_WORDS = set(SMALL_NUMBERS) | set(TENS) | {"hundred", "thousand", "and"}
UNIT_ALIASES = {
    "hour": "hours",
    "hours": "hours",
    "day": "days",
    "days": "days",
    "week": "weeks",
    "weeks": "weeks",
    "month": "months",
    "months": "months",
    "year": "years",
    "years": "years",
}
NUMERIC_MEASUREMENT = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*\)?\s*"
    r"(?:(?P<qualifier>business|calendar)\s+)?"
    r"(?P<unit>hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: str
    qualifier: str | None
    start: int
    end: int
    source: str

    @property
    def days(self) -> float:
        factors = {"hours": 1 / 24, "days": 1, "weeks": 7, "months": 30, "years": 365}
        return self.value * factors[self.unit]


def parse_number_words(value: str) -> int | None:
    tokens = re.findall(r"[a-z]+", value.lower().replace("-", " "))
    if not tokens or any(token not in NUMBER_WORDS for token in tokens):
        return None
    total = 0
    current = 0
    saw_number = False
    for token in tokens:
        if token == "and":
            continue
        saw_number = True
        if token in SMALL_NUMBERS:
            current += SMALL_NUMBERS[token]
        elif token in TENS:
            current += TENS[token]
        elif token == "hundred":
            current = max(1, current) * 100
        elif token == "thousand":
            total += max(1, current) * 1000
            current = 0
    return total + current if saw_number else None


def extract_measurements(text: str) -> list[Measurement]:
    results = [
        Measurement(
            value=float(match.group("value")),
            unit=UNIT_ALIASES[match.group("unit").lower()],
            qualifier=match.group("qualifier").lower() if match.group("qualifier") else None,
            start=match.start(),
            end=match.end(),
            source=match.group(0),
        )
        for match in NUMERIC_MEASUREMENT.finditer(text)
    ]

    # Written values are parsed only when no parenthetical/direct number already
    # supplies the value immediately before the same unit.
    tokens = list(re.finditer(r"[A-Za-z]+(?:-[A-Za-z]+)?|\d+(?:\.\d+)?|[()]", text))
    for index, token_match in enumerate(tokens):
        unit_token = token_match.group(0).lower()
        if unit_token not in UNIT_ALIASES:
            continue
        if any(item.start <= token_match.start() <= item.end for item in results):
            continue
        cursor = index - 1
        qualifier = None
        if cursor >= 0 and tokens[cursor].group(0).lower() in {"business", "calendar"}:
            qualifier = tokens[cursor].group(0).lower()
            cursor -= 1
        number_tokens: list[str] = []
        while cursor >= 0:
            candidate = tokens[cursor].group(0).lower()
            parts = candidate.replace("-", " ").split()
            if not parts or any(part not in NUMBER_WORDS for part in parts):
                break
            number_tokens.insert(0, candidate)
            cursor -= 1
        parsed = parse_number_words(" ".join(number_tokens))
        if parsed is None:
            continue
        start = tokens[cursor + 1].start()
        results.append(
            Measurement(
                value=float(parsed),
                unit=UNIT_ALIASES[unit_token],
                qualifier=qualifier,
                start=start,
                end=token_match.end(),
                source=text[start : token_match.end()],
            )
        )
    return sorted(results, key=lambda item: item.start)


def extract_duration(text: str, unit: str) -> float | None:
    normalized_unit = UNIT_ALIASES.get(unit.lower(), unit.lower())
    return next((item.value for item in extract_measurements(text) if item.unit == normalized_unit), None)


def extract_number_of_days(text: str) -> int | None:
    for item in extract_measurements(text):
        if item.unit == "days":
            return math.ceil(item.value)
        if item.unit == "hours":
            return math.ceil(item.value / 24)
    return None


def extract_number_of_hours(text: str) -> int | None:
    for item in extract_measurements(text):
        if item.unit == "hours":
            return math.ceil(item.value)
        if item.unit == "days":
            return math.ceil(item.value * 24)
    return None


def extract_payment_days(text: str) -> int | None:
    net_match = re.search(r"\bnet\s*[-:]?\s*(\d{1,3})\b", text, re.IGNORECASE)
    if net_match:
        return int(net_match.group(1))
    due_segment = re.search(r"\b(?:due|payable|payment)\b.{0,100}", text, re.IGNORECASE)
    if due_segment:
        return extract_number_of_days(due_segment.group(0))
    return None


def extract_percentages(text: str) -> list[float]:
    numeric = [float(match.group(1)) for match in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", text)]
    for match in re.finditer(r"\b([a-z]+(?:[- ][a-z]+){0,4})\s+percent\b", text.lower()):
        value = parse_number_words(match.group(1))
        if value is not None and float(value) not in numeric:
            numeric.append(float(value))
    return numeric
