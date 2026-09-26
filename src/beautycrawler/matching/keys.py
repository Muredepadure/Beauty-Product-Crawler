"""Pure matching logic: name keys, size comparison and pair scoring (no database).

A product "name key" is its title reduced to what identifies the product line:
retailer noise (`clean_title`), the brand, package sizes, punctuation and filler words
are removed, diacritics and case folded. "La Roche-Posay Effaclar Duo+ Cremă 40 ml"
becomes the tokens ``effaclar duo plus crema``.

`score_pair` compares two keys with rapidfuzz's ``token_set_ratio`` (robust to one
retailer adding descriptors like "cremă corectoare pentru ten gras") and then applies
guards, because a high string score is not enough in cosmetics: "Effaclar Duo+" vs
"Effaclar Duo+ M", "SPF 30" vs "SPF 50" or shade "110" vs "120" are different products.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz

from beautycrawler.normalization.brands import BRANDS, brand_key, canonical_brand
from beautycrawler.normalization.size import Size, parse_size, strip_sizes
from beautycrawler.normalization.text import fold
from beautycrawler.normalization.title import clean_title

# Filler words that carry no product identity (Romanian and English).
STOPWORDS = frozenset(
    [
        "a",
        "al",
        "ale",
        "and",
        "cu",
        "de",
        "din",
        "for",
        "in",
        "la",
        "of",
        "on",
        "pe",
        "pentru",
        "pt",
        "si",
        "sau",
        "the",
        "to",
        "with",
    ]
)
# A trailing "+" ("Duo+", "B5+", "Duo(+)", "SPF 50+") is part of the name -> "plus";
# between words ("Matte+Poreless", "10% + Zinc") it is a separator.
_ATTACHED_PLUS = re.compile(r"(?<=[0-9a-z])\+(?![0-9a-z])|\(\s*\+\s*\)")
_TOKEN = re.compile(r"[0-9a-z]+")

_TO_BASE: dict[str, tuple[str, Decimal]] = {
    "ml": ("ml", Decimal(1)),
    "l": ("ml", Decimal(1000)),
    "g": ("g", Decimal(1)),
    "kg": ("g", Decimal(1000)),
    "buc": ("buc", Decimal(1)),
}


def _brand_alias_keys(brand: str | None) -> list[tuple[str, ...]]:
    """Token sequences that spell `brand` (canonical name and aliases), longest first."""
    if not brand:
        return []
    canonical = canonical_brand(brand) or brand
    names = {brand, canonical, *BRANDS.get(canonical, ())}
    keys = {tuple(brand_key(n).split()) for n in names}
    keys.discard(())
    return sorted(keys, key=len, reverse=True)


def _drop_sequence(tokens: list[str], seq: tuple[str, ...]) -> list[str] | None:
    n = len(seq)
    for i in range(len(tokens) - n + 1):
        if tuple(tokens[i : i + n]) == seq:
            return tokens[:i] + tokens[i + n :]
    return None


def name_tokens(title: str, brand: str | None = None) -> tuple[str, ...]:
    """Identity tokens of a product title (see module docstring)."""
    text = fold(clean_title(title))
    text = strip_sizes(text)
    text = _ATTACHED_PLUS.sub(" plus ", text)
    # brand_key() drops apostrophes ("L'Oréal" -> "loreal"); do the same here.
    tokens = _TOKEN.findall(text.replace("'", ""))
    for seq in _brand_alias_keys(brand):
        remaining = _drop_sequence(tokens, seq)
        if remaining is not None:
            tokens = remaining
            break
    return tuple(t for t in tokens if t not in STOPWORDS)


def display_name(title: str, brand: str | None = None) -> str:
    """Human-readable product name from a retailer title: noise, a leading brand and
    size mentions removed, original casing kept. Falls back to the cleaned title."""
    cleaned = clean_title(title)
    words = cleaned.split()
    aliases = set(_brand_alias_keys(brand))
    # A brand can span more words than tokens or fewer ("La Roche-Posay" is 2 words,
    # 3 tokens), so compare every leading run of words, longest first.
    for n in range(min(len(words) - 1, 6), 0, -1):
        if tuple(brand_key(" ".join(words[:n])).split()) in aliases:
            words = words[n:]
            break
    name = strip_sizes(" ".join(words)).strip(" ,-|")
    return name or cleaned


def _is_distinctive(token: str) -> bool:
    """Tokens that tell variants apart: numbers ("50", "b5", "h2o"), "plus" and very
    short markers ("m", "ar", "uv")."""
    return any(c.isdigit() for c in token) or token == "plus" or len(token) <= 2


@dataclass(frozen=True, slots=True)
class PairScore:
    """Similarity of two name keys. `score` is 0-100."""

    score: float
    conflict: str | None = None  # set when the pair is certainly different products
    doubts: tuple[str, ...] = field(default=())  # reasons it may not be auto-merged


def score_pair(a: tuple[str, ...], b: tuple[str, ...]) -> PairScore:
    if not a or not b:
        return PairScore(0.0, conflict="empty name")
    score = fuzz.token_set_ratio(" ".join(a), " ".join(b))
    only_a = {t for t in set(a) - set(b) if _is_distinctive(t)}
    only_b = {t for t in set(b) - set(a) if _is_distinctive(t)}
    numbers_a = {t for t in only_a if t.isdigit()}
    numbers_b = {t for t in only_b if t.isdigit()}
    if numbers_a and numbers_b:
        # Both sides name a number the other lacks: SPF 30 vs 50, shade 110 vs 120.
        return PairScore(
            score, conflict=f"different numbers: {sorted(numbers_a)} vs {sorted(numbers_b)}"
        )
    doubts = []
    if only_a or only_b:
        doubts.append(f"variant markers differ: {sorted(only_a | only_b)}")
    return PairScore(score, doubts=tuple(doubts))


def base_size(value: Decimal | None, unit: str | None) -> tuple[Decimal, str] | None:
    """(value, unit) in base units (l -> ml, kg -> g) so 1 l equals 1000 ml."""
    if value is None or unit is None or unit not in _TO_BASE:
        return None
    base, factor = _TO_BASE[unit]
    amount = Decimal(value) * factor
    if amount == amount.to_integral_value():
        return Decimal(int(amount)), base
    return amount.normalize(), base


def offer_size(
    title: str, value: Decimal | None, unit: str | None
) -> tuple[tuple[Decimal, str] | None, int]:
    """(per-item size in base units, pack count) of an offer.

    Structured size fields win; the title fills in when they are missing and is always
    consulted for a multipack count ("2 x 50 ml").
    """
    parsed: Size | None = parse_size(title)
    count = parsed.count if parsed else 1
    size = base_size(value, unit)
    if size is None and parsed is not None:
        size = base_size(parsed.value, parsed.unit)
    elif size is not None and parsed is not None and count > 1:
        # Retailers sometimes put the pack total in the size field.
        total = base_size(parsed.total, parsed.unit)
        if size == total:
            size = base_size(parsed.value, parsed.unit)
    return size, count
