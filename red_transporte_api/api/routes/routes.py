"""Route-related API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from red_transporte_api.api.deps import get_gtfs
from red_transporte_api.models import RouteInfo, RouteBasic, RouteShape, RouteStopBasic, RouteStopSequence, FrequencySlot

router = APIRouter()


@router.get("", response_model=list[RouteBasic])
async def list_routes(
    mode: str | None = Query(None, description="Filtrar por modo: bus, metro, rail, tram"),
):
    """Listar todos los recorridos disponibles."""
    gtfs = get_gtfs()
    all_routes = gtfs.routes.values()
    if mode:
        all_routes = [r for r in all_routes if r.mode == mode.lower()]
    return [
        RouteBasic(
            route_id=r.route_id,
            short_name=r.route_short_name,
            long_name=r.route_long_name,
            mode=r.mode,
            color=f"#{r.route_color}" if r.route_color else None,
        )
        for r in sorted(all_routes, key=lambda r: r.route_short_name)
    ]


@router.get("/{route_id}", response_model=RouteInfo)
async def get_route(route_id: str):
    """Obtener información detallada de un recorrido."""
    gtfs = get_gtfs()
    route = gtfs.get_route(route_id)
    if not route:
        raise HTTPException(status_code=404, detail=f"Recorrido '{route_id}' no encontrado")

    stops_ida = gtfs.get_stops_on_route(route.route_id, direction=0)
    stops_vuelta = gtfs.get_stops_on_route(route.route_id, direction=1)
    freq_w = gtfs.get_route_frequency(route.route_id, "L")
    freq_s = gtfs.get_route_frequency(route.route_id, "S")
    freq_d = gtfs.get_route_frequency(route.route_id, "D")

    return RouteInfo(
        route_id=route.route_id,
        short_name=route.route_short_name,
        long_name=route.route_long_name,
        color=f"#{route.route_color}" if route.route_color else None,
        mode=route.mode,
        agency=route.agency_id,
        stops_ida=[RouteStopBasic(stop_id=s.stop_id, name=s.clean_name) for s in stops_ida],
        stops_vuelta=[RouteStopBasic(stop_id=s.stop_id, name=s.clean_name) for s in stops_vuelta],
        frequency_weekday=[FrequencySlot(start=f.start_time, end=f.end_time, headway_min=round(f.headway_secs / 60, 1)) for f in freq_w],
        frequency_saturday=[FrequencySlot(start=f.start_time, end=f.end_time, headway_min=round(f.headway_secs / 60, 1)) for f in freq_s],
        frequency_sunday=[FrequencySlot(start=f.start_time, end=f.end_time, headway_min=round(f.headway_secs / 60, 1)) for f in freq_d],
    )


@router.get("/{route_id}/stops", response_model=list[RouteStopSequence])
async def get_route_stops(
    route_id: str,
    direction: int = Query(0, ge=0, le=1, description="0=ida, 1=vuelta"),
):
    """Obtener la lista ordenada de paraderos de un recorrido."""
    gtfs = get_gtfs()
    route = gtfs.get_route(route_id)
    if not route:
        raise HTTPException(status_code=404, detail=f"Recorrido '{route_id}' no encontrado")
    stops = gtfs.get_stops_on_route(route.route_id, direction)
    return [
        RouteStopSequence(
            sequence=i + 1,
            stop_id=s.stop_id,
            stop_name=s.clean_name,
            latitude=s.stop_lat,
            longitude=s.stop_lon,
        )
        for i, s in enumerate(stops)
    ]


@router.get("/{route_id}/shape", response_model=RouteShape)
async def get_route_shape(
    route_id: str,
    direction: int = Query(0, ge=0, le=1),
):
    """Obtener la geometría (shape) de un recorrido en formato GeoJSON-compatible."""
    gtfs = get_gtfs()
    route = gtfs.get_route(route_id)
    if not route:
        raise HTTPException(status_code=404, detail=f"Recorrido '{route_id}' no encontrado")
    points = gtfs.get_route_shape(route.route_id, direction)
    return RouteShape(
        route_id=route.route_id,
        direction=direction,
        point_count=len(points),
        coordinates=[[p.lon, p.lat] for p in points],
    )
