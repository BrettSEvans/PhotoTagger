#!/usr/bin/env python3
"""
Build a self-contained PDF from a docs Markdown file (screenshots/diagrams
embedded).

Markdown -> HTML (python-markdown) -> PDF (Playwright headless Chromium).
Images are inlined as base64 data URIs so the PDF is fully self-contained.

Usage:
    python docs/build_pdf.py                          # builds the User Guide
    python docs/build_pdf.py USER_GUIDE.md "PhotoTagger User Guide"
    python docs/build_pdf.py ARCHITECTURE.md "PhotoTagger Architecture"
"""

import base64
import mimetypes
import re
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent

# CLI: [markdown_file] [footer_title]
_MD_NAME = sys.argv[1] if len(sys.argv) > 1 else "USER_GUIDE.md"
MD_FILE = DOCS / _MD_NAME
FOOTER_TITLE = sys.argv[2] if len(sys.argv) > 2 else "PhotoTagger User Guide"
OUT_PDF = DOCS / (MD_FILE.stem.replace("_", "-").title().replace("-", "-") + ".pdf")
# Friendlier output names for the two known docs.
_KNOWN = {
    "USER_GUIDE.md": "PhotoTagger-User-Guide.pdf",
    "ARCHITECTURE.md": "PhotoTagger-Architecture.pdf",
}
if _MD_NAME in _KNOWN:
    OUT_PDF = DOCS / _KNOWN[_MD_NAME]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 11pt; line-height: 1.55; color: #1f2430;
  max-width: 100%; margin: 0;
}
h1 {
  font-size: 26pt; color: #5b34d6; margin: 0 0 4pt;
  border-bottom: 3px solid #5b34d6; padding-bottom: 8pt;
}
h2 {
  font-size: 17pt; color: #2a2f3a; margin: 26pt 0 8pt;
  border-bottom: 1px solid #e2e2ea; padding-bottom: 4pt;
  page-break-after: avoid;
}
h3 { font-size: 13pt; color: #5b34d6; margin: 16pt 0 6pt; page-break-after: avoid; }
p, li { margin: 6pt 0; }
a { color: #5b34d6; text-decoration: none; word-break: break-all; }
code {
  background: #f3f1fb; color: #5b34d6; padding: 1pt 4pt;
  border-radius: 4px; font-size: 9.5pt;
  font-family: "SF Mono", Menlo, Consolas, monospace;
}
pre {
  background: #1f2430; color: #f7f7fb; padding: 12pt; border-radius: 8px;
  overflow-x: auto; page-break-inside: avoid;
}
pre code { background: none; color: #f7f7fb; padding: 0; }
blockquote {
  border-left: 4px solid #f5b301; background: #fffaf0;
  margin: 10pt 0; padding: 6pt 14pt; border-radius: 0 6px 6px 0;
}
blockquote p { margin: 3pt 0; }
table {
  border-collapse: collapse; width: 100%; margin: 10pt 0;
  font-size: 10pt; page-break-inside: avoid;
}
th { background: #5b34d6; color: #fff; text-align: left; padding: 7pt 9pt; }
td { border: 1px solid #e2e2ea; padding: 6pt 9pt; vertical-align: top; }
tr:nth-child(even) td { background: #faf9fe; }
img {
  max-width: 100%; max-height: 215mm; height: auto; width: auto;
  display: block; margin: 12pt auto;
  border: 1px solid #d9d9e3; border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); page-break-inside: avoid;
}
hr { border: none; border-top: 1px solid #e2e2ea; margin: 22pt 0; }
h2, h3, table, pre, blockquote, img { page-break-inside: avoid; }
"""


def inline_images(html: str) -> str:
    """Replace <img src="screenshots/x.png"> with base64 data URIs."""
    def repl(match):
        src = match.group(1)
        img_path = (DOCS / src).resolve()
        if not img_path.exists():
            return match.group(0)
        mime = mimetypes.guess_type(str(img_path))[0] or "image/png"
        data = base64.b64encode(img_path.read_bytes()).decode("ascii")
        return f'src="data:{mime};base64,{data}"'

    return re.sub(r'src="([^"]+)"', repl, html)


def main() -> None:
    md_text = MD_FILE.read_text(encoding="utf-8")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    body = inline_images(body)

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>{body}</body></html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm",
                    "left": "16mm", "right": "16mm"},
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=(
                '<div style="font-size:8pt;color:#999;width:100%;'
                'text-align:center;padding:0 16mm;">'
                f'{FOOTER_TITLE} &nbsp;·&nbsp; '
                'Page <span class="pageNumber"></span> of '
                '<span class="totalPages"></span></div>'
            ),
        )
        browser.close()

    size_kb = OUT_PDF.stat().st_size / 1024
    print(f"Wrote {OUT_PDF}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
