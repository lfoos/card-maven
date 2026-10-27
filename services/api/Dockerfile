# syntax=docker/dockerfile:1.7
# Build from the repository root: docker build -f services/api/Dockerfile .

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so source edits don't invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY packages/card_maven/pyproject.toml packages/card_maven/
COPY services/api/pyproject.toml services/api/
COPY services/workers/pyproject.toml services/workers/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package card-maven-api --no-install-workspace

COPY packages/card_maven packages/card_maven
COPY services/api services/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package card-maven-api --no-editable

FROM python:3.13-slim AS runtime
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY db db
COPY config config
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000/healthz\", timeout=2)"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "card_maven_api.wsgi:app"]
