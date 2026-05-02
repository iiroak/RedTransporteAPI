"""GTFS management routes — update, status."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from red_transporte_api.auth.deps import get_auth_service, require_access, require_master_token
from red_transporte_api.auth.models import ResourceType
from red_transporte_api.models import GTFSStatus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status", response_model=GTFSStatus)
async def gtfs_status(_token=Depends(require_access())):
    """Obtener el estado actual de los datos GTFS locales."""
    from red_transporte_api.gtfs.downloader import get_gtfs_status
    return GTFSStatus(**get_gtfs_status())


@router.post("/update")
async def gtfs_update(
    force: bool = False,
    _master: bool = Depends(require_master_token),
):
    """
    Descargar/actualizar los datos GTFS desde DTPM.

    Tras la actualización se recarga la data en memoria.
    Solo accesible con el master token.
    """
    from red_transporte_api.gtfs.downloader import download_latest_gtfs
    from red_transporte_api.gtfs.parser import GTFSData
    from red_transporte_api.api.deps import set_gtfs

    try:
        extract_dir = download_latest_gtfs(force=force)
        gtfs = GTFSData.from_directory(extract_dir)
        set_gtfs(gtfs)
        return {
            "status": "ok",
            "message": f"GTFS actualizado: {len(gtfs.stops)} paraderos, {len(gtfs.routes)} recorridos",
            "path": str(extract_dir),
        }
    except Exception as e:
        logger.exception("Failed to update GTFS")
        return JSONResponse(
            status_code=502,
            content={"error": "Error actualizando GTFS", "detail": str(e)},
        )

