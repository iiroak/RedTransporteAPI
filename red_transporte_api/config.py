"""Unified configuration for RedTransporteAPI."""
from __future__ import annotations

import os
from pathlib import Path

# ── Version ───────────────────────────────────────────────────
VERSION = "1.0.0"

# ── Data directory ────────────────────────────────────────────
DATA_DIR = Path(os.getenv("RED_TRANSPORTE_DATA_DIR", Path.home() / ".red_transporte"))
GTFS_DIR = DATA_DIR / "gtfs"

# ── GTFS source ──────────────────────────────────────────────
GTFS_PAGE_URL = "https://www.dtpm.cl/index.php/noticias/gtfs-vigente"
GTFS_METADATA_FILE = GTFS_DIR / "gtfs_metadata.json"

# ── RED app API (MITM-dependent) ─────────────────────────────
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

# ── RED web predictor ────────────────────────────────────────
RED_WEB_BASE_URL = "https://www.red.cl"
RED_WEB_PAGE_PATH = "/planifica-tu-viaje/cuando-llega/"
RED_WEB_PREDICTION_PATH = "/predictorPlus/prediccion"

# ── iBus scraper ─────────────────────────────────────────────
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

# ── API server ───────────────────────────────────────────────
API_HOST = os.getenv("RED_TRANSPORTE_HOST", "0.0.0.0")
API_PORT = int(os.getenv("RED_TRANSPORTE_PORT", "8000"))
