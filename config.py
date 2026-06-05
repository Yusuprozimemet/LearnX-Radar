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

# --- Exa web search (optional) — brief grounding, v7 Day 24 ---
# Free key at https://exa.ai. Absent -> the exa channel yields nothing and brief
# grounding falls back to reading the day's own source URLs (keyless, via Jina).
# Never required; the run continues without it.
EXA_API_KEY = os.getenv("EXA_API_KEY")

# --- Follow-up Q&A (Perplexity deep link) ---
# Each delivered lesson links to a Perplexity thread that already contains the
# lesson brief *text* as context, so the user can ask follow-ups / be quizzed
# there (replaces the old /recap bot). We embed the text rather than linking the
# raw brief URL because Perplexity will not reliably fetch an external link, so a
# "read this URL" prompt left it ungrounded. The brief is trimmed to
# FOLLOWUP_BRIEF_CHARS so the encoded query keeps the whole deep-link URL within
# what a Telegram inline button (and Perplexity's query box) accept.
FOLLOWUP_BRIEF_CHARS = 1200
# Raw base URL for the committed briefs/ directory (still committed as the full
# source of truth and referenced from docs; no longer embedded in the deep link).
BRIEFS_RAW_BASE = (
    "https://raw.githubusercontent.com/Yusuprozimemet/LearnX-Radar/main/briefs"
)

# --- Podcast feed + audio hosting (v4) ---
# Lesson MP3s are hosted as assets on a single rolling GitHub Release (tag below),
# uploaded by the radar workflow. The feed's <enclosure> and the dashboard's audio
# player both point at RELEASES_AUDIO_BASE + the lesson's audio filename. Releases
# keep audio out of git history and need no credential beyond GITHUB_TOKEN.
REPO_URL = "https://github.com/Yusuprozimemet/LearnX-Radar"
RELEASES_TAG = "lessons"
RELEASES_AUDIO_BASE = f"{REPO_URL}/releases/download/{RELEASES_TAG}"
RELEASES_PAGE_URL = f"{REPO_URL}/releases"  # human-facing list of all lesson assets
# The public Pages site (dashboard + feed are published here).
SITE_URL = "https://yusuprozimemet.github.io/LearnX-Radar/"
FEED_URL = f"{SITE_URL}podcast.xml"

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

# Reddit — open-vocabulary discovery via public weekly RSS (no auth; .rss, not
# .json, which 403s from datacenter IPs). Lanes: AI, software dev, full-stack,
# frontend, backend (infra + data layer), python, java, typescript, plus SaaS /
# startups for product/market-trend discovery. Tune freely — these are the
# discovery surface, not a fixed answer.
REDDIT_SUBREDDITS = [
    "artificial",       # AI
    "ExperiencedDevs",  # software development (high-signal)
    "webdev",           # full stack
    "Frontend",         # frontend
    "devops",           # backend — infra / CI-CD
    "Database",         # backend — database / data layer
    "Python",           # python
    "java",             # java
    "typescript",       # typescript
    "SaaS",             # SaaS — product/market discovery
    "startups",         # startups — product/market discovery
]
REDDIT_LIMIT = 15  # top posts per subreddit per week

# Hacker News front page (Algolia) — what devs are reading right now.
# No extra config; the front_page tag returns ~30 stories.

# Lobste.rs — curated, invite-only community; higher signal/noise than dev.to.
LOBSTERS_LIMIT = 25  # hottest stories pulled from the front-page RSS

# --- Gap scoring: per-source weight (favors real job-market demand over buzz) ---
# Tunable here without touching gap_scorer logic. Used as:
#   demand_weight = sum(weight of each distinct source mentioning a skill)
#   score         = demand_weight * novelty
SOURCE_WEIGHTS = {
    "HN Hiring": 2.0,        # real employer demand — strongest signal
    "Stack Overflow": 1.5,   # rising developer questions — real friction
    "GitHub Trending": 1.0,  # emerging tools, but buzz-driven
    "Lobste.rs": 1.0,        # curated discussion, high signal/noise
    "HN Front Page": 1.0,    # broad dev attention right now
    "Reddit": 0.75,          # community discovery, noisier than HN/Lobsters
    "dev.to": 0.5,           # community chatter — noisiest
}
DEFAULT_SOURCE_WEIGHT = 1.0  # any source not listed above

# How many top skill mentions to keep AFTER scoring (focuses brief + dashboard).
# With map-reduce extraction this is a post-scoring trim (main.py), not an
# extraction cap — extraction maximizes recall; scoring then keeps the top N.
MAX_SKILL_MENTIONS = 25

