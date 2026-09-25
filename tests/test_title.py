import pytest

from beautycrawler.normalization.title import clean_title


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        # discount badges
        ("La Roche-Posay Effaclar Duo+ 40 ml -20%", "La Roche-Posay Effaclar Duo+ 40 ml"),
        ("Gel 200 ml (-15%)", "Gel 200 ml"),
        ("Crema -15 % 50 ml", "Crema 50 ml"),
        ("Reducere 30% Vichy Mineral 89", "Vichy Mineral 89"),
        ("Vichy Mineral 89 - Discount: 10%", "Vichy Mineral 89"),
        ("Pana la -50% Sampon 400 ml", "Sampon 400 ml"),
        ("Crema -20% 50 ml", "Crema 50 ml"),
        # promo tags
        ("PROMO La Roche-Posay Effaclar", "La Roche-Posay Effaclar"),
        ("Promoție Nivea crema 150 ml", "Nivea crema 150 ml"),
        ("Promotie Nivea crema 150 ml", "Nivea crema 150 ml"),
        ("Ser [PROMO] 30 ml", "Ser 30 ml"),
        ("Ofertă specială: Bioderma Sensibio 500 ml", "Bioderma Sensibio 500 ml"),
        ("Black Friday - Sampon 400 ml |", "Sampon 400 ml"),
        ("Crema 50 ml - Exclusiv online", "Crema 50 ml"),
        ("Crema 50 ml Stoc limitat!", "Crema 50 ml"),
        ("NOU! Crema de noapte 50 ml", "Crema de noapte 50 ml"),
        ("NEW! Crema de noapte 50 ml", "Crema de noapte 50 ml"),
        ("Crema de noapte 50 ml [SALE]", "Crema de noapte 50 ml"),
        ("Super Preț Gel de duș 500 ml", "Gel de duș 500 ml"),
        # attached gifts
        ("Crema 50 ml + Cadou Gel de dus 15 ml", "Crema 50 ml"),
        ("Crema 50 ml + CADOU", "Crema 50 ml"),
        ("Crema 50 ml - CADOU ser 5 ml", "Crema 50 ml"),
        ("Parfum 100 ml cu cadou geantă", "Parfum 100 ml"),
        ("Ser (cadou) 30 ml", "Ser 30 ml"),
        ("Ser 30 ml (+ gift pouch)", "Ser 30 ml"),
        ("Ser 30 ml + un cadou surpriză", "Ser 30 ml"),
        # kept: product information
        ("Niacinamide 10% + Zinc 1% 30 ml", "Niacinamide 10% + Zinc 1% 30 ml"),
        ("Set cadou Lancôme La Vie Est Belle", "Set cadou Lancôme La Vie Est Belle"),
        ("Maybelline New York Lash Sensational", "Maybelline New York Lash Sensational"),
        ("Ser anti-aging 30 ml", "Ser anti-aging 30 ml"),
        ("Crema Nouvelle Formule", "Crema Nouvelle Formule"),
        ("Pronto Promotor", "Pronto Promotor"),
        ("  Crema   hidratanta  ", "Crema hidratanta"),
        ("", ""),
    ],
)
def test_clean_title(raw: str, clean: str) -> None:
    assert clean_title(raw) == clean


def test_idempotent() -> None:
    raw = "PROMO -20% Crema 50 ml + Cadou ser 5 ml"
    once = clean_title(raw)
    assert once == "Crema 50 ml"
    assert clean_title(once) == once
