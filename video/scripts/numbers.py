"""Write video/src/numbers.json: every figure the film shows, read from the pipeline's own outputs.

Run from anywhere with the repo's interpreter:  venv/bin/python video/scripts/numbers.py
Nothing is typed by hand: validation_report.json (headline_numbers, coverage_summary), manifest.json (run id) and
operator_trips.parquet (the top weekday DTC extra trip, the same ordering the API and the operator screen use).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# This file is called numbers.py, like the standard-library module that pandas and duckdb import:
# take its own folder off the import path first so it cannot shadow the real one.
sys.path = [p for p in sys.path if Path(p or ".").resolve() != HERE]
sys.path.insert(0, str(ROOT))

from src.pipeline.db import connect  # noqa: E402  (every DuckDB connection comes from db.connect)

PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "video" / "src" / "numbers.json"


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def top_operator_trip() -> dict:
    con = connect()
    row = con.execute(
        """SELECT short_name, depart_min, crowded_rider_min_removed, riders_moved_down
           FROM read_parquet(?) WHERE day_type = 'weekday' AND upper(operator) = 'DTC'
           ORDER BY crowded_rider_min_removed DESC, route_id, depart_min LIMIT 1""",
        [str(PROCESSED / "operator_trips.parquet")],
    ).fetchone()
    con.close()
    name, depart, removed, moved = row
    return {
        "route": name,
        "depart": hhmm(int(depart)),
        "crowded_rider_min_removed": round(removed),
        "riders_moved_down": round(moved),
    }


def build() -> dict:
    report = json.loads((PROCESSED / "validation_report.json").read_text())
    h = report["headline_numbers"]
    ev = report["coverage_summary"]["all"]["evidence"]
    manifest = json.loads((PROCESSED / "manifest.json").read_text())
    return {
        "run_id": manifest["run_id"],
        "tickets": h["tickets_clean"],
        "one_in": h["app_riders_one_in"],
        "peaks": [f"{h['am_peak_hour']:02d}:00", f"{h['pm_peak_hour']:02d}:00"],
        "bus_km_model": round(h["dtc_bus_km_model"]),
        "bus_km_published": round(h["dtc_bus_km_published"]),
        "load_factor_model": f"{h['load_factor_model']:.2f}",
        "load_band": f"{h['load_factor_band_low']:.2f}–{h['load_factor_band_high']:.2f}",
        "load_band_low": f"{h['load_factor_band_low']:.2f}",
        "load_band_high": f"{h['load_factor_band_high']:.2f}",
        "load_full_allocation": f"{h['load_factor_full_allocation']:.2f}",
        "corridor_hits_total": h["corridor_hits_total"],
        "corridors_total": h["corridors_total"],
        "corridor_chance": f"{h['corridor_hits_chance_expected']:.1f}",
        "corridor_top_decile_pct": round(100 * h["corridor_top_decile_share"]),
        "corridor_top_decile_chance_pct": round(100 * h["corridor_top_decile_chance"]),
        "corridor_both_ends": h["corridor_hits_both_ends"],
        "radial_pairs": h["radial_pairs"],
        "radial_am_pct": round(100 * h["radial_am_share"]),
        "radial_pm_pct": round(100 * h["radial_pm_share"]),
        "week_keep_pct": round(100 * h["unchanged_level_share"]),
        "week_load_corr": f"{h['load_correlation_week_pairs']:.2f}",
        "share_many_tickets": f"{100 * ev['many_tickets']:.1f}",
        "share_rough": f"{100 * ev['rough']:.0f}",
        "share_no_data": f"{100 * ev['none']:.1f}",
        "operator": top_operator_trip(),
    }


def main() -> None:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} (run {data['run_id']})")


if __name__ == "__main__":
    main()
