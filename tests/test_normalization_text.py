import pytest

from beautycrawler.normalization.text import fold


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("L’Oréal Paris", "l'oreal paris"),
        ("L'OREAL   PARIS", "l'oreal paris"),
        ("  Cremă  de  zi ", "crema de zi"),
        ("șțȘȚ", "stst"),  # comma-below ș ț Ș Ț
        ("şţŞŢ", "stst"),  # legacy cedilla ş ţ Ş Ţ
        ("împărăție Â", "imparatie a"),
        ("Vichy Minéral 89", "vichy mineral 89"),
        ("", ""),
    ],
)
def test_fold(raw: str, expected: str) -> None:
    assert fold(raw) == expected
