"""Stage 8: fill docs/*.tmpl.md from the pipeline's own numbers.

Every number in a judge-facing document comes from `validation_report.json` (`headline_numbers`) and a small flat
summary of `manifest.json`; nothing is typed by hand. A template placeholder is `{{name}}` or `{{name:fmt}}` where
`fmt` is a Python format spec (`{{match_rate:.1%}}`, `{{tickets_clean:,}}`).
"""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import TZ
from .errors import RenderError

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::([^{}]*))?\}\}")


def render_text(text: str, numbers: dict, source: str = "template") -> str:
    def fill(m: re.Match) -> str:
        name, fmt = m.group(1), m.group(2)
        if name not in numbers:
            raise RenderError(f"{source}: unknown placeholder {{{{{name}}}}}")
        value = numbers[name]
        if value is None:
            raise RenderError(f"{source}: placeholder {{{{{name}}}}} has no value (null in the pipeline output)")
        try:
            return format(value, fmt) if fmt else str(value)
        except (ValueError, TypeError) as e:
            raise RenderError(f"{source}: cannot format {name}={value!r} with {fmt!r}: {e}") from e

    out = PLACEHOLDER.sub(fill, text)
    if "{{" in out or "}}" in out:
        i = out.find("{{") if "{{" in out else out.find("}}")
        raise RenderError(f"{source}: unfilled or malformed placeholder near {out[max(0, i - 20):i + 30]!r}")
    return out


def render_file(template: Path, out: Path, numbers: dict) -> None:
    """Write `out` from `template`; on any error nothing is written."""
    template, out = Path(template), Path(out)
    text = render_text(template.read_text(encoding="utf-8"), numbers, source=template.name)
    out.write_text(text, encoding="utf-8")


def manifest_summary(path) -> dict:
    """Flat dict of what the manifest holds about this build: run id, code version, finish time (IST)."""
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    if not m.get("run_id"):
        raise RenderError(f"{path}: manifest has no run_id; run the pipeline first")
    stages = m.get("stages", {})
    last = max(stages.values(), key=lambda r: r.get("finished_at", ""), default=None)
    out = {"run_id": m["run_id"]}
    if last:
        out["code_version"] = last["versions"]["code"]
        finished = datetime.fromisoformat(last["finished_at"]).astimezone(ZoneInfo(TZ))
        out["pipeline_finished_ist"] = finished.strftime("%Y-%m-%d %H:%M")
        out["pipeline_finished_date"] = finished.strftime("%Y-%m-%d")
    return out


def run(con, paths, **_) -> str:
    templates = sorted((Path(paths.repo) / "docs").glob("*.tmpl.md"))
    if not templates:
        return "no templates, nothing rendered"
    report = json.loads((paths.processed / "validation_report.json").read_text(encoding="utf-8"))
    numbers = report["headline_numbers"] | manifest_summary(paths.processed / "manifest.json")
    for t in templates:
        render_file(t, t.with_name(t.name.replace(".tmpl.md", ".md")), numbers)
    return f"{len(templates)} file(s) rendered"
