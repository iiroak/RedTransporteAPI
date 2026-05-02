"""Rate limiting logic — per-minute window counters keyed by IP or token."""
from __future__ import annotations

import time
from typing import Optional

from red_transporte_api.auth.models import ResourceType
from red_transporte_api.auth.service import AuthService


class RateLimiter:
    def __init__(self, auth_service: AuthService):
        self._auth = auth_service

    def check(
        self,
        subject_type: str,
        subject_key: str,
        resource: ResourceType,
        limit: int,
    ) -> tuple[bool, int]:
        return self._auth.check_rate_limit(subject_type, subject_key, resource.value, limit)

    def public_limit(self, ip: str, resource: ResourceType, default_limit: int) -> tuple[bool, int]:
        return self.check("ip", ip, resource, default_limit)


def _classify_endpoint(path: str, method: str) -> ResourceType:
    p = path.lower()
    if p.startswith("/gtfs") and method == "POST":
        return ResourceType.GTFS_ADMIN
    if p.startswith("/routing/plan"):
        return ResourceType.RAPTOR
    if "/predictions/" in p:
        return ResourceType.IBUS
    if p.startswith("/stops/") and "/predictions" not in p:
        return ResourceType.GTFS_READ
    if p.startswith("/predictions"):
        return ResourceType.IBUS
    if p.startswith("/stops"):
        return ResourceType.GTFS_READ
    if p in ("/", "/health", "/stats"):
        return ResourceType.SYSTEM
    return ResourceType.GTFS_READ


def get_resource_type(path: str, method: str = "GET") -> ResourceType:
    return _classify_endpoint(path, method)