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
| 2 | eMAG | emag.ro | Marketplace | robots.txt readable from a home IP with our client; audit pending |
| 3 | Sephora | sephora.ro | Beauty chain | robots.txt returned 403 to curl from a home IP; recheck with our client, likely blocked |
| 4 | Douglas | douglas.ro | Beauty chain | robots.txt returned 403 to curl from a home IP; recheck with our client, likely blocked |
| 5 | Makeup.ro | makeup.ro | Beauty e-commerce | robots.txt 200 with our client (202 to curl); audit pending |
| 6 | dm drogerie markt | dm.ro | Drugstore | allowed by robots.txt (sitemap `product-sitemap.xml`, ~11 500 products), but product pages are rendered by JavaScript: the HTML has no product data → needs the optional Playwright path (CLAUDE.md) |
| 7 | Farmacia Tei | farmaciatei.ro | Pharmacy (dermocosmetics) | **not allowed**: robots.txt has a second `User-agent: *` group with `Disallow: /` (only named search/AI bots allowed) — no spider |
| 8 | Dr.Max | drmax.ro | Pharmacy (dermocosmetics) | **blocked**: sitemap answers our client with a Cloudflare challenge — rule 6, no spider |
| 9 | Parfimo | parfimo.ro | Perfume / cosmetics e-commerce | **done** (P3.9): JSON-LD + heading/gallery, ~17 500 products in 7 sitemaps |
| 10 | Elefant | elefant.ro | General e-commerce with beauty section | robots.txt readable with our client (Cloudflare, no challenge on robots); audit pending |
| R | Trendyol, Catena, Esteto, Marionnaud | — | Reserves: audit and add to replace blocked stores | — |

Audit notes (2026-09-27, done locally from a home connection because the nightly cloud
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

## Phase 3 — Retailer spiders

- [~] **P3.1** Retailer audit: see the table above (2026-09-27). Still to audit with our client: eMAG, Sephora, Douglas, Makeup.ro, Elefant, then the reserves. For each allowed and reachable site: note robots.txt rules, sitemaps, whether product JSON-LD is present, and save trimmed product pages as fixtures in `tests/fixtures/<retailer>/` (see `tests/fixtures/parfimo/`).
- [!] **P3.2** _Blocked 2026-09-27: Cloudflare challenges our client (see table). Real Notino pages are kept in `tests/fixtures/notino/` as JSON-LD variant examples._ Spider: Notino
- [ ] **P3.3** Spider: Sephora (after P3.1 recheck; skip and mark `[!]` if blocked)
- [ ] **P3.4** Spider: Douglas (after P3.1 recheck; skip and mark `[!]` if blocked)
- [ ] **P3.5** Spider: Makeup.ro
- [ ] **P3.6** Spider: dm — JavaScript-rendered pages: do this after the plain-HTTP stores, using Playwright behind an optional extra (CLAUDE.md stack table). Tests still run on saved (rendered) fixtures.
- [!] **P3.7** _Not allowed 2026-09-27: robots.txt disallows `/` for all generic bots._ Spider: Farmacia Tei
- [!] **P3.8** _Blocked 2026-09-27: Cloudflare challenge on the sitemap._ Spider: Dr.Max
- [x] **P3.9** Spider: Parfimo (2026-09-27, built and smoke-run locally: 20 pages, 20 offers, 0 errors)
- [ ] **P3.10** Spider: Elefant
- [ ] **P3.11** Spider: eMAG (marketplace: record seller name per offer)
- [x] **P3.12** Crawl CLI: `python -m beautycrawler.crawler run --retailer notino [--limit N]` and `run --all`; writes to DB via P1.3.

Each spider task: parser + fixture tests + discovery (prefer sitemaps) + a `--limit` smoke path. Skip and mark `[!]` if P3.1 says crawling is not allowed or not possible.
Use `src/beautycrawler/crawler/spiders/parfimo.py` + `tests/test_spider_parfimo.py` as the template.
- [ ] **P3.13** Reserve spiders (Trendyol, Catena, Esteto, Marionnaud, …) for each blocked store, same audit rules.

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
