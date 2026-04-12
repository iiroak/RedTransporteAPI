"""FastAPI dependency injection — shared instances of GTFSData and clients."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

from red_transporte_api.gtfs.parser import GTFSData
from red_transporte_api.gtfs.router import TransitRouter
from red_transporte_api.clients.ibus import IBusClient
from red_transporte_api.clients.red_web import RedWebClient

logger = logging.getLogger(__name__)

# Module-level singletons (set during app lifespan)
_gtfs: GTFSData | None = None
_router: TransitRouter | None = None
_ibus: IBusClient | None = None
_red_web: RedWebClient | None = None


def set_gtfs(gtfs: GTFSData) -> None:
    global _gtfs, _router
    _gtfs = gtfs
    logger.info("Building transit router...")
    _router = TransitRouter(gtfs)
    logger.info("Transit router ready")


def get_gtfs() -> GTFSData:
    if _gtfs is None:
        raise RuntimeError(
            "GTFS data not loaded. Run 'red-transporte gtfs update' first."
        )
    return _gtfs


def get_router() -> TransitRouter:
    if _router is None:
        raise RuntimeError(
            "Transit router not initialized. Load GTFS data first."
        )
    return _router


def get_ibus_client() -> IBusClient:
    global _ibus
    if _ibus is None:
        _ibus = IBusClient()
    return _ibus


def get_red_web_client() -> RedWebClient:
    global _red_web
    if _red_web is None:
        _red_web = RedWebClient()
    return _red_web
