"""Redact personally identifiable information from collected source text.

Public sources — especially the HN "Who is Hiring?" thread — embed contact PII
(recruiter emails, phone numbers, social handles) in otherwise-technical text.
We scrub it at INGESTION (see main._scrape), before anything is deduped, sent to
the LLM, persisted to the committed repo, linked to Perplexity, or delivered.
One choke point keeps PII out of every downstream sink.

Regex catches structured PII (emails/phones/handles) with high precision; it
does NOT catch free-text names — for those we rely on the extract prompt asking
for skills only, plus the fact that we never persist raw source text.
"""
import re

# Order matters: emails before handles, so "a@b.com" isn't half-eaten by @handle.
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# 8+ digits with common separators; word-boundaried so it won't eat version
# numbers like "3.12" or ports. Conservative by design.
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
# @handle (twitter/telegram/etc.), 2+ chars. Lookbehind avoids matching the
# local part of an email (already redacted) and code like "list@2".
_HANDLE = re.compile(r"(?<![\w@/])@[A-Za-z][A-Za-z0-9_]{1,}")
_CODE_FENCE = re.compile(r"^\s*```")
_DECORATOR_LINE = re.compile(r"^@[A-Za-z_][A-Za-z0-9_]*(?:\(.*\))?$")


def scrub(text: str) -> str:
    """Return text with emails, phone numbers, and @handles redacted."""
    if not text:
        return text
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    if "@" not in text:
        return text
    lines: list[str] = []
    in_code = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if _CODE_FENCE.match(stripped):
            in_code = not in_code
            lines.append(line)
            continue
        if in_code or _DECORATOR_LINE.match(stripped):
            lines.append(line)
            continue
        lines.append(_HANDLE.sub("[handle]", line))
    return "".join(lines)
