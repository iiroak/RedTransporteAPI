"""Unified configuration for RedTransporteAPI."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VERSION = "1.0.0"

DATA_DIR = Path(os.getenv("RED_TRANSPORTE_DATA_DIR", Path.home() / ".red_transporte"))
GTFS_DIR = DATA_DIR / "gtfs"

GTFS_PAGE_URL = "https://www.dtpm.cl/index.php/noticias/gtfs-vigente"
GTFS_METADATA_FILE = GTFS_DIR / "gtfs_metadata.json"

API_BASE_URL = os.getenv("RED_API_BASE_URL", "https://appred.tstgo.cl")
API_QA_URL = "https://appredqa.dtpmetropolitano.cl"
MAP_TILE_URL = "https://mapasred.tstgo.cl"

APP_ID = "9d756ff1-bd35-4edb-96df-ecbda9843022"
DEFAULT_HEADERS = {
    "User-Agent": "Dart/3.3 (dart:io)",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-App-Id": APP_ID,
}

RED_WEB_BASE_URL = "https://www.red.cl"
RED_WEB_PAGE_PATH = "/planifica-tu-viaje/cuando-llega/"
RED_WEB_PREDICTION_PATH = "/predictorPlus/prediccion"

IBUS_URL = os.getenv("RED_IBUS_URL", "http://m.ibus.cl/Servlet")
IBUS_TIMEOUT = float(os.getenv("RED_IBUS_TIMEOUT", "15"))
IBUS_CACHE_TTL = int(os.getenv("RED_IBUS_CACHE_TTL", "30"))
IBUS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
    "Connection": "keep-alive",
}

API_HOST = os.getenv("RED_TRANSPORTE_HOST", "0.0.0.0")
API_PORT = int(os.getenv("RED_TRANSPORTE_PORT", "8000"))

# GTFS runtime lifecycle
# Option 1 (min RAM): lazy load + idle unload by default.
GTFS_EAGER_LOAD = os.getenv("RED_TRANSPORTE_GTFS_EAGER_LOAD", "false").lower() in ("true", "1", "yes")
GTFS_IDLE_UNLOAD_SECONDS = int(os.getenv("RED_TRANSPORTE_GTFS_IDLE_UNLOAD_SECONDS", "900"))
GTFS_ROUTER_LAZY_BUILD = os.getenv("RED_TRANSPORTE_GTFS_ROUTER_LAZY_BUILD", "true").lower() in ("true", "1", "yes")
GTFS_SWEEP_INTERVAL_SECONDS = int(os.getenv("RED_TRANSPORTE_GTFS_SWEEP_INTERVAL_SECONDS", "60"))

DB_BACKEND = os.getenv("RED_TRANSPORTE_DB_BACKEND", "sqlite")
DB_URL = os.getenv("RED_TRANSPORTE_DB_URL", str(DATA_DIR / "red_transporte.db"))

MASTER_TOKEN = os.getenv("RED_TRANSPORTE_MASTER_TOKEN", "")

PUBLIC_API_ENABLED = os.getenv("RED_TRANSPORTE_PUBLIC_API", "true").lower() in ("true", "1", "yes")
PUBLIC_IP_LIMIT_PER_MINUTE = int(os.getenv("RED_TRANSPORTE_PUBLIC_IP_RPM", "20"))

# When True, the first IP in X-Forwarded-For is trusted for rate limiting.
# Only enable when the service runs behind a known reverse proxy.
TRUST_PROXY = os.getenv("RED_TRANSPORTE_TRUST_PROXY", "false").lower() in ("true", "1", "yes")

# Comma-separated list of allowed CORS origins.  Use "*" to allow all origins.
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("RED_TRANSPORTE_CORS_ORIGINS", "*").split(",")
    if o.strip()
]
