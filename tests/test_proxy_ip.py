"""Tests de la política de IP para rate limiting (proxy trust + CF-Connecting-IP)."""

import pytest

import red_transporte_api.config as config
from red_transporte_api.auth import deps as auth_deps
from red_transporte_api.auth.deps import _get_client_ip, _ip_matches_trusted


class _FakeRequest:
    def __init__(self, client_host, headers=None):
        class _Client:
            host = client_host
        self.client = _Client() if client_host else None
        self.headers = headers or {}


@pytest.fixture
def trusted_true(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    monkeypatch.setattr(config, "TRUSTED_PROXY_IPS", "127.0.0.1,10.0.0.0/8")


@pytest.fixture
def trusted_false(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)


def _ip(conn_host, headers=None):
    return _get_client_ip(_FakeRequest(conn_host, headers))


class TestIpMatchesTrusted:
    def test_exact_ip(self):
        assert _ip_matches_trusted("127.0.0.1", "127.0.0.1") is True
        assert _ip_matches_trusted("10.0.0.5", "127.0.0.1") is False

    def test_cidr(self):
        assert _ip_matches_trusted("10.0.0.5", "127.0.0.1,10.0.0.0/8") is True
        assert _ip_matches_trusted("10.1.2.3", "10.0.0.0/8") is True
        assert _ip_matches_trusted("192.168.1.1", "10.0.0.0/8") is False

    def test_invalid_ip_and_csv(self):
        assert _ip_matches_trusted("testclient", "127.0.0.1") is False
        assert _ip_matches_trusted("", "127.0.0.1") is False
        assert _ip_matches_trusted("127.0.0.1", "not-an-ip") is False


class TestClientIp:
    def test_no_trust_ignores_spoofed_headers(self, trusted_false):
        assert _ip("1.2.3.4", {"CF-Connecting-IP": "9.9.9.9"}) == "1.2.3.4"
        assert _ip("1.2.3.4", {"X-Forwarded-For": "9.9.9.9"}) == "1.2.3.4"

    def test_trust_uses_cf_connecting_ip(self, trusted_true):
        assert _ip(
            "127.0.0.1",
            {"CF-Connecting-IP": "200.55.1.1", "X-Forwarded-For": "200.55.1.1, 10.0.0.1"},
        ) == "200.55.1.1"

    def test_trust_falls_back_to_xff(self, trusted_true):
        assert _ip(
            "127.0.0.1",
            {"X-Forwarded-For": "200.55.1.1, 10.0.0.1"},
        ) == "200.55.1.1"

    def test_trust_without_headers_uses_connection_ip(self, trusted_true):
        assert _ip("127.0.0.1") == "127.0.0.1"

    def test_trust_ignores_spoof_from_untrusted_conn(self, trusted_true):
        # Conexión directa fuera de las redes permitidas: los headers no se confían.
        assert _ip("192.168.1.99", {"CF-Connecting-IP": "9.9.9.9"}) == "192.168.1.99"

    def test_trust_works_for_cidr_proxy(self, trusted_true):
        # Conexión desde un proxy dentro de la red permitida 10.0.0.0/8.
        assert _ip("10.0.0.7", {"CF-Connecting-IP": "200.55.1.1"}) == "200.55.1.1"

    def test_non_ip_client_host_untrusted(self, trusted_true):
        # TestClient usa "testclient" como host: nunca debe confiarse.
        assert _ip("testclient", {"CF-Connecting-IP": "9.9.9.9"}) == "testclient"

    def test_trust_disabled_returns_connection_ip(self, trusted_false):
        assert _ip("127.0.0.1") == "127.0.0.1"


def test_deps_imports_config_at_call_time(monkeypatch):
    # Los cambios de config se reflejan sin reimportar (uso en despliegues).
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    monkeypatch.setattr(config, "TRUSTED_PROXY_IPS", "127.0.0.1")
    assert auth_deps._get_client_ip(_FakeRequest("127.0.0.1", {"CF-Connecting-IP": "8.8.8.8"})) == "8.8.8.8"
