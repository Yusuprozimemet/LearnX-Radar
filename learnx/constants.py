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
