"""Stop-related API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from red_transporte_api.api.deps import get_gtfs
from red_transporte_api.auth.deps import require_access, require_access_for_sources
from red_transporte_api.auth.models import ResourceType
from red_transporte_api.models import StopInfo, ServiceInfo, NearbyStop

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search", response_model=list[dict])
async def search_stops(
    q: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="Texto de búsqueda (código o nombre parcial)",
    ),
    limit: int = Query(10, ge=1, le=100),
    _token=Depends(require_access()),
):
    """Buscar paraderos por nombre o código."""
    gtfs = get_gtfs()
    stops = gtfs.search_stops(q, limit=limit)
    return [
        {
            "stop_id": s.stop_id,
            "stop_name": s.clean_name,
            "latitude": s.stop_lat,
            "longitude": s.stop_lon,
        }
        for s in stops
    ]


@router.get("/{code}", response_model=StopInfo)
async def get_stop(
    code: str = Path(..., min_length=1, max_length=64),
    _token=Depends(require_access()),
):
    """Obtener información de un paradero por su código."""
    gtfs = get_gtfs()
    stop = gtfs.get_stop(code)
    if not stop:
        raise HTTPException(status_code=404, detail=f"Paradero '{code}' no encontrado")
    routes = gtfs.get_routes_at_stop(stop.stop_id)
    return StopInfo(
        stop_id=stop.stop_id,
        stop_name=stop.clean_name,
        stop_full_name=stop.stop_name,
        latitude=stop.stop_lat,
        longitude=stop.stop_lon,
        wheelchair_boarding=bool(stop.wheelchair_boarding),
        services=[
            ServiceInfo(
                route_id=r.route_id,
                short_name=r.route_short_name,
                long_name=r.route_long_name,
                color=f"#{r.route_color}" if r.route_color else None,
                mode=r.mode,
            )
            for r in routes
        ],
        service_count=len(routes),
    )


@router.get("/{code}/predictions")
async def get_stop_predictions(request: Request, code: str = Path(..., min_length=1, max_length=64)):
    """Obtener predicciones en tiempo real para un paradero (iBus + RED web).

    Si el token/carrier no tiene acceso a alguna fuente, esa fuente se omite.
    """
    _record, decisions = require_access_for_sources(
        request,
        [ResourceType.IBUS, ResourceType.RED_WEB],
    )

    results: dict = {"paradero": {"codigo": code}, "servicios": [], "sources": [], "access": {}}

    if decisions[ResourceType.RED_WEB].allowed:
        try:
            from red_transporte_api.api.deps import get_red_web_client
            red_web = get_red_web_client()
            red_data = await red_web.get_predictions(code)
            if red_data:
                results["red_web"] = red_data
                results["sources"].append("red_web")
        except Exception as e:
            logger.debug("RED web predictor failed for %s: %s", code, e)

    if decisions[ResourceType.IBUS].allowed:
        try:
            from red_transporte_api.api.deps import get_ibus_client
            ibus = get_ibus_client()
            ibus_data = await ibus.get_stop_predictions(code)
            if ibus_data:
                results["paradero"] = ibus_data.get("paradero", results["paradero"])
                results["servicios"] = ibus_data.get("servicios", [])
                results["sources"].append("ibus")
        except Exception as e:
            logger.debug("iBus failed for %s: %s", code, e)

    results["access"] = {
        "ibus": decisions[ResourceType.IBUS].allowed,
        "red_web": decisions[ResourceType.RED_WEB].allowed,
    }

    if not results["sources"]:
        allowed_any = any(d.allowed for d in decisions.values())
        if not allowed_any:
            raise HTTPException(
                status_code=403,
                detail="No se tiene acceso a ninguna fuente de predicciones para este paradero",
            )
        raise HTTPException(
            status_code=503,
            detail="Las fuentes de predicciones no están disponibles en este momento",
        )
    return results
