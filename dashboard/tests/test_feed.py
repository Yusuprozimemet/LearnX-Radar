"""Offline tests for the podcast feed builder. Pure render, no network."""
import xml.etree.ElementTree as ET

import config
from dashboard import feed


def _memory(lessons_by_skill):
    return {"version": 1, "skills": {
        skill: {"lessons": lessons} for skill, lessons in lessons_by_skill.items()
    }}


def test_feed_has_channel_and_items_newest_first():
    memory = _memory({
        "Kafka": [{"date": "2026-05-20", "title": "Kafka", "summary": "queues",
                   "audio": "lesson-20260520.mp3"}],
        "Rust": [{"date": "2026-05-29", "title": "Rust", "summary": "ownership",
                  "audio": "lesson-20260529.mp3"}],
    })
    root = ET.fromstring(feed.build_feed(memory))  # parses → well-formed
    channel = root.find("channel")
    assert channel.find("title").text == "LearnX-Radar"

    items = channel.findall("item")
    assert [i.find("title").text for i in items] == ["Rust", "Kafka"]  # newest first

    enc = items[0].find("enclosure")
    assert enc.attrib["url"] == f"{config.RELEASES_AUDIO_BASE}/lesson-20260529.mp3"
    assert enc.attrib["type"] == "audio/mpeg"
    assert "length" in enc.attrib


def test_lessons_without_audio_are_skipped():
    memory = _memory({"Kafka": [
        {"date": "2026-05-20", "title": "Has audio", "audio": "a.mp3"},
        {"date": "2026-05-21", "title": "No audio", "audio": ""},
    ]})
    items = ET.fromstring(feed.build_feed(memory)).find("channel").findall("item")
    assert [i.find("title").text for i in items] == ["Has audio"]


def test_empty_memory_is_valid_empty_channel():
    root = ET.fromstring(feed.build_feed({"version": 1, "skills": {}}))
    assert root.find("channel").findall("item") == []


def test_feed_escapes_special_characters():
    memory = _memory({"C#": [
        {"date": "2026-05-20", "title": "C# & <generics>", "summary": "a < b && c",
         "audio": "lesson-20260520.mp3"},
    ]})
    # If escaping were wrong the document would not parse; assert the round-trip too.
    item = ET.fromstring(feed.build_feed(memory)).find("channel").find("item")
    assert item.find("title").text == "C# & <generics>"
    assert item.find("description").text == "a < b && c"


def test_build_feed_file_writes(tmp_path, monkeypatch):
    out = tmp_path / "podcast.xml"
    monkeypatch.setattr("storage.load_memory", lambda: _memory(
        {"Rust": [{"date": "2026-05-29", "title": "Rust", "audio": "r.mp3"}]}
    ))
    path = feed.build_feed_file(out)
    assert path.exists()
    assert ET.fromstring(path.read_text(encoding="utf-8")).find("channel").find("item") is not None
