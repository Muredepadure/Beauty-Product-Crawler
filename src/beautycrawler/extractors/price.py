"""Parse Romanian price strings into integer bani (1 RON = 100 bani).

Two entry points:

- `parse_price(text)` for human-formatted prices on product pages:
  "1.234,99 lei", "49,90 RON", "de la 30 lei", "Lei 1 299", "129.99 lei".
- `parse_machine_price(value)` for structured data (JSON-LD `price`, microdata
  `content`): numbers or numeric strings where a lone "." or "," is always the decimal
  separator ("1234.5", "49,90").

Separator rules for human text: when both "." and "," appear, the last one is the decimal
separator. A single separator followed by exactly three digits is a thousands separator
("1.234 lei" = 1234 lei); followed by one or two digits it is the decimal separator.
Spaces (incl. non-breaking) inside a number group thousands.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CURRENCY = r"(?:lei|leu|ron)"
_SPACES = " " + chr(0x00A0) + chr(0x202F) + chr(0x2009)  # space, NBSP, narrow NBSP, thin
# A number as written by a retailer: thousands groups (dot/space/comma) and optional decimals.
_NUMBER = (
    rf"\d{{1,3}}(?:[.,{_SPACES}]\d{{3}})+(?:[.,]\d{{1,2}})?(?!\d)"
    r"|\d+(?:[.,]\d{1,2})?(?!\d)"
    r"|\d+(?:[.,]\d+)?"
)
_NUMBER_RE = re.compile(_NUMBER)
# A number with a currency marker right before or after it.
_PRICE_WITH_CURRENCY_RE = re.compile(
    rf"(?:(?P<pre>{_CURRENCY})\.?\s*(?P<a>{_NUMBER}))|(?:(?P<b>{_NUMBER})\s*{_CURRENCY}\b)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"-?\s*\d+(?:[.,]\d+)?\s*%")


def _to_bani(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _number_to_decimal(raw: str) -> Decimal:
    s = "".join(ch for ch in raw if ch not in _SPACES)
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_sep = "." if last_dot > last_comma else ","
        thousands_sep = "," if decimal_sep == "." else "."
        s = s.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif last_dot >= 0 or last_comma >= 0:
        sep = "." if last_dot >= 0 else ","
        parts = s.split(sep)
        thousands_only = len(parts) > 2 or len(parts[-1]) == 3
        s = "".join(parts) if thousands_only else ".".join(parts)
    return Decimal(s)


def parse_price(text: str | None) -> int | None:
    """The price in `text`, in bani; None if there is no number.

    Prefers the first amount with a currency marker ("Effaclar 40 ml 89,99 lei" gives
    8999); otherwise takes the first number ("79,99" gives 7999). Percentages ("-20%")
    are ignored.
    """
    if not text:
        return None
    marked = extract_prices(text)
    if marked:
        return marked[0]
    match = _NUMBER_RE.search(_PERCENT_RE.sub(" ", text))
    if match is None:
        return None
    return _to_bani(_number_to_decimal(match.group(0)))


def extract_prices(text: str | None) -> list[int]:
    """All amounts in `text` that carry a currency marker (lei/leu/RON), in bani, in order.

    Numbers without a currency next to them (quantities, "-20%", "40 ml") are skipped.
    """
    if not text:
        return []
    cleaned = _PERCENT_RE.sub(" ", text)
    prices = []
    for m in _PRICE_WITH_CURRENCY_RE.finditer(cleaned):
        raw = m.group("a") or m.group("b")
        prices.append(_to_bani(_number_to_decimal(raw)))
    return prices


def parse_price_pair(text: str | None) -> tuple[int | None, int | None]:
    """(current, old) from a block showing a sale, e.g. "129,99 lei 99,99 lei".

    The lowest amount is the current price and the highest the old price. With a single
    amount, old is None. Identical amounts count as no sale.
    """
    prices = extract_prices(text)
    if not prices:
        return None, None
    current, highest = min(prices), max(prices)
    return current, (highest if highest > current else None)


def parse_machine_price(value: object) -> int | None:
    """Price from structured data (JSON-LD/microdata), in bani; None if unparseable.

    Accepts int/float/Decimal and strings such as "49.90", "49,90", "1234.5", "1,234.50",
    "49.90 RON". A lone separator is always decimal here, unlike `parse_price`.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | Decimal):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        s = "".join(ch for ch in value.strip() if ch not in _SPACES)
        s = re.sub(rf"(?i){_CURRENCY}\.?", "", s)
        if "." in s and "," in s:
            return parse_price(s)
        try:
            amount = Decimal(s.replace(",", "."))
        except InvalidOperation:
            return None
    else:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return _to_bani(amount)
