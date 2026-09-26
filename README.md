# BeautyCrawler

**BeautyCrawler** is a price-comparison crawler for the **Romanian** beauty market.
Type a product (e.g. "La Roche-Posay Effaclar Duo 40ml") and see every tracked Romanian
retailer's current price (RON), stock status and link, plus price history.

> Status: early development. The API searches the product database (demo products from
> `scripts/seed.py` until retailer spiders exist); features are built phase by phase — see
> [`ROADMAP.md`](ROADMAP.md) and [`NIGHTLY_LOG.md`](NIGHTLY_LOG.md).

---

## Features (planned)

- Crawl product pages from the top Romanian beauty retailers (politely: robots.txt, rate limits)
- Normalize brands, sizes and prices; match the same product across retailers
- Price history and price-drop detection
- REST API (FastAPI) and a Streamlit UI for shoppers and sellers

---

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 (`src/beautycrawler/`) |
| HTTP fetching | `httpx` (async) |
| Parsing | `selectolax` (HTML), `extruct` (JSON-LD / microdata) |
| Database | SQLAlchemy 2.x + Alembic; SQLite by default, Postgres via `DATABASE_URL` |
| API | FastAPI |
| UI | Streamlit (`ui/`) |
| Scheduling | CLI command run by cron / GitHub Actions / APScheduler |
| Tooling | pytest, ruff (lint + format), mypy |

The authoritative version of this table, and the project rules, live in [`CLAUDE.md`](CLAUDE.md).

---

## Quick start

Requires Python 3.12+.

```bash
git clone https://github.com/Muredepadure/Beauty-Product-Crawler.git
cd Beauty-Product-Crawler

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: . .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"            # app + UI + test/lint tools

cp .env.example .env               # optional; every setting has a default
```

Create the database schema (default `DATABASE_URL` is a local SQLite file,
`sqlite:///beautycrawler.db`):

```bash
alembic upgrade head
python scripts/seed.py             # tracked retailers + a few demo products (idempotent)
```

After changing models in `src/beautycrawler/db/models.py`, generate a migration with
`alembic revision --autogenerate -m "<what changed>"` and review it; a test fails if models
and migrations drift apart.

### Run the API

```bash
uvicorn beautycrawler.api.main:app --reload --port 8000
```

- http://localhost:8000/healthz → `{"status": "ok"}`
- http://localhost:8000/api/products?q=effaclar → product search
  (params: `q` words in name/brand, diacritic-insensitive; `brand` any known alias;
  `category`; `sort` = `name` | `price_asc` | `price_desc` | `retailers`;
  `page` ≥ 1; `page_size` 1–100). Prices are integer bani (1 RON = 100 bani).
- http://localhost:8000/api/products/1 → one product with every retailer's offer
  (in stock by price first; `is_cheapest` marks the lowest in-stock price)
- http://localhost:8000/api/products/1/history?days=90 → price history per retailer
  offer (points are recorded on change only: draw them as steps)
- http://localhost:8000/api/retailers → tracked retailers with offer/product counts
- http://localhost:8000/api/brands?q=loreal → brands (paginated: `page`, `page_size` 1–200)
- http://localhost:8000/api/compare?brand=LRP → seller view: each retailer's price per
  product vs the market minimum/median, and each retailer's overall position
- http://localhost:8000/api/price-drops?min_pct=15&hours=24 → in-stock listings whose
  latest price change was a cut of at least 15 % in the last 24 h (biggest first)
- http://localhost:8000/docs → OpenAPI docs

### Run a crawl

```bash
python -m beautycrawler.crawler list                          # registered spiders
python -m beautycrawler.crawler run --retailer notino --limit 20
python -m beautycrawler.crawler run --all
python -m beautycrawler.crawler --log-format json run --all --match --summary-json run.json
```

Each retailer runs in isolation: a failing site is reported (`FAILED: ...`, exit code 1)
and the next one still runs. Retailers marked inactive in the database (e.g. blocked)
are skipped unless `--include-inactive`. `--match` links new offers to products after
the crawl; `--summary-json` writes a machine-readable run report (per-retailer status,
duration, pages, offers, errors; totals); `--log-format json` emits one JSON object per
log line with `event` (`crawl_finished`, `crawl_failed`, `crawl_skipped`) and `retailer`.

Listings a complete crawl (no `--limit`, at least one offer found) doesn't see count a
miss; after `BEAUTYCRAWLER_STALE_AFTER_RUNS` (default 3) misses in a row they are marked
out of stock, with a history row. Seeing the listing again resets the count.

