"""Brand normalization: map the many spellings retailers use to one canonical name.

`brand_key()` is a matching key that ignores case, diacritics, punctuation, apostrophe
style and trademark signs, so "LA ROCHE-POSAY", "La Roche Posay" and "la roche-posay®"
share one key. `canonical_brand()` then maps keys (and known aliases such as
"Eau Thermale Avène" or "YSL") to the display name in `BRANDS`.

Add brands/aliases to `BRANDS` as spiders encounter them; tests guard against an alias
pointing at two brands.
"""

import re
from collections.abc import Mapping
from functools import cache

from beautycrawler.normalization.text import fold

# canonical display name -> extra aliases (spelling variants that brand_key() alone
# doesn't unify). The canonical name itself is always an alias.
BRANDS: Mapping[str, tuple[str, ...]] = {
    "A-Derma": ("Aderma",),
    "Avène": ("Eau Thermale Avène", "Avene Eau Thermale"),
    "Babyliss": ("BaByliss PRO",),
    "Bioderma": (),
    "Bourjois": ("Bourjois Paris",),
    "Caudalie": (),
    "CeraVe": ("Cera Ve",),
    "Chanel": (),
    "Clarins": (),
    "Clinique": (),
    "Ducray": (),
    "Dior": ("Christian Dior", "Dior Beauty"),
    "Elmiplant": (),
    "Essence": ("essence cosmetics",),
    "Estée Lauder": ("Estee Lauder",),
    "Eucerin": (),
    "Farmec": (),
    "Filorga": (),
    "Garnier": ("Garnier Skin Naturals",),
    "Gerovital": ("Gerovital H3",),
    "Isdin": (),
    "Ivatherm": (),
    "Kiehl's": ("Kiehls", "Kiehl's Since 1851"),
    "L'Oréal Paris": ("L'Oreal", "L'Oréal", "Loreal Paris", "Loreal"),
    "L'Oréal Professionnel": ("L'Oreal Professionnel", "Loreal Professionnel"),
    "La Roche-Posay": ("LRP", "La Roche Posay"),
    "Lancôme": ("Lancome",),
    "Makeup Revolution": ("Revolution", "Revolution Beauty", "Makeup Revolution London"),
    "Max Factor": (),
    "Maybelline New York": ("Maybelline", "Maybelline NY"),
    "Neutrogena": (),
    "Nivea": (),
    "Nuxe": (),
    "NYX Professional Makeup": ("NYX", "NYX Cosmetics"),
    "Rimmel London": ("Rimmel",),
    "Sisley": ("Sisley Paris",),
    "SVR": ("Laboratoires SVR",),
    "The Ordinary": ("The Ordinary.",),
    "Uriage": ("Eau Thermale Uriage",),
    "Vichy": ("Vichy Laboratoires",),
    "Yves Saint Laurent": ("YSL", "Yves Saint-Laurent", "YSL Beauty"),
}

_TRADEMARKS = re.compile("[®™©]")  # ® ™ ©
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def brand_key(raw: str) -> str:
    """Matching key: folded, trademark signs and apostrophes dropped, other punctuation
    as spaces. ``brand_key("L'ORÉAL Paris®") == "loreal paris"``."""
    text = fold(_TRADEMARKS.sub("", raw)).replace("'", "")
    return " ".join(_NON_ALNUM.sub(" ", text).split())


@cache
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in BRANDS.items():
        for alias in (canonical, *aliases):
            key = brand_key(alias)
            existing = index.setdefault(key, canonical)
            if existing != canonical:
                raise ValueError(f"brand alias {alias!r} maps to {existing!r} and {canonical!r}")
    return index


def canonical_brand(raw: str | None) -> str | None:
    """Canonical display name for a scraped brand.

    Known brands (by key or alias) get their canonical name; unknown brands are returned
    trimmed, with whitespace collapsed and trademark signs removed, so they can still be
    grouped by `brand_key()`. Empty input gives None.
    """
    if raw is None:
        return None
    cleaned = " ".join(_TRADEMARKS.sub("", raw).split())
    if not cleaned:
        return None
    return _alias_index().get(brand_key(cleaned), cleaned)


def is_known_brand(raw: str) -> bool:
    return brand_key(raw) in _alias_index()
