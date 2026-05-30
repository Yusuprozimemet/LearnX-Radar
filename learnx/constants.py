"""Audio + curriculum constants. Trimmed from LearnX-CLI (tutor/constants.py)."""

# --- Curriculum sizing ---
WPM = 130                 # spoken words per minute (edge-tts default-ish pace)
OVERHEAD_WORDS = 120      # intro + transitions + outro, not in unit budgets
MIN_UNIT_WORDS = 120      # floor so no unit is too thin to be a real beat
MAX_UNITS = 6
MIN_UNITS = 3

# --- Voices (two co-hosts) ---
VOICE_ALEX = "en-US-GuyNeural"     # male co-host
VOICE_MAYA = "en-US-JennyNeural"   # female co-host
RATE_ALEX = "+0%"
RATE_MAYA = "+5%"

# --- Silence gaps between rendered segments (milliseconds) ---
SILENCE_BREATH_MS = 150   # same speaker, consecutive lines
SILENCE_TURN_MS = 450     # speaker change within a unit
SILENCE_UNIT_MS = 1000    # between units

# --- TTS concurrency ---
TTS_SEMAPHORE_LIMIT = 8
DIALOGUE_MAX_WORKERS = 4  # concurrent per-unit LLM calls

# --- Difficulty (v2): how a lesson deepens on repeat encounters ---
DIFFICULTY_CONTEXT: dict[str, str] = {
    "beginner": (
        "The listener is new to this topic. Assume no prior exposure: define "
        "terms, lead with intuition and analogies, and keep each unit on one "
        "idea. Keep complexity modest (max 2)."
    ),
    "intermediate": (
        "The listener has met this topic before. Assume the basics; skip "
        "definitions and go a level deeper into mechanics, trade-offs, and the "
        "mistakes people make."
    ),
    "advanced": (
        "The listener knows this well. Focus on edge cases, performance, design "
        "trade-offs, and production gotchas. Be concise and precise."
    ),
}
DEFAULT_DIFFICULTY = "beginner"
