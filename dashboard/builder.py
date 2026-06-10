"""Build the static skill-radar dashboard (v3).

One self-contained HTML page, regenerated each run: a trending-skills radar with
a per-day date picker, your coverage map, gap highlights, and a collapsible
lesson archive. Pure render from `skill_memory.json` + the per-day rankings in
`trending_history.json` — no backend, no JS framework, no dependencies (the only
JS is a few lines of vanilla DOM-swapping for the date picker).

The archive is metadata-only by design: lesson audio is delivered via Telegram
and email, not hosted on the web (keeps the project free-tier-forever, no
external storage credentials). The MP3 filename is still recorded per lesson as
provenance, in case web hosting is added later.
"""
import html
import json
import math
from datetime import date, timedelta
from pathlib import Path

import config
from dutch import wordlist as dutch_wordlist

OUTPUT = Path(__file__).parent / "index.html"
_TRENDING_TOP = 12
_GAP_TOP = 10
_ARCHIVE_RECENT = 5  # lessons shown before the rest collapse into a dropdown
_RADAR_AXES = 6      # how many top skills get an axis on the radar
_RADAR_W = 480       # SVG viewBox width — wider than tall so side labels fit
_RADAR_H = 320       # SVG viewBox height
_RADAR_R = 110       # outer-ring radius within the viewBox
_RADAR_LABEL_MAX = 20  # chars before a label is truncated (full text on hover)


def build(
    memory: dict,
    scored: list[dict] | None = None,
    today_skill: str | None = None,
    out_path: Path = OUTPUT,
    history: dict | None = None,
    dutch: dict | None = None,
) -> Path:
    """Render the dashboard to `out_path` and return it.

    `history` is {date: {"today_skill": str|None, "scored": [...]}} for the date
    picker. When absent (e.g. the live in-run build), today's `scored` is wrapped
    into a single-day history so the page still renders the current day. `dutch` is
    the Dutch SR memory (v5); when present a second tab renders the Dutch progress.
    """
    scored = scored or []
    if not history:
        history = {date.today().isoformat(): {"today_skill": today_skill, "scored": scored}}
    skills = memory.get("skills", {})
    radar_body = "\n".join(
        [
            _trending_html(history),
            _coverage_html(skills),
            _gaps_html(scored, skills),
            _archive_html(skills),
        ]
    )
    body = _tabs(radar_body, _dutch_html(dutch or {}))
    out_path = Path(out_path)
    out_path.write_text(_page("LearnX-Radar", body), encoding="utf-8")
    return out_path


def build_from_state(out_path: Path = OUTPUT) -> Path:
    """Rebuild the dashboard from committed state files only — no run, no API keys.

    This is what the GitHub Pages workflow calls: it reads skill_memory.json, the
    per-day rankings (trending_history.json), the last run's ranking
    (last_scored.json, as a fallback before any history accrues), and the Dutch SR
    memory (dutch_memory.json) for the Dutch tab.
    """
    import storage

    state = storage.load_last_scored()
    return build(
        storage.load_memory(),
        state.get("scored", []),
        state.get("today_skill"),
        out_path,
        history=storage.load_trending_history(),
        dutch=storage.load_dutch_memory(),
    )


def _tabs(radar_body: str, dutch_body: str) -> str:
    """Top Radar/Dutch nav + the two tab panels. Radar shows by default; clicking a
    button swaps panels (vanilla DOM, same technique as the trending date picker)."""
    nav = (
        "<div class='tabs'>"
        "<button data-tab='radar' class='active'>📡 Radar</button>"
        "<button data-tab='dutch'>🇳🇱 Dutch</button>"
        "</div>"
    )
    script = (
        "<script>(function(){"
        "var links=document.querySelectorAll('.tabs button');"
        "function show(t){"
        "document.getElementById('tab-radar').style.display=(t==='radar')?'':'none';"
        "document.getElementById('tab-dutch').style.display=(t==='dutch')?'':'none';"
        "links.forEach(function(a){a.classList.toggle('active',a.getAttribute('data-tab')===t);})}"
        "links.forEach(function(a){a.addEventListener('click',function(e){"
        "e.preventDefault();show(a.getAttribute('data-tab'));});});"
        "})();</script>"
    )
    return (
        nav
        + f"<div id='tab-radar'>{radar_body}</div>"
        + f"<div id='tab-dutch' style='display:none'>{dutch_body}</div>"
        + script
    )


