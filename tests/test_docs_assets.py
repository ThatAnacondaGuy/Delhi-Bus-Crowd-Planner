"""The README pictures: diagrams parse, move, respect reduced motion; figures build from pipeline outputs."""
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "docs" / "assets"
FORBIDDEN = ["κ", "kappa", "mcraptor", "pareto", "sigmoid", "score"]
DIAGRAMS = ["architecture.svg", "architecture-dark.svg", "how-it-works.svg", "how-it-works-dark.svg"]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "docs" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_committed_svgs_parse_and_are_clean():
    svgs = sorted(ASSETS.glob("*.svg"))
    assert len(svgs) >= len(DIAGRAMS)
    for p in svgs:
        text = p.read_text(encoding="utf-8")
        ET.fromstring(text)  # raises on bad XML
        assert "<script" not in text and "onload" not in text.lower(), p.name
        low = text.lower()
        for w in FORBIDDEN:
            assert w not in low, f"{p.name} contains {w!r}"
        assert p.stat().st_size < 300_000


@pytest.mark.parametrize("name", DIAGRAMS)
def test_diagrams_animate_and_honour_reduced_motion(name):
    text = (ASSETS / name).read_text(encoding="utf-8")
    assert "@keyframes" in text
    assert "prefers-reduced-motion: no-preference" in text
    # nothing may animate outside that media query: strip the media blocks and look for animation properties
    outside = re.sub(r"@media \(prefers-reduced-motion: no-preference\)\{.*?\}\}", "", text, flags=re.S)
    assert "animation:" not in outside and "animation-name" not in outside


def test_dark_variants_differ_from_light():
    for base in ("architecture", "how-it-works"):
        assert (ASSETS / f"{base}.svg").read_text() != (ASSETS / f"{base}-dark.svg").read_text()


def test_diagram_script_regenerates_identical_files(tmp_path):
    mod = _load("make_diagrams")
    mod.write_all(tmp_path)
    for name in DIAGRAMS:
        assert (tmp_path / name).read_text(encoding="utf-8") == (ASSETS / name).read_text(encoding="utf-8"), name


def _toy_outputs(d: Path):
    import duckdb

    (d / "planner").mkdir(parents=True)
    hn = {"load_factor_model": 0.54, "load_factor_full_allocation_capped_at_crush": 1.07, "load_factor_full_allocation": 1.7,
          "load_factor_band_low": 0.78, "load_factor_band_high": 0.89, "corridor_hits_total": 10, "corridors_total": 10,
          "corridor_hits_chance_expected": 9.99, "corridor_hits_both_ends": 7, "corridor_top_decile_share": 0.19,
          "corridor_top_decile_chance": 0.1, "corridor_hits_chance_method": "toy simulation",
          "pair_ratio_window": "0.4-2.5", "pair_ratio_window_alternative": "0.25-4"}
    (d / "validation_report.json").write_text(json.dumps({"headline_numbers": hn}))
    rows = ["operator,day_type,hour,level,evidence,bus_km,share"]
    for h in range(6, 22):
        rows += [f"DTC,weekday,{h},seats,rough,70,0.7", f"DTC,weekday,{h},standing,rough,20,0.2", f"DTC,weekday,{h},crowded,rough,{h % 4},0.05", f"DTC,weekday,{h},no_data,none,5,0.05"]
    (d / "coverage.csv").write_text("\n".join(rows))
    con = duckdb.connect()
    con.execute(f"COPY (SELECT 1 AS route_id, h AS hour, 'weekday' AS day_type, 0.3 + h/100.0 AS rho, 'cell' AS rho_src FROM range(5, 24) t(h)) TO '{d / 'planner' / 'gps_rho_fill.parquet'}' (FORMAT parquet)")
    con.execute(f"COPY (SELECT 'operator' AS scope, k AS key, h AS hour, 0.8 + h/40.0 AS factor, 10 AS n_pairs FROM range(0, 24) t(h), (VALUES ('DTC'), ('DIMTS')) v(k)) TO '{d / 'planner' / 'runtime_factors.parquet'}' (FORMAT parquet)")
    con.close()


def test_make_figures_runs_on_toy_outputs(tmp_path):
    mod = _load("make_figures")
    data, out = tmp_path / "processed", tmp_path / "figs"
    data.mkdir()
    _toy_outputs(data)
    written, skipped = mod.build(data, out)
    assert skipped == []
    assert len(written) == 5
    for p in written:
        text = p.read_text(encoding="utf-8")
        ET.fromstring(text)
        assert "{" not in re.sub(r"<style>.*?</style>", "", text, flags=re.S)  # no unformatted template left over
        for w in FORBIDDEN:
            assert w not in text.lower()


def test_make_figures_skips_cleanly_without_data(tmp_path):
    mod = _load("make_figures")
    written, skipped = mod.build(tmp_path / "nothing", tmp_path / "out")
    assert written == [] and skipped
    assert mod.main(["--data", str(tmp_path / "nothing"), "--out", str(tmp_path / "out")]) == 0


def test_make_figures_skips_one_figure_when_its_input_is_missing(tmp_path):
    mod = _load("make_figures")
    data = tmp_path / "processed"
    data.mkdir()
    _toy_outputs(data)
    (data / "coverage.csv").unlink()
    written, skipped = mod.build(data, tmp_path / "out")
    assert len(written) == 4 and len(skipped) == 1 and "coverage.csv" in skipped[0]
