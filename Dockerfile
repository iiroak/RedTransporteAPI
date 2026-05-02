# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Install dependencies.  uv creates ~/.cache/uv inside /app as root,
# which is fine since this layer only runs at build time.
# All needed packages are installed in /app/.venv and bundled in the image.
RUN uv sync --extra api --no-dev --no-editable

# Non-root user for running the server
RUN groupadd --system app && useradd --system --gid app --home /app app
USER app

# /data is provided as a Docker volume at runtime.
# The app user can write to it for the SQLite DB and GTFS cache.
# Tell uv to use /data for its runtime cache so app can write there.
# (packages are already in /app/.venv, so no re-download needed)
ENV UV_CACHE_DIR=/data/.cache/uv
ENV RED_TRANSPORTE_DATA_DIR=/data

EXPOSE 8000

# GTFS is downloaded on first request if not present.
# To prewarm: docker run --rm -v red_transporte_data:/data ghcr.io/iiroak/redtransporteapi:latest \
#   uv run red-transporte gtfs update
CMD ["uv", "run", "red-transporte-server"]
