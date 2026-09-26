from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import catalog, compare, products

app = FastAPI(title="BeautyCrawler API (MVP)")

# Allow local UI to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # narrow later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(products.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
