# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Non-root user for running the service
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Install only the api extra (MySQL optional — add --extra mysql to uv sync if needed)
RUN uv sync --extra api --no-dev --no-editable

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Data directory — mount a volume here to persist GTFS cache and SQLite DB
RUN install -d -o app -g app /data
ENV RED_TRANSPORTE_DATA_DIR=/data

EXPOSE 8000

USER app

# GTFS is downloaded on first request when not present; run once before shipping if you want to prewarm:
#   uv run red-transporte gtfs update
CMD ["uv", "run", "red-transporte-server"]
