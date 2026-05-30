"""One poll cycle of the /recap bot. I/O (Telegram, file reads) kept separate
from logic (parsing, catalog, brief selection) so the logic tests offline."""
import logging
import re
from pathlib import Path

import requests

import config
from learnx.llm import chat
from storage import load_brief, load_memory

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_BRIEFS = 6          # full briefs to include as context
_BRIEF_TRUNC = 1800      # chars per brief, to bound tokens
_ANSWER_MAX_TOKENS = 800


def _prompt() -> str:
    return (Path(__file__).parent / "prompts" / "recap.txt").read_text(encoding="utf-8")


# --- Telegram I/O ------------------------------------------------------------

def _endpoint(method: str) -> str:
    return _API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)


def fetch_updates() -> list[dict]:
    resp = requests.get(_endpoint("getUpdates"), params={"timeout": 0}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("result", [])


def send_message(text: str) -> None:
    resp = requests.post(
        _endpoint("sendMessage"),
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=20,
    )
    resp.raise_for_status()


def confirm(offset: int) -> None:
    """Acknowledge all updates below `offset` so they aren't returned again."""
    requests.get(_endpoint("getUpdates"), params={"offset": offset, "timeout": 0}, timeout=20)


# --- parsing / Q&A logic (pure) ----------------------------------------------

def recap_questions(updates: list[dict]) -> list[tuple[int, str]]:
    """Return (update_id, question) for /recap messages from our chat only."""
    out: list[tuple[int, str]] = []
    for u in updates:
        msg = u.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat_id != str(config.TELEGRAM_CHAT_ID):
            continue
        if not text.lower().startswith("/recap"):
            continue
        out.append((u["update_id"], text[len("/recap"):].strip()))
    return out


def _catalog(memory: dict) -> str:
    lines = []
    for name, data in memory.get("skills", {}).items():
        last = (data.get("lessons") or [{}])[-1]
        lines.append(
            f"- {name} (taught {data.get('times_taught', 0)}x, last "
            f"{data.get('last_taught', '?')}, level {last.get('difficulty', '?')}): "
            f"{data.get('summary', '')}"
        )
    return "\n".join(lines)


def _select_briefs(question: str, memory: dict) -> str:
    """Pick the briefs most relevant to the question (or the most recent ones).

    One candidate per skill (its latest lesson's brief). If the question names a
    skill, prefer those; otherwise fall back to the most recently taught.
    """
    candidates = []  # (last_taught, skill, brief_file)
    for name, data in memory.get("skills", {}).items():
        last = (data.get("lessons") or [{}])[-1]
        candidates.append((data.get("last_taught", ""), name, last.get("brief", "")))

    q = question.lower()
    matched = [c for c in candidates if _mentions(c[1], q)]
    chosen = matched or sorted(candidates, key=lambda c: c[0], reverse=True)
    chosen = chosen[:_MAX_BRIEFS]

    blocks = []
    for _, name, brief_file in chosen:
        text = load_brief(brief_file).strip()
        if text:
            blocks.append(f"### {name}\n{text[:_BRIEF_TRUNC]}")
    return "\n\n".join(blocks) or "(no full briefs available)"


def _mentions(skill: str, question_lower: str) -> bool:
    tokens = [t for t in re.split(r"[^a-z0-9]+", skill.lower()) if len(t) > 2]
    return any(t in question_lower for t in tokens)


def answer(question: str, memory: dict, chat_fn=chat) -> str:
    if not memory.get("skills"):
        return "You haven't completed any lessons yet — check back after the first daily lesson."
    prompt = _prompt().format(
        catalog=_catalog(memory),
        briefs=_select_briefs(question, memory),
        question=question or "(no question) Summarize what I've learned so far.",
    )
    return chat_fn([{"role": "user", "content": prompt}], max_tokens=_ANSWER_MAX_TOKENS).strip()


# --- orchestration -----------------------------------------------------------

def poll(chat_fn=chat) -> int:
    """Run one cycle. Returns the number of /recap questions answered."""
    updates = fetch_updates()
    if not updates:
        return 0
    questions = recap_questions(updates)
    memory = load_memory()
    for _, question in questions:
        try:
            reply = answer(question, memory, chat_fn)
        except Exception as exc:
            log.warning("answer failed: %s", exc)
            reply = "Sorry — I couldn't answer that right now. Try again shortly."
        try:
            send_message(reply)
        except Exception as exc:
            log.warning("send failed: %s", exc)
    # Confirm ALL fetched updates (even non-/recap) so the queue can't grow.
    confirm(max(u["update_id"] for u in updates) + 1)
    return len(questions)
