"""Build the static skill-radar dashboard (v3).

One self-contained HTML page, regenerated each run: trending skills this week,
your coverage map, gap highlights, and the lesson archive. Pure render from
`skill_memory.json` + the current run's scored mentions — no backend, no JS
framework, no dependencies.

The archive is metadata-only by design: lesson audio is delivered via Telegram
and email, not hosted on the web (keeps the project free-tier-forever, no
external storage credentials). The MP3 filename is still recorded per lesson as
provenance, in case web hosting is added later.
"""
import html
from datetime import date
from pathlib import Path

OUTPUT = Path(__file__).parent / "index.html"
_TRENDING_TOP = 12
_GAP_TOP = 10


def build(
    memory: dict,
    scored: list[dict] | None = None,
    today_skill: str | None = None,
    out_path: Path = OUTPUT,
) -> Path:
    """Render the dashboard to `out_path` and return it."""
    scored = scored or []
    skills = memory.get("skills", {})
    body = "\n".join(
        [
            _trending_html(scored, today_skill),
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

    This is what the GitHub Pages workflow calls: it reads skill_memory.json and
    the last run's ranking (last_scored.json) and renders the full page.
    """
    from storage import load_last_scored, load_memory

    state = load_last_scored()
    return build(
        load_memory(),
        state.get("scored", []),
        state.get("today_skill"),
        out_path,
    )


def _esc(text: object) -> str:
    return html.escape(str(text))


def _trending_html(scored: list[dict], today_skill: str | None) -> str:
    if not scored:
        return _section("📈 Trending this week", "<p class='muted'>No fresh data this run.</p>")
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
    table = (
        "<table><tr><th>Skill</th><th>Score</th><th>Demand</th><th>Sources</th></tr>"
        + "".join(rows)
        + "</table>"
    )
    return _section("📈 Trending this week", table)


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

    cards = []
    for lesson in lessons:
        cards.append(
            "<div class='card'>"
            f"<div class='meta'>{_esc(lesson.get('date', ''))} · "
            f"{_esc(lesson.get('difficulty', ''))}</div>"
            f"<div class='title'>{_esc(lesson.get('title', ''))}</div>"
            f"<p>{_esc(lesson.get('summary', ''))}</p>"
            "<div class='meta'>🎧 delivered via Telegram &amp; email</div>"
            "</div>"
        )
    return _section("🗂️ Lesson archive", "".join(cards))


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
</style></head><body>
<h1>📡 LearnX-Radar</h1>
<p class="sub">Skill radar · generated {date.today():%b %d, %Y}</p>
{body}
</body></html>"""
