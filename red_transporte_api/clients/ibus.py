"""
iBus.cl scraper client — real-time bus stop predictions via m.ibus.cl.

Adapted from iBus.CL-API. Includes an in-memory TTL cache to avoid
hammering the m.ibus.cl service.
"""
from __future__ import annotations

import re
import time
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from red_transporte_api.config import IBUS_URL, IBUS_HEADERS, IBUS_TIMEOUT, IBUS_CACHE_TTL

logger = logging.getLogger(__name__)


def _parse_ibus_html(html: str) -> dict:
    """Parse m.ibus.cl HTML response into structured data."""
    soup = BeautifulSoup(html, "html.parser")

    cabecera = soup.find("table", class_="cabecera4")
    if not cabecera:
        raise ValueError("No se encontró la tabla de cabecera en la respuesta")

    rows = cabecera.find_all("tr")
    paradero_code = ""
    paradero_nombre = ""
    hora = ""

    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 3:
            label = cells[0].get_text(strip=True).lower()
            value = cells[2].get_text(strip=True)
            if "paradero" in label:
                paradero_code = value
            elif "nombre" in label:
                paradero_nombre = value
            elif "hora" in label:
                hora = re.sub(r"\s*hrs\.?\s*$", "", value).strip()

    servicios: list[dict] = []
    tables = soup.find_all("table")
    result_table = None
    for table in tables:
        if table.find("td", class_="menu_respuesta_cabecera"):
            result_table = table
            break

    if result_table:
        data_rows = result_table.find_all("tr")
        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            if row.find("td", class_="menu_respuesta2"):
                i += 1
                continue
            if row.find("td", class_="menu_respuesta_cabecera"):
                i += 1
                continue

            cells = row.find_all("td", class_="menu_respuesta")
            if not cells:
                i += 1
                continue

            first_cell = cells[0]
            has_rowspan = first_cell.get("rowspan") is not None
            has_colspan = len(cells) >= 2 and cells[1].get("colspan") is not None

            if len(cells) == 4:
                servicio_text = first_cell.get_text(strip=True)

                def _parse_distancia(raw: str) -> int:
                    raw = raw.strip()
                    try:
                        return int(raw)
                    except ValueError:
                        return 0

                buses = [{
                    "patente": cells[1].get_text(strip=True),
                    "tiempo_llegada": cells[2].get_text(strip=True),
                    "distancia": _parse_distancia(cells[3].get_text()),
                }]
                if has_rowspan:
                    rowspan_count = int(first_cell["rowspan"])
                    for _ in range(rowspan_count - 1):
                        i += 1
                        if i >= len(data_rows):
                            break
                        next_row = data_rows[i]
                        next_cells = next_row.find_all("td", class_="menu_respuesta")
                        if len(next_cells) == 3:
                            buses.append({
                                "patente": next_cells[0].get_text(strip=True),
                                "tiempo_llegada": next_cells[1].get_text(strip=True),
                                "distancia": _parse_distancia(next_cells[2].get_text()),
                            })
                servicios.append({
                    "servicio": servicio_text,
                    "buses": buses,
                    "mensaje": None,
                })
                i += 1
                continue

            if len(cells) == 2 and has_colspan:
                servicio_text = first_cell.get_text(strip=True)
                mensaje = cells[1].get_text(strip=True)
                servicios.append({
                    "servicio": servicio_text,
                    "buses": [],
                    "mensaje": mensaje,
                })
                i += 1
                continue

            if len(cells) == 1 and first_cell.get("colspan"):
                i += 1
                continue

            i += 1

    return {
        "paradero": {
            "codigo": paradero_code,
            "nombre": paradero_nombre,
            "hora_consulta": hora,
        },
        "servicios": servicios,
    }


class IBusClient:
    """Async iBus.cl scraper with in-memory TTL cache."""

    def __init__(self, cache_ttl: int = IBUS_CACHE_TTL):
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict]] = {}

    def _cache_key(self, codigo: str, servicio: str) -> str:
        return f"{codigo.upper()}|{servicio.upper()}"

    def _get_cached(self, key: str) -> dict | None:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.monotonic() - ts < self._cache_ttl:
                return data
            del self._cache[key]
        return None

    async def get_stop_predictions(
        self, codigo: str, servicio: str = ""
    ) -> dict[str, Any]:
        """
        Query m.ibus.cl for real-time bus arrival info at a stop.

        Args:
            codigo: Stop code (e.g. "PA1", "PH123")
            servicio: Optional service/route filter (e.g. "201", "G37")

        Returns:
            Parsed dict with paradero info and servicios list.
        """
        key = self._cache_key(codigo, servicio)
        cached = self._get_cached(key)
        if cached is not None:
            logger.debug("iBus cache hit: %s", key)
            return cached

        params = {
            "paradero": codigo,
            "servicio": servicio,
            "button": "Consulta Paradero",
        }
        async with httpx.AsyncClient(
            headers=IBUS_HEADERS, timeout=IBUS_TIMEOUT, follow_redirects=False,
        ) as client:
            r = await client.get(IBUS_URL, params=params)

        if r.status_code in (301, 302):
            raise RuntimeError(
                "m.ibus.cl redirigió la solicitud. Posible problema con User-Agent."
            )
        if r.status_code != 200:
            raise RuntimeError(f"m.ibus.cl respondió con código {r.status_code}")
        if not r.text or not r.text.strip():
            raise ValueError("Paradero no encontrado. Verifique el código ingresado.")

        data = _parse_ibus_html(r.text)
        self._cache[key] = (time.monotonic(), data)
        return data

    def get_stop_predictions_sync(
        self, codigo: str, servicio: str = ""
    ) -> dict[str, Any]:
        """Synchronous version of get_stop_predictions."""
        key = self._cache_key(codigo, servicio)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        params = {
            "paradero": codigo,
            "servicio": servicio,
            "button": "Consulta Paradero",
        }
        r = httpx.get(
            IBUS_URL,
            params=params,
            headers=IBUS_HEADERS,
            follow_redirects=False,
            timeout=IBUS_TIMEOUT,
        )
        if r.status_code in (301, 302):
            raise RuntimeError(
                "m.ibus.cl redirigió la solicitud. Posible problema con User-Agent."
            )
        if r.status_code != 200:
            raise RuntimeError(f"m.ibus.cl respondió con código {r.status_code}")
        if not r.text or not r.text.strip():
            raise ValueError("Paradero no encontrado. Verifique el código ingresado.")

        data = _parse_ibus_html(r.text)
        self._cache[key] = (time.monotonic(), data)
        return data
