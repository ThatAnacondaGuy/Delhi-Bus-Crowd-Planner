"""Stage 8: fill docs/*.tmpl.md and the root README.tmpl.md from the pipeline's own numbers.

Every number in a judge-facing document comes from `validation_report.json` (`headline_numbers`), a small flat
summary of `manifest.json` and the constants in `config.py` (bus capacities, window sizes); nothing is typed by hand.
A template placeholder is `{{name}}` or `{{name:fmt}}` where `fmt` is a Python format spec (`{{match_rate:.1%}}`,
`{{tickets_clean:,}}`). The README template sits at the repository root (ruling R31) and is rendered to README.md.
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


def config_numbers() -> dict:
    """Flat dict of the modelling constants the documents quote (assumptions table), read from config.py."""
    from . import config as c
    out: dict = {}
    for key, spec in c.BUS_SPECS.items():
        out.update({f"seats_{key}": spec.seats, f"rated_{key}": spec.rated_total,
                    f"crush_{key}": spec.crush, f"comfortable_{key}": spec.comfortable})
    from .gps import SAMPLE_DAYS
    from src.routing.planner import NO_DATA_CUTOFF
    out.update({
        "seats_fraction": c.SEATS_FRACTION, "scale_low": c.SCALE_RANGE[0], "scale_high": c.SCALE_RANGE[1],
        "bound_percentile": c.BOUND_PERCENTILE, "bound_min_tickets": c.BOUND_MIN_TICKETS,
        "e_scale_ceiling": c.E_SCALE_CEILING_MULT,
        "base_weekday_min": c.WINDOWS["weekday"].base_min, "step_weekday_min": c.WINDOWS["weekday"].step_min,
        "base_weekend_min": c.WINDOWS["weekend"].base_min, "step_weekend_min": c.WINDOWS["weekend"].step_min,
        "no_data_percentile": c.NO_DATA_PERCENTILE, "low_app_use_fraction": c.LOW_APP_USE_FRACTION,
        "alighting_last_stretches": c.ALIGHTING_LAST_STRETCHES, "alighting_min_reverse_board": c.ALIGHTING_MIN_REVERSE_BOARD,
        "supply_widen_min": c.SUPPLY_WIDEN_MIN, "place_radius_m": c.PLACE_RADIUS_M,
        "fuzzy_floor": c.STOP_FUZZY_MIN_SCORE, "devi_vehicle_min_tickets": c.DEVI_VEHICLE_MIN_TICKETS,
        "devi_route_share": c.DEVI_ROUTE_SHARE, "runtime_min_pairs": c.RUNTIME_MIN_PAIRS,
        "runtime_min_gap_min": c.RUNTIME_MIN_GAP_S // 60, "runtime_gate_tol": c.RUNTIME_GATE_TOL,
        "conservation_tol": c.CONSERVATION_TOL, "s0_max_share": c.S0_MAX_SHARE,
        "alias_min_in_order": c.ALIAS_MIN_IN_ORDER, "women_free_period_days": c.WOMEN_FREE_PERIOD_DAYS,
        "gps_coverage_min": c.GPS_COVERAGE_MIN, "gps_trip_stop_share": c.GPS_TRIP_STOP_SHARE,
        "gps_sample_days": len(SAMPLE_DAYS), "min_daily_trips": c.MIN_DAILY_TRIPS,
        "less_crowded_slack_min": c.LESS_CROWDED_SLACK[0], "less_crowded_slack_share": c.LESS_CROWDED_SLACK[1],
        "headline_min_minutes": c.HEADLINE_MIN_MINUTES, "no_data_cutoff": NO_DATA_CUTOFF,
        "leave_later_first": c.LEAVE_LATER_SHIFTS[0], "leave_later_last": c.LEAVE_LATER_SHIFTS[-1],
        "corridor_top_quantile": c.CORRIDOR_TOP_QUANTILE, "night_start_h": c.NIGHT_START_H, "night_end_h": c.NIGHT_END_H,
        "sensitivity_e": c.SENSITIVITY_E, "sensitivity_capacity": c.SENSITIVITY_CAPACITY})
    return out


def run(con, paths, **_) -> str:
    repo = Path(paths.repo)
    templates = sorted((repo / "docs").glob("*.tmpl.md"))
    if (repo / "README.tmpl.md").exists():
        templates.append(repo / "README.tmpl.md")
    if not templates:
        return "no templates, nothing rendered"
    report = json.loads((paths.processed / "validation_report.json").read_text(encoding="utf-8"))
    numbers = (config_numbers() | report["headline_numbers"] | manifest_summary(paths.processed / "manifest.json"))
    for t in templates:
        render_file(t, t.with_name(t.name.replace(".tmpl.md", ".md")), numbers)
    return f"{len(templates)} file(s) rendered"
