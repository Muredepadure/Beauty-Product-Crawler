"""Parse package size from Romanian product titles.

Sizes are returned in base units so equal sizes compare equal: litres become ml,
kilograms become g, and piece words (buc, bucăți, capsule, tablete, plasturi, ...)
become "buc". Multipacks keep the per-item size and a `count`:
"2 x 50 ml" -> Size(50, "ml", count=2).

Conservative by design: a title mentioning two different sizes (gift sets like
"cremă 50 ml + ser 30 ml") yields None rather than a guess.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from beautycrawler.normalization.text import fold

BaseUnit = Literal["ml", "g", "buc"]

# folded unit word -> (base unit, multiplier)
_UNITS: dict[str, tuple[BaseUnit, Decimal]] = {
    "ml": ("ml", Decimal(1)),
    "l": ("ml", Decimal(1000)),
    "ltr": ("ml", Decimal(1000)),
    "litru": ("ml", Decimal(1000)),
    "litri": ("ml", Decimal(1000)),
    "cl": ("ml", Decimal(10)),
    "g": ("g", Decimal(1)),
    "gr": ("g", Decimal(1)),
    "grame": ("g", Decimal(1)),
    "kg": ("g", Decimal(1000)),
    "mg": ("g", Decimal("0.001")),
    "buc": ("buc", Decimal(1)),
    "bucati": ("buc", Decimal(1)),
    "bucata": ("buc", Decimal(1)),
    "pcs": ("buc", Decimal(1)),
    "capsule": ("buc", Decimal(1)),
    "caps": ("buc", Decimal(1)),
    "tablete": ("buc", Decimal(1)),
    "comprimate": ("buc", Decimal(1)),
    "plasturi": ("buc", Decimal(1)),
    "servetele": ("buc", Decimal(1)),
    "fiole": ("buc", Decimal(1)),
    "dischete": ("buc", Decimal(1)),
    "plicuri": ("buc", Decimal(1)),
}

_UNIT_ALT = "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
_NUM = r"\d+(?:[.,]\d+)?"
# The unit must not be followed by a letter ("5 gel", "30 lei" are not sizes).
_AMOUNT = rf"(?P<value>{_NUM})\s*(?P<unit>{_UNIT_ALT})(?![a-z])"
_SIZE_RE = re.compile(rf"(?<![\d.,]){_AMOUNT}")
_PACK_BEFORE_RE = re.compile(rf"(?<![\d.,])(?P<count>\d{{1,2}})\s*(?:x|buc\s*x)\s*{_AMOUNT}")
_PACK_AFTER_RE = re.compile(rf"(?<![\d.,]){_AMOUNT}\s*x\s*(?P<count>\d{{1,2}})(?![\d.,])")


@dataclass(frozen=True, slots=True)
class Size:
    value: Decimal
    unit: BaseUnit
    count: int = 1

    @property
    def total(self) -> Decimal:
        return self.value * self.count

    def __str__(self) -> str:
        value = f"{self.value.normalize():f}"
        return f"{self.count} x {value} {self.unit}" if self.count > 1 else f"{value} {self.unit}"


def _amount(value: str, unit: str) -> tuple[Decimal, BaseUnit] | None:
    try:
        number = Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None
    base, factor = _UNITS[unit]
    amount = number * factor
    if amount <= 0:
        return None
    # Canonical form so equal sizes are equal objects: 1.5 l and 1500 ml -> Decimal("1500").
    return (Decimal(int(amount)) if amount == amount.to_integral() else amount.normalize()), base


def parse_size(title: str | None) -> Size | None:
    """Package size mentioned in `title`, or None if absent or ambiguous."""
    if not title:
        return None
    text = fold(title)

    for pattern in (_PACK_BEFORE_RE, _PACK_AFTER_RE):
        m = pattern.search(text)
        if m:
            parsed = _amount(m.group("value"), m.group("unit"))
            count = int(m.group("count"))
            if parsed and count >= 1:
                rest = text[: m.start()] + " " + text[m.end() :]
                others = {
                    _amount(o.group("value"), o.group("unit")) for o in _SIZE_RE.finditer(rest)
                }
                others.discard(None)
                # e.g. "2 x 50 ml (100 ml)" is fine; a different extra size is a set.
                total = (parsed[0] * count, parsed[1])
                if others - {parsed, total}:
                    return None
                return Size(parsed[0], parsed[1], count)

    found = []
    for m in _SIZE_RE.finditer(text):
        parsed = _amount(m.group("value"), m.group("unit"))
        if parsed:
            found.append(parsed)
    if not found:
        return None
    # Only answer when exactly one distinct amount is mentioned; "30 ml (2 buc)" or
    # "60 capsule 30 g" could mean several things, so they give None.
    distinct = set(found)
    if len(distinct) != 1:
        return None
    [(value, unit)] = distinct
    return Size(value, unit, 1)


_STRIP_RES = tuple(
    re.compile(p.pattern, re.IGNORECASE) for p in (_PACK_BEFORE_RE, _PACK_AFTER_RE, _SIZE_RE)
)


def strip_sizes(text: str) -> str:
    """`text` with size mentions ("40 ml", "2 x 50 ml", "30 capsule") removed.

    Case-insensitive; unit words are matched in their ASCII spellings, so fold the text
    first when it may contain diacritic units ("bucăți"). Whitespace is collapsed.
    """
    for pattern in _STRIP_RES:
        text = pattern.sub(" ", text)
    return " ".join(text.split())
