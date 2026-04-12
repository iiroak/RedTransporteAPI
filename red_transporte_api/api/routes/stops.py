"""Stop-related API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from red_transporte_api.api.deps import get_gtfs
from red_transporte_api.models import StopInfo, ServiceInfo, NearbyStop

router = APIRouter()


@router.get("/search", response_model=list[dict])
async def search_stops(
    q: str = Query(..., description="Texto de búsqueda (código o nombre parcial)"),
    limit: int = Query(10, ge=1, le=100),
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
async def get_stop(code: str):
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
async def get_stop_predictions(code: str):
    """Obtener predicciones en tiempo real para un paradero (iBus + RED web)."""
    from red_transporte_api.api.deps import get_ibus_client, get_red_web_client

    results: dict = {"paradero": {"codigo": code}, "servicios": [], "sources": []}

    # Try RED web predictor first
    try:
        red_web = get_red_web_client()
        red_data = await red_web.get_predictions(code)
        if red_data:
            results["red_web"] = red_data
            results["sources"].append("red_web")
    except Exception:
        pass

    # Try iBus scraper
    try:
        ibus = get_ibus_client()
        ibus_data = await ibus.get_stop_predictions(code)
        if ibus_data:
            results["paradero"] = ibus_data.get("paradero", results["paradero"])
            results["servicios"] = ibus_data.get("servicios", [])
            results["sources"].append("ibus")
    except Exception:
        pass

    if not results["sources"]:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener predicciones de ninguna fuente",
        )
    return results
