"""
RED web predictor client — public predictions via www.red.cl JWT flow.

Extracts a JWT token from the "cuando-llega" page and uses it to query
the /predictorPlus/prediccion endpoint for real-time arrival times.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

import httpx

from red_transporte_api.config import RED_WEB_BASE_URL, RED_WEB_PAGE_PATH, RED_WEB_PREDICTION_PATH

logger = logging.getLogger(__name__)


class RedWebClient:
    """Client for the RED web predictor (public, no MITM required)."""

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=RED_WEB_BASE_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
            timeout=timeout,
            follow_redirects=True,
        )
        self._sync_client: httpx.Client | None = None
        self._token: str | None = None
        self._token_exp: int = 0

    @staticmethod
    def _decode_base64_jwt(encoded_value: str) -> str:
        padding = "=" * (-len(encoded_value) % 4)
        decoded = base64.b64decode(encoded_value + padding)
        return decoded.decode("utf-8")

    @staticmethod
    def _jwt_exp(jwt_token: str) -> int:
        try:
            payload_b64 = jwt_token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            payload_raw = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(payload_raw.decode("utf-8"))
            return int(payload.get("exp", 0))
        except Exception:
            return 0

    def _extract_token_from_html(self, html: str) -> str:
        encoded_match = re.search(r"\$jwt\s*=\s*'([^']+)'", html)
        if encoded_match:
            return self._decode_base64_jwt(encoded_match.group(1))

        direct_match = re.search(r"eyJ0eXAiOiJKV1Qi[^\"'\s<]+", html)
        if direct_match:
            return direct_match.group(0)

        url_match = re.search(r"prediccion\?t=([^&\"'\s<]+)", html)
        if url_match:
            return url_match.group(1)

        raise ValueError("Could not extract predictor token from page HTML")

    def _token_needs_refresh(self) -> bool:
        if not self._token:
            return True
        return int(time.time()) >= self._token_exp - 30

    async def refresh_token(self, stop_code: str = "PA121") -> str:
        resp = await self._client.get(RED_WEB_PAGE_PATH, params={"codsimt": stop_code})
        resp.raise_for_status()
        token = self._extract_token_from_html(resp.text)
        self._token = token
        self._token_exp = self._jwt_exp(token)
        return token

    def refresh_token_sync(self, stop_code: str = "PA121") -> str:
        client = self._get_sync_client()
        resp = client.get(RED_WEB_PAGE_PATH, params={"codsimt": stop_code})
        resp.raise_for_status()
        token = self._extract_token_from_html(resp.text)
        self._token = token
        self._token_exp = self._jwt_exp(token)
        return token

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=RED_WEB_BASE_URL,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json,text/plain,*/*",
                },
                timeout=30.0,
                follow_redirects=True,
            )
        return self._sync_client

    async def get_predictions(
        self, stop_code: str, service_code: str = ""
    ) -> dict[str, Any]:
        """Get real-time predictions from RED web predictor (async)."""
        if self._token_needs_refresh():
            await self.refresh_token(stop_code)
        referer = f"{RED_WEB_BASE_URL}{RED_WEB_PAGE_PATH}?codsimt={stop_code}"
        resp = await self._client.get(
            RED_WEB_PREDICTION_PATH,
            params={"t": self._token, "codsimt": stop_code, "codser": service_code},
            headers={"Referer": referer},
        )
        resp.raise_for_status()
        return resp.json()

    def get_predictions_sync(
        self, stop_code: str, service_code: str = ""
    ) -> dict[str, Any]:
        """Get real-time predictions from RED web predictor (sync)."""
        if self._token_needs_refresh():
            self.refresh_token_sync(stop_code)
        client = self._get_sync_client()
        referer = f"{RED_WEB_BASE_URL}{RED_WEB_PAGE_PATH}?codsimt={stop_code}"
        resp = client.get(
            RED_WEB_PREDICTION_PATH,
            params={"t": self._token, "codsimt": stop_code, "codser": service_code},
            headers={"Referer": referer},
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
        if self._sync_client:
            self._sync_client.close()
