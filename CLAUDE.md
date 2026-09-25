# CLAUDE.md

Guidance for Claude (and humans) working in this repository. The nightly agent reads this first.

## Product goal

A price-comparison tool for the **Romanian** beauty market. A user types a product
(e.g. "La Roche-Posay Effaclar Duo 40ml") and sees every tracked Romanian retailer's
current price, stock status and link, plus price history. Two audiences:
shoppers (where is it cheapest?) and sellers (how do competitors price it?).

- Country: Romania only. Currency: RON. Site language: Romanian (normalize diacritics:
  ș/ş, ț/ţ, ă, â, î).
- Retailers: see the table in `ROADMAP.md`.

## Stack (decided — do not swap without a note in ROADMAP.md)

| Concern | Choice |
|---|---|
| Language | Python 3.12, package in `src/beautycrawler/` |
| HTTP fetching | `httpx` (async). Playwright **only** for a retailer that cannot be read without JS, and only behind an optional extra |
| Parsing | `selectolax` for HTML, `extruct` for JSON-LD / microdata |
| DB | SQLAlchemy 2.x + Alembic. SQLite for dev and tests; Postgres supported via `DATABASE_URL` |
| API | FastAPI |
| UI | Streamlit (`ui/`) |
| Scheduling | CLI command run by cron / GitHub Actions / APScheduler. No Celery, Redis or OpenSearch unless the roadmap adds them |
| Tooling | `pytest`, `ruff` (lint + format), `mypy` |

## Commands

```bash
pip install -e ".[dev]"          # once pyproject.toml exists; until then: pip install -r requirements.txt
ruff check . && ruff format --check .
mypy src
pytest -q
```

## Hard rules

1. **Tests never touch the network.** Retailer parsing is tested against saved HTML/JSON
   fixtures in `tests/fixtures/<retailer>/`. HTTP is mocked (`respx` or a fake transport).
2. **Never push red.** Lint, type-check and the full test suite must pass before every push.
3. **Polite crawling.** Respect `robots.txt`, identify with a clear User-Agent, default
   ≥ 2 s delay per domain, retries with backoff, never hammer a site. If a site's
   robots.txt or terms forbid crawling product pages, do not build a spider for it —
   record it in `ROADMAP.md` and move on.
4. **Never commit secrets** (`.env` is gitignored; document variables in `.env.example`).
5. **Never push to `main` directly.** Work on `nightly/*` branches and open pull requests.
6. **Never bypass bot protection** (CAPTCHAs, Cloudflare challenges, fingerprint evasion).
   If a site blocks plain polite requests, mark it blocked and skip it.
7. Keep changes small and focused; one roadmap task per commit series.

## Conventions

- Prices stored as integer **bani** (1 RON = 100 bani) to avoid float errors.
- Every scraped offer records: retailer, URL, title, brand, price, old price (if on sale),
  currency, in-stock flag, EAN/GTIN if present, size + unit, image URL, `scraped_at`.
- One spider module per retailer in `src/beautycrawler/crawler/spiders/<retailer>.py`,
  implementing the common `Spider` interface.
- Type hints everywhere; `mypy` must pass.

## Nightly workflow state

- `ROADMAP.md` — the task list. Tick tasks (`[x]`) when merged-ready.
- `NIGHTLY_LOG.md` — one entry per night: what was done, what's next, blockers.
