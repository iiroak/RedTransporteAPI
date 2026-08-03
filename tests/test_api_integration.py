"""Tests de integración HTTP básicos (sin GTFS ni red externa)."""

import pytest
from fastapi.testclient import TestClient

from red_transporte_api.api.app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["version"]


def test_invalid_bearer_returns_401(client):
    r = client.get("/stats", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_malformed_auth_header_returns_401(client):
    r = client.get("/stats", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401
