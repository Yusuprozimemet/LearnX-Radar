"""Channel base class.

Vendored from LearnX-Search/learnx_search/channels/base.py (v7 Day 24). Trimmed
to what brief grounding needs: a channel either reads a URL (web) or searches
(exa). Keep the source path noted for future manual sync.
"""
from abc import ABC, abstractmethod

Item = dict  # the shared six-key item contract: id, source, title, url, text, meta


class Channel(ABC):
    """Base class for grounding channels."""

    name: str = ""
    description: str = ""
    language: str = "any"
    backends: list[str] = []
    tier: int = 0  # 0 zero-config, 1 needs free key

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Does this channel own this URL?"""
        ...

    def search(self, query: str, limit: int = 5) -> list[Item]:
        """Discovery search. Read-only channels keep the default (no results)."""
        return []

    def read(self, url: str) -> Item | None:
        """Fetch a single URL. Search-only channels keep the default (None)."""
        return None

    def check(self) -> tuple[str, str]:
        """Backend health. Returns (status, message); status in ok/warn/off/error."""
        return "ok", ", ".join(self.backends) if self.backends else "built-in"
