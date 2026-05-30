"""Make written text speakable. General code→speech, not Java-specific.

The dialogue model is told to avoid symbols, but this is a safety net so stray
operators or markdown never get read aloud literally as "asterisk asterisk".
"""
import re

# (pattern, replacement) — applied in order.
_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"```[\w]*", " "),                 # code fences
    (r"`", ""),                          # inline-code backticks
    (r"!=", " not equal to "),
    (r"(?<![=!<>])==(?![=])", " double equals "),
    (r"=>", " arrow "),
    (r"->", " arrow "),
    (r"&&", " and "),
    (r"\|\|", " or "),
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\betc\.", "and so on"),
    (r"\bvs\.?\b", "versus"),
    (r"\(\)", ""),                       # empty call parens, e.g. foo()
    (r"#+\s*", ""),                       # stray markdown headings
    (r"\*+", ""),                          # stray markdown emphasis
    (r"\s{2,}", " "),                     # collapse whitespace
]


def apply(text: str) -> str:
    for pattern, replacement in _SUBSTITUTIONS:
        text = re.sub(pattern, replacement, text)
    return text.strip()
