"""`python -m dashboard` — rebuild the static dashboard from committed state.

Used by the GitHub Pages workflow (no API keys, no full run needed).
"""
from dashboard import builder

if __name__ == "__main__":
    path = builder.build_from_state()
    print(f"wrote {path}")
