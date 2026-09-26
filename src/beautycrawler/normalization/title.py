"""Strip retailer marketing noise from product titles before matching.

Removes discount badges ("-20%", "Reducere 30%"), promo tags ("Promo", "Promoție",
"Ofertă", "Black Friday", "Exclusiv online", ...) and attached-gift mentions
("+ Cadou gel de duș 50 ml", "(cadou)", "cu cadou ..."). Ingredient percentages
("Niacinamide 10%") and gift *sets* ("Set cadou ...") are product information and are kept.
"""

import re

_WS = r"\s"  # str patterns: \s also matches NBSP
# Accept both diacritic and plain spellings (ț/ţ/t, ă/a, ...).
_T = "[tțţ]"
_A = "[aăâ]"
_I = "[iî]"
_S = "[sșş]"

_PROMO_WORDS = [
    rf"promo(?:{_T}i[ea])?",
    rf"ofert{_A}(?:{_WS}+special{_A})?",
    r"super[\s-]?pre[tțţ]",
    r"pre[tțţ][\s-]?special",
    r"black[\s-]?friday",
    r"cyber[\s-]?monday",
    r"best[\s-]?seller",
    rf"exclusiv(?:{_WS}+online)?",
    rf"stoc{_WS}+limitat",
    rf"livrare{_WS}+gratuit{_A}",
    rf"lichidare(?:{_WS}+stoc)?",
    r"outlet",
    r"hot[\s-]?deal",
    r"nou",
]
_PROMO = "|".join(_PROMO_WORDS)
# English tags that are also parts of names ("Maybelline New York"): only removed when
# bracketed or shouted with "!" ("NEW!", "[SALE]").
_PROMO_ENGLISH = r"new|sale"

_RULES: list[re.Pattern[str]] = [
    # Attached gifts: "+ Cadou ...", "+ gift", "+ gratis ...", "cu cadou ...", "- CADOU ..."
    # up to a closing bracket or the end of the title.
    re.compile(
        rf"(?:\+|{_WS}-|\bcu\b){_WS}*(?:un{_WS}+)?(?:cadou|gift|gratis|bonus)\b[^)\]]*",
        re.IGNORECASE,
    ),
    # A whole bracketed gift / promo / discount note: "(cadou)", "[PROMO]", "(-20%)".
    re.compile(
        rf"[(\[]{_WS}*(?:[^)\]]*\b(?:cadou|gift|gratis)\b[^)\]]*|(?:{_PROMO}|{_PROMO_ENGLISH})!*|-{_WS}*\d+(?:[.,]\d+)?{_WS}*%)"
        rf"{_WS}*[)\]]",
        re.IGNORECASE,
    ),
    # Discount badges: "-20%", "- 15 %", "Reducere 30%", "discount 10 %", "până la -50%".
    re.compile(
        rf"(?:\b(?:reducere|discount|p{_A}n{_A}{_WS}+la)\b{_WS}*:?{_WS}*-?|(?<![\w%])-){_WS}*"
        rf"\d+(?:[.,]\d+)?{_WS}*%",
        re.IGNORECASE,
    ),
    # Standalone promo words (whole words only, optional "!"), e.g. "PROMO Effaclar".
    re.compile(rf"(?<![\w-])(?:{_PROMO})!*(?![\w-])", re.IGNORECASE),
    re.compile(rf"(?<![\w-])(?:{_PROMO_ENGLISH})!+", re.IGNORECASE),
]
# A trailing "+" is only a separator after a space ("Cremă +" left by a removed gift);
# attached to a word it is part of the name ("Cicaplast Baume B5+", "SPF 50+").
_SEPARATORS = re.compile(r"^[\s\-|,:;/]+|(?:[\s\-|,:;/]|(?<=\s)\+)+$")
_EMPTY_BRACKETS = re.compile(rf"[(\[]{_WS}*[)\]]")


def clean_title(title: str) -> str:
    """`title` without promo/discount/gift noise, whitespace collapsed."""
    text = title
    for rule in _RULES:
        text = rule.sub(" ", text)
    text = _EMPTY_BRACKETS.sub(" ", text)
    text = " ".join(text.split())
    return _SEPARATORS.sub("", text).strip()
