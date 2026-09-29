"""app.integrations.whatsapp.WhatsAppClient and the /reports/issued/{id}/whatsapp send
path -- the real Meta Cloud API calls are mocked (same approach test_jina.py takes for
Jina's API), but nothing about the send path's own logic is faked: a real WhatsAppSend
row is created, a real background task runs, and its outcome is read back from the
database exactly as _run_whatsapp_send wrote it.

Covers, per the zero-fabrication rule this codebase holds everywhere else:
  * a successful upload+send moves the row to "sent" with the real message id Meta's
    mocked response carried;
  * a Meta error response (simulated the way Meta's own API actually replies -- a JSON
    error body with a code/message) moves the row to "failed" with that real message,
    never a bare "failed";
  * a student with no parent_whatsapp on file gets a real 422 -- never a queued job that
    would predictably fail later;
  * the webhook's HMAC-SHA256 signature verification genuinely rejects an unsigned/
    wrongly-signed payload and genuinely accepts a correctly-signed one, built the same
    way Meta itself would sign it;
  * a correctly-signed webhook delivery updates the right row by meta_message_id.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from app.integrations.whatsapp import WhatsAppAPIError, WhatsAppClient


# --- WhatsAppClient itself, mocked at the httpx layer -----------------------------------

def test_upload_media_returns_the_real_media_id(monkeypatch):
    def fake_post(url, *, headers, data=None, files=None, json=None, timeout=None):
        assert url.endswith("/123/media")
        assert files["file"][2] == "application/pdf"
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"id": "media-abc-999"})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = WhatsAppClient(phone_number_id="123", access_token="tok")
    assert client.upload_media(b"%PDF-1.4 fake", "report.pdf") == "media-abc-999"


def test_send_document_template_returns_metas_real_message_id(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json=None, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, request=request,
            json={"messages": [{"id": "wamid.REAL123"}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = WhatsAppClient(phone_number_id="123", access_token="tok")
    result = client.send_document_template(
        to="919876543210", media_id="media-abc-999", template_name="student_report",
        language="en",
        params={"parent_name": "Parent/Guardian", "school_name": "Bharath International",
                "student_name": "Asha", "test_title": "Unit Test 3"},
    )
    assert result["messages"][0]["id"] == "wamid.REAL123"
    assert captured["url"].endswith("/123/messages")
    body_params = captured["payload"]["template"]["components"][1]["parameters"]
    assert [p["text"] for p in body_params] == [
        "Parent/Guardian", "Bharath International", "Asha", "Unit Test 3",
    ]


def test_a_real_meta_error_is_surfaced_honestly_not_swallowed(monkeypatch):
    def fake_post(url, *, headers, json=None, data=None, files=None, timeout=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            401, request=request,
            json={"error": {"message": "Error validating access token: Session has expired",
                             "code": 190, "error_subcode": 463}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = WhatsAppClient(phone_number_id="123", access_token="expired-token")

    with pytest.raises(WhatsAppAPIError, match="Session has expired") as exc_info:
        client.send_document_template(
            to="919876543210", media_id="m1", template_name="student_report", language="en",
            params={},
        )
    assert exc_info.value.code == 190
    assert exc_info.value.subcode == 463


def test_placeholder_credentials_refuse_before_ever_calling_meta():
    with pytest.raises(ValueError, match="no WhatsApp credentials configured"):
        WhatsAppClient(phone_number_id="", access_token="")


# --- the send endpoint + background task, against a real school/student/report ---------

def _auth(school):
    return {"X-API-Key": school["api_key"]}


def _issue_report(client, school, h, *, tag: str, with_parent_whatsapp: str | None = None):
    """A minimal, real, issued report for one fresh student -- mirrors boardx_paper's own
    setup in test_boardx_report.py: the assessment and its one question through the API,
    the student written directly (the same shortcut every report test in this suite
    takes), one mark confirmed, then issued."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import StudentProfile

    aid = client.post(
        "/assessments", headers=h,
        json={"subject_code": "X.MATH", "title": f"WA Test {tag}", "total_marks": 5},
    ).json()["assessment_id"]
    out = client.post(
        f"/assessments/{aid}/questions", headers=h, json={"questions": [
            {"section": "A", "question_no": "1", "max_marks": 5, "board_unit": "X.MATH.U.MENSURATION",
             "concept_family": "X.MATH.CF.VOLUME", "concept_variant": f"wa-{tag}-1",
             "chapter": "X.MATH.SAV", "curriculum_section": "12.1"},
        ]},
    )
    assert out.status_code == 200, out.text

    db = SessionLocal()
    student = StudentProfile(
        school_id=school["school_id"], section_id=school["section_id"],
        name=f"WA Student {tag}", roll_no=f"wa-{tag}",
        parent_whatsapp=with_parent_whatsapp,
    )
    db.add(student)
    db.commit()
    student_id = student.id
    db.close()

    client.patch(
        f"/assessments/{aid}/answers/{student_id}/reading/A/1//",
        headers=h, json={"marks": 5, "state": "awarded", "by": "test"},
    )
    confirmed = client.post(
        f"/assessments/{aid}/answers/{student_id}/reading/confirm", headers=h, json={"by": "test"},
    )
    assert confirmed.status_code == 200, confirmed.text

    report = client.post(
        f"/reports/student/{student_id}/issue", headers=h,
        json={"assessment_id": aid, "by": "teacher"},
    ).json()
    return report["report_id"], student_id


