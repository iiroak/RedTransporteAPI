"""Geospatial auxiliary routes — nearby stops, stations, bounding box, route suggestions."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from red_transporte_api.api.deps import get_gtfs
from red_transporte_api.gtfs import spatial as geo
from red_transporte_api.gtfs.parser import haversine

router = APIRouter()


@router.get("/nearby/stops")
async def nearby_stops(
    lat: float = Query(..., description="Latitud (ej: -33.4372)"),
    lon: float = Query(..., description="Longitud (ej: -70.6506)"),
    radius: float = Query(0.5, description="Radio en km"),
    limit: int = Query(20, ge=1, le=100),
):
    """Encontrar paraderos dentro de un radio desde una coordenada."""
    gtfs = get_gtfs()
    results = geo.get_nearby_stops(gtfs, lat, lon, radius, limit)
    return [
        {
            "stop_id": stop.stop_id,
            "stop_name": stop.clean_name,
            "latitude": stop.stop_lat,
            "longitude": stop.stop_lon,
            "distance_m": round(dist * 1000),
        }
        for stop, dist in results
    ]


@router.get("/nearby/station")
async def nearest_station(
    lat: float = Query(..., description="Latitud"),
    lon: float = Query(..., description="Longitud"),
):
    """Encontrar la estación de metro/tren más cercana."""
    gtfs = get_gtfs()
    result = geo.get_closest_station(gtfs, lat, lon)
    if not result:
        raise HTTPException(status_code=404, detail="No se encontró estación cercana")
    stop, dist = result
    routes = gtfs.get_routes_at_stop(stop.stop_id)
    return {
        "stop_id": stop.stop_id,
        "stop_name": stop.clean_name,
        "latitude": stop.stop_lat,
        "longitude": stop.stop_lon,
        "distance_m": round(dist * 1000),
        "services": [
            {
                "route_id": r.route_id,
                "short_name": r.route_short_name,
                "mode": r.mode,
            }
            for r in routes
            if r.route_type in (1, 2)
        ],
    }


@router.get("/nearby/routes")
async def routes_near_point(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: float = Query(0.3, description="Radio en km"),
):
    """Encontrar recorridos que pasan cerca de una coordenada."""
    gtfs = get_gtfs()
    routes = geo.get_routes_near_point(gtfs, lat, lon, radius)
    return [
        {
            "route_id": r.route_id,
            "short_name": r.route_short_name,
            "long_name": r.route_long_name,
            "mode": r.mode,
            "color": f"#{r.route_color}" if r.route_color else None,
        }
        for r in routes
    ]


@router.get("/bbox/stops")
async def stops_in_bbox(
    min_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lat: float = Query(...),
    max_lon: float = Query(...),
):
    """Obtener paraderos dentro de un bounding box."""
    gtfs = get_gtfs()
    stops = geo.get_stops_in_bbox(gtfs, min_lat, min_lon, max_lat, max_lon)
    return [
        {
            "stop_id": s.stop_id,
            "stop_name": s.clean_name,
            "latitude": s.stop_lat,
            "longitude": s.stop_lon,
        }
        for s in stops
    ]


@router.get("/routing/suggest")
async def suggest_routes(
    from_lat: float = Query(..., description="Latitud origen"),
    from_lon: float = Query(..., description="Longitud origen"),
    to_lat: float = Query(..., description="Latitud destino"),
    to_lon: float = Query(..., description="Longitud destino"),
    radius: float = Query(0.5, description="Radio de búsqueda en km"),
):
    """
    Sugerir recorridos que conecten dos puntos.

    Busca recorridos que tengan paraderos cerca del origen y del destino.
    """
    gtfs = get_gtfs()
    suggestions = geo.suggest_routes_between(gtfs, from_lat, from_lon, to_lat, to_lon, radius)
    if not suggestions:
        return {
            "suggestions": [],
            "message": "No se encontraron recorridos directos entre los puntos. Intente aumentar el radio.",
        }
    return {"suggestions": suggestions, "count": len(suggestions)}
