# syntax=docker/dockerfile:1.7
# Build from the repository root: docker build -f analytics/dbt/Dockerfile .

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY analytics/dbt/pyproject.toml analytics/dbt/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project

FROM python:3.13-slim AS runtime
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY analytics/dbt/dbt_project.yml analytics/dbt/profiles.yml ./
COPY analytics/dbt/models models
COPY analytics/dbt/macros macros
COPY analytics/dbt/tests tests
COPY analytics/dbt/bin bin
# The root filesystem is read-only in Kubernetes: dbt writes only under /tmp.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/app DBT_TARGET_PATH=/tmp/dbt/target DBT_LOG_PATH=/tmp/dbt/logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
USER 10001
ENTRYPOINT ["python", "/app/bin/dbt-from-url"]
CMD ["build"]