def test_no_parent_whatsapp_on_file_is_a_real_422_not_a_queued_job(client, school):
    h = _auth(school)
    report_id, student_id = _issue_report(client, school, h, tag="noparent")
    r = client.post(f"/reports/issued/{report_id}/whatsapp", headers=h)
    assert r.status_code == 422
    assert "no parent whatsapp number" in r.json()["detail"].lower()
    # never queued: nothing to poll
    assert client.get(f"/reports/issued/{report_id}/whatsapp", headers=h).status_code == 404


def test_successful_send_updates_the_row_to_sent_with_a_real_message_id(client, school, monkeypatch):
    h = _auth(school)
    report_id, student_id = _issue_report(client, school, h, tag="sentok", with_parent_whatsapp="919876500001")

    def fake_post(url, *, headers, json=None, data=None, files=None, timeout=None):
        request = httpx.Request("POST", url)
        if url.endswith("/media"):
            return httpx.Response(200, request=request, json={"id": "media-777"})
        return httpx.Response(200, request=request, json={"messages": [{"id": "wamid.SENTOK1"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())

    r = client.post(f"/reports/issued/{report_id}/whatsapp", headers=h)
    assert r.status_code == 202
    status_row = client.get(f"/reports/issued/{report_id}/whatsapp", headers=h).json()
    assert status_row["status"] == "sent"
    assert status_row["meta_message_id"] == "wamid.SENTOK1"
    assert status_row["error_detail"] is None


def test_a_meta_error_during_send_updates_the_row_to_failed_with_the_real_reason(client, school, monkeypatch):
    h = _auth(school)
    report_id, student_id = _issue_report(client, school, h, tag="failtpl", with_parent_whatsapp="919876500002")

    def fake_post(url, *, headers, json=None, data=None, files=None, timeout=None):
        request = httpx.Request("POST", url)
        if url.endswith("/media"):
            return httpx.Response(200, request=request, json={"id": "media-778"})
        return httpx.Response(
            400, request=request,
            json={"error": {"message": "Invalid parameter: template not found", "code": 132001}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())

    r = client.post(f"/reports/issued/{report_id}/whatsapp", headers=h)
    assert r.status_code == 202
    status_row = client.get(f"/reports/issued/{report_id}/whatsapp", headers=h).json()
    assert status_row["status"] == "failed"
    assert "template not found" in status_row["error_detail"]


def _settings_with_creds():
    from app.config import Settings

    return Settings(
        whatsapp_phone_number_id="999888777", whatsapp_access_token="test-token",
        whatsapp_app_secret="test-app-secret", whatsapp_webhook_verify_token="verify-me",
    )


# --- the webhook: signature verification + status update by meta_message_id ------------

def _signed_headers(body: bytes, secret: str) -> dict:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"}


def test_webhook_verification_challenge_echoes_back_on_a_matching_token(client, monkeypatch):
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())
    r = client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345",
    })
    assert r.status_code == 200
    assert r.text == "12345"


def test_webhook_verification_refuses_a_wrong_token(client, monkeypatch):
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())
    r = client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345",
    })
    assert r.status_code == 403


def test_webhook_rejects_an_unsigned_payload(client, monkeypatch):
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())
    payload = {"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.SOMEID", "status": "delivered"},
    ]}}]}]}
    r = client.post("/webhooks/whatsapp", content=json.dumps(payload),
                     headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_webhook_rejects_a_wrongly_signed_payload(client, monkeypatch):
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())
    body = json.dumps({"entry": []}).encode()
    headers = _signed_headers(body, "not-the-real-secret")
    r = client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert r.status_code == 401


def test_webhook_accepts_a_correctly_signed_payload_and_updates_the_matching_row(
    client, school, monkeypatch,
):
    h = _auth(school)
    report_id, student_id = _issue_report(client, school, h, tag="webhook", with_parent_whatsapp="919876500003")

    def fake_post(url, *, headers, json=None, data=None, files=None, timeout=None):
        request = httpx.Request("POST", url)
        if url.endswith("/media"):
            return httpx.Response(200, request=request, json={"id": "media-779"})
        return httpx.Response(200, request=request, json={"messages": [{"id": "wamid.WEBHOOKTEST1"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.api.reports.get_settings", lambda: _settings_with_creds())
    client.post(f"/reports/issued/{report_id}/whatsapp", headers=h)
    assert client.get(f"/reports/issued/{report_id}/whatsapp", headers=h).json()["status"] == "sent"

    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.WEBHOOKTEST1", "status": "delivered"},
    ]}}]}]}).encode()
    headers = _signed_headers(body, "test-app-secret")
    r = client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert r.status_code == 200
    assert r.json()["updated"] == 1

    status_row = client.get(f"/reports/issued/{report_id}/whatsapp", headers=h).json()
    assert status_row["status"] == "delivered"
