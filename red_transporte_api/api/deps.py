"""FastAPI dependency injection and GTFS runtime lifecycle."""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

from red_transporte_api.config import (
    GTFS_IDLE_UNLOAD_SECONDS,
    GTFS_ROUTER_LAZY_BUILD,
    GTFS_SWEEP_INTERVAL_SECONDS,
)
from red_transporte_api.gtfs.parser import GTFSData
from red_transporte_api.gtfs.router import TransitRouter
from red_transporte_api.gtfs.downloader import ensure_gtfs_path
from red_transporte_api.clients.ibus import IBusClient
from red_transporte_api.clients.red_web import RedWebClient

logger = logging.getLogger(__name__)

_ibus: IBusClient | None = None
_red_web: RedWebClient | None = None


class GTFSRuntimeManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._gtfs: GTFSData | None = None
        self._router: TransitRouter | None = None
        self._last_used = time.monotonic()
        self._stop_event = threading.Event()
        self._sweeper: threading.Thread | None = None

    def start(self) -> None:
        if GTFS_IDLE_UNLOAD_SECONDS <= 0:
            return
        with self._lock:
            if self._sweeper and self._sweeper.is_alive():
                return
            self._stop_event.clear()
            self._sweeper = threading.Thread(
                target=self._sweeper_loop,
                name="gtfs-idle-sweeper",
                daemon=True,
            )
            self._sweeper.start()

    def stop(self) -> None:
        self._stop_event.set()
        sweeper = self._sweeper
        if sweeper and sweeper.is_alive():
            sweeper.join(timeout=2)

    def preload(self) -> None:
        self.get_gtfs()
        if not GTFS_ROUTER_LAZY_BUILD:
            self.get_router()

    def set_gtfs(self, gtfs: GTFSData) -> None:
        with self._lock:
            self._gtfs = gtfs
            if GTFS_ROUTER_LAZY_BUILD:
                self._router = None
            else:
                logger.info("Building transit router...")
                self._router = TransitRouter(gtfs)
                logger.info("Transit router ready")
            self._last_used = time.monotonic()

    def get_status(self) -> dict[str, bool]:
        with self._lock:
            return {
                "gtfs_loaded": self._gtfs is not None,
                "router_loaded": self._router is not None,
            }

    def get_gtfs(self) -> GTFSData:
        with self._lock:
            if self._gtfs is None:
                gtfs_path = ensure_gtfs_path()
                logger.info("Loading GTFS from %s", gtfs_path)
                self._gtfs = GTFSData.from_directory(gtfs_path)
                logger.info(
                    "GTFS loaded: %d stops, %d routes",
                    len(self._gtfs.stops),
                    len(self._gtfs.routes),
                )
            self._last_used = time.monotonic()
            return self._gtfs

    def get_router(self) -> TransitRouter:
        with self._lock:
            gtfs = self.get_gtfs()
            if self._router is None:
                logger.info("Building transit router...")
                self._router = TransitRouter(gtfs)
                logger.info("Transit router ready")
            self._last_used = time.monotonic()
            return self._router

    def maybe_unload_idle(self) -> None:
        if GTFS_IDLE_UNLOAD_SECONDS <= 0:
            return
        with self._lock:
            if self._gtfs is None:
                return
            idle = time.monotonic() - self._last_used
            if idle < GTFS_IDLE_UNLOAD_SECONDS:
                return
            self._router = None
            self._gtfs = None
            logger.info("GTFS unloaded after %ds idle", int(idle))

    def _sweeper_loop(self) -> None:
        interval = max(1, GTFS_SWEEP_INTERVAL_SECONDS)
        while not self._stop_event.wait(interval):
            try:
                self.maybe_unload_idle()
            except Exception:
                logger.exception("GTFS idle sweeper failed")


runtime_manager = GTFSRuntimeManager()


def set_gtfs(gtfs: GTFSData) -> None:
    runtime_manager.set_gtfs(gtfs)


def get_gtfs() -> GTFSData:
    return runtime_manager.get_gtfs()


def get_router() -> TransitRouter:
    return runtime_manager.get_router()


def get_gtfs_runtime_status() -> dict[str, bool]:
    return runtime_manager.get_status()


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
