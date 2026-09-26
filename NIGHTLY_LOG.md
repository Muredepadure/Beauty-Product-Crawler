# Nightly log

Newest entry on top. Each nightly run adds one entry:

```
## YYYY-MM-DD — <branch> — PR <link>
Done: <tasks + one-line summary each>
Tests: <passed/total>, lint ✓/✗, mypy ✓/✗
Next: <next task id>
Blockers / questions for owner: <or "none">
```

---

## 2026-09-26 — claude/nightly-2026-09-26-P4.4 — PR (link added when opened)
Builds on #4 (branch claude/nightly-2026-09-25-P0.1, not merged yet).
Done:
- P4.4 product matching: EAN exact → same-brand rapidfuzz match with guards (size/EAN
  contradictions excluded; different numbers such as SPF 30/50 or shade 110/120 = conflict;
  one-sided variant markers such as "Duo+" vs "Duo+M" block auto-merge). Only unambiguous
  matches auto-link; the rest go to the new `match_candidates` review table. Also fixed
  a P4.3 bug: clean_title dropped a trailing "+" ("B5+", "SPF 50+").
- P4.5 `python -m beautycrawler.matching run|list|approve|reject`.
- P5.1 /api/products served from the DB (diacritic-insensitive word search, brand aliases,
  category, sort, page/page_size); bundled fake JSON removed.
- P5.2 /api/products/{id} (offers by price, cheapest flagged).
- P5.3 /api/products/{id}/history (per-offer step series, `days` window).
- P5.4 /api/retailers, /api/brands.
- P5.5 /api/compare?brand= seller view (vs market min/median, retailer positions).
- P6.1 crawl job report (--summary-json), JSON logs, inactive retailers skipped, --match.
- P6.2 per-retailer crawl interval + `run --due` (hourly cron) + `crawl schedule`.
Tests: 492/492 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: P6.3 (stale offers), then P6.4.
Blockers / questions for owner:
- P3.1–P3.11 still blocked: retailer domains are denied by this environment's network
  policy (see the 2026-09-25 entry).
- Multipacks: offers like "2 x 50 ml" are never auto-linked or turned into products
  (they wait in review or stay unmatched) until Product/Offer get a `pack_count` column.
  OK to add it?
- Pagination on /api/products changed from limit/offset to page/page_size (as the
  roadmap specifies); the Streamlit UI was adapted.

## 2026-09-25 — claude/nightly-2026-09-25-P0.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/4
Done:
- P0.1 demo data loaded via importlib.resources (works from any CWD / wheel); deps added.
- P0.2 pyproject.toml (hatchling, `[dev]`/`[ui]` extras, ruff/mypy strict/pytest config); requirements.txt → `-e .[dev]`.
- P0.3 API tests (healthz, search, filters, pagination); pagination params validated (422).
- P0.4 GitHub Actions CI (ruff, format, mypy src/scripts/tests, pytest) — green.
- P0.5 pydantic-settings config + .env.example (delay floor 2 s enforced).
- P0.6 README rewritten to match reality.
- P1.1 SQLAlchemy models (Retailer, Brand, Product, Offer, PriceHistory; bani; SQLite FKs on).
- P1.2 Alembic + initial migration; upgrade/downgrade and models-vs-migrations drift tests.
- P1.3 upsert_offer: history only on price/stock change; stale observations ignored.
- P1.4 idempotent seed script (10 retailers + demo products without prices/EANs).
- P2.1 ScrapedOffer contract (GTIN check digit, integer bani, UTC).
- P2.3 Romanian price parser (done before P2.2, which depends on it).
- P2.2 JSON-LD extractor (graph, variants, AggregateOffer, sale prices, comma decimals).
- P2.4 PoliteFetcher (robots.txt per hop, per-host delay/Crawl-delay, retries, Retry-After, bot-wall → BlockedError).
- P2.5 Spider base + sitemap discovery + registry; JsonLdSpider.
- P3.12 crawl CLI (`python -m beautycrawler.crawler list|run`).
- P4.1 brand alias map, P4.2 size/multipack parser, P4.3 title noise cleanup.
Tests: 359/359 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: P4.4 (product matching + review table); P3.1 once the network allows retailer domains.
Blockers / questions for owner:
- P3.1–P3.11 blocked: this cloud environment's network policy denies the retailer domains
  (proxy CONNECT 403). Allow them in the environment's Network access settings, or run the
  audit locally and commit fixtures under tests/fixtures/<retailer>/.
- Multipacks: parse_size returns a pack count ("2 x 50 ml"), but Product/Offer have no
  column for it yet. Add `pack_count` to the model (with a migration) in P4.4?

## 2026-09-25 — setup
Done: Added CLAUDE.md (rules), ROADMAP.md (phases 0–8, retailer list), this log, and the nightly prompt in docs/NIGHTLY_PROMPT.md.
Next: P0.1
Blockers / questions for owner: none
