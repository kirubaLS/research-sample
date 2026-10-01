"""Model calls at half price: the Message Batches API behind the same ``messages.parse``.

The classify step is nobody's wait. A paper is uploaded, the teacher closes the tab, and
the server works through it by itself (see marks.py's zero-touch chain) -- so the one
thing the live Messages API sells, an answer in seconds, is paid for and thrown away on
every one of the hundreds of calls a paper costs. The Batches API runs the same requests
asynchronously at 50% of the price, usually within the hour.

Nothing upstream changes shape to get that. ``BatchedMessages.parse`` has the signature
of ``client.messages.parse`` and blocks the calling thread until its answer is back, so
a judge written against the live client runs unmodified. What changes is how the
answers are fetched: every call that arrives while a batch is being gathered joins it
(the gathering window closes ``linger`` seconds after the last arrival), the batch is
submitted once, polled until it ends, and each caller is woken with its own result or
its own error. A stage that asks its questions concurrently -- one thread per question
-- therefore turns into one batch per round of questions: the chapter judge's single
round, then the topic judge's read, confirm and verification rounds.

An item the API refused, or that expired, raises in the caller exactly as the live call
would have, so every existing "one question's failure must not sink the paper" guard
keeps working. A batch that outlives ``max_wait`` is cancelled and every caller raises.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """What a caller of ``parse`` gets back: the shape the judges read."""

    parsed_output: Any
    usage: Any
    content: list


def _output_format_param(model_type) -> dict:
    """The ``output_config.format`` the live ``parse`` would have sent for a pydantic
    ``output_format`` type -- the SDK's own schema transform where it is available."""
    from pydantic import TypeAdapter

    schema = TypeAdapter(model_type).json_schema()
    try:
        from anthropic.lib._parse._transform import transform_schema

        schema = transform_schema(schema)
    except Exception:  # noqa: BLE001 -- an older SDK: the plain schema is still valid
        pass
    return {"type": "json_schema", "schema": schema}


class BatchedMessages:
    """``parse(**kwargs)`` with the live call's signature, served from a batch."""

    def __init__(
        self, client, *, linger: float = 3.0, poll: float = 15.0, max_wait: float = 3 * 3600,
    ) -> None:
        self._client = client
        self.linger, self.poll, self.max_wait = linger, poll, max_wait
        self._lock = threading.Condition()
        self._pending: list[tuple[str, dict, Future, Any]] = []
        self._last_arrival = 0.0
        self._worker: threading.Thread | None = None
        #: batches submitted so far, for the spend report
        self.batches = 0

    # -- the caller's side -----------------------------------------------------------

    def parse(self, **kwargs):
        output_format = kwargs.pop("output_format", None)
        params = dict(kwargs)
        if output_format is not None:
            config = dict(params.get("output_config") or {})
            config["format"] = _output_format_param(output_format)
            params["output_config"] = config
        future: Future = Future()
        with self._lock:
            self._pending.append((uuid.uuid4().hex, params, future, output_format))
            self._last_arrival = time.monotonic()
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True, name="llm-batch")
                self._worker.start()
            self._lock.notify_all()
        return future.result()

    # -- the batch side --------------------------------------------------------------

    def _take(self) -> list[tuple[str, dict, Future, Any]]:
        """Wait for the gathering window to close, then take everything in it."""
        with self._lock:
            while True:
                if not self._pending:
                    return []
                quiet = time.monotonic() - self._last_arrival
                if quiet >= self.linger:
                    items, self._pending = self._pending, []
                    return items
                self._lock.wait(timeout=self.linger - quiet)

    def _run(self) -> None:
        while True:
            items = self._take()
            if not items:
                return
            try:
                self._submit(items)
            except Exception as exc:  # noqa: BLE001 -- every caller hears about it
                logger.exception("batch submission failed")
                for _, _, future, _ in items:
                    if not future.done():
                        future.set_exception(exc)

    def _submit(self, items: list[tuple[str, dict, Future, Any]]) -> None:
        by_id = {custom_id: (future, model_type) for custom_id, _, future, model_type in items}
        batch = self._client.messages.batches.create(
            requests=[{"custom_id": custom_id, "params": params} for custom_id, params, _, _ in items]
        )
        self.batches += 1
        logger.info("batch %s submitted with %d requests", batch.id, len(items))
        started = time.monotonic()
        while True:
            status = self._client.messages.batches.retrieve(batch.id)
            if getattr(status, "processing_status", None) == "ended":
                break
            if time.monotonic() - started > self.max_wait:
                try:
                    self._client.messages.batches.cancel(batch.id)
                finally:
                    raise TimeoutError(
                        f"batch {batch.id} did not finish within {self.max_wait:.0f}s"
                    )
            time.sleep(self.poll)
        for item in self._client.messages.batches.results(batch.id):
            future, model_type = by_id.pop(item.custom_id, (None, None))
            if future is None:
                continue
            kind = item.result.type
            if kind == "succeeded":
                message = item.result.message
                try:
                    future.set_result(_parse_message(message, model_type))
                except Exception as exc:  # noqa: BLE001 -- the caller's guard decides
                    future.set_exception(exc)
            elif kind == "errored":
                error = getattr(item.result, "error", None)
                future.set_exception(RuntimeError(f"batch item {kind}: {error}"))
            else:
                future.set_exception(RuntimeError(f"batch item {kind}"))
        for future, _ in by_id.values():
            future.set_exception(RuntimeError("batch returned no result for this request"))


def _parse_message(message, model_type) -> BatchResult:
    text = next((b.text for b in message.content if getattr(b, "type", None) == "text"), "")
    parsed = None
    if model_type is not None:
        from pydantic import TypeAdapter

        parsed = TypeAdapter(model_type).validate_json(text)
    elif text:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
    return BatchResult(
        parsed_output=parsed, usage=getattr(message, "usage", None), content=list(message.content),
    )


class BatchedClient:
    """An Anthropic client whose ``messages.parse`` is batched. Everything a judge reads
    off the client -- ``messages.parse`` only -- is here; nothing else is proxied."""

    def __init__(self, client, **options) -> None:
        self.messages = BatchedMessages(client, **options)
        self.live = client
