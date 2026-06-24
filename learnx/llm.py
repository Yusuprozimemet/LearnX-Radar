"""LLM client: NVIDIA NIM primary, optional Groq fallback (both OpenAI-compatible).

Used by both the radar (skill extraction, brief writing) and the learnx audio
pipeline (curriculum, dialogue), so it lives here as shared infra.

NVIDIA's free NIM endpoints stall intermittently (a trivial call can time out at
120s x 3 retries). When GROQ_API_KEY is set, chat() exhausts NVIDIA's retries and
then transparently retries the same request on Groq, so a flaky primary can't fail
the daily run. With no Groq key configured the behaviour is NVIDIA-only, unchanged.

Clients are built lazily so importing this module never requires an API key;
config.validate() reports a missing primary key cleanly in main() instead.
"""
import json
import logging
import re
import time

from openai import APITimeoutError, OpenAI

import config

log = logging.getLogger(__name__)

_RETRY_COUNT = 3
_RETRY_DELAY_S = 2.0
# Explicit per-request timeout. Without this the OpenAI SDK defaults to 600s,
# so one stuck NIM call x 3 retries could hang an unattended cron for ~30 min.
# Generous enough for a long generation, short enough to fail fast and retry.
_TIMEOUT_S = 120.0

# Circuit breaker: a degraded-slow (not dead) NVIDIA is the main wall-clock risk —
# it recovers within retries so the fallback never engages, yet each timeout burns
# ~_TIMEOUT_S and the accumulated waiting can blow the job's wall-clock budget. Once
# NVIDIA has timed out this many times in a run, we stop trying it and use Groq
# directly for every remaining call. State is process-global, so it resets naturally
# each run (one `python main.py`); reset_breaker() exists for tests.
_NVIDIA_TRIP_AFTER = 2
_nvidia_timeouts = 0
_nvidia_tripped = False

_clients: dict[str, OpenAI] = {}


def reset_breaker() -> None:
    """Reset the NVIDIA circuit breaker (for tests / explicit reuse in one process)."""
    global _nvidia_timeouts, _nvidia_tripped
    _nvidia_timeouts = 0
    _nvidia_tripped = False


def breaker_state() -> dict:
    """Snapshot of the per-run circuit breaker for the run report (v11 day 40):
    how many NVIDIA timeouts accrued and whether the breaker tripped to Groq. Read
    after a run so the Status tab can show fallback frequency over time."""
    return {"nvidia_timeouts": _nvidia_timeouts, "breaker_tripped": _nvidia_tripped}


def _client_for(base_url: str, api_key: str) -> OpenAI:
    if base_url not in _clients:
        _clients[base_url] = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_TIMEOUT_S,
            max_retries=0,  # we own retries below (with backoff + logging)
        )
    return _clients[base_url]


def _providers() -> list[tuple[str, str, str, str]]:
    """(label, base_url, api_key, model) in priority order. Groq is appended only
    when configured, so an absent key leaves the NVIDIA-only path unchanged. Once the
    circuit breaker has tripped, NVIDIA is dropped entirely and Groq serves alone."""
    nvidia = ("nvidia", config.NVIDIA_BASE_URL, config.NVIDIA_API_KEY, config.NVIDIA_MODEL)
    groq = (
        ("groq", config.GROQ_BASE_URL, config.GROQ_API_KEY, config.GROQ_MODEL)
        if config.GROQ_API_KEY
        else None
    )
    if _nvidia_tripped and groq:  # NVIDIA written off for the rest of the run
        return [groq]
    return [nvidia, groq] if groq else [nvidia]


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> str:
    """One chat completion with retry/backoff, falling back across providers.

    Each provider gets _RETRY_COUNT attempts; if it exhausts them (timeouts,
    5xx) the next provider is tried. Only when every provider fails does this
    raise, aggregating the last error from each so the run report is diagnostic."""
    global _nvidia_timeouts, _nvidia_tripped
    errors: list[str] = []
    for label, base_url, api_key, model in _providers():
        client = _client_for(base_url, api_key)
        for attempt in range(_RETRY_COUNT):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content
                assert content is not None, "LLM returned empty content"
                if label != "nvidia":
                    log.warning("LLM served by fallback provider: %s", label)
                return content
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                # Auth/bad-request won't recover by retrying this provider; record
                # it and move to the next one (a healthy fallback can still serve).
                if status in (400, 401, 403):
                    errors.append(f"{label}: auth/request error ({status}): {exc}")
                    break
                # Circuit breaker: a slow NVIDIA is the main wall-clock risk, so count
                # its timeouts and, once over threshold, write it off for the rest of
                # the run (next _providers() drops it) and abandon it for this call too.
                if label == "nvidia" and isinstance(exc, APITimeoutError):
                    _nvidia_timeouts += 1
                    if _nvidia_timeouts >= _NVIDIA_TRIP_AFTER and config.GROQ_API_KEY:
                        if not _nvidia_tripped:
                            log.warning(
                                "NVIDIA timed out %d times — tripping circuit breaker, "
                                "using Groq for the rest of this run", _nvidia_timeouts,
                            )
                        _nvidia_tripped = True
                        errors.append(f"{label}: {exc}")
                        break  # fall through to Groq (already in this call's provider list)
                if attempt < _RETRY_COUNT - 1:
                    log.warning(
                        "LLM call to %s failed (%s), retrying in %.1fs",
                        label, exc, _RETRY_DELAY_S,
                    )
                    time.sleep(_RETRY_DELAY_S)
                    continue
                errors.append(f"{label}: {exc}")
    raise RuntimeError("LLM call failed across all providers: " + " | ".join(errors))


def parse_json_response(raw: str) -> object:
    """Best-effort extraction of a JSON value from a (possibly fenced) reply."""
    text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from response: {raw[:200]}")
