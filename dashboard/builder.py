"""Build the static dashboard HTML (v3).

Shows trending skills this week, your coverage map from skill_memory.json, gap
highlights, and the lesson archive with audio players. Pure render from state
files — deferred until v3 (see plan/plan.md).

STATUS: v3 stub.
"""
from pathlib import Path

OUTPUT = Path(__file__).parent / "index.html"


def build(memory: dict, lessons: list[dict]) -> None:
    """Render the dashboard to dashboard/index.html for GitHub Pages."""
    raise NotImplementedError("v3: render static dashboard from state")
