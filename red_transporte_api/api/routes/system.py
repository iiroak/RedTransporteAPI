"""System routes — root, health, stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from red_transporte_api.auth.deps import require_access
from red_transporte_api.config import VERSION
from red_transporte_api.models import APIInfo, HealthCheck, SystemStats
from red_transporte_api.api.deps import get_gtfs, get_gtfs_runtime_status

router = APIRouter()


@router.get("/health", response_model=HealthCheck, tags=["Sistema"])
async def health():
    status = get_gtfs_runtime_status()
    return HealthCheck(version=VERSION, gtfs_loaded=status["gtfs_loaded"])


@router.get("/", response_model=APIInfo, tags=["Sistema"])
async def root():
    return APIInfo(version=VERSION)


@router.get("/stats", response_model=SystemStats, tags=["Sistema"])
async def stats(_token=Depends(require_access())):
    gtfs = get_gtfs()
    stops = [s for s in gtfs.stops.values() if s.location_type == 0]
    return SystemStats(
        total_stops=len(stops),
        total_routes=len(gtfs.routes),
        total_trips=len(gtfs.trips),
        service_days=list(gtfs.calendars.keys()),
        agencies=list({r.agency_id for r in gtfs.routes.values()}),
        modes=list({r.mode for r in gtfs.routes.values()}),
    )
