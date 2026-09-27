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

/* Search result cards (markup: `ui_data.card_html`). */
.bc-card-media {{
    position: relative;
    aspect-ratio: 1 / 1;
    background: #FFFFFF;
    border: 1px solid rgba(128, 128, 128, 0.18);
    border-radius: 0.5rem;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.75rem;
}}
.bc-card-media img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    padding: 8%;
    box-sizing: border-box;
}}
.bc-card-placeholder {{ font-size: 3rem; opacity: 0.35; }}
.bc-card-badges {{
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
}}
.bc-badge {{
    font-size: 0.72rem;
    font-weight: 600;
    line-height: 1.5;
    padding: 0.1rem 0.55rem;
    border-radius: 999px;
    color: #FFFFFF;
}}
.bc-badge-sale {{ background: {ACCENT_LIGHT}; }}
.bc-badge-out {{ background: #5E585B; }}
.bc-card-brand,
.bc-card-size,
.bc-card-stores {{
    font-size: 0.85rem;
    opacity: 0.72;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.bc-card-brand {{ font-variant-caps: all-small-caps; letter-spacing: 0.06em; }}
.bc-card-name {{
    font-weight: 600;
    line-height: 1.35;
    height: 2.7em;  /* always two lines, so cards in a row line up */
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}}
.bc-card-price {{
    font-size: 1.35rem;
    font-weight: 700;
    height: 2.2rem;  /* same with or without "de la" / for the muted text */
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    margin-top: 0.4rem;
}}
.bc-card-price .bc-from {{ font-size: 0.85rem; font-weight: 400; opacity: 0.72; }}
.bc-card-price.bc-muted {{ font-size: 1rem; font-weight: 600; opacity: 0.72; }}
.bc-card-stores {{ margin-bottom: 0.25rem; }}

/* Phone width: narrower side gutters, smaller page titles. */
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{
        padding-left: 1rem;
        padding-right: 1rem;
    }}
    h1 {{ font-size: 1.6rem !important; }}
    .bc-card-media {{ aspect-ratio: 4 / 3; }}  /* one card per row: keep it short */
}}
</style>
"""


def header_title() -> str:
    """Markdown for the app name in the header, in the theme's accent colour."""
    return f":primary[**{PAGE_ICON} {APP_NAME}**]"
