"""Data-collection agents.

Each agent exposes a single `fetch() -> list[dict]` returning normalized items:

    {
        "id":     "stable-unique-id",   # used for dedup in storage
        "source": "GitHub Trending",    # human-readable origin
        "title":  "...",
        "url":    "...",
        "text":   "...",                # free text for skill extraction
        "meta":   "stars 1.2k · python" # short context line
    }

Agents are independent: one failing must not kill the run (see main.py).
"""
