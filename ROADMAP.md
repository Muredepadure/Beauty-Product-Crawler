# Roadmap

Work top to bottom. Each task is sized for roughly one nightly session. A task is done
when its code, tests and docs are committed and lint/type-check/tests pass.
Mark `[x]` when done, `[~]` when partially done (add a note), `[!]` when blocked (add reason).

## Target retailers (Romania)

Candidate "top 10" by traffic and market position. Task P3.1 verifies each one
(robots.txt, terms, whether product data is readable without JS/bot walls) before a spider is built.

| # | Retailer | Domain | Type | Status |
|---|---|---|---|---|
| 1 | Notino | notino.ro | Beauty e-commerce (market leader online) | **blocked**: robots.txt allows product pages, but Cloudflare answers our HTTP client with a challenge (403, `cf-mitigated: challenge`) — rule 6, no spider |
| 2 | eMAG | emag.ro | Marketplace | **feasible**: robots.txt allows product pages (`/<slug>/pd/<id>/`); plain HTTP works; complete `Product` JSON-LD incl. brand and seller. But the sitemaps list the whole catalogue (423 × 5 000 URLs, all departments), so beauty products must be discovered via beauty category listings, not sitemaps. Also on Profitshare (feed) |
| 3 | Sephora | sephora.ro | Beauty chain | **blocked**: even robots.txt answers our client with 403 (Akamai) — rule 6, no spider |
| 4 | Douglas | douglas.ro | Beauty chain | **blocked**: even robots.txt answers our client with 403 — rule 6, no spider |
| 5 | Makeup.ro | makeup.ro | Beauty e-commerce | **blocked**: robots.txt and sitemaps load, but product pages return an AWS WAF challenge (202, `x-amzn-waf-action: challenge`) — rule 6, no spider |
| 6 | dm drogerie markt | dm.ro | Drugstore | allowed by robots.txt (sitemap `product-sitemap.xml`, ~11 500 products), but product pages are rendered by JavaScript: the HTML has no product data → needs the optional Playwright path (CLAUDE.md) |
| 7 | Farmacia Tei | farmaciatei.ro | Pharmacy (dermocosmetics) | **not allowed**: robots.txt has a second `User-agent: *` group with `Disallow: /` (only named search/AI bots allowed) — no spider. Re-checked 2026-10-18 on the shop domain `comenzi.farmaciatei.ro`: same policy |
| 8 | Dr.Max | drmax.ro | Pharmacy (dermocosmetics) | **blocked**: sitemap answers our client with a Cloudflare challenge — rule 6, no spider |
| 9 | Parfimo | parfimo.ro | Perfume / cosmetics e-commerce | **done** (P3.9): JSON-LD + heading/gallery, ~17 500 products in 7 sitemaps |
| 10 | Elefant | elefant.ro | General e-commerce with beauty section | **feasible with a custom parser**: robots.txt allows product pages; plain HTTP works; no JSON-LD, but the page's GTM data block has name, price (RON), brand and category (stock/old price from the HTML). Sitemaps list all products (books, watches, …): filter by category |
| 11 | Profihairshop | profihairshop.ro | Professional hair & body care (owner's priority) | **done** (P11.1): JSON-LD, ~1 300 products in `products-sitemap.xml`, `Crawl-delay: 10`. Live smoke run pending (owner) |
| 12 | ProBeauty | probeauty.ro | Professional hair tools & care (Shopify) | **done** (P11.2): Shopify JSON-LD, `sitemap_products_<n>.xml`. Live smoke run pending (owner) |
| 13 | Beauty Lounge | beauty-lounge.ro | Professional hair & skin care (Shopify) | **done** (P11.2): Shopify JSON-LD with sale prices; `<h1>` completes cut-short names. Live smoke run pending (owner) |
| 14 | Esteto | esteto.ro | General store with cosmetics and perfume | **done** (P11.3): JSON-LD; no sitemap, so discovery walks the `/produse-cosmetice` and `/parfumuri` listings. Live smoke run pending (owner) |
| 15 | XpertBeauty | xpertbeauty.ro | Professional skin, hair & nail care (Magento) | **done** (P11.4): custom parser (analytics block + price boxes), sitemaps `/sitemap/sitemap-1-{1,2,3}.xml`. Live smoke run pending (owner) |
| 16 | Citrika | citrika.ro | Cosmetics e-commerce | **blocked** (2026-10-18): Cloudflare challenge (403, `cf-mitigated: challenge`) on the home page and sitemaps — rule 6, no spider |
| 17 | Bebe Tei | comenzi.bebetei.ro | Baby & mother care (Farmacia Tei group) | **not allowed** (2026-10-18): robots.txt `User-agent: *` → `Disallow: /` (only named search/AI bots allowed) — no spider |
| R | Trendyol, Catena, Marionnaud | — | Reserves: audit and add to replace blocked stores | — |

Audit notes (2026-09-27 and 2026-09-29, done locally from a home connection because the nightly cloud
environment had no access yet): "our client" means the project's `PoliteFetcher` (httpx,
`BeautyCrawler/0.1` user agent). A site that challenges it is blocked even if curl or a
browser gets through: making our client look like something else is fingerprint evasion.

