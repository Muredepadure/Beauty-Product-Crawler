# BeautyCrawler

**BeautyCrawler** is a price-comparison crawler for the **Romanian** beauty market.
Type a product (e.g. "La Roche-Posay Effaclar Duo 40ml") and see every tracked Romanian
retailer's current price (RON), stock status and link, plus price history. Sellers get a
competitor view: how each shop prices a brand against the market.

> Status: the pipeline (crawl → normalize → match → API → UI) is built and tested; the
> per-retailer spiders (Phase 3 in [`ROADMAP.md`](ROADMAP.md)) are still to come, so a
> fresh install contains only seed data. Progress is logged in
> [`NIGHTLY_LOG.md`](NIGHTLY_LOG.md).

---

## Features

- **Polite crawling**: robots.txt checked on every hop, ≥ 2 s per domain, retries with
  backoff, a clear User-Agent, bot walls reported instead of bypassed; sitemap discovery;
  JSON-LD product extraction; Romanian price parsing (`1.234,99 lei`).
- **Normalization**: brand aliases (`LRP`, `L’Oreal` → canonical), package sizes and
  multipacks from titles, promo/gift noise stripped from titles, Romanian diacritics
  (ș/ş, ț/ţ) folded for matching and search.
- **Product matching**: EAN/GTIN first, then a guarded fuzzy match; anything uncertain
  goes to a human review queue instead of being merged.
- **History**: a price-history row on every price/stock change; listings that disappear
  are marked out of stock after N crawls; price-drop detection.
- **API** (FastAPI) and **UI** (Streamlit) for shoppers (search, product page, history
  chart) and sellers (brand/retailer vs market).
- **Operations**: per-retailer crawl intervals driven by one hourly cron line, JSON logs,
  run reports, Docker Compose stack with Postgres.

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 (`src/beautycrawler/`) |
| HTTP fetching | `httpx` (async) |
| Parsing | `selectolax` (HTML), `extruct` (JSON-LD / microdata) |
| Database | SQLAlchemy 2.x + Alembic; SQLite by default, Postgres via `DATABASE_URL` |
| API | FastAPI |
| UI | Streamlit (`ui/`) |
| Scheduling | `crawl run --due` from cron (or the compose `scheduler` service) |
| Tooling | pytest, ruff (lint + format), mypy (strict) |

The authoritative version of this table, and the project rules, live in [`CLAUDE.md`](CLAUDE.md).

---

## Setup

Requires Python 3.12+.

```bash
git clone https://github.com/Muredepadure/Beauty-Product-Crawler.git
cd Beauty-Product-Crawler

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: . .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"            # app + UI + test/lint tools

cp .env.example .env               # optional; every setting has a default
alembic upgrade head               # create the schema (default: SQLite file beautycrawler.db)
python scripts/seed.py             # tracked retailers + a few demo products (idempotent)
```

After changing models in `src/beautycrawler/db/models.py`, generate a migration with
`alembic revision --autogenerate -m "<what changed>"` and review it (autogenerate misses
check constraints); a test fails if models and migrations drift apart.

