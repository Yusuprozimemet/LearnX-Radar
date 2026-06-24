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
# Free-tier NIM inference endpoints hang intermittently per-model: a trivial
# 5-token call can time out at 30s+ while the catalog GET on the same key returns
# in <1s. It has bitten three picks in a row (z-ai/glm-5.1 -> llama-3.3-70b ->
# llama-3.1-70b recovered). Now on llama-3.1-70b: ~1s for a tiny call, 70B for
# quality, currently reliable. If this one starts hanging too, swap to the next
# responsive model — it's a one-line change by design (see plan/plan.md).
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"

# --- LLM fallback: Groq (OpenAI-compatible) ---
# Optional safety net: when every NVIDIA retry times out (the free NIM endpoints
# stall intermittently), learnx.llm.chat() transparently retries on Groq instead,
# so a flaky primary can't fail the daily run. Unset -> NVIDIA only (unchanged).
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

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
WAITLIST_ENABLED = False  # paused: no channel CTA while debugging NIM timeouts
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
# The show page Spotify created from the podcast feed, linked from the dashboard.
SPOTIFY_SHOW_URL = "https://open.spotify.com/show/033tPjkKDj5xF09FQC0Di7"

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
# MOMENTUM_WINDOW_DAYS: lookback window. Tuned 2026-06-20 from 18 days of history
# (exp_momentum.py sweep over {7,10,14,21}d): 7d damps real sustained skills;
# 10d reaches the stable 8-boosted/12-damped regime; 14d and 21d add no new
# separation and start over-smoothing. Knee = 10d.
MOMENTUM_WINDOW_DAYS = 10
MOMENTUM_MAX_BOOST = 1.5           # cap for a sustained, accelerating skill
MOMENTUM_SPIKE_DAMP = 0.9         # multiplier for a skill seen only today (mild)
# MOMENTUM_SEMANTIC_MATCH (v7 day26 vectordb): when True, _momentum links a skill
# to its prior days by embedding-cosine, not just exact canonical name. LEFT OFF
# by design: a 2026-06-20 experiment (scripts/exp_semantic_match.py, lexical and
# NVIDIA-NIM backends) showed no cosine threshold safely separates real variants
# ("AI agents"~"Autonomous AI agents") from related-but-distinct skills NIM rates
# just as close ("PostgreSQL"~"SQLite", "machine learning"~"deep learning"). So
# embeddings advise, humans decide: the live scorer stays on exact name + the
# curated SKILL_ALIASES below, and the matcher runs offline to PROPOSE new alias
# entries for review. Flip True only if you accept some wrong auto-merges.
MOMENTUM_SEMANTIC_MATCH = False
# Cutoff used both by the (off-by-default) live path and as the suggestion floor.
MOMENTUM_SEMANTIC_THRESHOLD = 0.75

# --- Lesson generation ---
LESSON_DURATION_MIN = 5  # target audio length for a daily lesson
LESSON_DIFFICULTY_DEFAULT = "beginner"  # auto-scales in v2 from skill_memory
# LESSON_DIFFICULTY_OVERRIDE: pin every lesson to one level, bypassing the
# per-skill spaced-repetition suggestion (gap_scorer's beginner→intermediate→
# advanced ramp). New skills surface daily, so without this almost every lesson
# lands on "beginner". Set to None to restore the auto-scaling ramp; otherwise
# one of "beginner" | "intermediate" | "advanced".
LESSON_DIFFICULTY_OVERRIDE = "advanced"

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
# GROUNDING_RECENCY_DAYS: Exa results older than this are excluded so grounding
# leans on current discourse (the threads/posts that made the skill trend now),
# not evergreen "what is X" explainers that read like an encyclopedia. The brief
# inherits whatever grounds it, so freshness here is what makes lessons feel
# current and specific rather than generic. None -> no recency filter.
GROUNDING_RECENCY_DAYS = 120

