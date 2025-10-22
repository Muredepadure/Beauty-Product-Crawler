#  BeautyCrawler

**BeautyCrawler** is an open-source web crawler and aggregator for beauty and skincare products across online stores.  
It collects product information — such as names, prices, brands, sizes, and images — and displays them in a clean interface with links to the original providers.

---

## 🚀 Features

- 🔍 Crawl and extract products from multiple beauty retailers  
- 🧠 Automatic normalization of brands, sizes, and prices  
- 💄 Beautiful UI for exploring and filtering products  
- ⏱️ Scheduled crawling and price updates  
- 💬 REST API for programmatic access  
- ⚖️ Data deduplication and price history tracking  

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-------------|
| **Language** | Python 🐍 |
| **Crawler** | Scrapy / Playwright / aiohttp |
| **Backend API** | FastAPI |
| **Database** | PostgreSQL + SQLAlchemy |
| **Search** | OpenSearch / Elasticsearch *(optional)* |
| **Scheduler / Queue** | Celery + Redis |
| **UI** | Next.js / Streamlit |
| **Containerization** | Docker + Docker Compose |

---

## 📂 Project Structure
```
beautycrawler/
├── crawler/                    # Crawl jobs, spiders, fetch policies, schedulers
│   ├── spiders/               # Site-specific spiders (one per merchant)
│   ├── pipelines.py           # Normalize, dedupe, persist
│   ├── settings.py            # Scrapy/Playwright settings
│   └── main.py                # CLI entrypoints to run jobs
├── extractors/                 # Parsers & helpers (HTML/JSON-LD → Product models)
├── normalization/              # Brand maps, unit conversion, title cleanup
├── api/                        # FastAPI application
│   ├── main.py                # FastAPI app factory & routes
│   ├── models.py              # Pydantic schemas
│   ├── deps.py                # DI, DB session wiring
│   └── routers/               # /products, /brands, /categories
├── db/                         # Database layer
│   ├── base.py                # SQLAlchemy/SQLModel base
│   ├── models.py              # Product, Offer, Merchant, Category, PriceHistory
│   └── migrations/            # Alembic migrations
├── ui/                         # Next.js or Streamlit app (choose one)
├── infra/                      # Infrastructure & deployment
│   ├── docker/                # Dockerfiles
│   ├── compose/               # docker-compose.yml
│   └── ci/                    # GitHub Actions workflows
├── tests/                      # pytest suites (unit + integration)
├── scripts/                    # Dev scripts (seed, export, backfill)
├── .env.example               # Environment variables template
├── requirements.txt           # Python dependencies (or poetry/uv/pip-tools)
├── pyproject.toml             # Tooling config (ruff/black/mypy) if used
├── alembic.ini                # Alembic configuration
└── README.md
```



---

## ⚙️ Quick Start

```bash
# 1) Clone
git clone https://github.com/<your-username>/beautycrawler.git
cd beautycrawler

# 2) Python env
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3) Install deps
pip install -r requirements.txt

# 4) Configure environment
cp .env.example .env
# Edit DB creds, Redis, Playwright, etc.

# 5) DB setup
alembic upgrade head

# 6) Run API (http://localhost:8000/docs)
uvicorn api.main:app --reload

# 7) Run a crawler job (example)
python crawler/main.py run --spider retailer_x

# 8) (Optional) UI
# Streamlit: streamlit run ui/App.py
# Next.js: cd ui && npm i && npm run dev
