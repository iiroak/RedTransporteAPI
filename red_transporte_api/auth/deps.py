"""FastAPI auth dependencies — master token, access control, rate limiting."""
from __future__ import annotations

import hashlib
import secrets
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status

from red_transporte_api.auth.models import AccessDecision, ResourceType, TokenRecord
from red_transporte_api.auth.rate_limit import RateLimiter, get_resource_type
from red_transporte_api.auth.service import AuthService


_auth_service: Optional[AuthService] = None
_rate_limiter: Optional[RateLimiter] = None
_master_token_hash: Optional[str] = None


def init_auth(auth_service: AuthService, master_token: str) -> None:
    global _auth_service, _rate_limiter, _master_token_hash
    _auth_service = auth_service
    _rate_limiter = RateLimiter(auth_service)
    if master_token:
        _master_token_hash = hashlib.sha256(master_token.encode()).hexdigest()


def get_auth_service() -> AuthService:
    if _auth_service is None:
        raise RuntimeError("Auth not initialized")
    return _auth_service


def get_rate_limiter() -> RateLimiter:
    if _rate_limiter is None:
        raise RuntimeError("Auth not initialized")
    return _rate_limiter


def _get_client_ip(request: Request) -> str:
    """Return the real client IP.

    X-Forwarded-For is only trusted when RED_TRANSPORTE_TRUST_PROXY=true.
    Otherwise the direct connection IP is used to prevent spoofing.
    """
    from red_transporte_api.config import TRUST_PROXY
    if TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_master_token(request: Request) -> bool:
    """FastAPI dependency: allow only requests bearing the master token."""
    if not _master_token_hash:
        raise HTTPException(status_code=500, detail="Master token not configured")
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not secrets.compare_digest(token_hash, _master_token_hash):
        raise HTTPException(status_code=403, detail="Invalid master token")
    return True


def _get_auth_token_record(request: Request) -> Optional[TokenRecord]:
    token = _extract_bearer_token(request)
    if not token:
        return None
    auth = get_auth_service()
    return auth.validate_token(token)


def require_access(resource: Optional[ResourceType] = None) -> Callable:
    """Factory that returns a FastAPI dependency for a specific resource.

    Usage:
        _token = Depends(require_access())                        # infer from path
        _token = Depends(require_access(ResourceType.RAPTOR))     # explicit scope

    When *resource* is None the scope is inferred from the request path via
    ``get_resource_type()``.
    """
    def _dependency(request: Request) -> Optional[TokenRecord]:
        auth = get_auth_service()
        settings = auth.get_settings()
        client_ip = _get_client_ip(request)

        # Resolve effective resource type
        effective_resource = resource if resource is not None else get_resource_type(
            request.url.path, request.method
        )

        record = _get_auth_token_record(request)

        if record:
            decision = auth.check_access(record, effective_resource)
            if not decision.allowed:
                raise HTTPException(status_code=403, detail=decision.reason)
            if not record.is_unlimited:
                limiter = get_rate_limiter()
                allowed, _ = limiter.check("token", str(record.id), effective_resource, record.requests_per_minute)
                if not allowed:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded. Try again in a minute.",
                    )
            return record

        # No token — check public access
        if not settings.public_api_enabled:
            raise HTTPException(status_code=401, detail="Authentication required")

        decision = auth.check_access(None, effective_resource)
        if not decision.allowed:
            raise HTTPException(status_code=403, detail=decision.reason)

        limiter = get_rate_limiter()
        allowed, _ = limiter.public_limit(client_ip, effective_resource, settings.public_ip_limit_per_minute)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Public rate limit exceeded. Try again in a minute.",
            )

        return None

    return _dependency


def require_access_for_sources(
    request: Request,
    required_sources: list[ResourceType],
) -> tuple[Optional[TokenRecord], dict[ResourceType, AccessDecision]]:
    """Check access for multiple prediction sources and apply rate limiting.

    Raises:
        401 — no token and public API is disabled
        429 — rate limit exceeded (token or IP)

    Returns a per-source AccessDecision dict; the caller decides which sources
    to query based on ``decision.allowed``.
    """
    auth = get_auth_service()
    settings = auth.get_settings()
    client_ip = _get_client_ip(request)

    record = _get_auth_token_record(request)

    if record is None and not settings.public_api_enabled:
        raise HTTPException(status_code=401, detail="Authentication required")

    results: dict[ResourceType, AccessDecision] = {}

    if record:
        for src in required_sources:
            results[src] = auth.check_access(record, src)
        # Apply per-token rate limit (keyed to first source as representative bucket)
        if not record.is_unlimited:
            limiter = get_rate_limiter()
            rate_src = required_sources[0]
            allowed, _ = limiter.check("token", str(record.id), rate_src, record.requests_per_minute)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Try again in a minute.",
                )
    else:
        for src in required_sources:
            results[src] = auth.check_access(None, src)
        # Apply per-IP rate limit
        limiter = get_rate_limiter()
        rate_src = required_sources[0]
        allowed, _ = limiter.public_limit(client_ip, rate_src, settings.public_ip_limit_per_minute)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Public rate limit exceeded. Try again in a minute.",
            )

    return record, results
