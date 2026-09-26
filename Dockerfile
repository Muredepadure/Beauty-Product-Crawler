# One image for every service (api, ui, scheduler, migrate); docker-compose.yml picks
# the command. Build: docker build -t beautycrawler .
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first (cached while only source changes): install from pyproject with a
# stub package, then replace it with the real source.
COPY pyproject.toml README.md ./
RUN mkdir -p src/beautycrawler && touch src/beautycrawler/__init__.py \
    && pip install ".[ui]" \
    && pip uninstall -y beautycrawler

COPY src ./src
COPY alembic.ini ./
COPY scripts ./scripts
COPY ui ./ui
RUN pip install --no-deps . \
    && useradd --create-home --uid 10001 app
USER app

EXPOSE 8000 8501
CMD ["uvicorn", "beautycrawler.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
