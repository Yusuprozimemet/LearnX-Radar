"""Render a lesson markdown brief to a PDF (pure-Python via xhtml2pdf).

Telegram audio captions are capped at 1024 chars, so the full lesson can't ride
as the audio caption (this is why the Dutch dialogue was getting cut). We attach
the whole brief as a PDF document instead (sendDocument), giving Telegram
subscribers the same detailed, formatted content the email gets. Pure-Python (no
system libs) so it works unchanged in the Actions cron.
"""
from pathlib import Path

from xhtml2pdf import pisa

from delivery.email_sender import _markdown_to_html

# xhtml2pdf supports a CSS subset — keep it simple: readable serif body, clear
# headings, boxed code. @page gives margins + a small footer.
_CSS = """
@page { size: A4; margin: 2cm 1.8cm; @frame footer { -pdf-frame-content: footer;
        bottom: 1cm; margin-left: 1.8cm; margin-right: 1.8cm; height: 1cm; } }
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #1a1a1a;
       line-height: 1.5; }
h1 { font-size: 19pt; color: #0b6; margin: 0 0 12pt; }
h2 { font-size: 13pt; color: #084; border-bottom: 1px solid #ddd;
     padding-bottom: 3pt; margin: 16pt 0 6pt; }
h3 { font-size: 11.5pt; color: #333; margin: 12pt 0 4pt; }
p, li { font-size: 11pt; }
ul { margin: 4pt 0 4pt 8pt; }
code { font-family: Courier, monospace; font-size: 10pt; background: #f2f4f7; }
pre { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 4px;
      padding: 8pt; font-family: Courier, monospace; font-size: 9.5pt; }
a { color: #06c; }
.footer { color: #999; font-size: 8pt; text-align: center; }
"""


def render_pdf(markdown_text: str, title: str, out_path: str | Path,
               footer: str = "📡 LearnX-Radar") -> Path:
    """Render `markdown_text` to a PDF at `out_path`; return the path."""
    out_path = Path(out_path)
    body = _markdown_to_html(markdown_text or "")
    html = (
        f"<html><head><meta charset='utf-8'><style>{_CSS}</style></head>"
        f"<body>{body}"
        f"<div id='footer' class='footer'>{footer}</div>"
        f"</body></html>"
    )
    with out_path.open("wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF render failed for {title!r}: {result.err} error(s)")
    return out_path