def _dutch_html(dutch: dict) -> str:
    """The Dutch tab: progress stats, recent words, and a Dutch lesson archive.

    Pure render from dutch_memory.json joined with the committed word bank (for the
    nl/en text, which the SR memory doesn't store). Empty state when nothing yet.
    """
    words = dutch.get("words", {})
    lessons = dutch.get("lessons", [])
    if not words and not lessons:
        return _section("🇳🇱 Dutch", "<p class='muted'>No Dutch lessons yet.</p>")

    bank = {w["id"]: w for w in dutch_wordlist.load()}
    today = date.today().isoformat()
    due = sum(1 for e in words.values() if e.get("due", "") and e["due"] <= today)
    progress = (
        "<div class='stats'>"
        f"<span>Level <strong>{_esc(dutch.get('cefr', 'A2'))}</strong></span>"
        f"<span>Streak <strong>{_esc(dutch.get('streak', 0))}</strong> day(s)</span>"
        f"<span>Words learned <strong>{len(words)}</strong></span>"
        f"<span>Due for review today <strong>{due}</strong></span>"
        f"{_recall_rate_html(dutch.get('recall', []))}"
        "</div>"
    )

    ordered = sorted(words.items(), key=lambda kv: kv[1].get("introduced", ""), reverse=True)
    rows = []
    for wid, entry in ordered[:15]:
        info = bank.get(wid, {})
        rows.append(
            "<tr><td>{nl}</td><td>{en}</td><td>{reps}</td><td>{due}</td></tr>".format(
                nl=_esc(info.get("nl", wid)),
                en=_esc(info.get("en", "")),
                reps=entry.get("reps", 1),
                due=_esc(entry.get("due", "—")),
            )
        )
    table = (
        "<table><tr><th>Word</th><th>Meaning</th><th>Reps</th><th>Next review</th></tr>"
        + "".join(rows)
        + "</table>"
    )

    sections = [_section("🇳🇱 Dutch progress", progress), _section("🆕 Recent words", table)]

    struggling = _struggling_html(words, bank)
    if struggling:
        sections.append(_section("🔁 Struggling words", struggling))

    if lessons:
        ordered_lessons = sorted(lessons, key=lambda lesson: lesson.get("date", ""), reverse=True)
        cards = [
            (
                "<div class='card'>"
                f"<div class='meta'>{_esc(lesson.get('date', ''))} · "
                f"{_esc(lesson.get('theme', ''))}</div>"
                f"<div class='title'>{_esc(lesson.get('summary', '') or 'Dutch lesson')}</div>"
                f"{_player(lesson)}"
                "</div>"
            )
            for lesson in ordered_lessons[:_ARCHIVE_RECENT]
        ]
        sections.append(_section("🗂️ Dutch lessons", "".join(cards)))

    return "\n".join(sections)


def _recall_rate_html(recall: list[dict]) -> str:
    """Rolling 30-day recall rate from the trainer report log (v9 day 33): measured
    production, not exposure — the difference between "the streak is alive" and
    "it's working". Empty string until a first report exists in the window."""
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    right = wrong = 0
    for r in recall:
        if r.get("date", "") >= cutoff:
            right += len(r.get("right", []))
            wrong += len(r.get("wrong", []))
    total = right + wrong
    if not total:
        return ""
    pct = round(100 * right / total)
    return f"<span>Recall (30d) <strong>{pct}% ({right}/{total})</strong></span>"