# --- Dutch coach (v5) ---
# A second learning track that rides the same daily run: a small A2 Dutch lesson
# (vocab + example sentences + dialogue + audio + spaced-repetition review + a
# recall quiz) delivered alongside the dev lesson. The whole block is guarded in
# main() so a Dutch failure never touches the dev pipeline; set DUTCH_ENABLED=False
# to switch the track off entirely. Vocabulary is anchored to dutch/wordlist.json
# (a frozen, human-reviewed bank) — the LLM only writes sentences around fixed
# words, never invents vocabulary. See specs/v5/ and plan/plan.md.
DUTCH_ENABLED = True
DUTCH_CEFR_START = "A2"              # starting level (auto-advances toward B1, below)
DUTCH_NEW_WORDS_PER_DAY = 4          # new words introduced each morning
DUTCH_REVIEW_WORDS_MAX = 6           # cap on due-for-review words pulled into a day
DUTCH_THEME_TECH_TIE_IN = True       # on tech days, tie the lesson to the dev topic

# Recall-driven CEFR progression. The engine MEASURES recall but used to teach at a
# fixed level forever (the owner held ~86% recall for weeks yet never left A2). This
# closes that gap: once rolling recall AT the current level clears the bar over enough
# reports, advance one rung — which raises the sentence/grammar complexity the lesson
# prompt asks for (the frozen vocab bank is unchanged; only the wrapping gets harder).
# The target is the inburgering B1, so the ladder caps there. cefr_since (in
# dutch_memory) marks when the current rung began, so only recall at this level counts.
DUTCH_CEFR_PROGRESSION = True        # False -> level stays fixed at DUTCH_CEFR_START
DUTCH_CEFR_LADDER = ("A2", "A2+", "B1")  # one intermediate rung before the B1 goal
DUTCH_CEFR_ADVANCE_RECALL = 0.85     # rolling recall fraction to clear a rung
DUTCH_CEFR_ADVANCE_MIN_REPORTS = 6   # recall reports at this rung before it can advance
DUTCH_CEFR_ADVANCE_MIN_WORDS = 30    # words attempted at this rung (so the rate is real)
DUTCH_CEFR_ADVANCE_WINDOW_DAYS = 30  # rolling window the rate is measured over

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

# Lesson quality signal: the Dutch track measures recall, but nothing told us
# whether the DEV lessons are any good. Same zero-backend loop as the trainer's
# recall feedback: the owner DM's lesson audio carries 1–5 star deep-link buttons
# (https://t.me/<username>?start=lr_<date>_<n>); one tap sends the rating as a
# /start message from the owner's own account, and the next morning's run reads
# it via getUpdates and stamps it on that day's lesson in skill_memory.json.
# Owner-only: buttons render on the DM (not the channel) and ratings from other
# chats are ignored. Needs TELEGRAM_BOT_USERNAME, like the trainer's Save button.
LESSON_RATING_ENABLED = True    # False -> no star buttons, ratings ignored

# Spaced repetition for vocab: shorter base than the dev track (SR_BASE_INTERVAL_DAYS
# = 7) because words need tighter early spacing than concept lessons. Intervals widen
# as reps grow: round(base * factor**(reps-1)) -> ~1, 2, 5, 11, 24 ... days.
DUTCH_SR_BASE_INTERVAL_DAYS = 1
DUTCH_SR_SPACING_FACTOR = 2.2

# Mistake-driven coaching (v10 day 36): the recall data above only retimes spaced
# repetition; the coach lets it change WHAT gets taught. A small LLM reads the
# accrued misses and picks today's focus — which struggling words to pull forward
# and a directive the lesson prompt emphasizes. Detection is deterministic; the one
# LLM call is skipped entirely on a cold start (no struggling words). The coach
# only selects/emphasizes within the frozen bank — it never invents vocabulary.
# See specs/v10/day36-mistake-driven-dutch-coach.md.
DUTCH_COACH_ENABLED    = True   # False -> mechanical selection only (rollback)
DUTCH_COACH_MIN_MISSES = 2      # misses before a word counts as "struggling"
DUTCH_COACH_MAX_FOCUS  = 3      # cap on focus words per lesson (targeted, not a dump)

