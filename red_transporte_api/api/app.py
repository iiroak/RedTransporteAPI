"""FastAPI application factory and server entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from red_transporte_api.config import (
    API_HOST,
    API_PORT,
    CORS_ORIGINS,
    DB_BACKEND,
    DB_URL,
    GTFS_EAGER_LOAD,
    MASTER_TOKEN,
    PUBLIC_API_ENABLED,
    PUBLIC_IP_LIMIT_PER_MINUTE,
    VERSION,
)

logger = logging.getLogger(__name__)


def _init_auth():
    """Initialize auth storage and service."""
    from red_transporte_api.auth.deps import init_auth
    from red_transporte_api.auth.service import AuthService

    if DB_BACKEND == "mysql":
        from red_transporte_api.auth.mysql import MySQLAuthStorage
        storage = MySQLAuthStorage(DB_URL)
    elif DB_BACKEND == "sqlite":
        from red_transporte_api.auth.sqlite import SQLiteAuthStorage
        storage = SQLiteAuthStorage(DB_URL)
    else:
        raise RuntimeError(
            f"RED_TRANSPORTE_DB_BACKEND inválido: {DB_BACKEND!r} "
            "(valores válidos: sqlite, mysql)"
        )

    storage.initialize(
        initial_public_api_enabled=PUBLIC_API_ENABLED,
        initial_public_ip_limit=PUBLIC_IP_LIMIT_PER_MINUTE,
    )
    auth_service = AuthService(storage)
    init_auth(auth_service, MASTER_TOKEN)
    logger.info("Auth system initialized (master token: %s)", "configured" if MASTER_TOKEN else "NOT SET")


def create_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    @asynccontextmanager
    async def lifespan(app):
        from red_transporte_api.api.deps import runtime_manager

        _init_auth()
        runtime_manager.start()
        if GTFS_EAGER_LOAD:
            runtime_manager.preload()
        yield
        runtime_manager.stop()

    app = FastAPI(
        title="RedTransporteAPI",
        description="API unificada para el transporte público de Santiago de Chile — GTFS, iBus y RED",
        version=VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from red_transporte_api.api.routes import admin, system, stops, routes, predictions, spatial, gtfs
    app.include_router(admin.router)
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
        # Proxy headers are handled by _get_client_ip() in auth/deps.py, which
        # verifies the connection IP against RED_TRANSPORTE_TRUSTED_PROXY_IPS
        # before trusting CF-Connecting-IP / X-Forwarded-For. Keeping uvicorn's
        # middleware disabled guarantees request.client is always the real
        # connection IP, so spoofed headers cannot change the rate-limit key.
        proxy_headers=False,
        forwarded_allow_ips="",
    )


if __name__ == "__main__":
    run_server()
