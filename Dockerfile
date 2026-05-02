# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Install dependencies as root.  Packages are bundled in /app/.venv.
RUN uv sync --extra api --no-dev --no-editable

# Non-root user for running the server
RUN groupadd --system app && useradd --system --gid app --home /app app
USER app

# /data is provided as a Docker named volume at runtime.
# Create the uv cache dir so app can write, and set HOME=/data
# so uv falls back to /data/.cache/uv (matches UV_CACHE_DIR).
RUN mkdir -p /data/.cache/uv && chown app:app /data/.cache/uv
ENV UV_CACHE_DIR=/data/.cache/uv
ENV HOME=/data
ENV RED_TRANSPORTE_DATA_DIR=/data

EXPOSE 8000

# GTFS is downloaded on first request if not present.
# To prewarm: docker run --rm -v red_transporte_data:/data ghcr.io/iiroak/redtransporteapi:latest \
#   uv run red-transporte gtfs update
CMD ["uv", "run", "red-transporte-server"]
