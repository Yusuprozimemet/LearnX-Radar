"""Offline tests for the LLM client's NVIDIA circuit breaker. No network: the
OpenAI client is replaced with fakes that time out (NVIDIA) or succeed (Groq)."""
import types

import httpx
import pytest
from openai import APITimeoutError

import config
from learnx import llm


def _resp(content: str):
    """Minimal stand-in for an OpenAI ChatCompletion response."""
    message = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class _FakeClient:
    """Routes create() to a per-provider behaviour and counts the calls."""

    def __init__(self, behavior, counter, label):
        self._behavior, self._counter, self._label = behavior, counter, label
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self._counter[self._label] += 1
        return self._behavior()


def _timeout():
    raise APITimeoutError(request=httpx.Request("POST", "https://example.test/v1"))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Reset the breaker and make retries instant + Groq configured for each test."""
    llm.reset_breaker()
    monkeypatch.setattr(llm, "_RETRY_DELAY_S", 0)
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "nv-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "groq-key")
    yield
    llm.reset_breaker()


def _wire(monkeypatch, counter):
    """Point _client_for at fakes: NVIDIA always times out, Groq always succeeds."""
    def fake_client_for(base_url, api_key):
        if "groq" in base_url:
            return _FakeClient(lambda: _resp("groq-ok"), counter, "groq")
        return _FakeClient(_timeout, counter, "nvidia")

    monkeypatch.setattr(llm, "_client_for", fake_client_for)


def test_breaker_trips_after_two_nvidia_timeouts_then_uses_groq(monkeypatch):
    counter = {"nvidia": 0, "groq": 0}
    _wire(monkeypatch, counter)

    # Call 1: NVIDIA times out twice -> breaker trips mid-call -> Groq serves.
    assert llm.chat([{"role": "user", "content": "hi"}]) == "groq-ok"
    assert llm._nvidia_tripped is True
    assert counter["nvidia"] == 2  # not the full 3 retries — we bailed early
    assert counter["groq"] == 1

    # Call 2: NVIDIA is written off — Groq directly, NVIDIA never touched again.
    assert llm.chat([{"role": "user", "content": "again"}]) == "groq-ok"
    assert counter["nvidia"] == 2  # unchanged
    assert counter["groq"] == 2


def test_no_groq_key_means_no_trip(monkeypatch):
    # With no fallback, dropping NVIDIA would leave nothing — so it must keep trying.
    monkeypatch.setattr(config, "GROQ_API_KEY", None)
    counter = {"nvidia": 0, "groq": 0}
    _wire(monkeypatch, counter)

    with pytest.raises(RuntimeError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert llm._nvidia_tripped is False
    assert counter["nvidia"] == 3  # full retry budget, NVIDIA-only path unchanged
