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
# Optional public broadcast CHANNEL (e.g. "@learnx_radar" or "-100…"). When set and
# the bot is an admin there, every lesson is also posted to the channel, so anyone
# who joins receives it — Telegram holds the subscriber list, so we store no PII.
# Absent -> delivery goes to TELEGRAM_CHAT_ID only (unchanged).
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
# Optional: a SEPARATE bot token for posting to the channel (e.g. a public
# LearnRadarBot), so the public product is decoupled from the personal bot. The
# bot owning this token must be an admin of TELEGRAM_CHANNEL_ID. Absent -> the
# channel is posted with TELEGRAM_BOT_TOKEN (which must then be the channel admin).
TELEGRAM_CHANNEL_BOT_TOKEN = os.getenv("TELEGRAM_CHANNEL_BOT_TOKEN")
# Attach the FULL lesson as a PDF document (sendDocument) so Telegram subscribers
# get the same detailed content as email — audio captions are capped at 1024 chars
# (which truncated the Dutch dialogue). False -> legacy caption-only behavior.
TELEGRAM_PDF_ENABLED = True
# DM a run report to TELEGRAM_CHAT_ID (owner only, never the channel) when any
# pipeline stage fails. The stage guards keep the run alive but otherwise leave
# failures buried in Actions logs; this surfaces them. False -> logs only.
RUN_REPORT_ENABLED = True

# --- Waitlist / personalization upsell (channel CTA) ---
# A recurring call-to-action posted to the channel inviting subscribers to a hosted
# waitlist form (we store NO data — the form provider does). Piggybacks the daily
# cron: posts only on WAITLIST_POST_WEEKDAY, channel-only.
WAITLIST_ENABLED = True
WAITLIST_URL = os.getenv("WAITLIST_URL", "")  # Tally/Forms PUBLIC link; empty -> skip
WAITLIST_POST_WEEKDAY = 3  # date.weekday(): Mon=0 … Thu=3 … Sun=6
WAITLIST_MESSAGE = (
    "🚀 <b>Want lessons tailored to you?</b>\n\n"
    "Daily lessons here are the same for everyone. Early access gets you lessons "
    "matched to <b>your stack &amp; goals</b>, with spaced-repetition review and "
    "mastery quizzes that track what you've actually learned.\n\n"
    "👉 <b>Join the waitlist</b> (individuals &amp; teams): {url}"
)

# --- dev.to auto cross-post (reach + SEO) ---
# Cross-post the lesson brief as a dev.to article. dev.to is a community platform,
# so this runs WEEKLY (not daily) and creates a DRAFT by default for review. One
# authenticated POST to the Forem API. No key / disabled / wrong weekday -> no-op.
DEVTO_API_KEY = os.getenv("DEVTO_API_KEY")  # dev.to → Settings → Extensions → API Keys
DEVTO_PUBLISH_ENABLED = True
DEVTO_POST_WEEKDAY = 0      # weekly cadence (Mon); not daily — respects the community
DEVTO_PUBLISHED = False     # False = create as DRAFT for review; True = publish live
DEVTO_POST_TAGS = ["programming", "learning", "career"]  # <=4, lowercase (Forem rule)

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
TRAINER_URL = f"{SITE_URL}dutch.html"  # interactive Delft trainer (v9 day 32)
OG_IMAGE_URL = f"{SITE_URL}og.png"  # social-share preview (pages.yml copies image.png)
# Public Telegram channel — a constant (not the TELEGRAM_CHANNEL_ID secret) so the
# dashboard/Pages build, which runs without secrets, can still link it.
CHANNEL_URL = "https://t.me/learnradar"

# Podcast directory metadata (Apple Podcasts / Spotify require these in the feed).
PODCAST_IMAGE_URL = f"{SITE_URL}cover.png"   # square artwork >=1400px (pages.yml copies it)
PODCAST_CATEGORY = "Technology"
PODCAST_OWNER_NAME = "Yusup Rozimemet"
PODCAST_OWNER_EMAIL = "yusuf.rozimemet@gmail.com"  # used by Apple to verify ownership

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

# --- Cross-day momentum (v7 Day 26, Phase 3a) ---
# Reward skills genuinely RISING over time, not one-day spikes. gap_scorer looks
# back over MOMENTUM_WINDOW_DAYS of trending_history (matched by canonical name,
# alias-aware) and folds a momentum multiplier into the score:
#   score = demand x novelty x table_stakes x known x goal x MOMENTUM
# Sustained + accelerating -> boost (up to MAX_BOOST); seen only today -> SPIKE_DAMP.
# Orthogonal to novelty (that's "have WE taught it"; this is "is the WORLD rising").
# See specs/v7/day26-momentum-and-vectordb.md.
MOMENTUM_ENABLED = True            # False (or no history) -> multiplier 1.0 (rollback)
# MOMENTUM_WINDOW_DAYS: lookback window. PROVISIONAL — the tuning sweep
# (scripts/exp_momentum.py) needs ~14+ days of post-Phase-2 history to be
# meaningful; revisit once the cron has accrued it.
MOMENTUM_WINDOW_DAYS = 14
MOMENTUM_MAX_BOOST = 1.5           # cap for a sustained, accelerating skill
MOMENTUM_SPIKE_DAMP = 0.9         # multiplier for a skill seen only today (mild)

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

# --- Delftse methode (v9) ---
# Restructure the Dutch MP3 into listen -> repeat -> listen-again blocks: every
# sentence is followed by a silent pause sized for the learner to SAY it back,
# then plays again for self-checking (Phase 1: imitation). A deterministic cloze
# exercise — today's new words blanked out of the lesson text — adds the
# production step (Phase 2). See specs/v9/day30-delft-audio.md / day31-delft-cloze.md.
DUTCH_DELFT_AUDIO = True        # False -> legacy v5 audio layout (rollback)
DUTCH_DELFT_PAUSE_FACTOR = 1.5  # repeat-pause = 1.5x the sentence duration
DUTCH_DELFT_MIN_PAUSE_MS = 1200 # floor so one-word sentences still leave time
DUTCH_CLOZE_ENABLED = True      # False -> lesson markdown unchanged (rollback)
# Interactive Delft trainer (v9 day 32): the daily run commits the lesson as
# storage/dutch_lesson.json; the static dashboard/dutch.html page on Pages reads it
# and runs the phases interactively (tap-to-play sentences, checked cloze, enforced
# one-chance listening). See specs/v9/day32-delft-trainer.md.
DUTCH_TRAINER_ENABLED = True    # False -> no lesson JSON, no trainer link (rollback)

# Recall feedback into spaced repetition (v9 day 33): the trainer page's "Save
# results" button deep-links to the bot (https://t.me/<username>?start=dr_…) so the
# learner's own /start message carries the trainer scores back; the next morning's
# run reads them via getUpdates and folds them into dutch_memory. No webhook, no
# token in the browser — the page only builds a URL. Owner-only for now (reports
# are accepted from TELEGRAM_CHAT_ID alone). See specs/v9/day33-recall-feedback.md.
DUTCH_RECALL_ENABLED = True     # False -> no Save button, no getUpdates ingestion
# The MAIN bot's public @username (without the @) — needed because the static page
# can't know it (the token is a secret; a username is not). Empty -> the trainer
# simply doesn't render the Save-results button.
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

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