def _struggling_html(words: dict, bank: dict) -> str:
    """The most-failed words (v9 day 33): recall_wrong desc, then shortest interval
    (nearest due) first — the words the trainer says you can't yet produce. Empty
    string (section omitted) until any word has a failed recall."""
    failed = [
        (wid, e) for wid, e in words.items() if int(e.get("recall_wrong", 0)) > 0
    ]
    if not failed:
        return ""
    failed.sort(key=lambda kv: (-int(kv[1].get("recall_wrong", 0)), kv[1].get("due", "")))
    rows = []
    for wid, entry in failed[:8]:
        info = bank.get(wid, {})
        rows.append(
            "<tr><td>{nl}</td><td>{en}</td><td>{wrong}</td><td>{right}</td><td>{due}</td></tr>".format(
                nl=_esc(info.get("nl", wid)),
                en=_esc(info.get("en", "")),
                wrong=int(entry.get("recall_wrong", 0)),
                right=int(entry.get("recall_right", 0)),
                due=_esc(entry.get("due", "—")),
            )
        )
    return (
        "<table><tr><th>Word</th><th>Meaning</th><th>Failed</th><th>Recalled</th>"
        "<th>Next review</th></tr>" + "".join(rows) + "</table>"
    )


def _esc(text: object) -> str:
    return html.escape(str(text))


