"""
CLI for RedTransporteAPI.

Usage:
    red-transporte stop PA433
    red-transporte search "providencia"
    red-transporte nearby -33.45 -70.65
    red-transporte station -33.45 -70.65
    red-transporte route 506
    red-transporte routes --mode bus
    red-transporte predict PA433
    red-transporte gtfs update
    red-transporte gtfs status
    red-transporte server
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any


def _load_gtfs():
    from red_transporte_api.gtfs.downloader import ensure_gtfs_path
    from red_transporte_api.gtfs.parser import GTFSData

    path = ensure_gtfs_path()
    return GTFSData.from_directory(path)


def _print_result(data: Any, as_json: bool = False):
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Try to use rich for nice output
    try:
        from rich import print as rprint
        from rich.json import JSON
        rprint(JSON(json.dumps(data, ensure_ascii=False)))
    except ImportError:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_stop(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.get_stop_info(args.code), args.json)


def cmd_search(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.search_stops(args.query, limit=args.limit), args.json)


def cmd_nearby(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(
        tools.get_nearby_stops(args.lat, args.lon, radius_km=args.radius),
        args.json,
    )


def cmd_station(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.get_closest_station(args.lat, args.lon), args.json)


def cmd_route(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.get_route_info(args.route_id), args.json)


def cmd_routes(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.list_routes(mode=args.mode), args.json)


def cmd_predict(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.get_predictions(args.code), args.json)


def cmd_stats(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(tools.get_system_stats(), args.json)


def cmd_suggest(args):
    from red_transporte_api.agent.tools import RedTransporteTools
    tools = RedTransporteTools(gtfs=_load_gtfs())
    _print_result(
        tools.suggest_routes(args.from_lat, args.from_lon, args.to_lat, args.to_lon, radius_km=args.radius),
        args.json,
    )


def cmd_gtfs(args):
    if args.gtfs_action == "update":
        from red_transporte_api.gtfs.downloader import download_latest_gtfs
        print("Descargando datos GTFS desde DTPM...")
        path = download_latest_gtfs(force=args.force)
        print(f"GTFS descargado y extraído en: {path}")
    elif args.gtfs_action == "status":
        from red_transporte_api.gtfs.downloader import get_gtfs_status
        _print_result(get_gtfs_status(), getattr(args, "json", False))
    else:
        print("Uso: red-transporte gtfs {update|status}", file=sys.stderr)
        sys.exit(1)


def cmd_server(args):
    try:
        from red_transporte_api.api.app import run_server
    except ImportError:
        print(
            "Error: FastAPI no instalado. Instala con: pip install 'red-transporte-api[api]'",
            file=sys.stderr,
        )
        sys.exit(1)
    run_server()


def main():
    parser = argparse.ArgumentParser(
        prog="red-transporte",
        description="RedTransporteAPI — CLI para el transporte público de Santiago de Chile",
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON cruda")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Modo verbose (debug logging)"
    )
    sub = parser.add_subparsers(dest="command")

    # stop
    p = sub.add_parser("stop", help="Info de un paradero")
    p.add_argument("code", help="Código del paradero (ej: PA433)")

    # search
    p = sub.add_parser("search", help="Buscar paraderos")
    p.add_argument("query", help="Texto de búsqueda")
    p.add_argument("--limit", type=int, default=10)

    # nearby
    p = sub.add_parser("nearby", help="Paraderos cercanos")
    p.add_argument("lat", type=float, help="Latitud")
    p.add_argument("lon", type=float, help="Longitud")
    p.add_argument("--radius", type=float, default=0.5, help="Radio en km")

    # station
    p = sub.add_parser("station", help="Estación de metro/tren más cercana")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)

    # route
    p = sub.add_parser("route", help="Info de un recorrido")
    p.add_argument("route_id", help="ID o nombre corto del recorrido")

    # routes
    p = sub.add_parser("routes", help="Listar recorridos")
    p.add_argument("--mode", choices=["bus", "metro", "rail", "tram"], default=None)

    # predict
    p = sub.add_parser("predict", help="Predicciones en tiempo real")
    p.add_argument("code", help="Código del paradero")

    # stats
    sub.add_parser("stats", help="Estadísticas del sistema")

    # suggest
    p = sub.add_parser("suggest", help="Sugerir recorridos entre dos puntos")
    p.add_argument("from_lat", type=float)
    p.add_argument("from_lon", type=float)
    p.add_argument("to_lat", type=float)
    p.add_argument("to_lon", type=float)
    p.add_argument("--radius", type=float, default=0.5)

    # gtfs
    p = sub.add_parser("gtfs", help="Gestión de datos GTFS")
    gsub = p.add_subparsers(dest="gtfs_action")
    pu = gsub.add_parser("update", help="Descargar/actualizar GTFS desde DTPM")
    pu.add_argument("--force", action="store_true", help="Forzar re-descarga")
    gsub.add_parser("status", help="Estado de los datos GTFS locales")

    # server
    sub.add_parser("server", help="Iniciar servidor API HTTP")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "stop": cmd_stop,
        "search": cmd_search,
        "nearby": cmd_nearby,
        "station": cmd_station,
        "route": cmd_route,
        "routes": cmd_routes,
        "predict": cmd_predict,
        "stats": cmd_stats,
        "suggest": cmd_suggest,
        "gtfs": cmd_gtfs,
        "server": cmd_server,
    }
    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
