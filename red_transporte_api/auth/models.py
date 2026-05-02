"""Auth models — Pydantic schemas for tokens, settings, and access control."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    GTFS_READ = "gtfs_read"
    IBUS = "ibus"
    RED_WEB = "red_web"
    RAPTOR = "raptor"
    GTFS_ADMIN = "gtfs_admin"
    SYSTEM = "system"


class APISettings(BaseModel):
    public_api_enabled: bool = True
    public_ip_limit_per_minute: int = 20
    updated_at: Optional[datetime] = None


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_unlimited: bool = False
    requests_per_minute: int = Field(default=60, ge=1, le=10000)
    allow_gtfs: bool = True
    allow_ibus: bool = True
    allow_red_web: bool = True
    allow_raptor: bool = True


class TokenUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    is_unlimited: Optional[bool] = None
    requests_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    allow_gtfs: Optional[bool] = None
    allow_ibus: Optional[bool] = None
    allow_red_web: Optional[bool] = None
    allow_raptor: Optional[bool] = None


class TokenResponse(BaseModel):
    id: int
    name: str
    is_unlimited: bool
    requests_per_minute: int
    allow_gtfs: bool
    allow_ibus: bool
    allow_red_web: bool
    allow_raptor: bool
    enabled: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class TokenCreated(BaseModel):
    id: int
    name: str
    token: str
    is_unlimited: bool
    requests_per_minute: int
    allow_gtfs: bool
    allow_ibus: bool
    allow_red_web: bool
    allow_raptor: bool
    enabled: bool
    created_at: datetime


class TokenRecord(BaseModel):
    id: int
    name: str
    token_hash: str
    is_unlimited: bool
    requests_per_minute: int
    allow_gtfs: bool
    allow_ibus: bool
    allow_red_web: bool
    allow_raptor: bool
    enabled: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class AccessDecision(BaseModel):
    allowed: bool
    reason: str
    source: Optional[str] = None