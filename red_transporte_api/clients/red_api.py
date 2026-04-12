"""
RED Metropolitana private API client (MITM-discovered endpoints).

This client uses endpoints discovered via MITM capture of the RED mobile app.
It is optional — most functionality works without it via GTFS + iBus + web predictor.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from red_transporte_api.config import API_BASE_URL, DEFAULT_HEADERS

logger = logging.getLogger(__name__)


class RedAPIClient:
    """HTTP client for the RED Metropolitana internal API (requires MITM setup)."""

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        endpoint_map_path: str | Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or dict(DEFAULT_HEADERS)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout,
            follow_redirects=True,
        )
        self._endpoint_map: dict[str, str] = {}
        if endpoint_map_path:
            self._load_endpoint_map(Path(endpoint_map_path))

    def _load_endpoint_map(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Endpoint map not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        self._endpoint_map = {k: v.get("path", v) if isinstance(v, dict) else v for k, v in raw.items()}
        logger.info("Loaded %d endpoint(s) from %s", len(self._endpoint_map), path)

    def configure_endpoints(self, mapping: dict[str, str]) -> None:
        self._endpoint_map = mapping

    def _resolve(self, name: str, fallback: str) -> str:
        return self._endpoint_map.get(name, fallback)

    @property
    def available(self) -> bool:
        return bool(self._endpoint_map)

    async def get_predictions(self, stop_code: str) -> dict[str, Any]:
        path = self._resolve("predictions", f"/stops/{stop_code}/predictions")
        resp = await self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def get_bus_positions(self, service_code: str) -> dict[str, Any]:
        path = self._resolve("bus_positions", f"/routes/{service_code}/buses")
        resp = await self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def get_metro_status(self) -> dict[str, Any]:
        path = self._resolve("metro_status", "/metro/status")
        resp = await self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
