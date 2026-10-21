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

## 2026-10-21 (nightly, second run) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Every roadmap task is still ticked or blocked/on hold ([!]); PRs #9 and #10 still
have no reviews or comments. The Phase 11 shops are still unreachable from the cloud (no connection).
No empty PR opened.
Tests: not re-run (no code changes).
Next: owner reviews and merges #9 then #10; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner: unchanged (see 2026-10-18). Sixth idle run in a row:
please pause the nightly schedule or add tasks to ROADMAP.md.

## 2026-10-21 (nightly) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Every roadmap task is still ticked or blocked/on hold ([!]); PRs #9 and #10 still
have no reviews or comments, and #10's head is unchanged since the last green CI run. No empty PR opened.
Tests: not re-run (no code changes).
Next: owner reviews and merges #9 then #10; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner: unchanged (see 2026-10-18). Fifth idle run in a row:
please pause the nightly schedule or add tasks to ROADMAP.md.

## 2026-10-20 (nightly, second run) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Every roadmap task is still ticked or blocked/on hold ([!]); PRs #9 and #10 have
no reviews or comments; CI on #10's head is green (checks ✓, postgres ✓). No empty PR opened.
Tests: not re-run (no code changes).
Next: owner reviews and merges #9 then #10; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner: unchanged (see 2026-10-18). Fourth idle run in a row:
please pause the nightly schedule or add tasks to ROADMAP.md.

## 2026-10-20 (nightly) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Same state as the two 2026-10-19 runs: every roadmap task is ticked or
blocked/on hold ([!]), PRs #9 and #10 still have no reviews or comments. No empty PR opened.
- The Phase 11 shops are still unreachable from the cloud environment (connection refused),
  so the live smoke runs remain the owner's.
Tests: not re-run (no code changes).
Next: owner reviews and merges #9 then #10; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner: unchanged (see 2026-10-18). Third idle run in a row:
please pause the nightly schedule or add tasks to ROADMAP.md.

## 2026-10-19 (nightly, second run) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Same state as the earlier 2026-10-19 run: every roadmap task is ticked or
blocked/on hold ([!]), PRs #9 and #10 have no reviews or comments, and CI on #10's head is green.
No empty PR opened; this entry is added to PR #10.
Tests: not re-run (no code changes). CI on PR #10's head: checks ✓, postgres ✓.
Next: owner reviews and merges #9 then #10; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner: unchanged from the entries below (live smoke runs of the five
Phase 11 spiders, Esteto categories, P3/P9 hold). Nightly runs stay idle until one of these
moves: consider pausing the schedule.

## 2026-10-19 (nightly) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10
Done: nothing. Every roadmap task is ticked or on hold/blocked ([!]), and PRs #9 and #10 have
no review comments yet. I added this entry to PR #10 instead of opening an empty PR.
- Re-checked the five new Phase 11 shops: the environment proxy still refuses the connection
  (CONNECT 403), so the live `--limit 10` smoke runs are still not possible from the cloud.
Tests: not re-run locally (no code changes; `pip install -e ".[dev]"` failed in this container
while building the `jstyleson` wheel, a dependency of extruct). CI on PR #10's head is green (checks + postgres).
Next: owner reviews and merges #9 then #10; live smoke runs; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner:
- Still open from 2026-10-18: live smoke runs for profihairshop, probeauty, beautylounge, esteto,
  xpertbeauty (or allow those domains in the cloud environment); Esteto categories/pagination.
- Nightly runs have no work until #9/#10 are reviewed or the P3/P9 hold is lifted: consider
  pausing the schedule or adding tasks.

