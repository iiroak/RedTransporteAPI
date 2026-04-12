"""Geospatial auxiliary routes — nearby stops, stations, bounding box, route suggestions, routing."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from red_transporte_api.api.deps import get_gtfs, get_router
from red_transporte_api.gtfs import spatial as geo
from red_transporte_api.gtfs.parser import haversine
from red_transporte_api.gtfs.router import secs_to_human
from red_transporte_api.models import RoutingResponse, RoutingPlan, RoutingLeg, FareDetail

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


@router.get("/routing/plan", response_model=RoutingResponse)
async def plan_route(
    from_lat: float = Query(..., description="Latitud origen"),
    from_lon: float = Query(..., description="Longitud origen"),
    to_lat: float = Query(..., description="Latitud destino"),
    to_lon: float = Query(..., description="Longitud destino"),
    departure_time: str = Query("08:00:00", description="Hora de salida HH:MM:SS"),
    day: str = Query("L", description="Día: L=laboral, S=sábado, D=domingo"),
    max_results: int = Query(3, ge=1, le=5, description="Máximo de alternativas"),
    max_transfers: int = Query(2, ge=0, le=3, description="Máximo de transbordos"),
    fare_type: str = Query("normal", description="Tipo tarifa: normal, estudiante, adulto_mayor"),
):
    """
    Planificar ruta de transporte público entre dos coordenadas (RAPTOR).

    Usa el algoritmo RAPTOR (Round-Based Public Transit Optimized Router):
    - Calcula rutas Pareto-óptimas (tiempo vs transbordos)
    - Tiempos de espera basados en frecuencias reales GTFS
    - Caminata entre paradas cercanas para transbordos
    - Cálculo de tarifa integrada RED (punta/valle/baja)
    - Máximo 2 transbordos en ventana de 120 min (regla RED)
    """
    transit_router = get_router()
    results = transit_router.route(
        from_lat, from_lon, to_lat, to_lon,
        departure_time=departure_time,
        service_day=day,
        max_results=max_results,
        max_transfers=max_transfers,
        fare_type=fare_type,
    )

    plans = []
    for r in results:
        if not r.found:
            continue
        legs = []
        for leg in r.legs:
            legs.append(RoutingLeg(
                mode=leg.mode,
                route_id=leg.route_id,
                route_name=leg.route_name,
                route_color=leg.route_color,
                direction=leg.direction,
                board_stop_id=leg.board_stop_id,
                board_stop_name=leg.board_stop_name,
                alight_stop_id=leg.alight_stop_id,
                alight_stop_name=leg.alight_stop_name,
                num_stops=leg.num_stops,
                duration_secs=leg.duration_secs,
                duration_human=secs_to_human(leg.duration_secs),
                wait_secs=leg.wait_secs,
                walk_distance_m=leg.walk_distance_m,
            ))
        transit_legs = [l for l in legs if l.route_name]
        summary_parts = []
        for tl in transit_legs:
            summary_parts.append(f"{tl.route_name} ({tl.board_stop_name} → {tl.alight_stop_name})")
        summary = " ➜ ".join(summary_parts) if summary_parts else "Caminar"
        if r.transfers > 0:
            summary += f" ({r.transfers} trasbordo{'s' if r.transfers > 1 else ''})"

        plans.append(RoutingPlan(
            found=True,
            total_time_secs=r.total_time_secs,
            total_time_human=r.total_time_human,
            departure_time=r.departure_time,
            arrival_time=r.arrival_time,
            walk_time_secs=r.walk_time_secs,
            ride_time_secs=r.ride_time_secs,
            wait_time_secs=r.wait_time_secs,
            transfers=r.transfers,
            total_walk_m=r.total_walk_m,
            legs=legs,
            fare=FareDetail(
                total=r.fare.total,
                periodo=r.fare.periodo,
                fare_type=r.fare.fare_type,
                breakdown=r.fare.breakdown,
            ),
            origin_stop_id=r.origin_stop_id,
            origin_stop_name=r.origin_stop_name,
            dest_stop_id=r.dest_stop_id,
            dest_stop_name=r.dest_stop_name,
            summary=summary,
        ))

    if not plans:
        return RoutingResponse(
            plans=[], count=0,
            message="No se encontró ruta. Intente ampliar el radio o verificar coordenadas.",
        )

    return RoutingResponse(
        plans=plans, count=len(plans),
        message=f"{len(plans)} alternativa(s) encontrada(s)",
    )