Or run everything in Docker: see [Run with Docker](#run-with-docker).

---

## Crawling

```bash
python -m beautycrawler.crawler list                          # registered spiders
python -m beautycrawler.crawler run --retailer notino --limit 20
python -m beautycrawler.crawler run --all --match             # crawl, then match offers
python -m beautycrawler.crawler --log-format json run --all --summary-json run.json
```

- Each retailer runs in isolation: a failing site is reported (`FAILED: ...`, exit code 1)
  and the next one still runs.
- Retailers marked inactive in the database (e.g. blocked sites) are skipped without a
  single request, unless `--include-inactive`.
- Offers are upserted; price history gets a row only when price or stock changes.
- After a complete crawl (no `--limit`, at least one offer found), listings it didn't
  see count a miss; after `BEAUTYCRAWLER_STALE_AFTER_RUNS` (default 3) misses in a row
  they are marked out of stock. Seeing the listing again resets the count.
- `--summary-json` writes a run report (per-retailer status, duration, pages, offers,
  errors, misses; totals). `--log-format json` emits one JSON object per log line with
  `event` (`crawl_finished`, `crawl_failed`, `crawl_skipped`) and `retailer`.

### Scheduling

Each retailer has a crawl interval (default 24 h). `run --due` crawls only retailers
whose interval has passed since their last successful crawl (a failed crawl is retried
on the next run), so one hourly cron entry is the whole scheduler:

```bash
python -m beautycrawler.crawler schedule                                  # intervals, last/next crawl (UTC)
python -m beautycrawler.crawler schedule --retailer notino --every-hours 12

# crontab -e  (one line; minute 17 of every hour, any minute works)
17 * * * * cd /srv/beautycrawler && .venv/bin/python -m beautycrawler.crawler --log-format json run --all --due --match >> logs/crawl.jsonl 2>&1
```

### Matching offers to products

```bash
python -m beautycrawler.matching run              # link unmatched offers (EAN, then name)
python -m beautycrawler.matching list             # ambiguous matches waiting for review
python -m beautycrawler.matching approve 12       # offer of candidate #12 -> its product
python -m beautycrawler.matching reject 12 13     # different products; re-match the offer
```

Offers are linked by EAN/GTIN when possible, otherwise by brand + name + size. A name
match is linked automatically only when it is unambiguous (high score, same known size,
no variant-marker difference such as "Duo+" vs "Duo+M", not a multipack, no close
runner-up); everything else waits in the `match_candidates` review table. An offer with
no candidate at all becomes a new product. Rejected pairs are never proposed again.

---

## API

```bash
uvicorn beautycrawler.api.main:app --reload --port 8000     # docs: http://localhost:8000/docs
```

All prices are integer **bani** (1 RON = 100 bani); times are UTC.

| Endpoint | Returns |
|---|---|
| `GET /healthz` | `{"status": "ok"}` |
| `GET /api/products` | Product search. `q` (every word must match name or brand; case/diacritics ignored), `brand` (any alias), `category`, `min_price`/`max_price` (bani, on the lowest in-stock price), `in_stock=true`, `sort` = `name` \| `price_asc` \| `price_desc` \| `retailers`, `page`, `page_size` (1–100) |
| `GET /api/products/{id}` | The product with every retailer's offer: in stock by price first, `is_cheapest` on the lowest in-stock price |
| `GET /api/products/{id}/history` | Price history per offer (`days` window). Points exist only on change: draw steps |
| `GET /api/retailers` | Tracked retailers with offer/product counts (`active` filter) |
| `GET /api/brands` | Brands with product counts (`q`, `page`, `page_size` 1–200) |
| `GET /api/compare?brand=X` | Seller view: each retailer's price per product vs the market min/median, plus each retailer's overall position |
| `GET /api/price-drops` | In-stock listings whose latest change cut the price by ≥ `min_pct` % in the last `hours` |

## UI

```bash
streamlit run ui/App.py            # http://localhost:8501 (the API must be running)
```

- **Caută produse**: search with brand/category/price/stock filters and product cards;
  a product page (`?product=<id>`, shareable) with the price table across retailers
  (cheapest highlighted, links out) and the price-history chart.
- **Comparație prețuri**: pick a brand to see each retailer's position and a
  product-by-retailer grid vs the median; pick a retailer to see where it is over or
  under the market.

The UI talks to the API only through `beautycrawler.ui_client` (`BEAUTYCRAWLER_API_BASE_URL`).

---

## Run with Docker

`docker-compose.yml` runs the whole stack from one image (`Dockerfile`):

| Service | What it does |
|---|---|
| `db` | Postgres 16 (data in the `pgdata` volume) |
| `migrate` | one-shot: `alembic upgrade head` + seed the retailers table |
| `api` | FastAPI on http://localhost:8000 |
| `ui` | Streamlit on http://localhost:8501 (talks to `api`) |
| `scheduler` | hourly `crawl run --all --due --match` (JSON logs) |

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" > .env   # anything but local use
docker compose up --build -d
docker compose logs -f scheduler
docker compose run --rm api python -m beautycrawler.crawler schedule
docker compose run --rm api python -m beautycrawler.matching list
```

`CRAWL_EVERY_SECONDS` (default 3600) sets how often the scheduler wakes up; each
retailer's own interval decides whether it is crawled then.

---

## Adding a new retailer

1. **Check that crawling is allowed.** Read the site's `robots.txt` and terms. If
   product pages are disallowed, or the site needs JavaScript or a bot challenge to show
   prices, don't build a spider: record it in `ROADMAP.md` (CLAUDE.md rules 3 and 6).
2. **Add the retailer** to `RETAILERS` in `src/beautycrawler/db/seed.py` and the table in
   `ROADMAP.md`, then run `python scripts/seed.py`.
3. **Save fixtures**: one or more product pages (and a sitemap excerpt if discovery is
   custom) under `tests/fixtures/<retailer>/`. Tests never fetch live pages.
4. **Write the spider** in `src/beautycrawler/crawler/spiders/<retailer>.py`:

   ```python
   from beautycrawler.crawler.spider import JsonLdSpider, register


   @register
   class NotinoSpider(JsonLdSpider):
       slug = "notino"                       # = Retailer.slug
       name = "Notino"
       base_url = "https://www.notino.ro"

       def is_product_url(self, url: str) -> bool:
           return "/p-" in url               # keep only product pages from the sitemaps
   ```

   `JsonLdSpider` covers sites with complete schema.org JSON-LD. Otherwise subclass
   `Spider` and implement `parse_product(html, url) -> list[ScrapedOffer]` (pure, no
   I/O; `extractors.price.parse_price` turns "1.234,99 lei" into bani), and override
   `discover()` if the sitemaps don't list products. Marketplaces set `seller_name` on
   each offer.
5. **Test** `parse_product` on the fixtures (price in bani, old price, stock, EAN, size,
   brand) and discovery with `respx`-mocked HTTP.
6. **Smoke-run** politely: `python -m beautycrawler.crawler run --retailer <slug> --limit 5`,
   then set its interval with `crawl schedule`.

If a site starts blocking polite requests later, set `is_active = false` on its
retailer row: scheduled crawls then skip it.

---

## Configuration

Settings are read from environment variables or `.env` (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///beautycrawler.db` | SQLAlchemy URL (Postgres: `postgresql+psycopg://...`) |
| `BEAUTYCRAWLER_USER_AGENT` | `BeautyCrawler/0.1 (+repo URL)` | Crawler identity |
| `BEAUTYCRAWLER_REQUEST_DELAY_SECONDS` | `2.0` (minimum 2) | Delay between requests per domain |
| `BEAUTYCRAWLER_REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `BEAUTYCRAWLER_MAX_RETRIES` / `_RETRY_BACKOFF_SECONDS` | `3` / `2.0` | Retry policy |
| `BEAUTYCRAWLER_ROBOTS_CACHE_TTL_SECONDS` | `86400` | robots.txt cache lifetime |
| `BEAUTYCRAWLER_STALE_AFTER_RUNS` | `3` | Complete crawls missing a listing before it's marked out of stock |
| `BEAUTYCRAWLER_API_BASE_URL` | `http://localhost:8000/api` | API URL used by the UI |

---

## Project structure

```
.
├── src/beautycrawler/
│   ├── api/
│   │   ├── main.py              # FastAPI app, /healthz
│   │   ├── deps.py              # DB session dependency
│   │   ├── schemas.py           # response models (shared with the UI client)
│   │   ├── routers/products.py  # /api/products, /{id}, /{id}/history
│   │   ├── routers/catalog.py   # /api/retailers, /api/brands
│   │   ├── routers/compare.py   # /api/compare (seller view)
│   │   └── routers/alerts.py    # /api/price-drops
│   ├── crawler/                 # fetcher, sitemap, Spider base, runner, CLI
│   │   └── spiders/             # one module per retailer (Phase 3)
│   ├── db/                      # models, session, repository, price drops, seed, migrations
│   ├── extractors/              # JSON-LD and Romanian price parsing
│   ├── normalization/           # brand aliases, sizes, title cleanup, text folding
│   ├── matching/                # offer -> product matching + review CLI
│   ├── ui_client.py             # typed API client used by the UI
│   ├── ui_data.py               # display helpers for the UI
│   ├── logs.py                  # text / JSON logging
│   └── config.py                # pydantic-settings configuration
├── ui/App.py                    # Streamlit UI
├── scripts/seed.py              # seed retailers + demo products
├── tests/                       # pytest suite (no network)
├── .github/workflows/ci.yml     # lint, type-check, tests on SQLite and Postgres
├── Dockerfile                   # one image for api, ui, scheduler, migrate
├── docker-compose.yml           # full stack with Postgres
├── alembic.ini                  # Alembic config (URL comes from DATABASE_URL)
├── pyproject.toml               # package metadata, deps, ruff/mypy/pytest config
├── .env.example                 # documented environment variables
├── CLAUDE.md                    # project rules and stack decisions
├── ROADMAP.md                   # task list and target retailers
└── NIGHTLY_LOG.md               # log of nightly development runs
```

---

## Development

Checks (the same as CI):

```bash
ruff check . && ruff format --check .
mypy src scripts tests
pytest -q
```

Tests never touch the network: retailer parsing is tested against saved fixtures, HTTP
is mocked with `respx`, and the UI is run headlessly (`streamlit.testing`) against the
API test app.

CI also runs the suite against Postgres 16. To do the same locally, point
`TEST_DATABASE_URL` at an **empty, disposable** database (its `public` schema is dropped
before each DB test):

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/beautycrawler_test pytest -q
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `uvicorn` / `streamlit` not found | Activate the virtualenv first |
| `ModuleNotFoundError: beautycrawler` | Run `pip install -e ".[dev]"` (no `PYTHONPATH` needed) |
| `no such table` / missing column | Run `alembic upgrade head` |
| UI shows a connection error | Start the API, and check `BEAUTYCRAWLER_API_BASE_URL` / the port |
| Run report lists "bot-protection challenge" errors | The site served a bot wall: mark the retailer inactive, don't work around it |
| PowerShell refuses to activate the venv | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