## Phase 0 — Foundation

- [x] **P0.1** Fix API data path: resolve `data/products.json` relative to the package, not the CWD. Add `streamlit`, `respx`, `rapidfuzz` to deps.
- [x] **P0.2** Add `pyproject.toml` (package metadata, `[dev]` extra, ruff/mypy/pytest config); make `pip install -e ".[dev]"` work; keep `requirements.txt` in sync or remove it.
- [x] **P0.3** First tests: `/healthz`, `/api/products` search/filter/pagination (FastAPI `TestClient`).
- [x] **P0.4** GitHub Actions CI: lint, mypy, pytest on every push/PR.
- [x] **P0.5** `src/beautycrawler/config.py` with `pydantic-settings` (`DATABASE_URL`, user agent, delays); `.env.example`.
- [x] **P0.6** Rewrite README "Quick Start"/"Project Structure" to match reality (src layout, SQLite default).

## Phase 1 — Data model

- [x] **P1.1** SQLAlchemy models: `Retailer`, `Brand`, `Product` (canonical item: brand, name, size, unit, EAN), `Offer` (product × retailer: URL, current price, stock), `PriceHistory` (offer, price, old price, in_stock, scraped_at). Prices in bani.
- [x] **P1.2** Alembic setup + initial migration; test that `upgrade head` works on a fresh SQLite DB.
- [x] **P1.3** Repository/service layer: upsert offer, append price history only when price or stock changes; unit tests.
- [x] **P1.4** Seed script (`scripts/seed.py`) that loads the retailers table and a few demo products.

## Phase 2 — Extraction core

- [x] **P2.1** `ScrapedOffer` Pydantic model (the spider output contract).
- [x] **P2.2** Generic JSON-LD `Product`/`Offer` extractor (`extractors/jsonld.py`) with fixtures covering: single offer, multiple variants, missing GTIN, price as string with comma decimals.
- [x] **P2.3** Romanian price parser: "1.234,99 lei", "49,90 RON", "de la 30 lei", old/new price pairs; exhaustive unit tests.
- [x] **P2.4** Polite HTTP fetcher: robots.txt check (cached), per-domain rate limit, retries with backoff, custom UA, timeout. Tested with `respx`.
- [x] **P2.5** `Spider` base interface: `discover()` (category/listing/sitemap → product URLs) and `parse_product(html, url) -> ScrapedOffer`.
- [x] **P2.6** _(Added and done by the 2026-10-18 nightly run, found while building P11.3.)_ RFC 9309 robots.txt matching (`crawler/robots.py`): `urllib.robotparser` ignored `*`/`$` wildcards (e.g. `Disallow: /*?sort=`) and every `User-agent: *` group after the first, so such rules were not respected.

## Phase 3 — Retailer spiders

