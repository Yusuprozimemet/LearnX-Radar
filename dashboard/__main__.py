"""`python -m dashboard` — rebuild the static dashboard + podcast feed from state.

Used by the GitHub Pages workflow (no API keys, no full run needed).
"""
from dashboard import builder, feed

if __name__ == "__main__":
    path = builder.build_from_state()
    print(f"wrote {path}")
    feed_path = feed.build_feed_file()
    print(f"wrote {feed_path}")
