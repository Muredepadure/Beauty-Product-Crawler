"""Shared look of the Streamlit UI (P10.1): names, colours and the one CSS block.

Theme colours live in `.streamlit/config.toml`; the values below mirror them for the few
places the theme cannot reach (cell highlights, the tests' contrast check). Keep all
custom CSS here instead of scattering `<style>` snippets through `ui/App.py`.
"""

APP_NAME = "BeautyCrawler"
TAGLINE = "Compară prețurile produselor cosmetice din magazinele online din România"
PAGE_TITLE = f"{APP_NAME} — prețuri cosmetice"
PAGE_ICON = "💄"

# Mirrors of `.streamlit/config.toml` ([theme.light] / [theme.dark]).
ACCENT_LIGHT = "#B4325A"
ACCENT_DARK = "#F08BA6"

# Table cell highlights. Translucent, so the same value reads well on the light and the
# dark background.
CHEAPEST_ROW = "background-color: rgba(46, 160, 67, 0.18)"
BELOW_MARKET = "background-color: rgba(46, 160, 67, 0.20)"
ABOVE_MARKET = "background-color: rgba(218, 54, 51, 0.20)"

# Streamlit's own classes are not a stable API, so only `data-testid` hooks and the
# `st-key-<key>` class Streamlit adds to keyed containers are used.
HEADER_KEY = "bc-header"

CSS = f"""
<style>
/* Less empty space above the content (but clear of Streamlit's 3.75rem top bar), and
   a comfortable reading width. */
[data-testid="stMainBlockContainer"] {{
    padding-top: 4rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}}
[data-testid="stDecoration"] {{ display: none; }}

/* Slim header: app name and tagline on one line (wraps on a phone). */
.st-key-{HEADER_KEY} {{
    border-bottom: 1px solid rgba(128, 128, 128, 0.25);
    padding-bottom: 0.5rem !important;  /* Streamlit zeroes container padding */
    align-items: baseline !important;   /* name and tagline on one text line */
    margin-bottom: 0.75rem;
}}
.st-key-{HEADER_KEY} p,
.st-key-{HEADER_KEY} [data-testid="stCaptionContainer"] {{ margin: 0; }}
.st-key-{HEADER_KEY} [data-testid="stMarkdownContainer"] strong {{
    font-size: 1.3rem;
    letter-spacing: 0.01em;
}}

/* Phone width: narrower side gutters, smaller page titles. */
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{
        padding-left: 1rem;
        padding-right: 1rem;
    }}
    h1 {{ font-size: 1.6rem !important; }}
}}
</style>
"""


def header_title() -> str:
    """Markdown for the app name in the header, in the theme's accent colour."""
    return f":primary[**{PAGE_ICON} {APP_NAME}**]"
