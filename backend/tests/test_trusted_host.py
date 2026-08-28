"""The health probe must not depend on the Host header.

Render's health check reaches the process from inside its network without the public
hostname, so a host allowlist that covers /healthz rejects every probe with 400 and the
deploy hangs on a healthy process. This is the regression that cost a production deploy.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def restricted_app(monkeypatch):
    monkeypatch.setenv("YAADHUM_TRUSTED_HOSTS", "api.example.com")
    from app import config

    config.get_settings.cache_clear()
    import app.main

    module = importlib.reload(app.main)
    yield module.app
    config.get_settings.cache_clear()
    importlib.reload(app.main)


def test_health_probe_survives_an_unknown_host(restricted_app):
    with TestClient(restricted_app) as client:
        # what Render actually sends: an internal address, not the public hostname
        r = client.get("/healthz", headers={"Host": "10.238.26.71"})
        assert r.status_code == 200, "a liveness probe must not be host-filtered"
        assert r.json()["status"] == "ok"


def test_real_routes_are_still_host_filtered(restricted_app):
    with TestClient(restricted_app) as client:
        assert client.get("/t/classes", headers={"Host": "evil.example"}).status_code == 400
        assert client.get("/t/classes", headers={"Host": "api.example.com"}).status_code == 200
