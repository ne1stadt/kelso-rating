"""Render the paper (docx) to PDF for download from the About page.

docx -> standalone HTML (headings, paragraphs with bold/italic/sub/superscript, lists, tables,
figures, display equations as LaTeX rendered by the vendored KaTeX) -> PDF via headless Chrome.

Usage: python scripts/build_paper_pdf.py [paper.docx] [out.pdf]
Needs Google Chrome / Chromium (set CHROME=/path/to/chrome if it is not found).
"""
from __future__ import annotations

import base64
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def omml_text(el) -> str:
    """Inline OMML -> plain text (the paper's inline math is short; display math is LaTeX in Code paragraphs)."""
    out = []
    for t in el.iter(M + "t"):
        out.append(t.text or "")
    return "".join(out)


def runs_html(p, rels, zf) -> str:
    out = []
    for el in p:
        tag = el.tag
        if tag == W + "r":
            rp = el.find(W + "rPr")
            b = rp is not None and rp.find(W + "b") is not None and rp.find(W + "b").get(W + "val") not in ("0", "false")
            i = rp is not None and rp.find(W + "i") is not None and rp.find(W + "i").get(W + "val") not in ("0", "false")
            va = rp.find(W + "vertAlign").get(W + "val") if rp is not None and rp.find(W + "vertAlign") is not None else None
            txt = []
            for c in el:
                if c.tag == W + "t":
                    txt.append(html.escape(c.text or ""))
                elif c.tag == W + "tab":
                    txt.append(" ")
                elif c.tag == W + "br":
                    txt.append("<br>")
                elif c.tag == W + "drawing":
                    blip = c.find(".//" + A + "blip")
                    if blip is not None:
                        target = rels.get(blip.get(R + "embed"))
                        if target:
                            data = base64.b64encode(zf.read("word/" + target)).decode()
                            txt.append(f'<img src="data:image/png;base64,{data}">')
            s = "".join(txt)
            if not s:
                continue
            if va == "subscript":
                s = f"<sub>{s}</sub>"
            elif va == "superscript":
                s = f"<sup>{s}</sup>"
            if i:
                s = f"<em>{s}</em>"
            if b:
                s = f"<strong>{s}</strong>"
            out.append(s)
        elif tag == M + "oMath":
            out.append(f'<span class="m">{html.escape(omml_text(el))}</span>')
        elif tag == W + "hyperlink":
            out.append(runs_html(el, rels, zf))
    return "".join(out)


def convert(docx: Path) -> str:
    zf = zipfile.ZipFile(docx)
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(zf.read("word/_rels/document.xml.rels")).iter(PR + "Relationship")}
    body = ET.fromstring(zf.read("word/document.xml")).find(W + "body")
    parts, in_list = [], False
    for el in body:
        if el.tag == W + "p":
            st = el.find(W + "pPr/" + W + "pStyle")
            style = st.get(W + "val") if st is not None else ""
            inner = runs_html(el, rels, zf).strip()
            if not inner:
                continue
            if style != "ListParagraph" and in_list:
                parts.append("</ul>"); in_list = False
            if style == "Heading1":
                parts.append(f"<h1>{inner}</h1>")
            elif style == "Heading2":
                parts.append(f"<h2>{inner}</h2>")
            elif style == "Heading3":
                parts.append(f"<h3>{inner}</h3>")
            elif style == "ListParagraph":
                if not in_list:
                    parts.append("<ul>"); in_list = True
                parts.append(f"<li>{inner}</li>")
            elif style == "Code":
                tex = html.unescape(re.sub(r"<[^>]+>", "", inner))
                parts.append(f'<div class="eq" data-tex="{html.escape(tex)}"></div>')
            elif inner.startswith("<img"):
                parts.append(f'<figure>{inner}</figure>')
            elif re.match(r"^(<strong>)?(Figure|Table) \d", inner):
                parts.append(f'<p class="cap">{inner}</p>')
            else:
                parts.append(f"<p>{inner}</p>")
        elif el.tag == W + "tbl":
            if in_list:
                parts.append("</ul>"); in_list = False
            rows = []
            for k, tr in enumerate(el.iter(W + "tr")):
                cells = []
                for tc in tr.findall(W + "tc"):
                    txt = " ".join(runs_html(p, rels, zf) for p in tc.iter(W + "p")).strip()
                    cells.append(f"<{'th' if k == 0 else 'td'}>{txt}</{'th' if k == 0 else 'td'}>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            parts.append("<table>" + "".join(rows) + "</table>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><title>A Cross-Event Rating for Speedcubing on the Elo Scale</title>
<link rel="stylesheet" href="{katex}/katex.min.css">
<style>
@page {{ size: A4; margin: 22mm 20mm 22mm 20mm; }}
body {{ font: 10.5pt/1.5 "Georgia", "Times New Roman", serif; color: #111; }}
h1 {{ font-size: 19pt; line-height: 1.25; margin: 0 0 4pt; }}
h1 + p {{ color: #555; margin-bottom: 16pt; }}
h2 {{ font-size: 13pt; margin: 18pt 0 6pt; break-after: avoid; }}
h3 {{ font-size: 11pt; margin: 14pt 0 4pt; break-after: avoid; }}
p {{ margin: 0 0 7pt; text-align: justify; hyphens: auto; }}
ul {{ margin: 0 0 8pt; padding-left: 16pt; }} li {{ margin-bottom: 3pt; }}
.eq {{ margin: 6pt 0 10pt; }}
figure {{ margin: 8pt 0 2pt; text-align: center; break-inside: avoid; }}
figure img {{ max-width: 100%; max-height: 120mm; }}
.cap {{ font-size: 9pt; color: #333; break-before: avoid; }}
table {{ border-collapse: collapse; width: 100%; font: 8.4pt/1.35 "Helvetica Neue", Arial, sans-serif; margin: 4pt 0 10pt; break-inside: auto; }}
th, td {{ border-bottom: 0.5pt solid #bbb; padding: 2.5pt 4pt; text-align: left; vertical-align: top; }}
th {{ border-bottom: 1pt solid #333; font-weight: 700; }}
tr {{ break-inside: avoid; }}
.m {{ font-style: italic; }}
</style></head><body>
{body}
<script src="{katex}/katex.min.js"></script>
<script>document.querySelectorAll('.eq').forEach(function(e){{katex.render(e.dataset.tex,e,{{displayMode:true,throwOnError:false}});}});</script>
</body></html>"""


def find_chrome() -> str:
    for c in [os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome")]:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium not found; set CHROME")


def main():
    docx = Path(sys.argv[1]) if len(sys.argv) > 1 else next((ROOT / "paper").glob("*.docx"))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "web/static/files/kelso-rating-paper.pdf"
    page = TEMPLATE.format(body=convert(docx), katex=(ROOT / "web/static/katex").as_uri())
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "paper.html"
        src.write_text(page, encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([find_chrome(), "--headless", "--disable-gpu", "--allow-file-access-from-files",
                        "--no-pdf-header-footer", "--virtual-time-budget=10000", f"--print-to-pdf={out}", src.as_uri()],
                       check=True, capture_output=True)
    print(out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