# Contrast drill for STUCK words (the coach's second tool). Re-exposure alone has a
# ceiling: some words are wrong over and over with no recall ever (email: wrong x3,
# right x0) because they're confused with a neighbour, not unlearned. For a word that's
# net-failing with zero successful recalls, pair it with the word the learner most often
# fails IN THE SAME report (their own confusion signal — deterministic, no LLM, both
# words from the frozen bank) and add a "mind the difference" section + force both into
# review. See dutch/coach.confusable_pairs / render_contrast.
DUTCH_COACH_STUCK_MISSES  = 2   # wrong this many times with ZERO recalls -> "stuck"
DUTCH_COACH_MAX_CONTRAST  = 2   # cap on contrast pairs per lesson

# Adherence streak (dutch_memory["streak"]): how many recent lessons the learner has
# actually completed — counted as the distinct recall-report days within this trailing
# window. The old metric counted consecutive CRON days (≈"did the job run"), which a
# same-day re-run reset to 1 and which ignored the learner entirely; this measures real
# engagement and is robust to batched reports. See storage.state.dutch_recall_adherence.
DUTCH_STREAK_WINDOW_DAYS = 30

# Backlog backpressure (v10 day 37): a lesson with no recall report wasn't finished.
# Letting unfinished lessons pile up while still generating new ones buries the
# learner and lets spaced repetition drift (delivery alone counts a word as "seen").
# After this many consecutive UNSUBMITTED lessons, pause new generation and nudge
# instead; one saved result breaks the streak and resumes it next run. 0 disables
# (always generate). See specs/v10/day37-backlog-backpressure.md.
DUTCH_BACKLOG_PAUSE_AFTER = 5

# Dutch TTS voices (edge-tts, no API key) — two co-hosts, slower than native so an
# A2 learner can follow. Speakers reuse the ALEX/MAYA labels of the dev dialogue so
# audio_builder's voice map keys line up.
# --- Multi-user Dutch personalization (Phase 1) ---
# The Dutch track is single-learner by default (the owner). Set ALLOWED_CHAT_IDS to a
# comma-separated list of Telegram chat ids to let a small, KNOWN group (~5 people)
# each keep their OWN spaced-repetition schedule and a personal cross-day review,
# while still sharing ONE generated lesson + audio (no per-user LLM/TTS cost). The
# owner (TELEGRAM_CHAT_ID) is always included. Empty -> single-user, unchanged.
# Identity is the chat id only - no email, no accounts. See plan/personalization.md.
ALLOWED_CHAT_IDS = [
    c.strip() for c in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if c.strip()
]
DUTCH_MULTIUSER_ENABLED = True   # rollback switch; effective only when ALLOWED_CHAT_IDS is set
# Secret keying each learner's review token (an HMAC of their chat id) that names the
# published review/<token>.json and rides the trainer URL (?u=<token>). The data is
# low-stakes (which words are due) but the token keeps it from being enumerable by raw
# chat id. Falls back to the bot token so it's always stable per deployment.
REVIEW_TOKEN_SECRET = os.getenv("REVIEW_TOKEN_SECRET") or (TELEGRAM_BOT_TOKEN or "learnx-radar")
DUTCH_REVIEW_MAX = 12            # cap on per-user cross-day review items published each run

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


def dutch_user_chat_ids() -> list[str]:
    """Chat ids for the Dutch track: the owner first, then any allowlisted
    learners, de-duped. Empty ALLOWED_CHAT_IDS -> just the owner (unchanged)."""
    ids: list[str] = []
    for cid in [TELEGRAM_CHAT_ID, *ALLOWED_CHAT_IDS]:
        c = str(cid).strip() if cid else ""
        if c and c not in ids:
            ids.append(c)
    return ids


def dutch_multiuser_active() -> bool:
    """True when multi-user is on AND more than just the owner is configured."""
    return DUTCH_MULTIUSER_ENABLED and len(dutch_user_chat_ids()) > 1


def validate() -> None:
    missing = [name for name, value in _REQUIRED.items() if not value]
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nSet them in .env (local) or GitHub repo secrets (CI)."
        )