- [x] **P3.1** Retailer audit (2026-09-27/29, from a home connection with our client): see the table above. Working: Parfimo (done), eMAG, Elefant. Blocked: Notino, Dr.Max, Sephora, Douglas, Makeup.ro. Not allowed: Farmacia Tei. Needs JavaScript: dm.
- [!] **P3.2** _Blocked 2026-09-27: Cloudflare challenges our client (see table). Real Notino pages are kept in `tests/fixtures/notino/` as JSON-LD variant examples._ Spider: Notino
- [!] **P3.3** _Blocked 2026-09-29: 403 (Akamai) even on robots.txt._ Spider: Sephora
- [!] **P3.4** _Blocked 2026-09-29: 403 even on robots.txt._ Spider: Douglas
- [!] **P3.5** _Blocked 2026-09-29: AWS WAF challenge on product pages._ Spider: Makeup.ro
- [!] **P3.6** _On hold (owner, 2026-09-27): the data source is being decided (affiliate product feeds vs crawling). Do not start until the owner lifts the hold._ Spider: dm — JavaScript-rendered pages: do this after the plain-HTTP stores, using Playwright behind an optional extra (CLAUDE.md stack table). Tests still run on saved (rendered) fixtures.
- [!] **P3.7** _Not allowed 2026-09-27: robots.txt disallows `/` for all generic bots._ Spider: Farmacia Tei
- [!] **P3.8** _Blocked 2026-09-27: Cloudflare challenge on the sitemap._ Spider: Dr.Max
- [x] **P3.9** Spider: Parfimo (2026-09-27, built and smoke-run locally: 20 pages, 20 offers, 0 errors)
- [!] **P3.10** _On hold (owner, 2026-09-27): the data source is being decided (affiliate product feeds vs crawling). Do not start until the owner lifts the hold._ Spider: Elefant
- [!] **P3.11** _On hold (owner, 2026-09-27): the data source is being decided (affiliate product feeds vs crawling). Do not start until the owner lifts the hold._ Spider: eMAG (marketplace: record seller name per offer)
- [x] **P3.12** Crawl CLI: `python -m beautycrawler.crawler run --retailer notino [--limit N]` and `run --all`; writes to DB via P1.3.

Each spider task: parser + fixture tests + discovery (prefer sitemaps) + a `--limit` smoke path. Skip and mark `[!]` if P3.1 says crawling is not allowed or not possible.
Use `src/beautycrawler/crawler/spiders/parfimo.py` + `tests/test_spider_parfimo.py` as the template.
- [!] **P3.13** _On hold (owner, 2026-09-27): the data source is being decided (affiliate product feeds vs crawling). Do not start until the owner lifts the hold._ Reserve spiders (Trendyol, Catena, Esteto, Marionnaud, …) for each blocked store, same audit rules.

## Phase 4 — Normalization & matching

- [x] **P4.1** Brand normalization: alias map (e.g. "L'Oreal Paris" / "L’Oréal" → `L'Oréal Paris`), diacritics/case folding.
- [x] **P4.2** Size/unit parsing from titles: ml, l, g, kg, buc; multipacks ("2 x 50 ml").
- [x] **P4.3** Title cleanup: strip retailer noise ("Promo", "-20%", gift mentions).
- [x] **P4.4** Product matching: 1) EAN/GTIN exact; 2) brand + normalized name + size with `rapidfuzz` threshold; ambiguous matches go to a review table rather than auto-merging. Tests with realistic cross-retailer pairs.
- [x] **P4.5** Admin CLI to list/approve/reject ambiguous matches.

## Phase 5 — API v1 (DB-backed)

- [x] **P5.1** Replace JSON file with DB: `GET /api/products?q=&brand=&category=&sort=&page=` (search over normalized name + brand).
- [x] **P5.2** `GET /api/products/{id}`: all offers across retailers, sorted by price; cheapest flagged.
- [x] **P5.3** `GET /api/products/{id}/history`: price history per retailer.
- [x] **P5.4** `GET /api/retailers`, `GET /api/brands`; pagination and response schemas documented in OpenAPI.
- [x] **P5.5** Seller view: `GET /api/compare?brand=X` — for a brand's products, each retailer's price vs the market minimum/median.

## Phase 6 — Scheduling & freshness

