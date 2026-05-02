#!/bin/bash
set -e
mkdir -p /data/.cache/uv
exec /app/.venv/bin/red-transporte-server
