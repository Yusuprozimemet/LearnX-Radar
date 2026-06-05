"""Load Dutch prompt templates from dutch/prompts/ (same convention as radar/)."""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")
