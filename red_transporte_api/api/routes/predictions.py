"""Prediction routes — aggregated real-time arrival data from multiple sources."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from red_transporte_api.api.deps import get_ibus_client, get_red_web_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{stop_code}")
async def get_predictions(stop_code: str):
    """
    Obtener predicciones de llegada agregadas de todas las fuentes disponibles.

    Intenta RED web predictor primero (datos estructurados), luego iBus (scraping HTML).
    """
    results: dict = {
        "paradero": {"codigo": stop_code},
        "servicios": [],
        "sources": [],
    }

    # Source 1: RED web predictor (structured JSON, preferred)
    try:
        red_web = get_red_web_client()
        red_data = await red_web.get_predictions(stop_code)
        if red_data:
            results["red_web"] = red_data
            results["sources"].append("red_web")
    except Exception as e:
        logger.debug("RED web predictor failed for %s: %s", stop_code, e)

    # Source 2: iBus scraper (HTML scraping, fallback)
    try:
        ibus = get_ibus_client()
        ibus_data = await ibus.get_stop_predictions(stop_code)
        if ibus_data:
            results["paradero"] = ibus_data.get("paradero", results["paradero"])
            results["servicios"] = ibus_data.get("servicios", [])
            results["sources"].append("ibus")
    except Exception as e:
        logger.debug("iBus failed for %s: %s", stop_code, e)

    if not results["sources"]:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener predicciones de ninguna fuente",
        )
    return results


@router.get("/{stop_code}/{service}")
async def get_predictions_for_service(stop_code: str, service: str):
    """Obtener predicciones filtradas por servicio específico."""
    results: dict = {
        "paradero": {"codigo": stop_code},
        "servicio_filtro": service,
        "servicios": [],
        "sources": [],
    }

    try:
        red_web = get_red_web_client()
        red_data = await red_web.get_predictions(stop_code, service)
        if red_data:
            results["red_web"] = red_data
            results["sources"].append("red_web")
    except Exception as e:
        logger.debug("RED web predictor failed for %s/%s: %s", stop_code, service, e)

    try:
        ibus = get_ibus_client()
        ibus_data = await ibus.get_stop_predictions(stop_code, service)
        if ibus_data:
            results["paradero"] = ibus_data.get("paradero", results["paradero"])
            results["servicios"] = ibus_data.get("servicios", [])
            results["sources"].append("ibus")
    except Exception as e:
        logger.debug("iBus failed for %s/%s: %s", stop_code, service, e)

    if not results["sources"]:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener predicciones de ninguna fuente",
        )
    return results
