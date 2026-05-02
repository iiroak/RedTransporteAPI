"""Admin routes — master-token protected API management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from red_transporte_api.auth.deps import get_auth_service, require_master_token
from red_transporte_api.auth.models import (
    APISettings,
    TokenCreate,
    TokenCreated,
    TokenResponse,
    TokenUpdate,
)
from red_transporte_api.auth.service import AuthService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/settings", response_model=APISettings)
async def get_settings(_: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    return auth.get_settings()


@router.patch("/settings", response_model=APISettings)
async def update_settings(settings: APISettings, _: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    return auth.update_settings(settings)


@router.post("/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(token_data: TokenCreate, _: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    created = auth.create_token(
        name=token_data.name,
        is_unlimited=token_data.is_unlimited,
        requests_per_minute=token_data.requests_per_minute,
        allow_gtfs=token_data.allow_gtfs,
        allow_ibus=token_data.allow_ibus,
        allow_red_web=token_data.allow_red_web,
        allow_raptor=token_data.allow_raptor,
    )
    return created


@router.get("/tokens", response_model=list[TokenResponse])
async def list_tokens(_: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    return auth.list_tokens()


@router.get("/tokens/{token_id}", response_model=TokenResponse)
async def get_token(token_id: int, _: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    token = auth.get_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.patch("/tokens/{token_id}", response_model=TokenResponse)
async def update_token(token_id: int, update: TokenUpdate, _: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    token = auth.update_token(token_id, update)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: int, _: bool = Depends(require_master_token)):
    auth: AuthService = get_auth_service()
    if not auth.delete_token(token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "deleted", "id": token_id}