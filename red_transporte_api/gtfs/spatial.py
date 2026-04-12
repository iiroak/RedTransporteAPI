"""
Geospatial query utilities for GTFS transit data.

Provides proximity searches, bounding-box queries, and basic route
suggestion between two points — all using pure-Python Haversine math.
"""
from __future__ import annotations

from red_transporte_api.gtfs.parser import GTFSData, Stop, Route, haversine


def get_nearby_stops(
    gtfs: GTFSData,
    lat: float,
    lon: float,
    radius_km: float = 0.5,
    limit: int = 20,
) -> list[tuple[Stop, float]]:
    """Find stops within *radius_km* of (lat, lon). Returns (stop, distance_km)."""
    return gtfs.get_nearby_stops(lat, lon, radius_km, limit)


def get_closest_stop(gtfs: GTFSData, lat: float, lon: float) -> tuple[Stop, float] | None:
    """Return the single closest stop to a coordinate, or None."""
    results = gtfs.get_nearby_stops(lat, lon, radius_km=50.0, limit=1)
    return results[0] if results else None


def get_closest_station(
    gtfs: GTFSData, lat: float, lon: float
) -> tuple[Stop, float] | None:
    """Return the closest metro or rail station (route_type 1 or 2)."""
    # Collect stops served by metro/rail routes
    station_ids: set[str] = set()
    for route in gtfs.routes.values():
        if route.route_type in (1, 2):  # metro, rail
            for trip in gtfs.trips.values():
                if trip.route_id == route.route_id:
                    for st in gtfs.stop_times_by_trip.get(trip.trip_id, []):
                        station_ids.add(st.stop_id)

    best: tuple[Stop, float] | None = None
    for sid in station_ids:
        stop = gtfs.stops.get(sid)
        if not stop:
            continue
        dist = haversine(lat, lon, stop.stop_lat, stop.stop_lon)
        if best is None or dist < best[1]:
            best = (stop, dist)
    return best


def get_stops_in_bbox(
    gtfs: GTFSData,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> list[Stop]:
    """Return all stops inside a latitude/longitude bounding box."""
    results: list[Stop] = []
    for stop in gtfs.stops.values():
        if stop.location_type != 0:
            continue
        if min_lat <= stop.stop_lat <= max_lat and min_lon <= stop.stop_lon <= max_lon:
            results.append(stop)
    return results


def get_routes_near_point(
    gtfs: GTFSData,
    lat: float,
    lon: float,
    radius_km: float = 0.3,
) -> list[Route]:
    """Return routes that have at least one stop within radius_km of (lat, lon)."""
    nearby = gtfs.get_nearby_stops(lat, lon, radius_km, limit=200)
    route_ids: set[str] = set()
    for stop, _ in nearby:
        route_ids.update(gtfs._routes_by_stop.get(stop.stop_id, set()))
    return [gtfs.routes[rid] for rid in sorted(route_ids) if rid in gtfs.routes]


def suggest_routes_between(
    gtfs: GTFSData,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    radius_km: float = 0.5,
) -> list[dict]:
    """
    Basic route suggestion: find routes that pass near both origin and destination.

    Returns a list of dicts with route info + the nearest stops at each end.
    """
    routes_near_origin = {
        r.route_id for r in get_routes_near_point(gtfs, from_lat, from_lon, radius_km)
    }
    routes_near_dest = {
        r.route_id for r in get_routes_near_point(gtfs, to_lat, to_lon, radius_km)
    }
    common = routes_near_origin & routes_near_dest

    suggestions = []
    for rid in sorted(common):
        route = gtfs.routes.get(rid)
        if not route:
            continue

        # Find the closest stop to origin and destination on this route
        route_stop_ids = set()
        for trip in gtfs.trips.values():
            if trip.route_id == rid:
                for st in gtfs.stop_times_by_trip.get(trip.trip_id, []):
                    route_stop_ids.add(st.stop_id)

        best_origin: tuple[Stop, float] | None = None
        best_dest: tuple[Stop, float] | None = None
        for sid in route_stop_ids:
            stop = gtfs.stops.get(sid)
            if not stop:
                continue
            d_orig = haversine(from_lat, from_lon, stop.stop_lat, stop.stop_lon)
            d_dest = haversine(to_lat, to_lon, stop.stop_lat, stop.stop_lon)
            if d_orig <= radius_km and (best_origin is None or d_orig < best_origin[1]):
                best_origin = (stop, d_orig)
            if d_dest <= radius_km and (best_dest is None or d_dest < best_dest[1]):
                best_dest = (stop, d_dest)

        if best_origin and best_dest:
            suggestions.append({
                "route_id": route.route_id,
                "short_name": route.route_short_name,
                "long_name": route.route_long_name,
                "mode": route.mode,
                "color": f"#{route.route_color}" if route.route_color else None,
                "board_at": {
                    "stop_id": best_origin[0].stop_id,
                    "stop_name": best_origin[0].clean_name,
                    "distance_m": round(best_origin[1] * 1000),
                },
                "alight_at": {
                    "stop_id": best_dest[0].stop_id,
                    "stop_name": best_dest[0].clean_name,
                    "distance_m": round(best_dest[1] * 1000),
                },
            })

    return suggestions
