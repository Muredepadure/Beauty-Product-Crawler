# BeautyCrawler

**BeautyCrawler** is a price-comparison crawler for the **Romanian** beauty market.
Type a product (e.g. "La Roche-Posay Effaclar Duo 40ml") and see every tracked Romanian
retailer's current price (RON), stock status and link, plus price history.

> Status: early development. The API currently serves a small bundled demo dataset;
> the database, spiders and normalization are being built phase by phase — see
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
```

After changing models in `src/beautycrawler/db/models.py`, generate a migration with
`alembic revision --autogenerate -m "<what changed>"` and review it; a test fails if models
and migrations drift apart.

### Run the API

```bash
uvicorn beautycrawler.api.main:app --reload --port 8000
```

- http://localhost:8000/healthz → `{"status": "ok"}`
- http://localhost:8000/api/products?q=serum → demo search results
  (params: `q`, `brand`, `category`, `limit` 1–100, `offset`)
- http://localhost:8000/docs → OpenAPI docs

### Run the UI

In a second terminal (API must be running):

```bash
streamlit run ui/App.py            # http://localhost:8501
```

### Checks (same as CI)

```bash
ruff check . && ruff format --check .
mypy src
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
│   │   └── routers/products.py  # /api/products (demo data for now)
│   ├── crawler/                 # spiders go in crawler/spiders/<retailer>.py (Phase 3)
│   ├── db/                      # SQLAlchemy models, engine/session, Alembic migrations
│   ├── data/products.json       # bundled demo dataset
│   └── config.py                # pydantic-settings configuration
├── ui/App.py                    # Streamlit UI
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
