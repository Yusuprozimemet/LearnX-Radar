"""Build a podcast RSS feed (podcast.xml) from committed lesson state (v4).

Each lesson's MP3 is hosted as an asset on a rolling GitHub Release (uploaded by
the radar workflow — see config.RELEASES_AUDIO_BASE); the feed's <enclosure>
points there. The feed itself is tiny static XML, published next to the dashboard
by the Pages workflow, so subscribing in a podcast app routes the daily lesson to
your phone.

Hand-written XML, no dependency — same spirit as the hand-written dashboard HTML.
Pure render from skill_memory.json; the audio files are not committed.
"""
import html
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import config

OUTPUT = Path(__file__).parent / "podcast.xml"

_TITLE = "LearnX-Radar"
_DESCRIPTION = "A daily audio lesson on an emerging developer skill."


def _esc(text: object) -> str:
    """XML-escape text (and quotes, so it is safe in attributes too)."""
    return html.escape(str(text), quote=True)


def _rfc822(iso_date: str) -> str:
    """ISO date -> RFC 822 pubDate (midnight UTC); falls back to now if unparseable."""
    try:
        dt = datetime.fromisoformat(iso_date).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        dt = datetime.now(UTC)
    return format_datetime(dt)


def _lessons(memory: dict, dutch: dict | None = None) -> list[dict]:
    """Every lesson with an audio file, newest first (standard podcast order).

    Dev lessons (skill_memory) and Dutch lessons (dutch_memory, v5) interleave by
    date in one feed. Their audio filenames differ (lesson-* vs dutch-*), so guids
    never collide; Dutch episodes get a 🇳🇱-prefixed title for scannability.
    """
    items = [
        lesson
        for data in memory.get("skills", {}).values()
        for lesson in data.get("lessons", [])
        if lesson.get("audio")
    ]
    if dutch:
        for lesson in dutch.get("lessons", []):
            if not lesson.get("audio"):
                continue
            title = lesson.get("summary") or f"Dutch — {lesson.get('theme', '')}".strip(" —")
            items.append({**lesson, "title": f"🇳🇱 {title}"})
    items.sort(key=lambda lesson: lesson.get("date", ""), reverse=True)
    return items


def _item(lesson: dict) -> str:
    audio = lesson["audio"]
    url = f"{config.RELEASES_AUDIO_BASE}/{audio}"
    # length is unknown at build time (the MP3 isn't committed); 0 is widely
    # accepted by podcast clients for generated feeds.
    return (
        "    <item>\n"
        f"      <title>{_esc(lesson.get('title', audio))}</title>\n"
        f"      <description>{_esc(lesson.get('summary', ''))}</description>\n"
        f"      <pubDate>{_rfc822(lesson.get('date', ''))}</pubDate>\n"
        f'      <guid isPermaLink="false">{_esc(audio)}</guid>\n'
        f'      <enclosure url="{_esc(url)}" type="audio/mpeg" length="0"/>\n'
        "    </item>"
    )


def build_feed(memory: dict, dutch: dict | None = None) -> str:
    """Return the podcast RSS 2.0 document for all recorded lessons (dev + Dutch).

    With no lessons yet, this is a well-formed channel with no <item>s (no crash).
    """
    items = [_item(lesson) for lesson in _lessons(memory, dutch)]
    head = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        "  <channel>",
        f"    <title>{_esc(_TITLE)}</title>",
        f"    <link>{_esc(config.SITE_URL)}</link>",
        f"    <description>{_esc(_DESCRIPTION)}</description>",
        "    <language>en-us</language>",
        f"    <itunes:author>{_esc(_TITLE)}</itunes:author>",
        "    <itunes:explicit>false</itunes:explicit>",
    ]
    tail = ["  </channel>", "</rss>", ""]
    return "\n".join(head + items + tail)


def build_feed_file(out_path: Path = OUTPUT) -> Path:
    """Write podcast.xml from committed state; return the path. Used by `python -m dashboard`."""
    import storage

    out_path = Path(out_path)
    out_path.write_text(
        build_feed(storage.load_memory(), storage.load_dutch_memory()), encoding="utf-8"
    )
    return out_path