# --- Map-reduce extraction (v7 Day 25) ---
# The old single-pass extractor flattened ~430 items into one LLM call that also
# had to tally per-skill sources — capping recall and resting the demand signal on
# LLM arithmetic. Map-reduce instead: chunk -> extract candidates per chunk (LLM,
# recall) -> merge variants (lexical + alias map) -> ATTRIBUTE sources by scanning
# the corpus (deterministic). See specs/v7/day25-mapreduce-extraction.md.
EXTRACTION_MAPREDUCE = True       # False -> legacy single-pass extract (rollback switch)
# EXTRACTION_CHUNK_TOKENS: token budget per map chunk. Set from the exp_extraction.py
# sweep over the real corpus, NOT a guess. Finding: recall (candidates) = 4k:60,
# 6k:60, 8k:45, 12k:43, single-pass:18 (cap 60). 6k ties 4k at the cap with fewer
# LLM calls (5 vs 7); 8k drops to 45. So 6k = largest budget still at max recall =
# the knee. (Attribution is deterministic, so chunk size trades only recall vs cost.)
EXTRACTION_CHUNK_TOKENS = 6000
EXTRACTION_MAX_CANDIDATES = 60    # safety cap on merged candidates before attribution
# Variant merging: lexical normalize (lowercase/strip/collapse) + this alias map.
# Deterministic + debuggable; grow as real variants are observed. (No LLM merge pass
# by decision — can be added later behind a flag if too many merges are missed.)
SKILL_ALIASES = {
    "k8s": "kubernetes",
    "rsc": "react server components",
    "postgres": "postgresql",
    "pg": "postgresql",
    "ts": "typescript",
    "js": "javascript",
}
# Short/ambiguous names where a corpus substring scan is unreliable ("Go" in
# "going", "C" everywhere) — attribute these from the map step's LLM-reported
# sources instead of scanning. Names <=2 chars are treated as ambiguous too.
AMBIGUOUS_SHORT_SKILLS = {"go", "c", "r", "d", "c#", "c++", "ml", "ai", "ci"}

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

# --- Brief grounding (v7 Day 24) ---
# Ground the brief in the REAL text of the sources that surfaced the skill (+ fresh
# Exa results when EXA_API_KEY is set), instead of writing it from the skill name
# alone. brief_writer selects candidate sources, full-reads the top N via the
# keyless Jina reader, and feeds numbered [n] context into Radar's brief prompt.
# See specs/v7/day24-brief-grounding.md.
GROUNDING_ENABLED = True        # False -> legacy ungrounded brief (skill + evidence)
GROUNDING_CANDIDATES = 12       # candidate sources ranked before deciding what to read
# GROUNDING_READ_TOP_N: how many candidates to FULL-READ (Jina) per brief. Set from
# the exp_grounding.py sweep (N in {0,2,3,5,8} over 3 real skills), NOT a guess.
# Finding: brief quality plateaus at N=3 (stable length, all sources cited); N=8 is
# wasteful (model ignores ~3 of 8 sources, brief gets shorter, +60% context tokens).
# Read latency is small (~8s at N=5) so latency doesn't bind. Chosen 5 = the N=3
# plateau + headroom for the blocked/empty Jina reads that occur in production.
GROUNDING_READ_TOP_N = 5
GROUNDING_TEXT_CHARS = 1500     # per-source text cap fed into the brief prompt
GROUNDING_HTTP_TIMEOUT_S = 20   # per Jina/Exa request

# --- Dutch coach (v5) ---
# A second learning track that rides the same daily run: a small A2 Dutch lesson
# (vocab + example sentences + dialogue + audio + spaced-repetition review + a
# recall quiz) delivered alongside the dev lesson. The whole block is guarded in
# main() so a Dutch failure never touches the dev pipeline; set DUTCH_ENABLED=False
# to switch the track off entirely. Vocabulary is anchored to dutch/wordlist.json
# (a frozen, human-reviewed bank) — the LLM only writes sentences around fixed
# words, never invents vocabulary. See specs/v5/ and plan/plan.md.
DUTCH_ENABLED = True
DUTCH_CEFR_START = "A2"              # starting level (auto-advances toward B1 in v6)
DUTCH_NEW_WORDS_PER_DAY = 4          # new words introduced each morning
DUTCH_REVIEW_WORDS_MAX = 6           # cap on due-for-review words pulled into a day
DUTCH_THEME_TECH_TIE_IN = True       # on tech days, tie the lesson to the dev topic

# Spaced repetition for vocab: shorter base than the dev track (SR_BASE_INTERVAL_DAYS
# = 7) because words need tighter early spacing than concept lessons. Intervals widen
# as reps grow: round(base * factor**(reps-1)) -> ~1, 2, 5, 11, 24 ... days.
DUTCH_SR_BASE_INTERVAL_DAYS = 1
DUTCH_SR_SPACING_FACTOR = 2.2

# Dutch TTS voices (edge-tts, no API key) — two co-hosts, slower than native so an
# A2 learner can follow. Speakers reuse the ALEX/MAYA labels of the dev dialogue so
# audio_builder's voice map keys line up.
DUTCH_VOICE_ALEX = "nl-NL-MaartenNeural"
DUTCH_VOICE_MAYA = "nl-NL-ColetteNeural"
DUTCH_TTS_RATE = "-10%"

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
