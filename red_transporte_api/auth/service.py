"""Auth service — token management, hashing, and access validation."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

from red_transporte_api.auth.models import (
    APISettings,
    AccessDecision,
    ResourceType,
    TokenCreated,
    TokenRecord,
    TokenResponse,
    TokenUpdate,
)
from red_transporte_api.auth.storage import AuthStorage


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secure_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


class AuthService:
    def __init__(self, storage: AuthStorage):
        self._storage = storage

    def create_token(self, name: str, is_unlimited: bool = False, requests_per_minute: int = 60, allow_gtfs: bool = True, allow_ibus: bool = True, allow_red_web: bool = True, allow_raptor: bool = True) -> TokenCreated:
        raw = _generate_token()
        token_hash = _hash_token(raw)
        token_id = self._storage.create_token(
            name=name,
            token_hash=token_hash,
            is_unlimited=is_unlimited,
            requests_per_minute=requests_per_minute,
            allow_gtfs=allow_gtfs,
            allow_ibus=allow_ibus,
            allow_red_web=allow_red_web,
            allow_raptor=allow_raptor,
        )
        record = self._storage.get_token_by_id(token_id)
        return TokenCreated(
            id=record.id,
            name=record.name,
            token=raw,
            is_unlimited=record.is_unlimited,
            requests_per_minute=record.requests_per_minute,
            allow_gtfs=record.allow_gtfs,
            allow_ibus=record.allow_ibus,
            allow_red_web=record.allow_red_web,
            allow_raptor=record.allow_raptor,
            enabled=record.enabled,
            created_at=record.created_at,
        )

    def validate_token(self, raw_token: str) -> Optional[TokenRecord]:
        token_hash = _hash_token(raw_token)
        record = self._storage.get_token_by_hash(token_hash)
        if record and record.enabled:
            self._storage.update_token_last_used(record.id)
        return record if record and record.enabled else None

    def list_tokens(self) -> list[TokenResponse]:
        records = self._storage.list_tokens()
        return [self._record_to_response(r) for r in records]

    def get_token(self, token_id: int) -> Optional[TokenResponse]:
        record = self._storage.get_token_by_id(token_id)
        return self._record_to_response(record) if record else None

    def update_token(self, token_id: int, update: TokenUpdate) -> Optional[TokenResponse]:
        self._storage.update_token(
            token_id=token_id,
            name=update.name,
            enabled=update.enabled,
            is_unlimited=update.is_unlimited,
            requests_per_minute=update.requests_per_minute,
            allow_gtfs=update.allow_gtfs,
            allow_ibus=update.allow_ibus,
            allow_red_web=update.allow_red_web,
            allow_raptor=update.allow_raptor,
        )
        return self.get_token(token_id)

    def delete_token(self, token_id: int) -> bool:
        record = self._storage.get_token_by_id(token_id)
        if not record:
            return False
        self._storage.delete_token(token_id)
        return True

    def get_settings(self) -> APISettings:
        return self._storage.get_settings()

    def update_settings(self, settings: APISettings) -> APISettings:
        self._storage.update_settings(settings)
        return self._storage.get_settings()

    def check_rate_limit(self, subject_type: str, subject_key: str, resource_type: str, limit: int) -> tuple[bool, int]:
        window = int(time.time()) // 60 * 60
        count = self._storage.get_rate_counter(subject_type, subject_key, resource_type, window)
        if count >= limit:
            return False, limit - count
        self._storage.increment_rate_counter(subject_type, subject_key, resource_type, window)
        return True, limit - count - 1

    def check_access(self, record: Optional[TokenRecord], resource: ResourceType) -> AccessDecision:
        if record and record.is_unlimited:
            return AccessDecision(allowed=True, reason="unlimited token")
        if resource == ResourceType.GTFS_READ:
            allowed = record.allow_gtfs if record else True
            return AccessDecision(allowed=allowed, reason="gtfs not allowed" if not allowed else "public gtfs")
        if resource == ResourceType.IBUS:
            allowed = record.allow_ibus if record else True
            return AccessDecision(allowed=allowed, reason="ibus not allowed" if not allowed else "allowed")
        if resource == ResourceType.RED_WEB:
            allowed = record.allow_red_web if record else True
            return AccessDecision(allowed=allowed, reason="red_web not allowed" if not allowed else "allowed")
        if resource == ResourceType.RAPTOR:
            allowed = record.allow_raptor if record else False
            return AccessDecision(allowed=allowed, reason="raptor not allowed" if not allowed else "allowed")
        if resource == ResourceType.GTFS_ADMIN:
            return AccessDecision(allowed=False, reason="gtfs_admin requires admin token")
        if resource == ResourceType.SYSTEM:
            return AccessDecision(allowed=True, reason="system resource")
        return AccessDecision(allowed=False, reason="unknown resource")

    def _record_to_response(self, record: TokenRecord) -> TokenResponse:
        return TokenResponse(
            id=record.id,
            name=record.name,
            is_unlimited=record.is_unlimited,
            requests_per_minute=record.requests_per_minute,
            allow_gtfs=record.allow_gtfs,
            allow_ibus=record.allow_ibus,
            allow_red_web=record.allow_red_web,
            allow_raptor=record.allow_raptor,
            enabled=record.enabled,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
        )