"""S3ObjectStore's own construction -- the shape boto3 itself refuses ("ValueError:
Invalid endpoint: ") when YAADHUM_S3_ENDPOINT_URL is blank, which is the CORRECT value for
real AWS S3 (the setting only exists at all for Cloudflare R2 or MinIO). A blank env var
arrives here as an empty string, never as None, so this is the one place that distinction
has to be handled.

``boto3`` is not installed in this sandbox (a genuine dependency -- see pyproject.toml's
storage extra -- just not present here), so a small fake stands in for it, the same
technique used for the anthropic client elsewhere in this test suite.
"""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def fake_boto3(monkeypatch):
    calls: list[dict] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake = types.ModuleType("boto3")
    fake.client = lambda service, **kwargs: _FakeClient(**kwargs)
    monkeypatch.setitem(sys.modules, "boto3", fake)
    return calls


def test_a_blank_endpoint_url_reaches_boto3_as_none_not_an_empty_string(fake_boto3):
    from app.storage import S3ObjectStore

    S3ObjectStore(
        "my-bucket", endpoint_url="", region="ap-south-1",
        access_key="AKIA...", secret_key="secret",
    )
    assert fake_boto3[-1]["endpoint_url"] is None


def test_a_real_endpoint_url_passes_through_unchanged(fake_boto3):
    """R2/MinIO still work -- only the blank case needs coercing."""
    from app.storage import S3ObjectStore

    S3ObjectStore(
        "my-bucket", endpoint_url="https://minio.example.com", region="ap-south-1",
        access_key="key", secret_key="secret",
    )
    assert fake_boto3[-1]["endpoint_url"] == "https://minio.example.com"