- [x] **P6.1** `crawl all` job with per-retailer isolation (one failing site doesn't stop others), run summary + structured logs.
- [x] **P6.2** Scheduling: APScheduler entry point and/or documented cron; configurable frequency per retailer.
- [x] **P6.3** Mark offers stale/out-of-stock when not seen for N runs.
- [x] **P6.4** Price-drop detection: query/endpoint for products whose price fell ≥ X% since last run (foundation for alerts).

## Phase 7 — UI (Streamlit)

- [x] **P7.1** Search page: results as cards with lowest price, number of retailers, image.
- [x] **P7.2** Product page: price table across retailers (cheapest highlighted, stock, link out) + price-history chart.
- [x] **P7.3** Filters: brand, category, price range, in-stock only.
- [x] **P7.4** Competitor view: pick a brand/retailer, see where it's over/under market price.
- [x] **P7.5** UI talks to the API via a small client module; API base URL from config.

## Phase 8 — Packaging & deployment

- [x] **P8.1** Dockerfile(s) + `docker-compose.yml` (api, ui, postgres, scheduler).
- [x] **P8.2** Postgres integration test job in CI (service container).
- [x] **P8.3** Final README: setup, running crawls, API reference, adding a new retailer.

## Phase 9 — Data sources (on hold, owner)

The owner is deciding how prices get in: affiliate product feeds (2Performant, Profitshare:
XML/CSV with price, stock, EAN, image) as the main source, crawling as the fallback for
stores without a feed. Nothing here starts until the owner lifts the hold.

- [!] **P9.1** _On hold (owner)._ Feed importer: read a merchant XML/CSV feed into the same `upsert_offer` path (so matching, history and the UI work unchanged); tested with sample feed files.
- [~] **P9.2** _(2026-10-26, local session: resumable part done — `--skip-seen-hours`, `--until`, adaptive 429 pacing and a rate-limit give-up, `scripts/nightly_crawl.ps1` + Task Scheduler. Still open: sitemap `lastmod`, and remembering dead (404) sitemap URLs so they are not re-fetched every night — ~14% of Profihairshop's sitemap.)_ Incremental and resumable crawls (sitemap `lastmod`, continue after an interruption).
- [!] **P9.3** _Deferred (owner, 2026-09-28: "wait")._ `pack_count` on Product/Offer so multipacks ("2 x 50 ml") can be matched; revisit once there is multi-store data.

## Phase 10 — UI redesign (simple, polished)

Goal: a clean, modern, simple look for the Streamlit UI — not new features. Keep the
Romanian copy, keep every existing page working, and keep `tests/test_ui_app.py` green
(update it when markup changes). Prefer Streamlit theming (`.streamlit/config.toml`) and a
small, well-scoped CSS block over heavy custom HTML. Must look right in light and dark mode
and on a phone-width window. In each PR, describe the visual changes; attach screenshots
if the environment can take them (e.g. Playwright against a local run with seeded data).

- [x] **P10.1** Design foundation: theme in `.streamlit/config.toml` (one accent colour suited to beauty, neutral greys, readable font sizes), page title/icon, a slim header with the app name and a one-line tagline, consistent spacing. Collect shared styling in one module (e.g. `ui/style.py`) instead of scattering CSS.
- [x] **P10.2** Search results: tidy product cards — fixed-ratio image on a light background, brand in small caps above the name, size, **lowest price** prominent, "la N magazine" (retailer count), badges for "Reducere" (on sale) and "Stoc epuizat" (out of stock); consistent card heights; placeholder image when missing.
- [x] **P10.3** Search bar and filters: search field at the top with a clear placeholder, filters in the sidebar grouped and labelled, result count and sort in one row, friendly empty state ("Niciun produs găsit") with a hint.
- [x] **P10.4** Product page: header with image, brand, name, size; price comparison table with retailer name, price, old price struck through, stock status, "Vezi în magazin" button; cheapest row highlighted; price-history chart styled to match the theme; back link to results.
- [x] **P10.5** Seller view ("Comparație prețuri"): clearer table/heatmap of each retailer vs the market median (green below, red above), short explanation text, same visual language as the other pages.
- [x] **P10.6** Polish: loading spinners, error message when the API is down (with the command to start it: `python -m uvicorn beautycrawler.api.main:app --port 8000`, which also works where Windows Smart App Control blocks `uvicorn.exe`), formatted prices ("1.234,50 lei"), favicon, footer with data freshness ("Actualizat la …" = newest `scraped_at`).
- [x] **P10.7** Hide demo data: once any retailer has real offers, the seed's demo products without offers no longer appear in search (or add a `--no-demo` seed option); document it.

## Phase 11 — Owner's priority shops (2026-10-18)

The owner's list of shops to cover. Audited on 2026-10-18 from a home connection with our
client (`PoliteFetcher`, `BeautyCrawler/0.1` user agent). This phase is **not** on hold:
work it top to bottom. The P3/P9 hold still applies to everything else.

| Shop | Domain | Audit result |
|---|---|---|
| **Profihairshop** (owner's #1) | profihairshop.ro → www.profihairshop.ro | ✅ robots.txt allows all, **`Crawl-delay: 10`** (the fetcher must honour it: ~3.6 h for a full crawl). Sitemap index `/sitemap-index.xml` → `products-sitemap.xml` (~1 300 products; skip pages/categories/brands sitemaps). Complete `Product` JSON-LD: name, price, availability, GTIN, brand, image. |
| ProBeauty | probeauty.ro | ✅ Shopify. robots.txt allows `/products/*`. `/sitemap.xml` → `sitemap_products_<n>.xml`. Complete `Product` JSON-LD. |
| Beauty Lounge | beauty-lounge.ro | ✅ Shopify, same layout as ProBeauty (7 product sitemaps). JSON-LD has sale prices (old price) — but the JSON-LD name can be cut short ("…Deteriora"): prefer the `<h1>` when it is longer. |
| Esteto | www.esteto.ro | ✅ robots.txt allows product pages (`/produse-<id>-<slug>`). **No sitemap** (404): discover through category pages linked from the home page. Complete `Product` JSON-LD (GTIN often missing). |
| XpertBeauty | www.xpertbeauty.ro | ✅ robots.txt: the `*` group only blocks filter URLs. Sitemaps `/sitemap/sitemap-1-{1,2,3}.xml` mix categories and products (products are single-segment paths). **No Product JSON-LD**: custom parser — `product:price:amount` meta, an inline JSON object with `"price"`, `"brand"`, `"availability"`, and `data-price-amount` / `data-price-type="oldPrice"` for the old price. |
| Citrika | www.citrika.ro | ❌ **Blocked**: Cloudflare challenge (403, `cf-mitigated: challenge`) on the home page and sitemaps — rule 6, no spider. |
| Farmacia Tei | comenzi.farmaciatei.ro | ❌ **Not allowed**: robots.txt `User-agent: *` → `Disallow: /` (only named search/AI bots allowed). Do not impersonate an allowed bot. |
| Bebe Tei | comenzi.bebetei.ro | ❌ **Not allowed**: same robots.txt policy as Farmacia Tei. |

Trimmed real pages (reviews removed) are in `tests/fixtures/<shop>/`, so every spider can be
built and tested without network access. Use `spiders/parfimo.py` + `tests/test_spider_parfimo.py`
as the template. Each task: add the retailer to `RETAILERS` in `db/seed.py` (and the table at
the top of this file), spider + fixture tests + discovery test with mocked HTTP; if the cloud
environment can reach the shop, finish with a polite live smoke run (`--limit 10`) and report
the numbers in the PR; if it can't, say so in the PR and leave the live run to the owner.

- [x] **P11.1** _(2026-10-18 nightly: spider + fixture/discovery tests; Crawl-delay and apex→www redirects tested. The cloud environment cannot reach the shop, so the live `--limit 10` smoke run is left to the owner.)_ Spider: **Profihairshop** (priority). Fixtures: `tests/fixtures/profihairshop/` (gift set, hair dye). Make sure `Crawl-delay: 10` is honoured (add a test if the fetcher lacks one) and that `profihairshop.ro` → `www.` redirects work for robots.txt and sitemaps.
- [x] **P11.2** _(2026-10-18 nightly: `crawler/shopify.py` + both spiders, fixture and discovery tests; live smoke runs left to the owner, no cloud access.)_ Shared `ShopifySpider` base (sitemap_products_N discovery, `/products/<handle>` URLs, JSON-LD parse, `<h1>` title fallback) + spiders **ProBeauty** and **Beauty Lounge**. Fixtures: `tests/fixtures/probeauty/`, `tests/fixtures/beautylounge/`.
- [x] **P11.3** _(2026-10-18 nightly: spider walks the `/produse-cosmetice` and `/parfumuri` listings breadth-first: subcategories and `?page=N` only, no sort/filter URLs, capped at 2 000 listing pages. The pagination format is a guess (no listing fixture): check it on the first live run. Owner: are these the right categories?)_ Spider: **Esteto** with category-page discovery (no sitemap). Fixtures: `tests/fixtures/esteto/` (product page + the home page's links). Keep discovery polite: only category listing pages and their pagination, respect robots.txt.
- [x] **P11.4** _(2026-10-18 nightly: parser reads the `product_viewed` analytics block and the `old-price-<id>`/`product-price-<id>` boxes; EAN from the nested JSON-LD `mpn` when its check digit is valid. Top-level category URLs pass the sitemap filter and are dropped by the parser. Live smoke run left to the owner.)_ Spider: **XpertBeauty** with a custom parser (no Product JSON-LD). Fixture: `tests/fixtures/xpertbeauty/guinot_mask.html` (59,20 lei, old price 74 lei, brand Guinot, in stock). Filter sitemap URLs to product pages.
- [x] **P11.5** _(2026-10-18 nightly: rows 7, 16, 17 of the retailer table; Citrika and Bebe Tei added to the seed retailers like the other blocked shops.)_ Record the blocked/not-allowed shops (Citrika, Farmacia Tei, Bebe Tei) in the retailer table at the top; no spiders.


## Phase 12 — Owner's UI requests (2026-10-28)

Reported by the owner while using the site with real data (~2 100 products, Profihairshop +
XpertBeauty). Not on hold: work it top to bottom, **in this order** (priority). UI copy stays
Romanian. Keep `tests/test_ui_app.py` green and add tests for each behaviour (Streamlit
`AppTest` for the UI, API tests for new query parameters). The cloud cannot reach the API
with real data: test with the seeded DB / fixtures, and describe in the PR what the owner
should click to check it.

- [x] **P12.1** _(2026-10-28 nightly: the URL is the source of truth for the search: `load_search_from_url`/`save_search_to_url` in `ui/App.py`, encoding in `ui_data.py`. Plain `st.query_params` is enough on Streamlit 1.66: the frontend pushes a history entry when the script changes it and reruns on back/forward (checked in headless Chromium). Each filter change is its own history entry.)_ _(bug, highest priority)_ **Coming back from a product page keeps the search.** Today the filters live only in `st.session_state` and the product in `?product=<id>`: going back (the "← Înapoi la rezultate" button) shows the initial state with filters reset, and the **browser back arrow does nothing useful** (only the button works). Fix both: keep the search text, every sidebar filter, sort and page in the URL query parameters (e.g. `?q=…&brand=…&sort=…&page=2`) and restore them from the URL on load, so (a) "Înapoi la rezultate" returns to the same filtered results and page, (b) the browser back/forward arrows move between results and product pages, (c) a results URL can be shared/bookmarked. Check how `st.query_params` updates the browser history in the pinned Streamlit version; if setting it does not push a history entry, find the supported way (e.g. `st.navigation`/`st.switch_page` with query params, or a tiny `components.html` that calls `history.pushState`) and note the choice in the PR. Empty/default filters stay out of the URL.
- [x] **P12.2** _(2026-10-28 nightly: repeatable `retailer` on `/api/products`; sidebar "Magazine" multiselect of the shops with listed products, in the URL as `?retailer=a,b`; slugs no shop has any more are dropped from old links.)_ **Shop filter ("Magazin").** API: `GET /api/products` accepts a repeatable `retailer=<slug>` parameter — only products with an offer from at least one of those retailers; price/retailer-count stats unchanged. UI: a multiselect "Magazine" in the sidebar filters (only retailers that have offers; names, not slugs), kept in the URL like the other filters (P12.1).
- [ ] **P12.3** **Only products sold in several shops (intersection).** API: `common=true` (with P12.2's `retailer`) → only products that have an offer from **every** selected retailer; `common=true` with no retailer selected → products offered by **at least 2** retailers. UI: a toggle "Doar produse comune" next to the shop filter (help text: with shops selected = sold in all of them; otherwise = sold in 2+ shops). Show the result count, and an empty state that explains when nothing overlaps. Add `retailers` as the default sort when the toggle is on (most shops first).
