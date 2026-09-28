"""P10.1: the Streamlit theme (`.streamlit/config.toml`) and the shared style module."""

import tomllib
from pathlib import Path
from typing import Any

import pytest
from streamlit import config as st_config

from beautycrawler import ui_style

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


@pytest.fixture(scope="module")
def theme_config() -> dict[str, Any]:
    with CONFIG.open("rb") as f:
        return tomllib.load(f)


def _flatten(table: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in table.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{name}."))
        else:
            out[name] = value
    return out


def test_every_option_is_known_to_streamlit(theme_config: dict[str, Any]) -> None:
    """A misspelt option is silently ignored by Streamlit, so check the names here."""
    known = set(st_config._config_options_template)
    for name in _flatten(theme_config):
        # [theme.light] / [theme.dark] take the same options as [theme].
        generic = name.replace("theme.light.", "theme.").replace("theme.dark.", "theme.")
        assert generic in known, name


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two #RRGGBB colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_helper() -> None:
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast("#777777", "#777777") == pytest.approx(1)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_both_modes_are_readable(theme_config: dict[str, Any], mode: str) -> None:
    """WCAG AA (4.5:1) for body text and for the accent, which is also the link colour."""
    theme = theme_config["theme"][mode]
    background = theme["backgroundColor"]
    assert contrast(theme["textColor"], background) >= 7
    assert contrast(theme["textColor"], theme["secondaryBackgroundColor"]) >= 7
    assert contrast(theme["primaryColor"], background) >= 4.5
    assert contrast(theme["primaryColor"], theme["secondaryBackgroundColor"]) >= 4.5
    assert theme["linkColor"] == theme["primaryColor"]


def test_style_module_mirrors_the_theme(theme_config: dict[str, Any]) -> None:
    assert theme_config["theme"]["light"]["primaryColor"] == ui_style.ACCENT_LIGHT
    assert theme_config["theme"]["dark"]["primaryColor"] == ui_style.ACCENT_DARK


def test_light_accent_carries_white_button_text() -> None:
    """Primary buttons put white text on the accent in light mode."""
    assert contrast(ui_style.ACCENT_LIGHT, "#FFFFFF") >= 4.5


def test_css_is_one_style_block_scoped_to_the_header_key() -> None:
    css = ui_style.CSS.strip()
    assert css.startswith("<style>") and css.endswith("</style>")
    assert css.count("<style>") == 1
    assert f".st-key-{ui_style.HEADER_KEY}" in css
    assert "@media (max-width: 640px)" in css


def test_header_title_uses_the_accent() -> None:
    assert ui_style.header_title() == ":primary[**💄 BeautyCrawler**]"
