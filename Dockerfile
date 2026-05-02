# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Install dependencies.  No UV_CACHE_DIR needed — image is self-contained after this.
# The /app/.cache/uv default is fine since this layer runs as root.
RUN uv sync --extra api --no-dev --no-editable

# Non-root user for running the server
RUN groupadd --system app && useradd --system --gid app --home /app app
USER app

# Data directory — mount a volume here to persist GTFS and SQLite DB.
# Created owned by app so the running process can write.
RUN mkdir -p /data && chown app:app /data
ENV RED_TRANSPORTE_DATA_DIR=/data

EXPOSE 8000

# GTFS is downloaded on first request if not present.
CMD ["uv", "run", "red-transporte-server"]
