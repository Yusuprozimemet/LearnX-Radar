"""Delivery channels for the finished lesson.

Each channel exposes `send(lesson)` where lesson carries the MP3 path, title,
skill, and a short summary:

    {"title", "skill", "summary", "mp3_path", "brief_md"}

Channels are independent — one failing must not block the other (see main.py).
"""
