"""Single-provider LLM client: NVIDIA NIM (OpenAI-compatible).

Collapses the multi-provider wrapper from LearnX-CLI (tutor/infra/llm.py) down
to one provider, since the whole app standardizes on GLM-5.1 via NVIDIA NIM.
Used by both the radar (skill extraction, brief writing) and the learnx audio
pipeline (curriculum, dialogue), so it lives here as shared infra.

The client is built lazily so importing this module never requires the API key;
config.validate() reports a missing key cleanly in main() instead.
"""
import json
import logging
import re
import time

from openai import OpenAI

import config

log = logging.getLogger(__name__)

_RETRY_COUNT = 3
_RETRY_DELAY_S = 2.0
# Explicit per-request timeout. Without this the OpenAI SDK defaults to 600s,
# so one stuck NIM call x 3 retries could hang an unattended cron for ~30 min.
# Generous enough for a long generation, short enough to fail fast and retry.
_TIMEOUT_S = 120.0

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.NVIDIA_API_KEY,
            base_url=config.NVIDIA_BASE_URL,
            timeout=_TIMEOUT_S,
            max_retries=0,  # we own retries below (with backoff + logging)
        )
    return _client


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> str:
    """One chat completion against config.NVIDIA_MODEL, with retry/backoff."""
    for attempt in range(_RETRY_COUNT):
        try:
            resp = _get_client().chat.completions.create(
                model=config.NVIDIA_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            assert content is not None, "LLM returned empty content"
            return content
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in (400, 401, 403):
                raise RuntimeError(f"Auth/request error ({status}): {exc}") from exc
            if attempt < _RETRY_COUNT - 1:
                log.warning("LLM call failed (%s), retrying in %.1fs", exc, _RETRY_DELAY_S)
                time.sleep(_RETRY_DELAY_S)
                continue
            raise RuntimeError(f"LLM call failed after {_RETRY_COUNT} attempts: {exc}") from exc
    raise RuntimeError("unreachable")


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
