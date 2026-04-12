"""
Unified AI agent tools for RedTransporteAPI.

Provides tools usable by AI agents (OpenAI function calling, LangChain,
Claude tools, etc.) to query Santiago's public transit data. Combines
GTFS offline data, iBus real-time scraping, and RED web predictions.

Usage:
    from red_transporte_api.agent import RedTransporteTools

    tools = RedTransporteTools()

    # Offline (GTFS) — always available
    tools.get_stop_info("PA433")
    tools.search_stops("providencia")
    tools.get_nearby_stops(-33.4372, -70.6506)
    tools.get_closest_station(-33.45, -70.65)
    tools.get_route_info("506")
    tools.list_routes("metro")

    # Online — real-time
    tools.get_predictions("PA433")

    # GTFS management
    tools.update_gtfs()
    tools.get_gtfs_status()
"""
from __future__ import annotations

import logging
from typing import Any

from red_transporte_api.gtfs.parser import GTFSData
from red_transporte_api.gtfs import spatial as geo
from red_transporte_api.gtfs.downloader import (
    get_gtfs_path,
    get_gtfs_status,
    download_latest_gtfs,
)

logger = logging.getLogger(__name__)


def _load_gtfs() -> GTFSData:
    path = get_gtfs_path()
    if path:
        return GTFSData.from_directory(path)
    raise FileNotFoundError(
        "No GTFS data found. Run 'red-transporte gtfs update' to download, "
        "or download manually from https://www.dtpm.cl/index.php/noticias/gtfs-vigente"
    )


