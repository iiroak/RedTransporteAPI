# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Non-root user for running the service
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Data directory — mount a volume here to persist GTFS, SQLite DB, and uv cache
RUN install -d -o app -g app /data
ENV RED_TRANSPORTE_DATA_DIR=/data
ENV UV_CACHE_DIR=/data/.cache/uv

# Install dependencies as root (uv needs to write to UV_CACHE_DIR which is /data)
RUN uv sync --extra api --no-dev --no-editable

# Switch to non-root user for running the server
USER app

EXPOSE 8000

# GTFS is downloaded on first request when not present; run once before shipping if you want to prewarm:
#   docker run --rm -v red_transporte_data:/data ghcr.io/iiroak/redtransporteapi:latest \
#     uv run red-transporte gtfs update
CMD ["uv", "run", "red-transporte-server"]