## 2026-10-18 (nightly) — claude/nightly-2026-10-18-P11.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/10 (builds on #9)
Done:
- CI fix: selectolax 1.0 removed `selectolax.parser.HTMLParser` (PR #9 was red on mypy); switched
  to the lexbor parser. Streamlit 1.66 AppTest returns query params as strings; UI test accepts both.
- P11.1 Profihairshop spider (JSON-LD, products sitemap only; Crawl-delay 10 and apex→www tested).
- P11.2 `ShopifySpider` base + ProBeauty and Beauty Lounge (h1 completes cut-short names).
- P11.3 Esteto spider: walks `/produse-cosmetice` and `/parfumuri` listings (subcategories,
  `?page=N`), no sort/filter URLs, capped.
- P11.4 XpertBeauty spider: custom parser (analytics block, price boxes, EAN from JSON-LD mpn).
- P11.5 Citrika (blocked), Farmacia Tei and Bebe Tei (not allowed) recorded; all shops seeded (17).
- P2.6 (new, found during P11.3): robots.txt matching per RFC 9309; `urllib.robotparser` ignored
  `*`/`$` wildcards and every `User-agent: *` group after the first.
Tests: 800/800 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: owner's live smoke runs of the five new spiders; then whatever the owner unblocks (P3/P9 hold).
Blockers / questions for owner:
- The cloud environment can't reach any of the shops (proxy refuses the connection), so no live
  smoke runs: please run `python -m beautycrawler.crawler run --retailer <slug> --limit 10` for
  profihairshop, probeauty, beautylounge, esteto, xpertbeauty, or allow the domains.
- Esteto: are `/produse-cosmetice` and `/parfumuri` the right categories? Pagination format guessed.
- Profihairshop's Crawl-delay makes a full crawl ~3.6 h; `run --all` runs retailers one after another.

## 2026-10-18 — claude/nightly-2026-10-18-P11-new-shops — (local session with the owner, not a nightly run)
Done:
- Carried over from PR #8 (merged before they were pushed): hide brands without listed products
  (`/api/brands?unlisted=auto`), and the P3.1 audit of eMAG, Elefant, Sephora, Douglas, Makeup.ro.
- Audited the owner's priority shops (Phase 11 in ROADMAP.md): Profihairshop, ProBeauty,
  Beauty Lounge, Esteto, XpertBeauty work; Citrika blocked (Cloudflare); Farmacia Tei and
  Bebe Tei disallow generic bots. Saved trimmed real pages (reviews removed) as fixtures.
Tests: 687/687 passed, lint ✓, format ✓, mypy ✓
Next: P11.1 Profihairshop spider (owner's priority), then P11.2–P11.5.
Blockers / questions for owner: none for Phase 11 (fixtures are committed). Live smoke runs
need the shops' domains in the cloud environment's allowed domains.

## 2026-09-28 — claude/nightly-2026-09-27-P10.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/8
Done: nothing. Every open roadmap task (P3.x, P9.x) is on hold for the owner's data-source decision,
and PR #8 has no review comments yet. I added this entry to PR #8 instead of opening an empty PR.
Tests: not re-run (no code changes). CI on PR #8's head is green (checks + postgres), mergeable.
Next: review and merge PR #8; then whatever the owner unblocks (P9.1 feed importer or P3.x spiders).
Blockers / questions for owner:
- Lift the P3/P9 hold (affiliate feeds vs crawling), or pause the nightly schedule until then.
- Still open from PR #8: hide demo brands in the sidebar after the first crawl? `pack_count` for multipacks?

## 2026-09-27 (nightly) — claude/nightly-2026-09-27-P10.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/8
Done (all of Phase 10, the UI redesign):
- P10.1 theme (.streamlit/config.toml, rose accent, light + dark), shared `ui_style.py`, slim header.
- P10.2 search cards: fixed-ratio image, placeholder, small-caps brand, big price, "la N magazine",
  badges "Reducere"/"Stoc epuizat", equal heights. API: `on_sale` on product summaries.
- P10.3 search bar with icon, grouped sidebar filters + reset, count and sort on one row, empty state.
- P10.4 product page: header, HTML price table (old price struck through, "Vezi în magazin",
  cheapest highlighted, stacks on a phone), themed chart, back link.
- P10.5 seller view: explanation + legend, retailer cards, graded heatmap (fixed "None" cells).
- P10.6 API-down message with the start command, spinners, favicon, "Actualizat la …" footer
  (API: `last_seen_at` on /api/retailers).
- P10.7 `unlisted=auto` on /api/products: demo products vanish from search after the first crawl.
Screenshots (light/dark, desktop/phone) in docs/screenshots/p10.*/.
Tests: 681/681 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: nothing unblocked. Every remaining task (P3.x spiders, P9.x data sources) is on hold for the
owner's data-source decision.
Blockers / questions for owner:
- Lift the P3/P9 hold (affiliate feeds vs crawling) so nightly runs have work again.
- The sidebar brand list still includes demo brands after the first crawl (only products are hidden).
  Hide brands without listed products too?
- Still open from 2026-09-26: `pack_count` column for multipacks.

## 2026-09-27 — claude/nightly-2026-09-27-P3.9-parfimo — (local session with the owner, not a nightly run)
Done:
- P3.1 (partial) retailer audit from a home connection with our own client: Notino and Dr.Max
  blocked by Cloudflare challenges, Farmacia Tei disallows all generic bots in robots.txt,
  dm needs JavaScript (Playwright path), Parfimo works. See the table in ROADMAP.md.
- P3.9 Parfimo spider (JSON-LD + brand from the heading + image from the gallery). Live smoke
  run: 20 pages, 20 offers, 0 errors, 20 new products matched.
- JSON-LD extractor: a variant's own `name`/`image` win over the product's; the product GTIN
  is only used on single-offer products (it was copied to every shade). Titles collapse
  non-breaking spaces. `Spider.is_wanted_sitemap()` hook to skip image/review/blog sitemaps.
- Nightly prompt: end the session after the PR; no follow-up check-ins.
Tests: 626/626 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: Phase 10 (UI redesign), starting with P10.1. Phase 3 spiders and Phase 9 (data
sources) are on hold: the owner is deciding between affiliate product feeds and crawling.
Blockers / questions for owner: still open from 2026-09-26 — `pack_count` column for multipacks.

## 2026-09-27 — claude/nightly-2026-09-26-P3.1 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/6
Done: nothing. Every open roadmap task is P3.x, and P3.1 is still blocked. I added this entry
to PR #6 instead of opening another empty PR.
Tests: not re-run (no code changes; main is unchanged since the last green run).
Next: P3.1 retailer audit, as soon as the retailer domains are reachable.
Blockers / questions for owner:
- Rechecked 2026-09-27: all 10 retailers' robots.txt fail at the environment proxy (CONNECT rejected).
  Allow the retailer domains in the cloud environment's Network access settings, or commit
  fixtures under tests/fixtures/<retailer>/.
- Still open: add a `pack_count` column for multipacks? Is the /api/products page/page_size switch OK?

## 2026-09-26 (second run) — claude/nightly-2026-09-26-P3.1 — PR (see branch)
Done: no roadmap task. Every task not marked [!] is ticked, and all remaining tasks
(P3.1–P3.11) are still blocked.
- Re-checked P3.1: robots.txt requests to all 10 retailer domains fail from this environment
  (no connection, HTTP 000), so the audit and fixtures are still not possible.
- Checked that main (#4 and #5 landed) is healthy on Python 3.12.
- No owner comments on #4/#5, so the open questions below still stand. I did not add
  `pack_count` without an answer.
Tests: 604/604 passed, lint ✓, format ✓, mypy ✓ (src, scripts, tests)
Next: P3.1 as soon as the retailer domains are reachable (or fixtures are committed).
Blockers / questions for owner:
- Nightly runs have nothing left to do until P3.1 is unblocked: allow the 10 retailer domains
  in the environment's Network access settings, or run the audit locally and commit
  fixtures under tests/fixtures/<retailer>/. Consider pausing the schedule until then.
- Still open: add `pack_count` to Product/Offer for multipacks?
- Environment note: the container's default `python` is 3.11. The project needs 3.12
  (`uv venv -p python3.12`).

## 2026-09-26 — claude/nightly-2026-09-26-P4.4 — PR https://github.com/Muredepadure/Beauty-Product-Crawler/pull/5
Builds on #4 (branch claude/nightly-2026-09-25-P0.1, not merged yet).
Done (every non-blocked roadmap task is now ticked):
- P4.4 product matching: EAN exact → same-brand rapidfuzz match with guards (size/EAN
  contradictions excluded; different numbers such as SPF 30/50 = conflict; one-sided variant
  markers such as "Duo+" vs "Duo+M" block auto-merge); uncertain → `match_candidates` review
  table. Fixed a P4.3 bug: clean_title dropped a trailing "+" ("B5+", "SPF 50+").
- P4.5 `python -m beautycrawler.matching run|list|approve|reject`.
- P5.1–P5.5 DB-backed API: search (diacritic-insensitive, aliases, sort, page/page_size),
  product detail (cheapest flagged), history (step series, `days`), retailers, brands,
  seller view /api/compare. Bundled fake JSON data removed.
- P6.1 crawl job report (--summary-json), JSON logs, inactive retailers skipped, --match.
- P6.2 per-retailer crawl interval + `run --due` (hourly cron) + `crawl schedule`.
- P6.3 listings missed by N complete crawls → out of stock (not for --limit/empty crawls).
- P6.4 price-drop detection + /api/price-drops.
- P7.5 (done first, the others build on it) typed API client parsing into the API schemas.
- P7.1–P7.4 Streamlit UI: search cards, product page (price table + step chart), filters
  (brand/category/price/in stock; API gained min_price/max_price/in_stock), seller view.
  UI tested end to end with streamlit AppTest → respx → FastAPI test app.
- P8.1 Dockerfile + docker-compose (db, migrate, api, ui, scheduler). Image built and run
  against Postgres 16 here (compose's postgres pull hit Docker Hub rate limits).
- P8.2 CI `postgres` job; TEST_DATABASE_URL runs DB tests + migrations on Postgres.
- P8.3 final README (API reference, adding a retailer, Docker, config).
Tests: 604/604 passed (SQLite) and 604/604 against local Postgres 16; lint ✓, format ✓,
mypy ✓ (src, scripts, tests). CI green on GitHub except the P8.3 commit (README code
block not ruff-formatted; my local check piped through `tail` and hid the exit code) —
fixed in the next commit.
Next: Phase 3 (P3.1 retailer audit, then spiders) as soon as the network allows it.
Blockers / questions for owner:
- P3.1–P3.11 still blocked: retailer domains unreachable from this environment
  (re-checked tonight: notino, emag, sephora, dm, douglas, makeup all fail). Allow them in
  the environment's network settings, or run the audit locally and commit fixtures under
  tests/fixtures/<retailer>/.
- Multipacks: "2 x 50 ml" offers are never auto-linked or turned into products until
  Product/Offer get a `pack_count` column. OK to add it?
- /api/products pagination changed from limit/offset to page/page_size (roadmap spec).

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
