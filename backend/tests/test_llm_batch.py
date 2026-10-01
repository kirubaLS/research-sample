"""app.llm_batch: the Batches API behind the live ``messages.parse`` signature."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from pydantic import BaseModel

from app.llm import estimate_usd
from app.llm_batch import BatchedClient


class _Answer(BaseModel):
    section: str
    rationale: str


class _FakeBatches:
    """A batch endpoint that answers each request from its own prompt text."""

    def __init__(self, *, fail_custom_text: str | None = None, polls_before_end: int = 1):
        self.created: list[list[dict]] = []
        self.fail_custom_text = fail_custom_text
        self.polls_before_end = polls_before_end
        self._polls = 0

    def create(self, *, requests):
        self.created.append(list(requests))
        return SimpleNamespace(id=f"batch-{len(self.created)}", processing_status="in_progress")

    def retrieve(self, batch_id):
        self._polls += 1
        ended = self._polls >= self.polls_before_end
        return SimpleNamespace(id=batch_id, processing_status="ended" if ended else "in_progress")

    def cancel(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status="canceling")

    def results(self, batch_id):
        requests = self.created[int(batch_id.split("-")[1]) - 1]
        for r in requests:
            text = r["params"]["messages"][0]["content"]
            if self.fail_custom_text and self.fail_custom_text in text:
                yield SimpleNamespace(
                    custom_id=r["custom_id"],
                    result=SimpleNamespace(type="errored", error=SimpleNamespace(type="invalid_request")),
                )
                continue
            body = f'{{"section": "{text[-3:]}", "rationale": "from the batch"}}'
            message = SimpleNamespace(
                content=[SimpleNamespace(type="text", text=body)],
                usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=5),
            )
            yield SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(type="succeeded", message=message))


def _client(**kw):
    batches = _FakeBatches(**kw)
    return BatchedClient(SimpleNamespace(messages=SimpleNamespace(batches=batches)), linger=0.2, poll=0.01), batches


def test_concurrent_callers_share_one_batch_and_each_gets_its_own_answer():
    client, batches = _client()
    out: dict[str, object] = {}

    def ask(n: int):
        out[str(n)] = client.messages.parse(
            model="claude-sonnet-5", max_tokens=100, system="s",
            messages=[{"role": "user", "content": f"question {n} -> 1.{n}"}],
            output_format=_Answer, output_config={"effort": "low"},
        )

    threads = [threading.Thread(target=ask, args=(n,)) for n in range(1, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(batches.created) == 1, "three callers arriving together form one batch"
    assert {r["custom_id"] for r in batches.created[0]} and len(batches.created[0]) == 3
    params = batches.created[0][0]["params"]
    assert params["output_config"]["effort"] == "low"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert "section" in params["output_config"]["format"]["schema"]["properties"]
    assert "output_format" not in params
    for n in range(1, 4):
        r = out[str(n)]
        assert r.parsed_output == _Answer(section=f"1.{n}", rationale="from the batch")
        assert r.usage.cache_read_input_tokens == 5


def test_an_item_the_api_refused_raises_in_its_own_caller_only():
    client, _ = _client(fail_custom_text="bad")
    results: dict[str, object] = {}

    def ask(label: str, text: str):
        try:
            results[label] = client.messages.parse(
                model="m", max_tokens=10, messages=[{"role": "user", "content": text}],
                output_format=_Answer,
            )
        except Exception as exc:  # noqa: BLE001
            results[label] = exc

    threads = [threading.Thread(target=ask, args=("ok", "fine -> 2.1")),
               threading.Thread(target=ask, args=("bad", "bad one -> 2.2"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert isinstance(results["bad"], RuntimeError) and "errored" in str(results["bad"])
    assert results["ok"].parsed_output.section == "2.1"


def test_calls_arriving_after_a_batch_closed_form_the_next_batch():
    client, batches = _client()
    first = client.messages.parse(model="m", max_tokens=10,
                                  messages=[{"role": "user", "content": "a -> 3.1"}], output_format=_Answer)
    time.sleep(0.05)
    second = client.messages.parse(model="m", max_tokens=10,
                                   messages=[{"role": "user", "content": "b -> 3.2"}], output_format=_Answer)
    assert len(batches.created) == 2
    assert (first.parsed_output.section, second.parsed_output.section) == ("3.1", "3.2")
    assert client.messages.batches == 2


def test_a_batch_that_outlives_its_deadline_raises_in_every_caller():
    batches = _FakeBatches(polls_before_end=10_000)
    client = BatchedClient(SimpleNamespace(messages=SimpleNamespace(batches=batches)),
                           linger=0.05, poll=0.01, max_wait=0.1)
    try:
        client.messages.parse(model="m", max_tokens=10,
                              messages=[{"role": "user", "content": "x -> 4.1"}], output_format=_Answer)
    except TimeoutError as exc:
        assert "did not finish" in str(exc)
    else:
        raise AssertionError("expected a timeout")


def test_the_estimate_follows_list_price_and_halves_for_a_batch():
    live = estimate_usd("claude-sonnet-5", 1_000_000, 100_000, 2_000_000)
    assert live == 2.0 + 1.0 + 0.4
    assert estimate_usd("claude-sonnet-5", 1_000_000, 100_000, 2_000_000, batched=True) == 1.7
    assert estimate_usd("claude-opus-5", 1_000_000, 0) == 5.0
    assert estimate_usd("some-unknown-model", 1_000_000, 0) == 2.0, "an unknown model prices as Sonnet"
