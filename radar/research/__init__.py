"""Brief-grounding helpers, vendored from LearnX-Search (v7 Day 24).

A minimal subset of LearnX-Search's gather->read->synthesize machinery, copied
(not imported — both projects ship a top-level `config.py`, so a clean
cross-import is impossible) and rewired to Radar's config + learnx.llm. We reuse
the *machinery* only; the brief prompt/structure stays Radar's (radar/brief_writer
owns synthesis so the audio pipeline's section parsing keeps working).

Exposed: web (keyless Jina reader), exa (key-gated search), filter_relevant +
format_context (pure, no LLM). See specs/v7/day24-brief-grounding.md.
"""
from radar.research import exa, web
from radar.research.synth import filter_relevant, format_context

__all__ = ["web", "exa", "filter_relevant", "format_context"]
