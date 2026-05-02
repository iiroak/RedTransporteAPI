"""Prediction routes — aggregated real-time arrival data from multiple sources."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from red_transporte_api.auth.deps import require_access_for_sources
from red_transporte_api.auth.models import ResourceType
from red_transporte_api.api.deps import get_ibus_client, get_red_web_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{stop_code}")
async def get_predictions(stop_code: str, request: Request):
    """
    Obtener predicciones de llegada agregadas de todas las fuentes disponibles.

    Si el carrier no tiene acceso a alguna fuente, esa fuente se omite.
    """
    _record, decisions = require_access_for_sources(
        request,
        [ResourceType.IBUS, ResourceType.RED_WEB],
    )

    results: dict = {
        "paradero": {"codigo": stop_code},
        "servicios": [],
        "sources": [],
        "access": {},
    }

    if decisions[ResourceType.RED_WEB].allowed:
        try:
            red_web = get_red_web_client()
            red_data = await red_web.get_predictions(stop_code)
            if red_data:
                results["red_web"] = red_data
                results["sources"].append("red_web")
        except Exception as e:
            logger.debug("RED web predictor failed for %s: %s", stop_code, e)

    if decisions[ResourceType.IBUS].allowed:
        try:
            ibus = get_ibus_client()
            ibus_data = await ibus.get_stop_predictions(stop_code)
            if ibus_data:
                results["paradero"] = ibus_data.get("paradero", results["paradero"])
                results["servicios"] = ibus_data.get("servicios", [])
                results["sources"].append("ibus")
        except Exception as e:
            logger.debug("iBus failed for %s: %s", stop_code, e)

    results["access"] = {
        "ibus": decisions[ResourceType.IBUS].allowed,
        "red_web": decisions[ResourceType.RED_WEB].allowed,
    }

    if not results["sources"]:
        raise HTTPException(
            status_code=403,
            detail="No se tiene acceso a ninguna fuente de predicciones",
        )
    return results


@router.get("/{stop_code}/{service}")
async def get_predictions_for_service(stop_code: str, service: str, request: Request):
    """Obtener predicciones filtradas por servicio específico."""
    _record, decisions = require_access_for_sources(
        request,
        [ResourceType.IBUS, ResourceType.RED_WEB],
    )

    results: dict = {
        "paradero": {"codigo": stop_code},
        "servicio_filtro": service,
        "servicios": [],
        "sources": [],
        "access": {},
    }

    if decisions[ResourceType.RED_WEB].allowed:
        try:
            red_web = get_red_web_client()
            red_data = await red_web.get_predictions(stop_code, service)
            if red_data:
                results["red_web"] = red_data
                results["sources"].append("red_web")
        except Exception as e:
            logger.debug("RED web predictor failed for %s/%s: %s", stop_code, service, e)

    if decisions[ResourceType.IBUS].allowed:
        try:
            ibus = get_ibus_client()
            ibus_data = await ibus.get_stop_predictions(stop_code, service)
            if ibus_data:
                results["paradero"] = ibus_data.get("paradero", results["paradero"])
                results["servicios"] = ibus_data.get("servicios", [])
                results["sources"].append("ibus")
        except Exception as e:
            logger.debug("iBus failed for %s/%s: %s", stop_code, service, e)

    results["access"] = {
        "ibus": decisions[ResourceType.IBUS].allowed,
        "red_web": decisions[ResourceType.RED_WEB].allowed,
    }

    if not results["sources"]:
        raise HTTPException(
            status_code=403,
            detail="No se tiene acceso a ninguna fuente de predicciones",
        )
    return results
