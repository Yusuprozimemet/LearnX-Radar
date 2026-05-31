"""Central config for LearnX-Radar.

Loads .env locally; in CI the vars come from GitHub secrets. Fails loudly if a
required key is missing, so local and CI behave the same.

Single LLM provider by design: every LLM task in the pipeline goes through the
NVIDIA NIM API (OpenAI-compatible). If the model name changes, the one constant
NVIDIA_MODEL below is the only edit needed (see plan/plan.md).
"""
import os

# python-dotenv is optional: it only loads .env for local runs. The dashboard /
# podcast-feed build (`python -m dashboard`) imports this module for its constants
# in a dependency-free CI job where dotenv isn't installed — don't hard-fail there.
try:
    from dotenv import load_dotenv

    load_dotenv()  # loads .env locally; no-op in CI where .env doesn't exist
except ModuleNotFoundError:
    pass

# --- LLM: NVIDIA NIM (OpenAI-compatible, free tier, 40 RPM) ---
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Was z-ai/glm-5.1 (plan's original pick) but its inference endpoint hangs
# intermittently on the free tier — even a 10-token call times out at 90s, while
# every other model on the same key responds in <1s. Switched to llama-3.3-70b:
# ~6s for a brief, reliable, plenty capable for extraction/brief/curriculum.
# Swapping the model is a one-line change by design (see plan/plan.md).
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"

# --- Telegram delivery ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Email delivery (Gmail SMTP) ---
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")

# --- GitHub API (optional) ---
# A token raises the GitHub API rate limit from 60 to 5000 req/hr. In Actions
# the built-in GITHUB_TOKEN is passed automatically. Not required locally.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- Follow-up Q&A (Perplexity deep link) ---
# Each delivered lesson links to a Perplexity thread pre-loaded with that day's
# committed brief, so the user can ask follow-up questions there (replaces the
# old /recap bot). This is the raw base URL for the briefs/ directory.
BRIEFS_RAW_BASE = (
    "https://raw.githubusercontent.com/Yusuprozimemet/LearnX-Radar/main/briefs"
)

# --- Podcast feed (v4) ---
# Lesson MP3s are hosted as assets on a single rolling GitHub Release (tag below),
# uploaded by the radar workflow. The feed's <enclosure> points at this base +
# the lesson's audio filename. Releases keep audio out of git history and need no
# credential beyond the workflow's GITHUB_TOKEN. The public Pages site (where the
# feed and dashboard are published) is SITE_URL.
RELEASES_TAG = "lessons"
RELEASES_AUDIO_BASE = (
    f"https://github.com/Yusuprozimemet/LearnX-Radar/releases/download/{RELEASES_TAG}"
)
SITE_URL = "https://yusuprozimemet.github.io/LearnX-Radar/"

# --- Data sources (all free, no paid APIs) ---
# Languages/topics to watch on GitHub Trending — proxy for emerging tools.
TRENDING_LANGUAGES = ["python", "typescript", "rust", "go"]
TRENDING_SINCE = "daily"  # daily | weekly | monthly

# dev.to tags whose RSS feeds we pull for community buzz.
DEVTO_TAGS = ["ai", "webdev", "devops", "python", "rust"]
DEVTO_LIMIT = 10  # top posts per tag

# Stack Overflow tags to track week-over-week question frequency deltas.
STACKOVERFLOW_TAGS = ["python", "rust", "kubernetes", "langchain", "duckdb"]

# Hacker News "Who is Hiring?" — employer skill demand via the Algolia API.
HN_HIRING_LIMIT = 100  # comments to scan from the latest hiring thread

# --- Gap scoring: per-source weight (favors real job-market demand over buzz) ---
# Tunable here without touching gap_scorer logic. Used as:
#   demand_weight = sum(weight of each distinct source mentioning a skill)
#   score         = demand_weight * novelty
SOURCE_WEIGHTS = {
    "HN Hiring": 2.0,        # real employer demand — strongest signal
    "Stack Overflow": 1.5,   # rising developer questions — real friction
    "GitHub Trending": 1.0,  # emerging tools, but buzz-driven
    "dev.to": 0.5,           # community chatter — noisiest
}
DEFAULT_SOURCE_WEIGHT = 1.0  # any source not listed above

# How many top skill mentions to keep after extraction (focuses scoring + brief).
MAX_SKILL_MENTIONS = 25

# --- Spaced repetition (v2) ---
# A taught skill is suppressed, then becomes eligible again after a spacing
# interval that widens with each repetition. With base 7 + factor 2 the intervals
# are 7, 14, 28 days... so a topic resurfaces less often the more it's been taught.
SR_BASE_INTERVAL_DAYS = 7
SR_SPACING_FACTOR = 2.0

# Table-stakes skills: too broad/established to be a teachable "gap" (every dev
# already knows them). They appear in every source and would otherwise dominate
# the ranking, drowning out genuinely emerging skills. The scorer multiplies
# their score by TABLE_STAKES_PENALTY so they sink unless nothing else surfaces.
# Tunable here without touching gap_scorer logic. Match is exact (normalized).
TABLE_STAKES_SKILLS = {
    "python", "javascript", "typescript", "java", "go", "golang", "c", "c++",
    "c#", "rust", "ruby", "php", "html", "css", "sql", "bash", "git", "linux",
    "docker", "kubernetes", "react", "node.js", "nodejs", "aws",
}
TABLE_STAKES_PENALTY = 0.1  # 0 = drop entirely; 1 = no penalty

# --- Personalization: the profile the radar scores against (v4) ---
# Tunable here like SOURCE_WEIGHTS / TABLE_STAKES_SKILLS — gap_scorer reads them as
# extra score multipliers. Leave both collections empty to disable personalization
# (the pipeline then behaves exactly as v3: global scoring, identical for everyone).
#
# KNOWN_SKILLS: skills you already have. Sunk like table-stakes so the radar stops
# offering them. Matched exactly, normalized (lowercased + stripped). EDIT THESE.
KNOWN_SKILLS = {"python", "fastapi", "docker"}
# LEARNING_GOALS: topics on your learning path. A skill matching any goal (substring,
# either direction, normalized) is boosted so your goals surface sooner. EDIT THESE.
# COMPOSITION: the scorer multiplies GOAL_BOOST with TABLE_STAKES_PENALTY and
# KNOWN_PENALTY (score = demand x novelty x table_stakes x known x goal). So a skill
# that is BOTH a goal and table-stakes/known is still sunk (1.5 x 0.1 = 0.15) — the
# penalty overrides the boost. Keep these examples disjoint from TABLE_STAKES_SKILLS
# and KNOWN_SKILLS (e.g. "rust" would be a no-op here, since it is table-stakes).
LEARNING_GOALS = ["distributed systems", "wasm", "llm agents"]
KNOWN_PENALTY = 0.1   # multiplier for a KNOWN_SKILLS hit (0 = drop; 1 = no effect)
GOAL_BOOST = 1.5      # multiplier when a skill matches a LEARNING_GOALS entry

# --- Lesson generation ---
LESSON_DURATION_MIN = 5  # target audio length for a daily lesson
LESSON_DIFFICULTY_DEFAULT = "beginner"  # auto-scales in v2 from skill_memory

# A descriptive User-Agent keeps free endpoints (Reddit/SO) from returning 429.
USER_AGENT = "learnx-radar/1.0 (+https://github.com/learnx-radar)"

_REQUIRED = {
    "NVIDIA_API_KEY": NVIDIA_API_KEY,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
    "EMAIL_FROM": EMAIL_FROM,
    "EMAIL_TO": EMAIL_TO,
}


def validate() -> None:
    missing = [name for name, value in _REQUIRED.items() if not value]
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nSet them in .env (local) or GitHub repo secrets (CI)."
        )
