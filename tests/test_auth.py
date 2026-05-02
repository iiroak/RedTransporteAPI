"""Tests para el sistema de autenticación y rate limiting."""

import hashlib
import tempfile
import time

import pytest

from red_transporte_api.auth.models import APISettings, ResourceType, TokenRecord
from red_transporte_api.auth.service import AuthService
from red_transporte_api.auth.sqlite import SQLiteAuthStorage


@pytest.fixture
def storage():
    import os
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "test.db")
    s = SQLiteAuthStorage(db)
    s.initialize()
    yield s
    s._conn.close() if s._conn else None
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def auth_service(storage):
    return AuthService(storage)


class TestAuthServiceTokenLifecycle:
    def test_create_token(self, auth_service):
        created = auth_service.create_token(
            name="test-token",
            is_unlimited=False,
            requests_per_minute=100,
            allow_gtfs=True,
            allow_ibus=True,
            allow_red_web=True,
            allow_raptor=False,
        )
        assert created.id > 0
        assert created.name == "test-token"
        assert len(created.token) > 20
        assert created.is_unlimited is False
        assert created.allow_raptor is False

    def test_validate_token_success(self, auth_service):
        created = auth_service.create_token(name="validate-test", allow_gtfs=True)
        record = auth_service.validate_token(created.token)
        assert record is not None
        assert record.id == created.id

    def test_validate_token_invalid(self, auth_service):
        record = auth_service.validate_token("invalid-token-value")
        assert record is None

    def test_validate_disabled_token(self, auth_service):
        created = auth_service.create_token(name="to-disable", allow_gtfs=True)
        from red_transporte_api.auth.models import TokenUpdate
        auth_service.update_token(created.id, TokenUpdate(enabled=False))
        record = auth_service.validate_token(created.token)
        assert record is None

    def test_list_tokens(self, auth_service):
        auth_service.create_token(name="tok1", allow_gtfs=True)
        auth_service.create_token(name="tok2", allow_gtfs=True)
        tokens = auth_service.list_tokens()
        assert len(tokens) >= 2
        names = [t.name for t in tokens]
        assert "tok1" in names
        assert "tok2" in names

    def test_update_token(self, auth_service):
        created = auth_service.create_token(name="to-update", allow_gtfs=True, allow_raptor=False)
        from red_transporte_api.auth.models import TokenUpdate
        updated = auth_service.update_token(
            created.id,
            TokenUpdate(name="updated-name", allow_raptor=True, requests_per_minute=200),
        )
        assert updated is not None
        assert updated.name == "updated-name"
        assert updated.allow_raptor is True
        assert updated.requests_per_minute == 200

    def test_delete_token(self, auth_service):
        created = auth_service.create_token(name="to-delete", allow_gtfs=True)
        tid = created.id
        assert auth_service.delete_token(tid) is True
        assert auth_service.get_token(tid) is None
        assert auth_service.delete_token(tid) is False


class TestAuthServiceSettings:
    def test_get_default_settings(self, auth_service):
        s = auth_service.get_settings()
        assert s.public_api_enabled is True
        assert s.public_ip_limit_per_minute == 20

    def test_update_settings(self, auth_service):
        new_settings = APISettings(public_api_enabled=False, public_ip_limit_per_minute=50)
        updated = auth_service.update_settings(new_settings)
        assert updated.public_api_enabled is False
        assert updated.public_ip_limit_per_minute == 50


class TestRateLimiting:
    def test_rate_limit_allows_under_limit(self, auth_service):
        allowed, remaining = auth_service.check_rate_limit("ip", "1.2.3.4", "gtfs_read", 10)
        assert allowed is True
        assert remaining >= 0

    def test_rate_limit_blocks_over_limit(self, auth_service):
        import time
        window = int(time.time()) // 60 * 60
        for _ in range(5):
            auth_service._storage.increment_rate_counter("ip", "5.5.5.5", "gtfs_read", window)
        allowed, remaining = auth_service.check_rate_limit("ip", "5.5.5.5", "gtfs_read", 5)
        assert allowed is False


