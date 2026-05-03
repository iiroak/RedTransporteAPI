# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml README.md ./

# Copy source
COPY red_transporte_api/ ./red_transporte_api/

# Install dependencies as root.  Packages are bundled in /app/.venv.
RUN uv sync --extra api --no-dev --no-editable

# Create non-root user and pre-create /data directories with correct ownership.
# This must happen as root (before USER app) so chown works.
# Named volumes inherit build-time ownership on first init;
# the entrypoint also runs mkdir -p as a safety net for existing volumes.
RUN groupadd --system app \
    && useradd --system --gid app --home /app app \
    && mkdir -p /data/.cache/uv \
    && chown -R app:app /data

# Copy and prepare entrypoint (still root at this point)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app

ENV UV_CACHE_DIR=/data/.cache/uv
ENV HOME=/data
ENV RED_TRANSPORTE_DATA_DIR=/data

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
