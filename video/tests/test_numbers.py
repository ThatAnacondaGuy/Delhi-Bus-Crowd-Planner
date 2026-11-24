"""Numbers for the film are never typed: video/scripts/numbers.py writes video/src/numbers.json from the pipeline outputs."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "video" / "scripts" / "numbers.py"
OUT = ROOT / "video" / "src" / "numbers.json"


def run_script():
    subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, check=True)
    return json.loads(OUT.read_text())


def test_script_exists():
    assert SCRIPT.exists()


def test_numbers_match_validation_report():
    n = run_script()
    h = json.loads((ROOT / "data/processed/validation_report.json").read_text())["headline_numbers"]
    assert n["tickets"] == h["tickets_clean"] == 2559899
    assert n["one_in"] == h["app_riders_one_in"]
    assert n["peaks"] == [f"{h['am_peak_hour']:02d}:00", f"{h['pm_peak_hour']:02d}:00"]
    assert n["bus_km_model"] == round(h["dtc_bus_km_model"])
    assert n["bus_km_published"] == round(h["dtc_bus_km_published"])
    assert n["load_factor_model"] == f"{h['load_factor_model']:.2f}"
    assert n["load_band"] == f"{h['load_factor_band_low']:.2f}–{h['load_factor_band_high']:.2f}"
    assert n["load_full_allocation"] == f"{h['load_factor_full_allocation']:.2f}"
    assert n["corridor_hits_total"] == h["corridor_hits_total"]
    assert n["corridors_total"] == h["corridors_total"]
    assert n["corridor_chance"] == f"{h['corridor_hits_chance_expected']:.1f}"
    assert n["corridor_top_decile_pct"] == round(100 * h["corridor_top_decile_share"])
    assert n["corridor_top_decile_chance_pct"] == round(100 * h["corridor_top_decile_chance"])
    assert n["corridor_both_ends"] == h["corridor_hits_both_ends"]
    assert n["radial_pairs"] == h["radial_pairs"]
    assert n["radial_am_pct"] == round(100 * h["radial_am_share"])
    assert n["radial_pm_pct"] == round(100 * h["radial_pm_share"])
    assert n["week_keep_pct"] == round(100 * h["unchanged_level_share"])
    assert n["week_load_corr"] == f"{h['load_correlation_week_pairs']:.2f}"


def test_numbers_evidence_shares_and_run_id():
    n = run_script()
    cov = json.loads((ROOT / "data/processed/validation_report.json").read_text())["coverage_summary"]["all"]["evidence"]
    assert n["share_many_tickets"] == f"{100 * cov['many_tickets']:.1f}"
    assert n["share_rough"] == f"{100 * cov['rough']:.0f}"
    assert n["share_no_data"] == f"{100 * cov['none']:.1f}"
    m = json.loads((ROOT / "data/processed/manifest.json").read_text())
    assert n["run_id"] == m["run_id"]


def test_operator_headline_is_top_weekday_dtc_trip():
    n = run_script()
    op = n["operator"]
    assert op["route"] == "578DOWN"
    assert op["depart"] == "08:30"
    assert op["crowded_rider_min_removed"] == 19589
    assert op["riders_moved_down"] == 7363
