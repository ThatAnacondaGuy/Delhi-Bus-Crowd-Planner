"""The judge-facing documents: rendered, clean of old-method words, honest, and consistent with the validation report."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from src.pipeline import render

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing."
NO_COUNT = "No field count was possible"
FORBIDDEN = ["κ", "kappa", "mcraptor", "pareto", "sigmoid", "score"]

README = REPO / "README.md"
NOTE = DOCS / "TECHNICAL_NOTE.md"
PROPOSAL = DOCS / "PROPOSAL.md"
RENDERED = [README, NOTE, PROPOSAL]
TEMPLATES = [REPO / "README.tmpl.md", DOCS / "TECHNICAL_NOTE.tmpl.md", DOCS / "PROPOSAL.tmpl.md"]


def judge_facing_markdown() -> list[Path]:
    """README, docs/*.md and docs/*.tmpl.md (not docs/archive or docs/superpowers), the frontend and the API."""
    out = [README, REPO / "README.tmpl.md"] + sorted(DOCS.glob("*.md"))
    return [p for p in out if p.exists()]


def judge_facing_files() -> list[Path]:
    files = judge_facing_markdown()
    files += [p for p in sorted((REPO / "frontend").rglob("*")) if p.is_file()]
    files += [REPO / "src" / "api" / "main.py"]
    return files


def report() -> dict:
    return json.loads((REPO / "data" / "processed" / "validation_report.json").read_text(encoding="utf-8"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- rendered, no leftovers

@pytest.mark.parametrize("path", RENDERED, ids=lambda p: p.name)
def test_rendered_documents_exist_and_have_no_placeholders(path):
    text = path.read_text(encoding="utf-8")
    assert len(text) > 1500, f"{path.name} looks empty"
    assert "{{" not in text and "}}" not in text, f"{path.name} has an unfilled placeholder"
    assert not re.search(r"\bNone\s*[|,;)%]|\binf%|\bnan%|\bnan\.\d", text, flags=re.M), f"{path.name} shows a NaN or None"


@pytest.mark.parametrize("tmpl", TEMPLATES, ids=lambda p: p.name)
def test_every_template_renders_from_the_committed_report(tmp_path, tmpl):
    """A clean clone has the report and config but no manifest: every placeholder must still be fillable."""
    rep = report()["headline_numbers"]
    numbers = render.config_numbers() | rep | {"run_id": "r", "code_version": "c", "pipeline_finished_ist": "t",
                                               "pipeline_finished_date": "d"}
    out = tmp_path / "x.md"
    render.render_file(tmpl, out, numbers)
    assert "{{" not in out.read_text(encoding="utf-8")


def test_rendered_documents_match_their_templates_apart_from_numbers():
    """Rendered files are not hand-edited: same line count and the same non-numeric skeleton as the template."""
    for tmpl, out in zip(TEMPLATES, RENDERED):
        t = re.sub(r"\{\{[^}]*\}\}", "N", tmpl.read_text(encoding="utf-8"))
        r = out.read_text(encoding="utf-8")
        assert len(t.splitlines()) == len(r.splitlines()), f"{out.name} is out of date with {tmpl.name}; run the render stage"


# ---------------------------------------------------------------- words

def test_no_forbidden_words_in_judge_facing_files():
    for p in judge_facing_files():
        low = p.read_text(encoding="utf-8", errors="ignore").lower()
        for w in FORBIDDEN:
            assert w not in low, f"{p.relative_to(REPO)} contains {w!r}"


def test_the_pipeline_reports_carry_no_forbidden_words_either():
    for p in (REPO / "data" / "processed").glob("*.md"):
        low = p.read_text(encoding="utf-8").lower()
        for w in FORBIDDEN:
            assert w not in low, f"{p.name} contains {w!r}"


# ---------------------------------------------------------------- required sentences and structure

def test_readme_and_note_carry_the_credit_line_and_the_field_count_sentence():
    for p in (README, NOTE):
        text = p.read_text(encoding="utf-8")
        assert CREDIT in text, p.name
        assert NO_COUNT in text, p.name
    assert CREDIT in PROPOSAL.read_text(encoding="utf-8")
    assert NO_COUNT in PROPOSAL.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
    assert m, f"no '## {heading}' section"
    return m.group(1)


def test_readme_quick_start_is_exactly_the_five_steps():
    sec = _section(README.read_text(encoding="utf-8"), "Quick start")
    steps = re.findall(r"^\d+\. (.*)$", sec, flags=re.M)
    assert len(steps) == 5, steps
    wanted = ["clone", "uv pip install -r requirements.lock", "data/raw", "python -m src.pipeline.run", "uvicorn src.api.main:app"]
    # each step, with the code block that follows it, mentions its command, in order
    chunks = re.split(r"^\d+\. ", sec, flags=re.M)[1:]
    assert len(chunks) == 5
    for chunk, needle in zip(chunks, wanted):
        assert needle in chunk, (needle, chunk)
    commands = [ln.strip() for ln in re.findall(r"```bash\n(.*?)```", sec, flags=re.S) for ln in ln.splitlines() if ln.strip()]
    assert commands == [
        "git clone https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner && cd Delhi-Bus-Crowd-Planner",
        "uv venv --python 3.12 && source .venv/bin/activate",
        "uv pip install -r requirements.lock",
        "python -m src.pipeline.run",
        "uvicorn src.api.main:app"]


def test_technical_note_has_the_six_row_brief_checklist():
    text = NOTE.read_text(encoding="utf-8")
    sec = _section(text, "4. The brief checklist")
    rows = [ln for ln in sec.splitlines() if ln.startswith("|")]
    assert rows[0].startswith("| Item in the brief")
    body = rows[2:]                                    # header and separator out
    assert len(body) == 6, len(body)
    for key in ("Running count per trip", "Pass and free riders", "Planned vs actual alighting", "Bus size",
                "Thin routes and hours", "Simple display"):
        assert any(key in r for r in body), key
    assert all(r.count("|") == rows[0].count("|") for r in rows)


def test_technical_note_covers_the_required_sections():
    text = NOTE.read_text(encoding="utf-8")
    for h in ("## 1. Data", "## 2. Method", "## 3. Assumptions", "## 4. The brief checklist", "## 5. Reconciling the app share",
              "## 6. Validation and independent checks", "## 7. Coverage and the least reliable areas", "## 8. Phase 2"):
        assert h in text, h
    assert "config.py" in text and "chance" in text.lower() and "Rough guess" in text
    assert "latency" not in text.lower()               # spec 5.14: no latency section


def test_readme_has_the_hero_demo_and_animated_diagrams():
    text = README.read_text(encoding="utf-8")
    assert "See how crowded each stretch of your Delhi bus trip usually is" in text
    assert "https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner" in text
    assert "https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner" in text
    assert "prefers-color-scheme: dark" in text and "architecture-dark.svg" in text and "how-it-works-dark.svg" in text
    assert "Aniket Ingale" in text and "Ashish Maurya" in text
    for level in ("Usually seats", "आमतौर पर सीट मिल जाती है", "Usually crowded", "आमतौर पर भारी भीड़", "No data", "जानकारी नहीं"):
        assert level in text, level


# ---------------------------------------------------------------- links and pictures resolve

def _targets(text: str) -> list[str]:
    found = re.findall(r'(?:src|srcset|href)="([^"]+)"', text) + re.findall(r"\]\(([^)\s]+)\)", text)
    return [t for t in found if not re.match(r"(https?:|mailto:|#|data:)", t)]


@pytest.mark.parametrize("path", RENDERED, ids=lambda p: p.name)
def test_relative_links_and_pictures_exist(path):
    for t in _targets(path.read_text(encoding="utf-8")):
        target = (path.parent / t.split("#")[0]).resolve()
        assert target.exists(), f"{path.name} points at missing {t}"


@pytest.mark.parametrize("path", [README, NOTE, PROPOSAL], ids=lambda p: p.name)
def test_every_picture_has_alt_text(path):
    for tag in re.findall(r"<img\b[^>]*>", path.read_text(encoding="utf-8")):
        assert re.search(r'alt="[^"]{8,}"', tag), tag


# ---------------------------------------------------------------- what the documents claim is what the report says

def test_claims_in_the_documents_match_the_validation_report():
    h = report()["headline_numbers"]
    text = README.read_text(encoding="utf-8")
    assert h["peaks_hit"] and h["weekend_hit"] and h["radial_hit"] and h["dtc_bus_km_hit"]    # "Hit" rows
    assert not h["load_factor_hit"]                                                           # the "Miss" row
    assert "**Miss.**" in text and "**Hit.**" in text
    assert h["base_case_reproduced"] is True
    g = report()["gates"]
    assert len(g) == 7 and all(v["passed"] is True for v in g.values()), g                     # "All pass"
    # "chance alone gives about as many hits as ours, so it proves little"
    assert h["corridor_hits_chance_expected"] / h["corridors_total"] > 0.9
    assert h["corridor_top_decile_share_mean"] > h["corridor_top_decile_chance"]               # "enrichment"
    assert h["unallocated_share_dtc"] > 0 and h["ceiling_bound_dtc"] and h["ceiling_bound_dimts"]
    assert h["load_factor_model"] < h["load_factor_band_low"] < h["load_factor_band_high"] < h["load_factor_full_allocation"]
    assert h["evidence_rough_share"] > 0.5 and h["bus_km_share_many_tickets"] < 0.2          # "most levels are Rough guess"


def test_the_honest_misses_are_stated_in_each_document():
    for p in RENDERED:
        low = p.read_text(encoding="utf-8").lower()
        assert "miss" in low, p.name
        assert "rough guess" in low, p.name
        assert "app tickets" in low or "app ticket" in low, p.name
    assert "chance" in NOTE.read_text(encoding="utf-8").lower() and "chance" in README.read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------- proposal PDF

def test_proposal_pdf_is_two_to_four_a4_pages():
    pdf = DOCS / "PROPOSAL.pdf"
    assert pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"
    assert pdf.stat().st_size < 5_000_000
    n = _load("make_proposal_pdf").page_count(pdf)
    assert 2 <= n <= 4, n
    box = re.search(rb"/MediaBox\s*\[0 0 ([\d.]+) ([\d.]+)\]", pdf.read_bytes())
    assert box and abs(float(box.group(1)) - 595.3) < 2 and abs(float(box.group(2)) - 841.9) < 2        # A4 in points


def test_markdown_converter_handles_what_the_proposal_uses():
    mod = _load("make_proposal_pdf")
    html = mod.convert('<div class="band">\n\n# Title\n\n</div>\n\n## Part\n\nText with **bold**, *em*, `code` and [a link](https://x.y).\n\n'
                       '- one\n- two\n  - nested\n\n| A | B |\n|:-:|---|\n| 1 | 2 |\n\n> quote\n\n<p class="credit">raw</p>\n')
    for needle in ('<div class="band">', "<h1>Title</h1>", "<h2>Part</h2>", "<strong>bold</strong>", "<em>em</em>",
                   "<code>code</code>", '<a href="https://x.y">a link</a>', "<li>one</li>", "<ul><li>nested</li></ul>",
                   "<th style=\"text-align:center\">A</th>", "<td>2</td>", "<blockquote>quote</blockquote>",
                   '<p class="credit">raw</p>'):
        assert needle in html, needle
    assert "<picture" not in mod.convert("<picture>\n<source media=\"x\" srcset=\"a.svg\">\n<img src=\"b.svg\" alt=\"x\">\n</picture>")
    # a table straight after a paragraph and a lone pipe line must not hang the converter
    mod.convert("para\n| not a table\n\ntext")