class TestAccessControl:
    def test_unlimited_token_bypasses_access_check(self, auth_service):
        created = auth_service.create_token(name="unlimited-test", is_unlimited=True, allow_raptor=False)
        decision = auth_service.check_access(created, ResourceType.RAPTOR)
        assert decision.allowed is True
        assert decision.reason == "unlimited token"

    def test_limited_token_denied_raptor(self, auth_service):
        created = auth_service.create_token(name="limited-no-raptor", allow_raptor=False, allow_gtfs=True)
        decision = auth_service.check_access(created, ResourceType.RAPTOR)
        assert decision.allowed is False

    def test_public_gtfs_allowed_without_token(self, auth_service):
        decision = auth_service.check_access(None, ResourceType.GTFS_READ)
        assert decision.allowed is True

    def test_public_ibus_denied_without_token(self, auth_service):
        decision = auth_service.check_access(None, ResourceType.IBUS)
        assert decision.allowed is False

    def test_public_raptor_denied_without_token(self, auth_service):
        decision = auth_service.check_access(None, ResourceType.RAPTOR)
        assert decision.allowed is False

    def test_system_resource_always_allowed(self, auth_service):
        decision = auth_service.check_access(None, ResourceType.SYSTEM)
        assert decision.allowed is True


class TestTokenHashing:
    def test_same_token_produces_same_hash(self):
        from red_transporte_api.auth.service import _hash_token
        h1 = _hash_token("my-secret-token")
        h2 = _hash_token("my-secret-token")
        assert h1 == h2

    def test_different_tokens_produce_different_hashes(self):
        from red_transporte_api.auth.service import _hash_token
        h1 = _hash_token("token-a")
        h2 = _hash_token("token-b")
        assert h1 != h2

    def test_token_not_stored_in_plain_text(self, auth_service):
        created = auth_service.create_token(name="secure-test", allow_gtfs=True)
        record = auth_service._storage.get_token_by_id(created.id)
        assert record is not None
        assert record.token_hash != created.token
        assert len(record.token_hash) == 64


class TestResourceClassification:
    def test_gtfs_read_for_stops(self):
        from red_transporte_api.auth.rate_limit import get_resource_type
        assert get_resource_type("/stops/search?q=providencia") == ResourceType.GTFS_READ
        assert get_resource_type("/stops/PA433") == ResourceType.GTFS_READ
        assert get_resource_type("/routes") == ResourceType.GTFS_READ

    def test_raptor_for_routing_plan(self):
        from red_transporte_api.auth.rate_limit import get_resource_type
        assert get_resource_type("/routing/plan") == ResourceType.RAPTOR

    def test_ibus_for_predictions(self):
        from red_transporte_api.auth.rate_limit import get_resource_type
        assert get_resource_type("/predictions/PA433") == ResourceType.IBUS

    def test_gtfs_admin_for_gtfs_update(self):
        from red_transporte_api.auth.rate_limit import get_resource_type
        assert get_resource_type("/gtfs/status") == ResourceType.GTFS_READ
        assert get_resource_type("/gtfs/update", "POST") == ResourceType.GTFS_ADMIN


class TestTokenScopes:
    def test_token_with_only_gtfs_cannot_access_ibus(self, auth_service):
        created = auth_service.create_token(
            name="gtfs-only",
            allow_gtfs=True,
            allow_ibus=False,
            allow_red_web=False,
            allow_raptor=False,
        )
        decision = auth_service.check_access(created, ResourceType.IBUS)
        assert decision.allowed is False

    def test_token_with_only_ibus_cannot_access_raptor(self, auth_service):
        created = auth_service.create_token(
            name="ibus-only",
            allow_gtfs=False,
            allow_ibus=True,
            allow_red_web=False,
            allow_raptor=False,
        )
        decision = auth_service.check_access(created, ResourceType.RAPTOR)
        assert decision.allowed is False

    def test_token_can_have_multiple_sources(self, auth_service):
        created = auth_service.create_token(
            name="multi-source",
            allow_gtfs=True,
            allow_ibus=True,
            allow_red_web=True,
            allow_raptor=True,
        )
        for src in [ResourceType.GTFS_READ, ResourceType.IBUS, ResourceType.RED_WEB, ResourceType.RAPTOR]:
            decision = auth_service.check_access(created, src)
            assert decision.allowed is True, f"Failed for {src}"