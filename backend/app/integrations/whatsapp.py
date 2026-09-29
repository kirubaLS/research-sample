"""Meta's WhatsApp Cloud API, direct -- no BSP middleman.

Chosen for cost, not convenience: at this school's real volume (roughly 300 report sends
a month), Meta's own direct per-message utility rate (~Rs 0.115) is what a BSP subscription
would cost 40x or more of, for nothing this deployment needs (no multi-agent inbox, no
shared team number). See the commit that added this module for the pricing analysis.

A report card is sensitive: a child's name and marks. WhatsApp's document-message API will
take either a public `link` or a `media_id` from Meta's own Media Upload API -- this module
only ever uses the second. The PDF bytes are uploaded straight to Meta and referenced by
the media_id the upload returns; they are never hosted at a public, unauthenticated URL
Meta (or anyone holding the link) could otherwise fetch indefinitely.

Real HTTP calls throughout, mirroring app.ingest.jina.JinaEmbedder's shape: raise on a
genuine failure, and keep Meta's own error body in the message rather than swallowing it
into a bare "failed". No mocked/simulated success path exists here -- with a placeholder
phone_number_id or token, `upload_media`/`send_document_template` will genuinely call Meta
and genuinely fail with Meta's own real error (an invalid token, an unrecognised phone
number id), which is exactly what should happen before Meta Business verification is done.
"""

from __future__ import annotations

import httpx

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

#: The approved template's body-variable shape, as a single documented, adjustable
#: constant -- the real template does not exist yet (Meta approval is still pending), so
#: this names what a "student report ready" utility template is expected to need, in
#: order: parent's name, the SCHOOL's name, the student's name, the test/assessment
#: title. school_name is not optional: this platform sends from one shared, Meta-
#: verified WhatsApp Business number on behalf of every school it hosts (not a number
#: per school), so a parent who does not recognise the sending number has nothing else
#: in the message to say this is real and not phishing -- the template's own wording is
#: expected to read roughly "Hi {parent_name}, this is {school_name}. {student_name}'s
#: {test_title} report is ready -- see the attached PDF." Once the real template is
#: approved, only this list (and Settings.whatsapp_template_name) needs to change --
#: never the call sites in app.api.reports.
WHATSAPP_TEMPLATE_PARAMS = ["parent_name", "school_name", "student_name", "test_title"]


class WhatsAppAPIError(RuntimeError):
    """Meta's own structured error, kept intact rather than collapsed to a status code.

    Meta's Graph API error body carries a `code`, a `message` and often an
    `error_subcode` (e.g. 190 = expired/invalid access token, 100 = bad parameter). All
    three are kept on the exception so a caller -- and, ultimately, WhatsAppSend.error_detail
    -- can show the real reason, not "the send failed".
    """

    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.subcode = subcode


class WhatsAppClient:
    """Wraps the two Graph API calls a report send needs: upload the PDF to get a
    media_id, then send a template message referencing it. No other capability of the
    Cloud API is implemented -- this deployment sends exactly one kind of message."""

    def __init__(
        self, *, phone_number_id: str, access_token: str, timeout: float = 30.0,
    ) -> None:
        if not phone_number_id or not access_token:
            raise ValueError(
                "no WhatsApp credentials configured. Set YAADHUM_WHATSAPP_PHONE_NUMBER_ID "
                "and YAADHUM_WHATSAPP_ACCESS_TOKEN once Meta Business verification and a "
                "real WhatsApp Business number exist -- until then, a send genuinely "
                "attempts the real API and this is the honest reason it cannot."
            )
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _raise_for_meta_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            body = response.json()
            error = body.get("error", {})
        except ValueError:
            error = {}
        message = error.get("message") or response.text or f"HTTP {response.status_code}"
        raise WhatsAppAPIError(
            f"Meta WhatsApp API error: {message}",
            code=error.get("code"), subcode=error.get("error_subcode"),
        )

    def upload_media(self, pdf_bytes: bytes, filename: str) -> str:
        """POST /{phone_number_id}/media -- returns Meta's own media_id for this PDF.

        This is the whole privacy point of this module: the bytes go straight to Meta
        over this one call and nowhere else. Nothing about the report is ever placed at
        a public URL for the later `send_document_template` call to merely point at.
        """
        response = httpx.post(
            f"{GRAPH_BASE}/{self.phone_number_id}/media",
            headers=self._headers(),
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            timeout=self.timeout,
        )
        self._raise_for_meta_error(response)
        media_id = response.json().get("id")
        if not media_id:
            raise WhatsAppAPIError("Meta's media upload returned no media id")
        return media_id

    def send_document_template(
        self, *, to: str, media_id: str, template_name: str, language: str, params: dict[str, str],
    ) -> dict:
        """POST /{phone_number_id}/messages -- a template message with the uploaded PDF
        as its document header, and the template's body variables filled from `params`
        (see WHATSAPP_TEMPLATE_PARAMS for the order/shape expected).

        Returns Meta's real response body, including the message id Meta assigns
        (`messages[0].id`) -- the correlation key delivery/read-status webhooks refer
        back to.
        """
        body_parameters = [
            {"type": "text", "text": params.get(key, "")} for key in WHATSAPP_TEMPLATE_PARAMS
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "header",
                        "parameters": [{"type": "document", "document": {"id": media_id}}],
                    },
                    {"type": "body", "parameters": body_parameters},
                ],
            },
        }
        response = httpx.post(
            f"{GRAPH_BASE}/{self.phone_number_id}/messages",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        self._raise_for_meta_error(response)
        return response.json()
