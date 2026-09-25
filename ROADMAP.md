# Roadmap

Work top to bottom. Each task is sized for roughly one nightly session. A task is done
when its code, tests and docs are committed and lint/type-check/tests pass.
Mark `[x]` when done, `[~]` when partially done (add a note), `[!]` when blocked (add reason).

## Target retailers (Romania)

Candidate "top 10" by traffic and market position. Task P3.1 verifies each one
(robots.txt, terms, whether product data is readable without JS/bot walls) before a spider is built.

| # | Retailer | Domain | Type | Status |
|---|---|---|---|---|
| 1 | Notino | notino.ro | Beauty e-commerce (market leader online) | to verify |
| 2 | eMAG | emag.ro | Marketplace | to verify |
| 3 | Sephora | sephora.ro | Beauty chain | to verify |
| 4 | Douglas | douglas.ro | Beauty chain | to verify |
| 5 | Makeup.ro | makeup.ro | Beauty e-commerce | to verify |
| 6 | dm drogerie markt | dm.ro | Drugstore | to verify |
| 7 | Farmacia Tei | farmaciatei.ro | Pharmacy (dermocosmetics) | to verify |
| 8 | Dr.Max | drmax.ro | Pharmacy (dermocosmetics) | to verify |
| 9 | Parfimo | parfimo.ro | Perfume / cosmetics e-commerce | to verify |
| 10 | Elefant | elefant.ro | General e-commerce with beauty section | to verify |
| R | Trendyol, Catena, Esteto, Marionnaud | — | Reserves if any above is blocked | — |

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
- [ ] **P1.3** Repository/service layer: upsert offer, append price history only when price or stock changes; unit tests.
- [ ] **P1.4** Seed script (`scripts/seed.py`) that loads the retailers table and a few demo products.

## Phase 2 — Extraction core

- [ ] **P2.1** `ScrapedOffer` Pydantic model (the spider output contract).
- [ ] **P2.2** Generic JSON-LD `Product`/`Offer` extractor (`extractors/jsonld.py`) with fixtures covering: single offer, multiple variants, missing GTIN, price as string with comma decimals.
- [ ] **P2.3** Romanian price parser: "1.234,99 lei", "49,90 RON", "de la 30 lei", old/new price pairs; exhaustive unit tests.
- [ ] **P2.4** Polite HTTP fetcher: robots.txt check (cached), per-domain rate limit, retries with backoff, custom UA, timeout. Tested with `respx`.
- [ ] **P2.5** `Spider` base interface: `discover()` (category/listing/sitemap → product URLs) and `parse_product(html, url) -> ScrapedOffer`.

## Phase 3 — Retailer spiders

- [ ] **P3.1** Retailer audit: for each of the 10 retailers, record in this file robots.txt rules for product pages, sitemap availability, whether JSON-LD is present, and whether plain HTTP works. Update the status column. Save one product page per allowed retailer as a fixture (only if the sandbox has network access; otherwise note it and ask the owner to add fixtures).
- [ ] **P3.2** Spider: Notino
- [ ] **P3.3** Spider: Sephora
- [ ] **P3.4** Spider: Douglas
- [ ] **P3.5** Spider: Makeup.ro
- [ ] **P3.6** Spider: dm
- [ ] **P3.7** Spider: Farmacia Tei
- [ ] **P3.8** Spider: Dr.Max
- [ ] **P3.9** Spider: Parfimo
- [ ] **P3.10** Spider: Elefant
- [ ] **P3.11** Spider: eMAG (marketplace: record seller name per offer)
- [ ] **P3.12** Crawl CLI: `python -m beautycrawler.crawler run --retailer notino [--limit N]` and `run --all`; writes to DB via P1.3.

Each spider task: parser + fixture tests + discovery (prefer sitemaps) + a `--limit` smoke path. Skip and mark `[!]` if P3.1 says crawling is not allowed or not possible.

## Phase 4 — Normalization & matching

- [ ] **P4.1** Brand normalization: alias map (e.g. "L'Oreal Paris" / "L’Oréal" → `L'Oréal Paris`), diacritics/case folding.
- [ ] **P4.2** Size/unit parsing from titles: ml, l, g, kg, buc; multipacks ("2 x 50 ml").
- [ ] **P4.3** Title cleanup: strip retailer noise ("Promo", "-20%", gift mentions).
- [ ] **P4.4** Product matching: 1) EAN/GTIN exact; 2) brand + normalized name + size with `rapidfuzz` threshold; ambiguous matches go to a review table rather than auto-merging. Tests with realistic cross-retailer pairs.
- [ ] **P4.5** Admin CLI to list/approve/reject ambiguous matches.

## Phase 5 — API v1 (DB-backed)

- [ ] **P5.1** Replace JSON file with DB: `GET /api/products?q=&brand=&category=&sort=&page=` (search over normalized name + brand).
- [ ] **P5.2** `GET /api/products/{id}`: all offers across retailers, sorted by price; cheapest flagged.
- [ ] **P5.3** `GET /api/products/{id}/history`: price history per retailer.
- [ ] **P5.4** `GET /api/retailers`, `GET /api/brands`; pagination and response schemas documented in OpenAPI.
- [ ] **P5.5** Seller view: `GET /api/compare?brand=X` — for a brand's products, each retailer's price vs the market minimum/median.

## Phase 6 — Scheduling & freshness

- [ ] **P6.1** `crawl all` job with per-retailer isolation (one failing site doesn't stop others), run summary + structured logs.
- [ ] **P6.2** Scheduling: APScheduler entry point and/or documented cron; configurable frequency per retailer.
- [ ] **P6.3** Mark offers stale/out-of-stock when not seen for N runs.
- [ ] **P6.4** Price-drop detection: query/endpoint for products whose price fell ≥ X% since last run (foundation for alerts).

## Phase 7 — UI (Streamlit)

- [ ] **P7.1** Search page: results as cards with lowest price, number of retailers, image.
- [ ] **P7.2** Product page: price table across retailers (cheapest highlighted, stock, link out) + price-history chart.
- [ ] **P7.3** Filters: brand, category, price range, in-stock only.
- [ ] **P7.4** Competitor view: pick a brand/retailer, see where it's over/under market price.
- [ ] **P7.5** UI talks to the API via a small client module; API base URL from config.

## Phase 8 — Packaging & deployment

- [ ] **P8.1** Dockerfile(s) + `docker-compose.yml` (api, ui, postgres, scheduler).
- [ ] **P8.2** Postgres integration test job in CI (service container).
- [ ] **P8.3** Final README: setup, running crawls, API reference, adding a new retailer.