### Schedule crawls

Each retailer has a crawl interval (default 24 h). `run --due` crawls only retailers
whose interval has passed since their last successful crawl (a failed crawl is retried
on the next run), so one hourly cron entry is the whole scheduler:

```bash
python -m beautycrawler.crawler schedule                                  # intervals, last/next crawl
python -m beautycrawler.crawler schedule --retailer notino --every-hours 12

# crontab -e  (one line; minute 17 of every hour, any minute works)
17 * * * * cd /srv/beautycrawler && .venv/bin/python -m beautycrawler.crawler --log-format json run --all --due --match >> logs/crawl.jsonl 2>&1
```

Offers are upserted into the database; price history gets a row only when price or
stock changes. No retailer spiders exist yet (see Phase 3 in `ROADMAP.md`).

### Match offers to products

```bash
python -m beautycrawler.matching run              # link unmatched offers (EAN, then name)
python -m beautycrawler.matching list             # ambiguous matches waiting for review
python -m beautycrawler.matching approve 12       # offer of candidate #12 -> its product
python -m beautycrawler.matching reject 12 13     # different products; re-match the offer
```

Offers are linked by EAN/GTIN when possible, otherwise by brand + name + size. Only
unambiguous name matches are linked automatically; anything uncertain (variant
markers such as "Duo+" vs "Duo+M", unknown size, multipacks, two close candidates)
waits in the `match_candidates` review table.

### Run the UI

In a second terminal (API must be running):

```bash
streamlit run ui/App.py            # http://localhost:8501
```

### Checks (same as CI)

```bash
ruff check . && ruff format --check .
mypy src scripts tests
pytest -q
```

Tests never touch the network; retailer parsing is tested against saved fixtures.

---

## Configuration

Settings are read from environment variables or `.env` (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///beautycrawler.db` | SQLAlchemy URL |
| `BEAUTYCRAWLER_USER_AGENT` | `BeautyCrawler/0.1 (+repo URL)` | Crawler identity |
| `BEAUTYCRAWLER_REQUEST_DELAY_SECONDS` | `2.0` (minimum 2) | Delay between requests per domain |
| `BEAUTYCRAWLER_REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `BEAUTYCRAWLER_MAX_RETRIES` / `_RETRY_BACKOFF_SECONDS` | `3` / `2.0` | Retry policy |
| `BEAUTYCRAWLER_ROBOTS_CACHE_TTL_SECONDS` | `86400` | robots.txt cache lifetime |
| `BEAUTYCRAWLER_API_BASE_URL` | `http://localhost:8000/api` | API URL used by the UI |

---

## Project structure

What exists today:

```
.
├── src/beautycrawler/
│   ├── api/
│   │   ├── main.py              # FastAPI app, /healthz
│   │   ├── deps.py              # DB session dependency
│   │   ├── schemas.py           # response models
│   │   ├── routers/products.py  # /api/products, /{id}, /{id}/history
│   │   ├── routers/catalog.py   # /api/retailers, /api/brands
│   │   ├── routers/compare.py   # /api/compare (seller view)
│   │   └── routers/alerts.py    # /api/price-drops
│   ├── crawler/                 # spiders go in crawler/spiders/<retailer>.py (Phase 3)
│   ├── db/                      # SQLAlchemy models, engine/session, Alembic migrations
│   ├── extractors/              # JSON-LD and Romanian price parsing
│   ├── normalization/           # brand aliases, sizes, title cleanup
│   ├── matching/                # offer -> product matching + review CLI
│   └── config.py                # pydantic-settings configuration
├── ui/App.py                    # Streamlit UI
├── scripts/seed.py              # seed retailers + demo products
├── tests/                       # pytest suite (no network)
├── .github/workflows/ci.yml     # lint, type-check, tests
├── alembic.ini                  # Alembic config (URL comes from DATABASE_URL)
├── pyproject.toml               # package metadata, deps, ruff/mypy/pytest config
├── .env.example                 # documented environment variables
├── CLAUDE.md                    # project rules and stack decisions
├── ROADMAP.md                   # task list and target retailers
└── NIGHTLY_LOG.md               # log of nightly development runs
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `uvicorn` / `streamlit` not found | Activate the virtualenv first |
| `ModuleNotFoundError: beautycrawler` | Run `pip install -e ".[dev]"` (no `PYTHONPATH` needed) |
| UI shows a connection error | Start the API, and check `BEAUTYCRAWLER_API_BASE_URL` / the port |
| PowerShell refuses to activate the venv | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
