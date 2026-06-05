"""The Dutch coach — a second daily learning track (v5).

Rides the same daily run as the dev radar: each morning a small A2 Dutch lesson
(themed vocabulary + example sentences + a short dialogue + audio) is built and
delivered alongside the dev lesson, governed by spaced repetition.

Design guardrail: vocabulary is anchored to dutch/wordlist.json — a frozen,
human-reviewed word bank. The LLM only writes sentences/dialogue around a fixed
set of words; it never invents vocabulary at run time. See specs/v5/.
"""
