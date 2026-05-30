"""The audio pipeline — markdown brief to a finished MP3 lesson.

Ported and trimmed from LearnX-CLI (tutor/). The flow:

    curriculum.plan(brief)          -> list[TeachingUnit]
    dialogue.generate(units)        -> list[DialogueLine]
    audio_builder.build(lines, out) -> writes lesson.mp3   (async, edge-tts)

Single LLM provider here too: learnx.llm.chat() talks to NVIDIA NIM. TTS is
edge-tts (no API key). Together these are the whole "no paid API" critical path.
"""
