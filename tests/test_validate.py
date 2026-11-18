import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import loads, validate
from src.pipeline.config import PUBLISHED_RIDERSHIP, Source
from src.pipeline.errors import GateError
from tests.test_loads_levels import DAY, a2b, build

KEYS = ["route_id", "day_type", "seq", "window_start_min"]


def level_table(con, name, levels, weights=None):
    df = pd.DataFrame({"route_id": 1, "day_type": "weekday", "seq": 1,
                       "window_start_min": [480 + 30 * i for i in range(len(levels))], "level": levels})
    con.register("_t", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _t")
    con.unregister("_t")


def weight_table(con, name, weights, tickets=None):
    df = pd.DataFrame({"route_id": 1, "day_type": "weekday", "seq": 1,
                       "window_start_min": [480 + 30 * i for i in range(len(weights))],
                       "weight": weights, "tickets": tickets or [100] * len(weights)})
    con.register("_t", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _t")
    con.unregister("_t")


def test_repeatability(con):
    same = ["seats", "standing", "crowded", "seats"]
    level_table(con, "wk1", same)
    level_table(con, "wk2", same)
    r = validate.compare_levels(con, "wk1", "wk2")
    assert r["unchanged_share"] == 1.0 and r["changed"] == 0
    level_table(con, "wk3", ["seats", "standing", "seats", "seats"])  # one cell of four flips
    r = validate.compare_levels(con, "wk1", "wk3")
    assert r["unchanged_share"] == 0.75 and r["unchanged_share_rider_weighted"] == 0.75
    assert r["less_crowded"] == 1 and r["more_crowded"] == 0
    weight_table(con, "wt", [1, 1, 3, 1])                              # the flipped cell carries the riders
    r = validate.compare_levels(con, "wk1", "wk3", "wt")
    assert r["unchanged_share"] == 0.75 and r["unchanged_share_rider_weighted"] == pytest.approx(0.5)
    assert r["bands"]["100+"]["cells"] == 4
    level_table(con, "wk4", ["no_data", "standing", "crowded", "seats"])  # no_data cells are not compared
    assert validate.compare_levels(con, "wk1", "wk4")["cells"] == 3


def test_corridor_hit_rule():
    pairs = [f"p{i}" for i in range(20)]
    rows = [(p, 480, 1.0 + i * 0.01) for i, p in enumerate(pairs)]  # p18 and p19 are the top decile at 08:00
    rows += [(p, 780, 1.0) for p in pairs]
    am = (480, 600)
    df = pd.DataFrame(rows, columns=["pair_id", "window_start_min", "rm_per_km"])
    assert validate.corridor_hit(df, {"p19"}, am)["hit"] is True
    assert validate.corridor_hit(df, {"p0", "p1"}, am)["hit"] is False
    # the same stretch high only at 13:00 does not count in the 08-10 window
    late = df.copy()
    late.loc[(late.pair_id == "p3") & (late.window_start_min == 780), "rm_per_km"] = 50.0
    assert validate.corridor_hit(late, {"p3"}, am)["hit"] is False
    assert validate.corridor_hit(late, {"p3"}, (780, 840))["hit"] is True
    zeros = pd.DataFrame([(p, 480, 0.0) for p in pairs], columns=df.columns)
    assert validate.corridor_hit(zeros, {"p0"}, am)["hit"] is False   # a zero never counts as top decile


def test_published_checks():
    hit = validate.published_check(450_000, (400_800, 601_200))
    assert hit["hit"] is True and hit["position"] == "inside"
    miss = validate.published_check(0.70, (0.78, 0.89))                # reported as a miss, not raised
    assert miss["hit"] is False and miss["position"] == "below" and miss["value"] == 0.70


def test_sensitivity_counts():
    # 55 people on a 12 m AC bus (rated 63) is standing; x1.3 = 71.5 is crowded, counted once
    r = validate.level_change_counts([55.0, 10.0, 80.0], [35, 35, 35], [63, 63, 63], 1.3)
    assert r["changed"] == 1 and r["cells"] == 3 and r["share"] == pytest.approx(1 / 3)
    assert validate.level_change_counts([55.0], [35], [63], 1.0)["changed"] == 0


def test_nan_gate(con):
    con.execute("""CREATE TABLE stretch_crowding AS
                   SELECT 1 AS route_id, 5.0::DOUBLE AS people_mid, 1.0::DOUBLE AS people_low,
                          9.0::DOUBLE AS people_high, 3.0::DOUBLE AS "E_r" """)
    assert validate.check_finite(con) == 0
    con.execute("UPDATE stretch_crowding SET people_mid = 'NaN'::DOUBLE")
    with pytest.raises(GateError):
        validate.check_finite(con)
    con.execute("UPDATE stretch_crowding SET people_mid = 5.0, people_high = 'Infinity'::DOUBLE")
    with pytest.raises(GateError):
        validate.check_finite(con)


def test_radial_rule():
    assert validate.radial_hit(in_am=40, out_am=10, in_pm=10, out_pm=40)["hit"] is True
    assert validate.radial_hit(in_am=10, out_am=40, in_pm=40, out_pm=10)["hit"] is False  # the reverse pattern
    part = validate.radial_hit(in_am=40, out_am=10, in_pm=40, out_pm=10)
    assert part["am"] is True and part["pm"] is False and part["hit"] is False


def radial_tables(con, flipped):
    con.execute("""CREATE TABLE canonical_stops AS SELECT * FROM (VALUES
        (1, 1, 28.760, 77.2167), (1, 2, 28.6315, 77.2167), (2, 1, 28.6315, 77.2167), (2, 2, 28.760, 77.2167))
        t(route_id, seq, lat, lon)""")
    con.execute("CREATE TABLE route_meta AS SELECT * FROM (VALUES (1, 2, false), (2, 1, false)) "
                "t(route_id, opposite_route_id, is_ring)")
    am_in, am_out, pm_in, pm_out = (10, 40, 40, 10) if flipped else (40, 10, 10, 40)
    rows = [(1, "weekday", 500, am_in, 5.0), (2, "weekday", 500, am_out, 5.0),
            (1, "weekday", 1100, pm_in, 5.0), (2, "weekday", 1100, pm_out, 5.0)]
    con.register("_sc", pd.DataFrame(rows, columns=["route_id", "day_type", "window_start_min", "people_mid",
                                                    "app_riders"]))
    con.execute("CREATE TABLE stretch_crowding AS SELECT * FROM _sc")


def test_radial_on_tables(con):
    radial_tables(con, flipped=False)         # route 1 runs from the outskirts to CP: inbound
    r = validate.radial(con)
    assert r["pairs"] == 1 and r["hit"] is True and r["am_share"] == 1.0 and r["pm_share"] == 1.0


def test_radial_on_tables_reverse_is_a_miss(con):
    radial_tables(con, flipped=True)
    r = validate.radial(con)
    assert r["pairs"] == 1 and r["hit"] is False and r["am_share"] == 0.0


def test_weekend_rule():
    wd = np.zeros(24)
    wd[9], wd[18], wd[13] = 100, 70, 10
    we = np.zeros(24)
    we[10], we[9], we[11], we[12] = 20, 15, 15, 15
    r = validate.weekend_rule(wd, we)
    assert r["lower"] and r["flatter"] and r["later_peak"] and r["hit"]
    assert validate.weekend_rule(wd, wd * 2)["lower"] is False
    spiky = np.zeros(24)
    spiky[10] = 30
    r = validate.weekend_rule(wd, spiky)                      # lower and later, but spikier
    assert r["flatter"] is False and r["hit"] is False


def test_peak_rule():
    h = np.zeros(24)
    h[9], h[18] = 5, 4
    assert validate.peak_rule(h, [8, 10], [17, 20])["hit"] is True
    h2 = np.zeros(24)
    h2[10], h2[18] = 5, 4                                      # 10:00 is outside 08-10
    r = validate.peak_rule(h2, [8, 10], [17, 20])
    assert r["am_hit"] is False and r["pm_hit"] is True


def toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch):
    rows = [a2b(DAY, f"{h:02d}:{m:02d}") for h in (8, 9, 18) for m in (0, 15, 30, 45)] * 8
    paths = build(con, tmp_path, toy_gtfs_dir, rows, published={"DTC": 2_000, "DIMTS": 1_000},
                  monkeypatch=monkeypatch)
    loads.run_levels(con, paths)
    return paths


def test_report_has_headline_numbers(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)
    rep = validate.run(con, paths)
    h = rep["headline_numbers"]
    for k in ("match_rate", "e_dtc", "e_dimts", "capped_routes", "unchanged_level_share", "corridor_hits_strong",
              "dtc_bus_km_model", "load_factor_model", "unallocated_share_dtc", "unallocated_share_dimts",
              "ceiling_bound_dimts", "alighting_sensitive_routes", "pair_ratio_window"):
        assert k in h, k
    assert h["pair_ratio_window"] == "0.4-2.5" and h["gps_available"] is False
    assert h["base_case_reproduced"] is True
    assert set(rep) >= {"gates", "expectations", "repeatability", "independent", "sensitivity", "diagnostics",
                        "coverage_summary", "headline_numbers"}
    assert "capacity_minus_10" in rep["sensitivity"] and "ceiling_2x" in rep["sensitivity"]
    assert rep["expectations"]["gps_stoptime"]["status"] == "not available"
    out = paths.processed
    data = json.loads((out / "validation_report.json").read_text())
    assert data["headline_numbers"]["match_rate"] == h["match_rate"]
    md = (out / "validation_report.md").read_text() + (out / "data_quality.md").read_text()
    for w in ("κ", "kappa", "McRAPTOR", "Pareto", "sigmoid", "score"):
        assert w.lower() not in md.lower(), w
    assert "service_class_regular" in md.replace(" ", "_") or "regular" in md
    # the stored tables are untouched by the variant runs
    assert con.execute("SELECT count(*) FROM stretch_crowding").fetchone()[0] == rep["reproduction"]["rows_stored"]
    assert rep["reproduction"]["exact"]
