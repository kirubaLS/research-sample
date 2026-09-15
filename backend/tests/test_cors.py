"""A method missing from CORS's allow_methods fails only in a real browser -- every
server-side test calls the route directly, with no preflight, so a gap here is invisible
to the rest of this suite. This is the one place that actually sends the preflight
request a browser would, for every method the API uses.
"""

from __future__ import annotations


def test_a_delete_route_survives_its_own_cors_preflight(client):
    """The bug that reached production: DELETE was missing from allow_methods, so every
    Delete button's OPTIONS preflight 400'd before the real request was ever sent."""
    r = client.options(
        "/assessments/does-not-matter",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert r.status_code == 200, r.text
    assert "DELETE" in r.headers.get("access-control-allow-methods", "")


def test_every_method_this_api_actually_uses_survives_preflight(client):
    for method in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        r = client.options(
            "/assessments/does-not-matter",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
            },
        )
        assert r.status_code == 200, f"{method} preflight: {r.status_code} {r.text}"
