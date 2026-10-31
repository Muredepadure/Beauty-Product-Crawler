"""Product categories from product names (P13.3).

The shops' pages give no usable category, but names say what a product is, in Romanian
or English, at the start ("Vopsea de par Wella…") or after the brand ("Gucci Bloom Apă
de parfum…"). `categorize` matches keyword rules in order and returns the first fitting
category from `CATEGORIES`, or `OTHER`. Order matters: "Set cadou Apă de toaletă + gel
de duș" is a set, "Sampon nuantator" a shampoo, "Pensula fond de ten" an accessory.

Names are compared folded (lowercase, no diacritics), so "Șampon" and "Sampon" match.
"""

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from beautycrawler.db.models import Product
from beautycrawler.normalization.text import fold

OTHER = "Altele"

# (category, pattern) in priority order. Patterns run on the folded name.
_RULES: list[tuple[str, str]] = [
    ("Seturi & cadouri", r"\bset\b|\bseturi\b|\bkit\b|coffret|gift set|cutie cadou"),
    (
        "Unghii",
        r"\blac (de )?unghii|\boja\b|\bnail|\bunghii|gel semipermanent|gel uv|top ?coat|"
        r"base ?coat|pudra acrilica|acril|gel de sculptare|builder gel|polygel|cuticul|"
        r"manichiur|pedichiur|\bpila\b|\btips\b",
    ),
    (
        "Parfumuri",
        r"\bapa de (parfum|toaleta|colonie)|extract de parfum|eau de (parfum|toilette|cologne)|"
        r"\bedp\b|\bedt\b|\bparfum\b|\bperfume\b|\bcologne\b|body mist|brume",
    ),
    ("Șampon", r"\bsampon|\bshampoo|\bwash\b|\bbain\b"),
    ("Balsam", r"\bbalsam|conditioner|\bapres\b"),
    (
        "Îngrijire față",
        r"\bmasca (de |pentru )?(fata|ten)\b|face mask|sheet mask|masca facial|peel[- ]?off",
    ),
    ("Mască de păr", r"\bmasca\b|mask\b|\bmasque\b"),
    (
        "Vopsea & oxidant",
        r"\bvopse|\boxidant|developer|decolor|bleach|\bhenna\b|coloratie|"
        r"(demi|semi)?permanent(a|e)? colo|color touch|koleston|majirel|\binoa\b|"
        r"dia (light|richesse)|welloxon|illumina color|blondor|"
        r"\bcolou?r\b.*\b\d{1,2}[./]\d{1,2}\b",
    ),
    (
        "Styling",
        r"\bfixativ|hairspray|hair spray|spray (de |pentru )?(par|volum|fixare|texturiz)|"
        r"\bspuma|\bmousse|\bgel (de |pentru )?par\b|\bgel par\b|ceara (de |pentru )?par|"
        r"\bwax\b|\bpomad|\bpasta (de |pentru )?par|texturiz|sugar lift|ocean spritz|"
        r"styling|\bfixare\b|stralucire|\bshine\b|glam mist|fixing|\bhold\b|root (lift|boost)|"
        r"\bpaste\b|\bpasta\b|modelat|texurizant|refresh|volumiz|sea salt|root shoot",
    ),
    (
        "Accesorii & aparate",
        r"\bperi(e|i)\b|\bbrush\b|\bpiepten|\bcomb\b|foarfec|uscator|\bplaca (de )?par|"
        r"ondulator|\baparat|bigudi|placa de indreptat|\bclips|\bagraf|\belastic|\bpenset|"
        r"\bpensul|\bburete|"
        r"\binstrument|\bprosop|\bmanusa|\bfoarfece|\bbonet|\bcasca|\bpelerina|scrunch|"
        r"invisibobble|\bbentit|detangler|tangle teezer|\blumanar|\bcandle|card cadou",
    ),
    (
        "Machiaj",
        r"fond de ten|foundation|\bpudra\b|\bpowder\b|\bblush|bronzer|\brimel|mascara|"
        r"eyeliner|\bliner\b|microliner|\bcreion|\bpencil\b|\bruj\b|lipstick|lip gloss|"
        r"luciu de buze|\bfard|"
        r"eyeshadow|concealer|corector|\bprimer\b|highlighter|\bgene\b|\blash|"
        r"sprancene|\bbrow\b|sclipici|glitter|\bmachiaj|make-?up|contour",
    ),
    (
        "Îngrijire corp",
        r"gel de dus|shower|\bcorp\b|\bcorps\b|\bbody\b|deodorant|antiperspirant|"
        r"crema de maini|hand cream|\bmaini\b|\bpicioare\b|\bsapun|\bsoap\b|\bbaie\b|"
        r"\bbath\b|depil|epil|\bintim|autobronz|self[- ]tan|protectie solara|\bspf\b.*corp|"
        r"after ?shave|barbierit|\bbarba\b|beard|\bscrub|exfoli|lapte de corp|\bdeo|"
        r"mouthwash|dental|dinti|\bsun\b|solar|roll-?on|anti-?perspirant",
    ),
    (
        "Îngrijire față",
        r"\bfata\b|\bten\b|facial|\bface\b|\bochi\b|\beye\b|riduri|antirid|anti-?age|"
        r"\btonic|\btoner\b|micelar|demachi|cleanser|cleansing|acnee|pleoape|\bbuze\b|"
        r"\blip\b|\bneck\b|decollete|\btint\b|esenta",
    ),
    (
        "Tratament & îngrijire păr",
        r"\bpar\b|\bparul\b|\bparului\b|\bhair\b|\bscalp|capilar|leave-?in|keratin|cheratina|"
        r"\bfiol|\btratament|\btreatment\b|\bulei\b|\boil\b|\bser\b|elixir|varfuri",
    ),
    (
        "Îngrijire față",
        r"\bserum|\bampoule|\bfluid\b|\bcrema\b|\bcream\b|\bcreme\b|concentrat|\bemulsi|"
        r"\bmilk\b|\bgel\b|\blotion\b|\blotiune\b",
    ),
]

_COMPILED = [(category, re.compile(pattern)) for category, pattern in _RULES]

# Every category the rules can give, in the order the UI lists them.
CATEGORIES: tuple[str, ...] = (
    "Șampon",
    "Balsam",
    "Mască de păr",
    "Tratament & îngrijire păr",
    "Vopsea & oxidant",
    "Styling",
    "Parfumuri",
    "Îngrijire față",
    "Îngrijire corp",
    "Machiaj",
    "Unghii",
    "Accesorii & aparate",
    "Seturi & cadouri",
    OTHER,
)


def categorize(name: str) -> str:
    """The category of a product called `name` (`OTHER` when no rule fits)."""
    text = fold(name)
    for category, pattern in _COMPILED:
        if pattern.search(text):
            return category
    return OTHER


def categorize_product(product: Product) -> str:
    """The product's category from its name, else from its listings' titles."""
    category = categorize(product.name)
    for offer in product.offers if category == OTHER else ():
        category = categorize(offer.title)
        if category != OTHER:
            break
    return category


def categorize_products(session: Session, *, recompute: bool = False) -> Counter[str]:
    """Set the category of products without one (every product with `recompute`).
    Returns how many products went to each category. Flushes; does not commit."""
    query = select(Product).options(selectinload(Product.offers))
    if not recompute:
        query = query.where(Product.category.is_(None))
    counts: Counter[str] = Counter()
    for product in session.scalars(query):
        product.category = categorize_product(product)
        counts[product.category] += 1
    session.flush()
    return counts
