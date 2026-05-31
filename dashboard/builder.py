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
from datetime import date
from pathlib import Path

import config

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
) -> Path:
    """Render the dashboard to `out_path` and return it.

    `history` is {date: {"today_skill": str|None, "scored": [...]}} for the date
    picker. When absent (e.g. the live in-run build), today's `scored` is wrapped
    into a single-day history so the page still renders the current day.
    """
    scored = scored or []
    if not history:
        history = {date.today().isoformat(): {"today_skill": today_skill, "scored": scored}}
    skills = memory.get("skills", {})
    body = "\n".join(
        [
            _trending_html(history),
            _coverage_html(skills),
            _gaps_html(scored, skills),
            _archive_html(skills),
        ]
    )
    out_path = Path(out_path)
    out_path.write_text(_page("LearnX-Radar", body), encoding="utf-8")
    return out_path


def build_from_state(out_path: Path = OUTPUT) -> Path:
    """Rebuild the dashboard from committed state files only — no run, no API keys.

    This is what the GitHub Pages workflow calls: it reads skill_memory.json, the
    per-day rankings (trending_history.json) and the last run's ranking
    (last_scored.json, as a fallback before any history accrues).
    """
    import storage

    state = storage.load_last_scored()
    return build(
        storage.load_memory(),
        state.get("scored", []),
        state.get("today_skill"),
        out_path,
        history=storage.load_trending_history(),
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


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
  body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:880px;
         margin:2rem auto; padding:0 1rem; color:#1f2328; line-height:1.5; }}
  h1 {{ margin-bottom:0; }} .sub {{ color:#888; margin-top:.25rem; }}
  section {{ margin:2.5rem 0; }} h2 {{ border-bottom:1px solid #eee; padding-bottom:.3rem; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid #f0f0f0; }}
  th {{ color:#666; font-size:.85rem; text-transform:uppercase; letter-spacing:.03em; }}
  .muted {{ color:#999; }}
  .card {{ border:1px solid #eee; border-radius:8px; padding:.8rem 1rem; margin:.6rem 0; }}
  .card .meta {{ color:#888; font-size:.8rem; }} .card .title {{ font-weight:600; }}
  .ctrl {{ display:inline-block; color:#666; font-size:.9rem; margin-bottom:.8rem; }}
  .ctrl select {{ font:inherit; margin-left:.3rem; padding:.15rem .3rem; }}
  details > summary {{ cursor:pointer; color:#2563eb; margin:.6rem 0; }}
  .nav {{ margin:.5rem 0 0; font-size:.9rem; }} .nav a {{ color:#2563eb; margin-right:1rem; }}
  audio {{ outline:none; }}
</style></head><body>
<h1>📡 LearnX-Radar</h1>
<p class="sub">Skill radar · generated {date.today():%b %d, %Y}</p>
<p class="nav">
  <a href="{_esc(config.FEED_URL)}">🎧 Podcast feed</a>
  <a href="{_esc(config.RELEASES_PAGE_URL)}">📦 All lesson audio (Releases)</a>
</p>
{body}
</body></html>"""
