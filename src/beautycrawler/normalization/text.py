import unicodedata

# Right/left single quotation marks, grave and acute accents used as apostrophes.
_APOSTROPHES = str.maketrans(dict.fromkeys("\u2019\u2018`\u00b4", "'"))


def fold(text: str) -> str:
    r"""Case- and diacritic-insensitive key for matching.

    Handles Romanian letters in both comma-below (ș, ț) and legacy cedilla (ş, ţ) forms,
    typographic apostrophes and runs of whitespace:
    ``fold("  L\u2019Or\u00e9al   Paris ") == "l'oreal paris"``, ``fold("Ţesătură") == "tesatura"``.
    """
    decomposed = unicodedata.normalize("NFKD", text.translate(_APOSTROPHES))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())
