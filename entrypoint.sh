#!/bin/bash
set -e
# Safety net: if this is an existing named volume that pre-dates the build-time
# mkdir, create the uv cache dir so uv can write without errors.
mkdir -p /data/.cache/uv
exec uv run red-transporte-server