class RedTransporteTools:
    """
    Unified AI agent tools for Santiago's RED transit system.

    All methods return dicts/lists suitable for JSON serialization.
    """

    def __init__(self, gtfs: GTFSData | None = None):
        self._gtfs = gtfs or _load_gtfs()
        self._ibus = None
        self._red_web = None

    def _get_ibus(self):
        if self._ibus is None:
            from red_transporte_api.clients.ibus import IBusClient
            self._ibus = IBusClient()
        return self._ibus

    def _get_red_web(self):
        if self._red_web is None:
            from red_transporte_api.clients.red_web import RedWebClient
            self._red_web = RedWebClient()
        return self._red_web

    # ─── GTFS-based tools (offline) ──────────────────────────

    def get_stop_info(self, stop_code: str) -> dict[str, Any]:
        """Get information about a bus stop (paradero)."""
        stop = self._gtfs.get_stop(stop_code)
        if not stop:
            return {"error": f"Paradero '{stop_code}' no encontrado"}
        routes = self._gtfs.get_routes_at_stop(stop.stop_id)
        return {
            "stop_id": stop.stop_id,
            "stop_name": stop.clean_name,
            "stop_full_name": stop.stop_name,
            "latitude": stop.stop_lat,
            "longitude": stop.stop_lon,
            "wheelchair_boarding": bool(stop.wheelchair_boarding),
            "services": [
                {
                    "route_id": r.route_id,
                    "short_name": r.route_short_name,
                    "long_name": r.route_long_name,
                    "color": f"#{r.route_color}" if r.route_color else None,
                    "mode": r.mode,
                }
                for r in routes
            ],
            "service_count": len(routes),
        }

    def search_stops(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for stops by name or code."""
        stops = self._gtfs.search_stops(query, limit=limit)
        return [
            {
                "stop_id": s.stop_id,
                "stop_name": s.clean_name,
                "latitude": s.stop_lat,
                "longitude": s.stop_lon,
            }
            for s in stops
        ]

    def get_nearby_stops(
        self, lat: float, lon: float, radius_km: float = 0.5, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find stops near a location."""
        results = self._gtfs.get_nearby_stops(lat, lon, radius_km, limit)
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

    def get_closest_station(self, lat: float, lon: float) -> dict[str, Any]:
        """Find the closest metro/rail station to a coordinate."""
        result = geo.get_closest_station(self._gtfs, lat, lon)
        if not result:
            return {"error": "No se encontró estación cercana"}
        stop, dist = result
        routes = self._gtfs.get_routes_at_stop(stop.stop_id)
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

    def get_route_info(self, route_id: str) -> dict[str, Any]:
        """Get route details, stops, and frequency info."""
        route = self._gtfs.get_route(route_id)
        if not route:
            return {"error": f"Recorrido '{route_id}' no encontrado"}
        stops_ida = self._gtfs.get_stops_on_route(route.route_id, direction=0)
        stops_vuelta = self._gtfs.get_stops_on_route(route.route_id, direction=1)
        freq_w = self._gtfs.get_route_frequency(route.route_id, "L")
        freq_s = self._gtfs.get_route_frequency(route.route_id, "S")
        freq_d = self._gtfs.get_route_frequency(route.route_id, "D")
        return {
            "route_id": route.route_id,
            "short_name": route.route_short_name,
            "long_name": route.route_long_name,
            "color": f"#{route.route_color}" if route.route_color else None,
            "mode": route.mode,
            "agency": route.agency_id,
            "stops_ida": [{"stop_id": s.stop_id, "name": s.clean_name} for s in stops_ida],
            "stops_vuelta": [{"stop_id": s.stop_id, "name": s.clean_name} for s in stops_vuelta],
            "frequency_weekday": [{"start": f.start_time, "end": f.end_time, "headway_min": round(f.headway_secs / 60, 1)} for f in freq_w],
            "frequency_saturday": [{"start": f.start_time, "end": f.end_time, "headway_min": round(f.headway_secs / 60, 1)} for f in freq_s],
            "frequency_sunday": [{"start": f.start_time, "end": f.end_time, "headway_min": round(f.headway_secs / 60, 1)} for f in freq_d],
        }

    def get_stops_on_route(self, route_id: str, direction: int = 0) -> list[dict[str, Any]]:
        """Get ordered stops on a route."""
        route = self._gtfs.get_route(route_id)
        if not route:
            return [{"error": f"Recorrido '{route_id}' no encontrado"}]
        stops = self._gtfs.get_stops_on_route(route.route_id, direction)
        return [
            {
                "sequence": i + 1,
                "stop_id": s.stop_id,
                "stop_name": s.clean_name,
                "latitude": s.stop_lat,
                "longitude": s.stop_lon,
            }
            for i, s in enumerate(stops)
        ]

    def get_route_shape(self, route_id: str, direction: int = 0) -> dict[str, Any]:
        """Get GeoJSON-compatible route shape."""
        route = self._gtfs.get_route(route_id)
        if not route:
            return {"error": f"Recorrido '{route_id}' no encontrado"}
        points = self._gtfs.get_route_shape(route.route_id, direction)
        return {
            "route_id": route.route_id,
            "direction": direction,
            "point_count": len(points),
            "coordinates": [[p.lon, p.lat] for p in points],
        }

    def list_routes(self, mode: str | None = None) -> list[dict[str, Any]]:
        """List all routes, optionally filtered by mode."""
        routes = list(self._gtfs.routes.values())
        if mode:
            routes = [r for r in routes if r.mode == mode.lower()]
        return [
            {
                "route_id": r.route_id,
                "short_name": r.route_short_name,
                "long_name": r.route_long_name,
                "mode": r.mode,
                "color": f"#{r.route_color}" if r.route_color else None,
            }
            for r in sorted(routes, key=lambda r: r.route_short_name)
        ]

    def get_system_stats(self) -> dict[str, Any]:
        """Get transit system statistics."""
        stops = [s for s in self._gtfs.stops.values() if s.location_type == 0]
        return {
            "total_stops": len(stops),
            "total_routes": len(self._gtfs.routes),
            "total_trips": len(self._gtfs.trips),
            "service_days": list(self._gtfs.calendars.keys()),
            "agencies": list({r.agency_id for r in self._gtfs.routes.values()}),
            "modes": list({r.mode for r in self._gtfs.routes.values()}),
        }

    def suggest_routes(
        self,
        from_lat: float, from_lon: float,
        to_lat: float, to_lon: float,
        radius_km: float = 0.5,
    ) -> dict[str, Any]:
        """Suggest routes connecting two points."""
        suggestions = geo.suggest_routes_between(
            self._gtfs, from_lat, from_lon, to_lat, to_lon, radius_km
        )
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
        }

    # ─── Online tools ────────────────────────────────────────

    def get_predictions(self, stop_code: str) -> dict[str, Any]:
        """Get real-time arrivals (tries RED web predictor, then iBus)."""
        results: dict[str, Any] = {
            "paradero": {"codigo": stop_code},
            "servicios": [],
            "sources": [],
        }

        # Try RED web predictor
        try:
            red_web = self._get_red_web()
            red_data = red_web.get_predictions_sync(stop_code)
            if red_data:
                results["red_web"] = red_data
                results["sources"].append("red_web")
        except Exception as e:
            logger.debug("RED web predictor failed: %s", e)

        # Try iBus
        try:
            ibus = self._get_ibus()
            ibus_data = ibus.get_stop_predictions_sync(stop_code)
            if ibus_data:
                results["paradero"] = ibus_data.get("paradero", results["paradero"])
                results["servicios"] = ibus_data.get("servicios", [])
                results["sources"].append("ibus")
        except Exception as e:
            logger.debug("iBus failed: %s", e)

        if not results["sources"]:
            # Fallback to schedule-based info
            stop_info = self.get_stop_info(stop_code)
            return {
                "error": "No se pudieron obtener predicciones en tiempo real.",
                "fallback": {
                    "nota": "Mostrando información de horarios programados.",
                    "stop": stop_info,
                },
            }
        return results

    # ─── GTFS management ─────────────────────────────────────

    def update_gtfs(self, force: bool = False) -> dict[str, Any]:
        """Download/update GTFS from DTPM."""
        path = download_latest_gtfs(force=force)
        self._gtfs = GTFSData.from_directory(path)
        return {
            "status": "ok",
            "path": str(path),
            "stops": len(self._gtfs.stops),
            "routes": len(self._gtfs.routes),
        }

    def get_gtfs_status_info(self) -> dict[str, Any]:
        """Return GTFS data status."""
        return get_gtfs_status()

    # ─── AI framework integration ────────────────────────────

    def get_tool_definitions(self) -> list[dict]:
        """Get OpenAI-compatible function/tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_stop_info",
                    "description": "Obtener información de un paradero de transporte público en Santiago, Chile. Retorna nombre, coordenadas y servicios.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "stop_code": {"type": "string", "description": "Código del paradero, ej: 'PA433', 'PB1'"}
                        },
                        "required": ["stop_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_stops",
                    "description": "Buscar paraderos por nombre o código.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Texto de búsqueda"},
                            "limit": {"type": "integer", "description": "Máximo de resultados", "default": 10},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_nearby_stops",
                    "description": "Encontrar paraderos cercanos a una coordenada geográfica.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number", "description": "Latitud (ej: -33.4372)"},
                            "lon": {"type": "number", "description": "Longitud (ej: -70.6506)"},
                            "radius_km": {"type": "number", "description": "Radio en km", "default": 0.5},
                            "limit": {"type": "integer", "description": "Máximo de resultados", "default": 10},
                        },
                        "required": ["lat", "lon"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_closest_station",
                    "description": "Encontrar la estación de metro o tren más cercana a una coordenada.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number", "description": "Latitud"},
                            "lon": {"type": "number", "description": "Longitud"},
                        },
                        "required": ["lat", "lon"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_route_info",
                    "description": "Obtener información de un recorrido (paradas, frecuencia, horario).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "route_id": {"type": "string", "description": "ID o nombre corto del recorrido (ej: '506', 'D12')"}
                        },
                        "required": ["route_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stops_on_route",
                    "description": "Obtener lista ordenada de paradas de un recorrido.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "route_id": {"type": "string"},
                            "direction": {"type": "integer", "enum": [0, 1], "description": "0=ida, 1=vuelta"},
                        },
                        "required": ["route_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_route_shape",
                    "description": "Obtener la geometría de un recorrido (coordenadas GeoJSON).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "route_id": {"type": "string"},
                            "direction": {"type": "integer", "enum": [0, 1]},
                        },
                        "required": ["route_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_routes",
                    "description": "Listar recorridos del sistema de transporte público.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["bus", "metro", "rail", "tram"], "description": "Filtrar por modo de transporte"}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_predictions",
                    "description": "Obtener predicciones de llegada en tiempo real para un paradero.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "stop_code": {"type": "string", "description": "Código del paradero"}
                        },
                        "required": ["stop_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_stats",
                    "description": "Obtener estadísticas del sistema de transporte.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_routes",
                    "description": "Sugerir recorridos que conecten dos puntos geográficos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from_lat": {"type": "number"},
                            "from_lon": {"type": "number"},
                            "to_lat": {"type": "number"},
                            "to_lon": {"type": "number"},
                            "radius_km": {"type": "number", "default": 0.5},
                        },
                        "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_gtfs",
                    "description": "Descargar/actualizar datos GTFS desde DTPM.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "force": {"type": "boolean", "description": "Forzar re-descarga", "default": False}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_gtfs_status",
                    "description": "Obtener estado de los datos GTFS locales.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def call_tool(self, tool_name: str, args: dict) -> Any:
        """Dispatch a tool call by name — for AI framework integration."""
        dispatch = {
            "get_stop_info": lambda: self.get_stop_info(args["stop_code"]),
            "search_stops": lambda: self.search_stops(args["query"], args.get("limit", 10)),
            "get_nearby_stops": lambda: self.get_nearby_stops(
                args["lat"], args["lon"], args.get("radius_km", 0.5), args.get("limit", 10)
            ),
            "get_closest_station": lambda: self.get_closest_station(args["lat"], args["lon"]),
            "get_route_info": lambda: self.get_route_info(args["route_id"]),
            "get_stops_on_route": lambda: self.get_stops_on_route(
                args["route_id"], args.get("direction", 0)
            ),
            "get_route_shape": lambda: self.get_route_shape(
                args["route_id"], args.get("direction", 0)
            ),
            "get_predictions": lambda: self.get_predictions(args["stop_code"]),
            "list_routes": lambda: self.list_routes(args.get("mode")),
            "get_system_stats": lambda: self.get_system_stats(),
            "suggest_routes": lambda: self.suggest_routes(
                args["from_lat"], args["from_lon"], args["to_lat"], args["to_lon"],
                args.get("radius_km", 0.5),
            ),
            "update_gtfs": lambda: self.update_gtfs(args.get("force", False)),
            "get_gtfs_status": lambda: self.get_gtfs_status_info(),
        }
        handler = dispatch.get(tool_name)
        if not handler:
            return {"error": f"Tool desconocido: {tool_name}"}
        return handler()
