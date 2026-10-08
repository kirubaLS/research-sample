"""School onboarding details: a contact number (digits only), an optional email, and a school
code that names one school."""

from __future__ import annotations

import uuid

import pytest

KEY = "contact-platform-key"
HEAD = {"X-Platform-Key": KEY}


@pytest.fixture(autouse=True)
def _operator():
    from app.config import get_settings

    s = get_settings()
    before = s.platform_admin_key
    s.platform_admin_key = KEY
    yield
    s.platform_admin_key = before


def _school(client, label=""):
    name = f"Contact Test School {label}{uuid.uuid4().hex[:6]}"
    r = client.post("/platform/schools", headers=HEAD, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch(client, sid, **body):
    return client.patch(f"/platform/schools/{sid}", headers=HEAD, json=body)


def test_a_mobile_number_is_stored_as_digits_and_a_new_school_has_none(client):
    sid = _school(client)
    assert client.get(f"/platform/schools/{sid}", headers=HEAD).json()["contact_phone"] is None
    r = _patch(client, sid, contact_phone="+91 98765-43210")
    assert r.status_code == 200 and r.json()["contact_phone"] == "9876543210"


@pytest.mark.parametrize("number", ["04343 222333", "0422-2345678", "044 12345678"])
def test_a_landline_with_its_std_code_is_stored_as_digits(client, number):
    sid = _school(client)
    r = _patch(client, sid, contact_phone=number)
    assert r.status_code == 200, r.text
    assert r.json()["contact_phone"] == "".join(c for c in number if c.isdigit())


@pytest.mark.parametrize("bad", ["98765", "abcdefghij", "12345678901234", "5876543210", "98765 4321x"])
def test_a_number_that_is_not_digits_or_the_wrong_length_is_refused(client, bad):
    sid = _school(client)
    assert _patch(client, sid, contact_phone=bad).status_code == 422


def test_the_email_is_optional_checked_and_lowercased(client):
    sid = _school(client)
    r = _patch(client, sid, contact_email="Office@School.EDU.in")
    assert r.json()["contact_email"] == "office@school.edu.in"
    assert _patch(client, sid, contact_email="").json()["contact_email"] is None
    assert _patch(client, sid, contact_email="not-an-email").status_code == 422


def test_two_schools_cannot_share_a_code_but_a_school_can_keep_its_own(client):
    a, b = _school(client, "a"), _school(client, "b")
    code = f"KR-BH-{uuid.uuid4().hex[:4].upper()}"
    assert _patch(client, a, code=code).status_code == 200
    assert _patch(client, a, code=code).status_code == 200, "re-saving its own code is fine"
    clash = _patch(client, b, code=code.lower())
    assert clash.status_code == 409 and "already in use" in clash.text
    assert _patch(client, b, code=code + "X").status_code == 200