def _date_label(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%b %d, %Y")
    except ValueError:
        return iso


def _trending_table(scored: list[dict], today_skill: str | None) -> str:
    if not scored:
        return "<p class='muted'>No fresh data this run.</p>"
    rows = []
    for s in scored[:_TRENDING_TOP]:
        mark = " 🎧 today" if s["skill"] == today_skill else ""
        rows.append(
            "<tr><td>{skill}{mark}</td><td>{score:.2f}</td><td>{demand:.1f}</td><td>{sources}</td></tr>".format(
                skill=_esc(s["skill"]),
                mark=mark,
                score=s.get("score", 0.0),
                demand=s.get("demand_weight", 0.0),
                sources=_esc(", ".join(s.get("sources", []))),
            )
        )
    return (
        "<table><tr><th>Skill</th><th>Score</th><th>Demand</th><th>Sources</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _radar_svg(scored: list[dict]) -> str:
    """Inline SVG spider chart of the top scored skills (radius = score)."""
    pts = [s for s in scored if s.get("score", 0) > 0][:_RADAR_AXES]
    if len(pts) < 3:
        return "<p class='muted'>Need at least 3 scored skills to draw the radar.</p>"
    n = len(pts)
    cx, cy = _RADAR_W / 2, _RADAR_H / 2
    top = max(s.get("score", 0.0) for s in pts) or 1.0

    def coord(i: int, radius: float) -> tuple[float, float]:
        angle = -math.pi / 2 + i * 2 * math.pi / n
        return cx + radius * math.cos(angle), cy + radius * math.sin(angle)

    def polygon(radius_at) -> str:
        pairs = []
        for i in range(n):
            x, y = coord(i, radius_at(i))
            pairs.append(f"{x:.1f},{y:.1f}")
        return " ".join(pairs)

    rings = "".join(
        f"<polygon points='{polygon(lambda i, f=frac: _RADAR_R * f)}' fill='none' stroke='#eee' />"
        for frac in (0.25, 0.5, 0.75, 1.0)
    )
    spokes, labels = [], []
    for i, s in enumerate(pts):
        ex, ey = coord(i, _RADAR_R)
        spokes.append(
            f"<line x1='{cx:.1f}' y1='{cy:.1f}' x2='{ex:.1f}' y2='{ey:.1f}' stroke='#eee' />"
        )
        lx, ly = coord(i, _RADAR_R + 14)
        anchor = "middle" if abs(lx - cx) < 1 else ("end" if lx < cx else "start")
        full = str(s["skill"])
        shown = full if len(full) <= _RADAR_LABEL_MAX else full[: _RADAR_LABEL_MAX - 1] + "…"
        title = f"<title>{_esc(full)}</title>" if shown != full else ""
        labels.append(
            f"<text x='{lx:.1f}' y='{ly:.1f}' text-anchor='{anchor}' "
            f"dominant-baseline='middle' font-size='11' fill='#555'>{title}{_esc(shown)}</text>"
        )
    data = polygon(lambda i: _RADAR_R * (pts[i].get("score", 0.0) / top))
    dots = "".join(
        "<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='#2563eb' />".format(
            x=coord(i, _RADAR_R * (pts[i].get("score", 0.0) / top))[0],
            y=coord(i, _RADAR_R * (pts[i].get("score", 0.0) / top))[1],
        )
        for i in range(n)
    )
    return (
        f"<svg viewBox='0 0 {_RADAR_W} {_RADAR_H}' width='100%' "
        f"style='max-width:480px;display:block;margin:0 auto' "
        f"role='img' aria-label='Top trending skills radar'>"
        f"{rings}{''.join(spokes)}"
        f"<polygon points='{data}' fill='rgba(37,99,235,0.15)' "
        f"stroke='#2563eb' stroke-width='1.5' />"
        f"{dots}{''.join(labels)}</svg>"
    )


def _trending_html(history: dict) -> str:
    dates = sorted((d for d, v in history.items() if v.get("scored")), reverse=True)
    if not dates:
        return _section("📈 Trending today", "<p class='muted'>No fresh data this run.</p>")

    fragments = {
        d: {
            "radar": _radar_svg(history[d]["scored"]),
            "table": _trending_table(history[d]["scored"], history[d].get("today_skill")),
        }
        for d in dates
    }
    latest = dates[0]
    selector = ""
    if len(dates) > 1:
        options = "".join(
            f"<option value='{_esc(d)}'{' selected' if d == latest else ''}>"
            f"{_esc(_date_label(d))}</option>"
            for d in dates
        )
        selector = (
            f"<label class='ctrl'>Showing <select id='trend-date'>{options}</select></label>"
        )
    # Embed the per-day fragments; escape '</' so the HTML can't close the script early.
    payload = json.dumps(fragments, ensure_ascii=False).replace("</", "<\\/")
    inner = (
        f"{selector}"
        f"<div id='trend-radar'>{fragments[latest]['radar']}</div>"
        f"<div id='trend-table'>{fragments[latest]['table']}</div>"
        f"<script id='trend-data' type='application/json'>{payload}</script>"
        "<script>(function(){"
        "var sel=document.getElementById('trend-date');if(!sel)return;"
        "var data=JSON.parse(document.getElementById('trend-data').textContent);"
        "sel.addEventListener('change',function(){var d=data[sel.value];if(!d)return;"
        "document.getElementById('trend-radar').innerHTML=d.radar;"
        "document.getElementById('trend-table').innerHTML=d.table;});"
        "})();</script>"
    )
    return _section("📈 Trending today", inner)


def _coverage_html(skills: dict) -> str:
    if not skills:
        return _section("🧠 Your coverage", "<p class='muted'>No lessons yet.</p>")
    ordered = sorted(skills.items(), key=lambda kv: kv[1].get("last_taught", ""), reverse=True)
    rows = []
    for name, data in ordered:
        last_lesson = (data.get("lessons") or [{}])[-1]
        rows.append(
            "<tr><td>{name}</td><td>{n}</td><td>{last}</td><td>{diff}</td></tr>".format(
                name=_esc(name),
                n=data.get("times_taught", 0),
                last=_esc(data.get("last_taught", "—")),
                diff=_esc(last_lesson.get("difficulty", "—")),
            )
        )
    table = (
        "<table><tr><th>Skill</th><th>Times taught</th><th>Last</th><th>Level</th></tr>"
        + "".join(rows)
        + "</table>"
    )
    return _section("🧠 Your coverage", table)


def _gaps_html(scored: list[dict], skills: dict) -> str:
    """Multi-source demand that you haven't been taught yet — the real gaps."""
    gaps = [
        s
        for s in scored
        if s["skill"] not in skills
        and s.get("frequency", 0) >= 2
        and not s.get("table_stakes")
    ]
    if not gaps:
        return _section("🎯 Gap highlights", "<p class='muted'>No standout gaps this run.</p>")
    items = "".join(
        f"<li><strong>{_esc(s['skill'])}</strong> — {_esc(s.get('evidence', ''))} "
        f"<span class='muted'>({_esc(', '.join(s.get('sources', [])))})</span></li>"
        for s in gaps[:_GAP_TOP]
    )
    return _section("🎯 Gap highlights", f"<ul>{items}</ul>")


def _archive_html(skills: dict) -> str:
    lessons: list[dict] = []
    for data in skills.values():
        lessons.extend(data.get("lessons", []))
    lessons.sort(key=lambda lesson: lesson.get("date", ""), reverse=True)
    if not lessons:
        return _section("🗂️ Lesson archive", "<p class='muted'>No lessons yet.</p>")

    cards = [
        (
            "<div class='card'>"
            f"<div class='meta'>{_esc(lesson.get('date', ''))} · "
            f"{_esc(lesson.get('difficulty', ''))}</div>"
            f"<div class='title'>{_esc(lesson.get('title', ''))}</div>"
            f"<p>{_esc(lesson.get('summary', ''))}</p>"
            f"{_player(lesson)}"
            "</div>"
        )
        for lesson in lessons
    ]
    inner = "".join(cards[:_ARCHIVE_RECENT])
    older = cards[_ARCHIVE_RECENT:]
    if older:
        inner += (
            f"<details><summary>Show {len(older)} older "
            f"lesson{'s' if len(older) != 1 else ''}</summary>"
            + "".join(older)
            + "</details>"
        )
    return _section("🗂️ Lesson archive", inner)


def _player(lesson: dict) -> str:
    """Inline audio player for a lesson, streaming the MP3 from its GitHub Release
    asset. Falls back to the delivery note when a lesson has no recorded audio."""
    audio = lesson.get("audio")
    if not audio:
        return "<div class='meta'>🎧 delivered via Telegram &amp; email</div>"
    src = f"{config.RELEASES_AUDIO_BASE}/{audio}"
    return (
        f"<audio controls preload='none' src='{_esc(src)}' "
        "style='width:100%;margin-top:.5rem'></audio>"
    )


def _section(title: str, inner: str) -> str:
    return f"<section><h2>{_esc(title)}</h2>{inner}</section>"


_OG_TITLE = "LearnX-Radar — daily developer skill radar and lessons"
_OG_DESC = (
    "A free daily developer lesson (plus a Dutch lesson) — what's rising right now, "
    "grounded in real sources and explained. Subscribe free on Telegram."
)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(_OG_DESC)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{_esc(config.SITE_URL)}">
<meta property="og:title" content="{_esc(_OG_TITLE)}">
<meta property="og:description" content="{_esc(_OG_DESC)}">
<meta property="og:image" content="{_esc(config.OG_IMAGE_URL)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(_OG_TITLE)}">
<meta name="twitter:description" content="{_esc(_OG_DESC)}">
<meta name="twitter:image" content="{_esc(config.OG_IMAGE_URL)}">
<style>
  :root {{
    --green:#5fbf38; --green-edge:#48992a; --green-soft:#e8f7e0;
    --blue:#2bb3f0;  --blue-edge:#1f93c7;
    --ink:#3d4350; --grey:#8a909c; --border:#e6e8ec; --bg:#f7f8f5; --card:#fff;
  }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:"Nunito","Segoe UI",-apple-system,Roboto,sans-serif;
         background:var(--bg); max-width:880px; margin:0 auto 4rem;
         padding:0 1rem; color:var(--ink); line-height:1.55; }}
  header.bar {{ display:flex; align-items:center; gap:.7rem; padding:1.1rem 0 .6rem;
                flex-wrap:wrap; }}
  header.bar .owl {{ font-size:1.9rem; }}
  header.bar h1 {{ font-size:1.25rem; margin:0; font-weight:800; }}
  header.bar .meta {{ color:var(--grey); font-size:.85rem; font-weight:700;
                      background:var(--card); border:2px solid var(--border);
                      border-radius:999px; padding:.15rem .7rem; }}
  header.bar a {{ margin-left:auto; color:var(--blue); text-decoration:none;
                  font-weight:800; font-size:.9rem; }}
  .sub {{ color:var(--grey); font-weight:700; margin:.2rem 0 .8rem; font-size:.9rem; }}
  section {{ margin:2rem 0; }}
  h2 {{ font-size:.95rem; font-weight:800; text-transform:uppercase;
        letter-spacing:.05em; color:var(--grey); margin-bottom:.8rem; border:0; padding:0; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--border); }}
  th {{ color:var(--grey); font-size:.82rem; text-transform:uppercase; letter-spacing:.03em;
        font-weight:800; }}
  .muted {{ color:var(--grey); }}
  .card {{ background:var(--card); border:2px solid var(--border); border-radius:16px;
           padding:.8rem 1rem; margin:.6rem 0; }}
  .card .meta {{ color:var(--grey); font-size:.8rem; font-weight:700; }}
  .card .title {{ font-weight:800; color:var(--ink); }}
  .ctrl {{ display:inline-block; color:var(--grey); font-size:.9rem; margin-bottom:.8rem;
           font-weight:700; }}
  .ctrl select {{ font:inherit; margin-left:.3rem; padding:.15rem .3rem;
                  border:2px solid var(--border); border-radius:8px; }}
  details > summary {{ cursor:pointer; color:var(--blue); margin:.6rem 0; font-weight:700; }}
  .nav {{ margin:.5rem 0 .9rem; font-size:.9rem; display:flex; flex-wrap:wrap; gap:.5rem; }}
  .nav a {{ color:var(--blue); font-weight:700; text-decoration:none;
            background:var(--card); border:2px solid var(--border);
            border-radius:999px; padding:.2rem .8rem; }}
  .tabs {{ display:flex; gap:.5rem; margin:.6rem 0 1rem; }}
  .tabs button {{ flex:1; background:var(--card); color:var(--grey); font:inherit;
                  font-weight:800; text-transform:uppercase; letter-spacing:.05em;
                  font-size:.82rem; padding:.55rem; cursor:pointer;
                  border:2px solid var(--border); border-bottom-width:4px; border-radius:14px; }}
  .tabs button:active {{ transform:translateY(2px); border-bottom-width:2px; }}
  .tabs button.active {{ background:var(--green-soft); color:var(--green-edge);
                         border-color:var(--green); }}
  .stats {{ display:flex; flex-wrap:wrap; gap:1.2rem; color:var(--grey); font-size:.95rem;
            font-weight:700; }}
  .stats strong {{ color:var(--ink); }}
  audio {{ outline:none; width:100%; margin-top:.5rem; }}
  .cta {{ margin:.9rem 0 1.2rem; display:flex; align-items:center; flex-wrap:wrap; gap:.5rem; }}
  .cta a {{ display:inline-block; background:var(--blue); color:#fff; padding:.55rem 1rem;
            border:0; border-bottom:4px solid var(--blue-edge); border-radius:14px;
            text-decoration:none; font-weight:800; font-size:.9rem; }}
  .cta a:active {{ transform:translateY(2px); border-bottom-width:2px; }}
  .cta .note {{ color:var(--grey); font-size:.85rem; font-weight:700; }}
  ul {{ padding-left:1.2rem; }}
  li {{ margin:.3rem 0; }}
  li strong {{ color:var(--ink); }}
</style></head><body>
<header class="bar">
  <span class="owl">📡</span>
  <h1>LearnX-Radar</h1>
  <span class="meta">generated {date.today():%b %d, %Y}</span>
  <a href="dutch.html">🇳🇱 Dutch trainer</a>
</header>
<div class="sub">Daily developer skill radar + Dutch lesson</div>
<p class="cta">
  <a href="{_esc(config.CHANNEL_URL)}">📣 Join free on Telegram</a>
  <span class="note">a daily developer lesson (+ Dutch) — audio &amp; PDF</span>
</p>
<p class="nav">
  <a href="{_esc(config.FEED_URL)}">🎧 Podcast feed</a>
  <a href="{_esc(config.RELEASES_PAGE_URL)}">📦 Audio releases</a>
</p>
{body}
</body></html>"""
