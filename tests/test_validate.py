import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import loads, validate
from src.pipeline.config import PUBLISHED_RIDERSHIP, Source, WindowSpec
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
    for k in ("corridor_hits_chance_expected", "corridor_top_decile_share", "corridor_hits_both_ends"):
        assert k in h, k
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


def test_chance_baseline_is_high_for_many_stretches_and_low_for_few():
    pairs = [f"p{i}" for i in range(200)]
    df = pd.DataFrame([(p, 480, 1.0 + i * 0.01) for i, p in enumerate(pairs)],
                      columns=["pair_id", "window_start_min", "rm_per_km"])
    r = validate.chance_expected_hits(df, [(100, ["am"]), (1, ["am"])], {"am": (480, 600)}, draws=1000, seed=1)
    big, small = r["per_corridor"]
    assert big > 0.99 and 0.05 < small < 0.2                # 1 - 0.9^n; one stretch hits about 10% of the time
    assert r["expected_hits"] == pytest.approx(big + small)
    again = validate.chance_expected_hits(df, [(100, ["am"]), (1, ["am"])], {"am": (480, 600)}, draws=1000, seed=1)
    assert again == r                                        # seeded: reproducible


def test_published_bands_come_from_expectations(con, tmp_path, toy_gtfs_dir, monkeypatch):
    import dataclasses
    from src.pipeline.expectations import load_expectations
    exp = dataclasses.replace(load_expectations(Path(__file__).parent.parent / "validation" / "expectations.yaml"),
                              dtc_bus_km_published=777_000.0, dtc_bus_km=(1.0, 2.0), load_factor_band=(0.11, 0.22))
    monkeypatch.setattr(validate, "load_expectations", lambda _p: exp)
    paths = toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)
    rep = validate.run(con, paths)
    bk, lf = rep["independent"]["dtc_bus_km"], rep["independent"]["load_factor"]
    assert bk["published"] == 777_000.0 and bk["band"] == [1.0, 2.0] and lf["band"] == [0.11, 0.22]
    assert rep["headline_numbers"]["dtc_bus_km_published"] == 777_000.0
    md = (paths.processed / "validation_report.md").read_text()
    assert "777,000" in md and "0.11-0.22" in md
    assert "501,000" not in md and "0.78-0.89" not in md


def test_corridor_headline_is_one_clean_sentence(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)
    rep = validate.run(con, paths)
    h = rep["headline_numbers"]
    line = next(x for x in (paths.processed / "validation_report.md").read_text().splitlines()
                if x.startswith("- Pre-registered corridors"))
    assert line.count("(") == line.count(")")                 # no stray bracket
    assert f"{h['corridor_hits_weak']} of {h['corridors_weak']} weak;" in line
    assert "the primary rule's result" not in line.split("weak")[0]


def test_bus_km_weights_come_from_the_window_config(con, tmp_path, toy_gtfs_dir, monkeypatch):
    toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)

    def weekday_bus_km():
        validate._scx(con)
        return con.execute("SELECT sum(bus_km) FROM _scx WHERE day_type = 'weekday'").fetchone()[0]

    base = weekday_bus_km()
    assert base > 0
    monkeypatch.setattr(validate, "WINDOWS", {**validate.WINDOWS, "weekday": WindowSpec(60, 90)})
    assert weekday_bus_km() == pytest.approx(2 * base)


def test_headline_carries_the_numbers_the_documents_quote(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)
    h = validate.run(con, paths)["headline_numbers"]
    for k in ("passengers_clean", "route_strings", "days_in_file", "weekday_crowded_share",
              "evidence_rough_share", "ticket_pairs"):
        assert k in h and h[k] is not None, k


def test_app_share_numbers_follow_published_ridership_and_scale(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = toy_report(con, tmp_path, toy_gtfs_dir, monkeypatch)
    rep = validate.run(con, paths)
    head = {"published_ridership_dtc": 2_000_000.0, "published_ridership_dimts": 1_000_000.0,
            "e_dtc": 40.0, "e_dimts": 100.0}
    out = validate.doc_numbers(con, rep["diagnostics"], rep["coverage_summary"], head)
    share = (2_000_000 / 40 + 1_000_000 / 100) / 3_000_000
    assert out["app_share_of_riders"] == pytest.approx(share)
    assert out["app_riders_one_in"] == round(1 / share)
    # if app tickets are 3% or 4% of tickets, this share of riders must be outside the ticket base
    assert out["outside_ticket_base_needed_low"] == pytest.approx(1 - share / 0.03)
    assert out["outside_ticket_base_needed_high"] == pytest.approx(1 - share / 0.04)
    assert all(v is not None for v in out.values())
