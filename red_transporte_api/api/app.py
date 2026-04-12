"""FastAPI application factory and server entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from red_transporte_api.config import API_HOST, API_PORT, VERSION

logger = logging.getLogger(__name__)


def _try_load_gtfs():
    """Try to load GTFS data on startup."""
    from red_transporte_api.gtfs.downloader import get_gtfs_path
    from red_transporte_api.gtfs.parser import GTFSData
    from red_transporte_api.api.deps import set_gtfs

    gtfs_path = get_gtfs_path()
    if gtfs_path:
        logger.info("Loading GTFS from %s", gtfs_path)
        gtfs = GTFSData.from_directory(gtfs_path)
        set_gtfs(gtfs)
        logger.info(
            "GTFS loaded: %d stops, %d routes",
            len(gtfs.stops), len(gtfs.routes),
        )
    else:
        logger.warning(
            "No GTFS data found. Run 'red-transporte gtfs update' to download. "
            "API will start but GTFS-dependent endpoints will return errors."
        )


def create_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    @asynccontextmanager
    async def lifespan(app):
        _try_load_gtfs()
        yield

    app = FastAPI(
        title="RedTransporteAPI",
        description="API unificada para el transporte público de Santiago de Chile — GTFS, iBus y RED",
        version=VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from red_transporte_api.api.routes import system, stops, routes, predictions, spatial, gtfs
    app.include_router(system.router)
    app.include_router(stops.router, prefix="/stops", tags=["Paraderos"])
    app.include_router(routes.router, prefix="/routes", tags=["Recorridos"])
    app.include_router(predictions.router, prefix="/predictions", tags=["Predicciones"])
    app.include_router(spatial.router, tags=["Geoespacial"])
    app.include_router(gtfs.router, prefix="/gtfs", tags=["GTFS"])

    return app


app = create_app()


def run_server():
    import uvicorn
    uvicorn.run(
        "red_transporte_api.api.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    run_server()
