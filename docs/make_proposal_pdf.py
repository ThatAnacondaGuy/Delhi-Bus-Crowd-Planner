"""Make docs/PROPOSAL.pdf from docs/PROPOSAL.md (the rendered proposal) with headless Chrome.

    python docs/make_proposal_pdf.py            # writes docs/PROPOSAL.pdf and prints the page count
    python docs/make_proposal_pdf.py --html out.html   # also keep the HTML wrapper, for looking at it

pandoc is not installed, so a small Markdown converter lives here. It handles only what the proposal uses:
headings, paragraphs, bold/italic/code/links/images, bullet and numbered lists, tables, block quotes, rules,
standalone <div ...> and </div> lines (markdown inside them is still converted) and raw HTML blocks. Print CSS
makes A4 pages. Animated diagrams are shown as still pictures (Chrome is asked to reduce motion; the <picture>
dark-mode source is dropped so the light diagram is used).
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOCS = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MAX_PAGES, MIN_PAGES = 4, 2

CSS = """
@page { size: A4; margin: 11mm 12mm 14mm 12mm;
  @bottom-left { content: "Delhi Bus Crowding Planner · Transport Stack Hackathon 2026 · Phase 1"; font: 7.5pt sans-serif; color:#566069; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 7.5pt sans-serif; color:#566069; } }
:root { --ink:#1d2327; --muted:#566069; --teal:#0f766e; --amber:#b45309; --red:#8f1d1d; --blue:#1f4e79;
        --paper:#fbfaf7; --line:#e3e0d6; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin:0; color:var(--ink); background:#fff; font: 9.2pt/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI",
       Roboto, "Helvetica Neue", Arial, "Noto Sans", "Noto Sans Devanagari", sans-serif; }
h1,h2,h3 { line-height:1.2; margin:0; }
h2 { font-size:12.2pt; margin:11px 0 5px; color:var(--blue); letter-spacing:.01em; padding-bottom:3px;
     border-bottom:1.5px solid var(--line); break-after: avoid; }
h2::before { content:""; display:inline-block; width:7px; height:7px; background:var(--teal); border-radius:2px;
             margin-right:7px; vertical-align:1px; }
p { margin:0 0 5px; }
a { color:var(--blue); text-decoration:none; word-break:break-word; }
strong { font-weight:700; }
code { font: 8.4pt ui-monospace, Menlo, monospace; background:#f2f0e9; padding:0 3px; border-radius:3px; }
ul, ol { margin:3px 0 6px; padding-left:17px; }
li { margin:0 0 2px; }
img { max-width:100%; display:block; }
table { border-collapse:collapse; width:calc(100% - 1px); margin:4px 0 7px; font-size:8.5pt; break-inside: avoid; }
th, td { border:1px solid var(--line); padding:3.5px 6px; vertical-align:top; text-align:left; }
th { background:#f2f0e9; font-weight:700; }
tbody tr:nth-child(even) td { background:#fcfbf8; }
.band { background:linear-gradient(115deg,#0b3d3a 0%,#0f766e 55%,#1f4e79 100%); color:#fff; border-radius:9px;
        padding:14px 18px 12px; margin:0 0 6px; }
.band h1 { font-size:22pt; letter-spacing:-.01em; margin:0 0 3px; }
.band .tag { font-size:11.5pt; font-weight:600; margin:0 0 7px; color:#e8f5f2; }
.band .meta { font-size:8.3pt; margin:0; color:#cfe6e2; }
.gallery table { border:0; margin:3px 0 5px; }
.gallery th, .gallery td { border:0; padding:0 5px; text-align:center; font-size:8pt; color:var(--muted); background:none !important; }
.gallery th { vertical-align:bottom; }
.gallery td { vertical-align:top; text-align:left; padding-top:5px; }
.gallery th img { margin:0 auto; border-radius:8px; border:1px solid var(--line); }
.gallery th img { max-height:196px; width:auto; }
.gallery th:nth-child(1), .gallery th:nth-child(2) { width:23%; }
.diagram img { width:100%; max-height:236px; object-fit:contain; margin:2px auto 3px; }
.tiles table { border:0; margin:5px 0 7px; table-layout:fixed; }
.tiles th, .tiles td { border:0; background:none !important; padding:0 4px; text-align:left; }
.tiles th { background:var(--paper) !important; border:1px solid var(--line); border-bottom:0; border-radius:8px 8px 0 0;
            font-size:17pt; color:var(--teal); padding:8px 9px 0; line-height:1.1; }
.tiles td { background:var(--paper) !important; border:1px solid var(--line); border-top:0; border-radius:0 0 8px 8px;
            font-size:8.1pt; color:var(--muted); padding:2px 9px 8px; }
.tiles th, .tiles td { border-left-width:4px; border-left-color:#fff; border-right-width:4px; border-right-color:#fff; }
.links table { margin-top:2px; }
.links th { display:none; }
.credit { font-size:8pt; color:var(--muted); margin-top:8px; border-top:1px solid var(--line); padding-top:5px; }
blockquote { margin:5px 0; padding:4px 10px; border-left:3px solid var(--teal); background:#f4f9f8; }
hr { border:0; border-top:1px solid var(--line); margin:8px 0; }
"""


# ---------------------------------------------------------------- inline

_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")


def inline(text: str) -> str:
    keep: list[str] = []

    def stash(s: str) -> str:
        keep.append(s)
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = re.sub(r"<(https?://[^>\s]+)>", lambda m: stash(f'<a href="{m.group(1)}">{m.group(1)}</a>'), text)
    text = _TAG.sub(lambda m: stash(m.group(0)), text)
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: stash(f'<img src="{m.group(2)}" alt="{html.escape(m.group(1))}">'), text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)


# ---------------------------------------------------------------- blocks

def _cells(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*", line)) and "-" in line


def _table(lines: list[str]) -> str:
    head, aligns, body = _cells(lines[0]), _cells(lines[1]), [_cells(x) for x in lines[2:]]

    def al(i: int) -> str:
        a = aligns[i] if i < len(aligns) else ""
        return ' style="text-align:center"' if a.startswith(":") and a.endswith(":") else \
            ' style="text-align:right"' if a.endswith(":") else ""

    out = ["<table>", "<thead><tr>" + "".join(f"<th{al(i)}>{inline(c)}</th>" for i, c in enumerate(head)) + "</tr></thead>", "<tbody>"]
    for r in body:
        out.append("<tr>" + "".join(f"<td{al(i)}>{inline(c)}</td>" for i, c in enumerate(r)) + "</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def _list(lines: list[str], i: int) -> tuple[str, int]:
    first = re.match(r"^(\s*)([-*]|\d+\.)\s+", lines[i])
    base = len(first.group(1))
    tag = "ol" if first.group(2)[0].isdigit() else "ul"
    items: list[str] = []
    while i < len(lines):
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
        if m and len(m.group(1)) == base:
            items.append(m.group(3))
            i += 1
        elif m and len(m.group(1)) > base:
            sub, i = _list(lines, i)
            items[-1] += "\x01" + sub
        elif lines[i].strip() and lines[i].startswith(" " * (base + 2)) and items:
            items[-1] += " " + lines[i].strip()
            i += 1
        else:
            break
    li = "".join("<li>" + (inline(t.split("\x01")[0]) + "".join(t.split("\x01")[1:])) + "</li>" for t in items)
    return f"<{tag}>{li}</{tag}>", i


def convert(md: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"<source\b[^>]*>\s*", "", md)                       # light diagram only
    md = re.sub(r"</?picture>\s*", "", md)
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
        elif re.fullmatch(r"</?div\b[^>]*>", s):
            out.append(s)
            i += 1
        elif s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif m := re.match(r"^(#{1,4})\s+(.*)$", s):
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
        elif re.fullmatch(r"-{3,}|\*{3,}", s):
            out.append("<hr>")
            i += 1
        elif s.startswith("|") and i + 1 < len(lines) and _is_sep(lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j]))
            i = j
        elif s.startswith(">"):
            j = i
            while j < len(lines) and lines[j].strip().startswith(">"):
                j += 1
            out.append("<blockquote>" + inline(" ".join(x.strip().lstrip(">").strip() for x in lines[i:j])) + "</blockquote>")
            i = j
        elif re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            block, i = _list(lines, i)
            out.append(block)
        elif s.startswith("<") and not s.startswith("<http"):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            out.append("\n".join(lines[i:j]))
            i = j
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not re.match(r"^\s*(#{1,4}\s|\||>|```|([-*]|\d+\.)\s)", lines[j]) \
                    and not re.fullmatch(r"</?div\b[^>]*>", lines[j].strip()):
                j += 1
            j = max(j, i + 1)                                            # always make progress
            out.append("<p>" + inline(" ".join(x.strip() for x in lines[i:j])) + "</p>")
            i = j
    return "\n".join(out)


def wrapper(md_path: Path) -> str:
    body = convert(md_path.read_text(encoding="utf-8"))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>Delhi Bus Crowding Planner: proposal</title>"
            f"<base href=\"{md_path.parent.as_uri()}/\"><style>{CSS}</style></head><body>{body}</body></html>")


# ---------------------------------------------------------------- pdf

def page_count(pdf: Path) -> int:
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def build(md_path: Path, pdf_path: Path, keep_html: Path | None = None) -> int:
    if not Path(CHROME).exists():
        raise SystemExit(f"Google Chrome not found at {CHROME}")
    page = wrapper(md_path)
    with tempfile.TemporaryDirectory() as tmp:
        h = Path(tmp) / "proposal.html"
        h.write_text(page, encoding="utf-8")
        if keep_html:
            shutil.copyfile(h, keep_html)
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--force-prefers-reduced-motion",
               "--allow-file-access-from-files", "--no-first-run", f"--user-data-dir={Path(tmp) / 'profile'}",
               f"--print-to-pdf={pdf_path}", h.as_uri()]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    return page_count(pdf_path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(DOCS / "PROPOSAL.md"))
    ap.add_argument("--pdf", default=str(DOCS / "PROPOSAL.pdf"))
    ap.add_argument("--html", default=None, help="also write the HTML wrapper here")
    a = ap.parse_args(argv)
    n = build(Path(a.md), Path(a.pdf), Path(a.html) if a.html else None)
    print(f"{a.pdf}: {n} A4 page(s)")
    if not MIN_PAGES <= n <= MAX_PAGES:
        print(f"expected {MIN_PAGES} to {MAX_PAGES} pages", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
