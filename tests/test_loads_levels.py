import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import clean, loads, network, resolve
from src.pipeline.config import BUS_SPECS, PUBLISHED_RIDERSHIP, SCALE_RANGE, Source
from src.pipeline.errors import GateError
from src.pipeline.loads import cap_to_crush, evidence, level, sampling_se, waterfill
from src.pipeline.paths import Paths
from tests.helpers import make_tickets

DAY = "2026-10-14"  # a Wednesday


def tk(start, end, day, hhmm, route="101UP", vehicle="DL1X"):
    return {"route": route, "start_stop_name": start, "end_stop_name": end, "vehicle_number": vehicle,
            "created_at": f"{day} {hhmm}:00+05:30", "amount": 9.0}


def a2b(day, hhmm, route="101UP"):
    return tk("Alpha Terminal", "Bravo Market", day, hhmm, route=route)


def build(con, tmp_path, gtfs_dir, rows, published=None, monkeypatch=None):
    base = Paths.default()
    paths = Paths(base.repo, Path(gtfs_dir), make_tickets(tmp_path, rows), base.gps_archive,
                  base.gps_aggregates, tmp_path / "out")
    clean.run(con, paths)
    resolve.run(con, paths)
    network.run_network(con, paths)
    loads.run_riders(con, paths)
    if published is not None:
        monkeypatch.setattr(loads, "PUBLISHED_RIDERSHIP", {k: Source(v, "t", "u", "n") for k, v in published.items()})
    return paths


def cr(con, where="true", cols="*"):
    return con.execute(f"SELECT {cols} FROM stretch_crowding WHERE {where}").df()


# ------------------------------------------------------------------ pure functions

def test_level_thresholds():
    assert level(24.4, BUS_SPECS["12m_ac"]) == "seats" and level(24.6, BUS_SPECS["12m_ac"]) == "standing"
    assert level(63, BUS_SPECS["12m_ac"]) == "standing" and level(63.1, BUS_SPECS["12m_ac"]) == "crowded"
    assert level(16.0, BUS_SPECS["9m_devi"]) == "seats" and level(36.5, BUS_SPECS["9m_devi"]) == "crowded"


def test_waterfill():
    E, Er = waterfill({"a": 100, "b": 100}, {"a": 10.0, "b": 1e9}, total=4000)
    assert Er["a"] == 10.0 and abs(E - 30.0) < 1e-6 and abs(100 * 10 + 100 * Er["b"] - 4000) < 1e-6
    # nobody capped, an unbounded route, a route without sales
    E, Er = waterfill({"a": 100, "b": 100, "c": 0}, {"a": 50.0}, total=2000)
    assert E == pytest.approx(10.0) and Er == {"a": 10.0, "b": 10.0, "c": 10.0}
    # the bounds cannot reach the total: everyone capped
    E, Er = waterfill({"a": 100, "b": 100}, {"a": 5.0, "b": 8.0}, total=4000)
    assert Er == {"a": 5.0, "b": 8.0}


def test_waterfill_ceiling_binds_and_leaves_residual():
    app, bound = {"a": 100, "b": 100}, {"a": 10.0}
    E, Er = waterfill(app, bound, total=4000, ceiling=15.0)
    assert E == 15.0 and Er == {"a": 10.0, "b": 15.0}
    assert 4000 - sum(app[r] * Er[r] for r in app) == pytest.approx(1500.0)  # unallocated
    E, _ = waterfill(app, bound, total=4000, ceiling=100.0)                 # ceiling above: unchanged
    assert E == pytest.approx(30.0)


def test_evidence_states():
    s = BUS_SPECS["12m_ac"]
    assert evidence(20, 30, s, set(), False) == "rough"          # spans seats/standing
    assert evidence(30, 50, s, set(), False) == "many_tickets"   # standing throughout
    assert evidence(30, 50, s, {"low_app_use"}, False) == "rough"
    assert evidence(30, 50, s, set(), True) == "none"
    assert evidence(0, 10, s, set(), False) == "rough"           # upper end under the seats threshold


def test_cap_at_crush_function():
    assert cap_to_crush(130, BUS_SPECS["12m_ac"]) == (100.0, True)
    assert cap_to_crush(99.5, BUS_SPECS["12m_ac"]) == (99.5, False)


def test_sampling_se_from_daily_values():
    assert sampling_se([0, 2, 0, 2]) == pytest.approx(np.std([0, 2, 0, 2], ddof=1) / 2)
    assert sampling_se([5]) == 0.0


def test_simplify_drops_collinear_points():
    pts = [[28.6, 77.2], [28.601, 77.2], [28.602, 77.2], [28.602, 77.201]]
    out = loads._simplify(pts, 3.0)
    assert out == [[77.2, 28.6], [77.2, 28.602], [77.201, 28.602]]


# ------------------------------------------------------------------ on the toy network

def test_load_base_centred_90(con, tmp_path, toy_gtfs_dir):
    rows = [a2b(DAY, h) for h in ("07:14", "07:15", "08:44", "08:45")]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    loads.run_levels(con, paths)
    r = cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=480").iloc[0]
    assert r.app_riders == 2.0                       # 07:15 and 08:44 only: [07:15, 08:45)
    assert r.buses == 6 and r.bus_source == "schedule"  # buses at 07:15 ... 08:30
    assert cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=450").iloc[0].app_riders \
        == 2.0                                       # [06:45, 08:15): 07:14 and 07:15
    assert cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=510").iloc[0].app_riders \
        == 2.0                                       # [07:45, 09:15): 08:44 and 08:45


def test_s0_widened_then_mismatch_and_gate(con, tmp_path, toy_gtfs_dir):
    rows = [a2b(DAY, "08:00") for _ in range(300)]
    rows += [a2b(DAY, "06:20", route="D-005UP"), a2b(DAY, "05:00", route="D-005UP")]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    stats = loads.run_levels(con, paths)             # the gate passes: well under 1% of rider volume
    w = cr(con, "route_id=301 AND seq=1 AND window_start_min=360").iloc[0]
    assert w.bus_source == "widened" and w.buses == 1  # base [05:15, 06:45) is empty, +-30 min finds 07:00
    m = cr(con, "route_id=301 AND seq=1 AND window_start_min=300").iloc[0]
    assert m.bus_source == "none" and m.level == "no_data" and m.evidence == "none"
    assert "schedule_mismatch" in m["flags"] and pd.isna(m.people_mid)
    assert 0 < stats.s0_mismatch_share < 0.01 and stats.s0_widened_share > 0


def test_s0_gate_fails_when_riders_have_no_bus(con, tmp_path, toy_gtfs_dir):
    rows = [a2b(DAY, "05:00", route="D-005UP")] + [a2b(DAY, "08:00")]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    with pytest.raises(GateError):
        loads.run_levels(con, paths)


def test_cap_at_crush_end_to_end(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00")])  # real published totals: huge scale
    loads.run_levels(con, paths)
    r = cr(con, "route_id=101 AND seq=1 AND window_start_min=480").iloc[0]
    assert r.people_mid == 100 and r.level == "crowded" and "full" in r["flags"].split(",")
    assert r.people_low <= r.people_mid <= r.people_high <= 100


def test_zero_ticket_route_is_no_data(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00")])
    loads.run_levels(con, paths)
    z = cr(con, "route_id=501")
    assert len(z) > 0 and (z.level == "no_data").all() and (z.evidence == "none").all()
    assert not (z.level == "seats").any()


def test_service_classes_in_supply(con, tmp_path, toy_gtfs_dir):
    """R6: passings are not filtered, supply is: office_special runs weekdays only, school never."""
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00"), a2b("2026-10-11", "08:00")])  # a Sunday too
    assert con.execute("SELECT count(*) FROM passings WHERE route_id IN (601, 701)").fetchone()[0] > 0
    loads.run_levels(con, paths)
    assert cr(con, "day_type='weekend' AND route_id=101", "count(*)").iloc[0, 0] > 0
    assert cr(con, "route_id=701", "count(*)").iloc[0, 0] == 0
    assert cr(con, "route_id=601 AND day_type='weekend'", "count(*)").iloc[0, 0] == 0
    wk = cr(con, "route_id=601 AND day_type='weekday'")
    assert len(wk) > 0 and (wk.buses > 0).all() and wk["flags"].str.contains("office_special").all()
    assert not cr(con, "route_id=101")["flags"].str.contains("office_special").any()


def test_sampling_range_and_scale(con, tmp_path, toy_gtfs_dir, monkeypatch):
    rows = [a2b(f"2026-10-{d}", "08:00") for d in (12, 12, 14, 14)] + [a2b("2026-10-15", "15:00")]
    # E_op = 10 / 1.25 app passengers per clean day = 8
    paths = build(con, tmp_path, toy_gtfs_dir, rows, published={"DTC": 10.0, "DIMTS": 5.0}, monkeypatch=monkeypatch)
    loads.run_levels(con, paths)
    r = cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=480").iloc[0]
    se_l = sampling_se([2, 0, 2, 0]) / 6
    lo, hi = SCALE_RANGE
    assert r.E_r == pytest.approx(8.0) and r.buses == 6
    assert r.people_mid == pytest.approx(8 * (1 / 6), abs=1e-3)
    assert r.people_low == pytest.approx(lo * 8 * max(1 / 6 - se_l, 0), abs=1e-3)
    assert r.people_high == pytest.approx(hi * 8 * (1 / 6 + se_l), abs=1e-3)
    assert r.level == "seats" and r.evidence == "rough"          # a quiet count is a rough "usually seats"
    # the SQL levels agree with the Python functions
    d = cr(con, "people_mid IS NOT NULL")
    for x in d.itertuples():
        spec = BUS_SPECS["12m_ac"]._replace(seats=x.seats, rated_total=x.rated_total, crush=x.crush)
        assert x.level == level(x.people_mid, spec)
        assert x.evidence == evidence(x.people_low, x.people_high, spec, set(x.flags.split(",")), False)


def test_water_filling_flags_capped_routes(con, tmp_path, toy_gtfs_dir, monkeypatch):
    rows = [a2b(DAY, "08:00") for _ in range(40)]
    rows += [tk("Echo Depot", "Delta Metro", DAY, "10:00", route="101DOWN") for _ in range(10)]
    paths = build(con, tmp_path, toy_gtfs_dir, rows, published={"DTC": 1000.0, "DIMTS": 5.0}, monkeypatch=monkeypatch)
    stats = loads.run_levels(con, paths)
    cells = cr(con, "route_id=101 AND day_type='weekday' AND tickets >= 30")
    bound = 100 / np.quantile(cells.app_riders / cells.buses, 0.95)
    e_star = (1000 - 40 * bound) / 10
    assert stats.e_op["DTC"] == pytest.approx(20.0) and stats.e_star["DTC"] == pytest.approx(e_star, rel=2e-3)
    assert stats.capped_routes == 1
    up, down = cr(con, "route_id=101").iloc[0], cr(con, "route_id=102").iloc[0]
    assert up.E_r == pytest.approx(bound, rel=2e-3) and down.E_r == pytest.approx(e_star, rel=2e-3)
    assert cr(con, "route_id=101")["flags"].str.contains("scaled_to_capacity").all()
    assert not cr(con, "route_id=102")["flags"].str.contains("scaled_to_capacity").any()
    assert cells.people_mid.max() <= 100 + 1e-6 and (cells.people_mid.max() > 90)  # the p95 cell sits at crush


def test_alighting_sensitive_flag(con, tmp_path, toy_gtfs_dir):
    rows = [a2b(DAY, "08:00") for _ in range(3)] + [
        tk("Alpha Terminal", "Charlie Chowk", DAY, "08:00", route="D-005UP") for _ in range(3)]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    loads.run_levels(con, paths)
    r = cr(con, "route_id=301")
    assert r["flags"].str.contains("alighting_sensitive").all()
    assert (r[r.seq == 2].evidence != "many_tickets").all()      # the last stretch is rough at best
    assert not cr(con, "route_id=101")["flags"].str.contains("alighting_sensitive").any()


def test_gps_rho_applies_when_table_exists(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00")])
    con.execute("CREATE TABLE gps_route_hour AS SELECT 101::BIGINT AS route_id, 8 AS hour, 0.5 AS rho")
    loads.run_levels(con, paths)
    r = cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=480").iloc[0]
    assert r.buses == 3 and r.bus_source == "gps"
    assert cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=450").iloc[0].bus_source \
        == "schedule"


def test_gps_rho_model_by_day_type_and_schedule_only(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00")])
    con.execute("""CREATE TABLE gps_route_hour AS
        SELECT * FROM (VALUES (101::BIGINT, 8, 'weekday', 0.5, 'gps'), (101::BIGINT, 8, 'weekend', 0.25, 'gps'),
                              (101::BIGINT, 7, 'weekday', NULL, 'schedule_only')) t(route_id, hour, day_type, rho_model, source)""")
    con.execute("ALTER TABLE gps_route_hour ADD COLUMN rho DOUBLE")
    loads.run_levels(con, paths)
    r = cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=480").iloc[0]
    assert r.buses == 3 and r.bus_source == "gps"            # rho_model 0.5 on 6 scheduled buses
    r = cr(con, "route_id=101 AND seq=1 AND day_type='weekday' AND window_start_min=420")
    assert (r.bus_source == "schedule").all() or r.empty     # NULL rho_model: rho = 1, flagged schedule


def test_outputs_and_planner_export(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00") for _ in range(3)])
    loads.run_levels(con, paths)
    out = paths.processed
    for f in ("stretch_crowding.parquet", "corridor_values.parquet", "corridor_geometry.geojson",
              "route_hour_summary.csv", "coverage.csv"):
        assert (out / f).exists(), f
    sc = pd.read_parquet(out / "stretch_crowding.parquet")
    assert list(sc.columns) == [
        "route_id", "short_name", "operator", "direction", "seq", "from_stop_id", "to_stop_id", "from_name",
        "to_name", "day_type", "window_start_min", "app_riders", "tickets", "buses", "bus_source", "share_9m",
        "seats", "rated_total", "crush", "E_r", "people_mid", "people_low", "people_high", "level", "evidence",
        "flags"]
    assert set(sc.level) <= {"seats", "standing", "crowded", "no_data"}
    assert set(sc.bus_source) <= {"schedule", "gps", "widened", "none"}
    cv = pd.read_parquet(out / "corridor_values.parquet")
    geo = json.loads((out / "corridor_geometry.geojson").read_text())
    ids = {f["id"] for f in geo["features"]}
    assert ids == set(cv.pair_id) and all(len(f["geometry"]["coordinates"]) >= 2 for f in geo["features"])
    # one stop pair: 101UP is the only routed bus with data on Alpha -> Bravo
    r = sc[(sc.route_id == 101) & (sc.seq == 1) & (sc.window_start_min == 480) & (sc.day_type == "weekday")].iloc[0]
    c = cv[(cv.pair_id == f"{r.from_stop_id}-{r.to_stop_id}") & (cv.window_start_min == 480)
           & (cv.day_type == "weekday")].iloc[0]
    assert c.load_ratio == pytest.approx(r.people_mid / r.rated_total, abs=1e-3)
    assert c.share_crowded == 1.0 and c.crowded_rider_min > 0
    names = {p.stem for p in paths.planner_dir.glob("*.parquet")}
    assert names == {"canonical_stops", "segment_shapes", "places", "hub_alias", "passings", "service_hours",
                     "service_class", "runtime_factors", "bus_mix", "route_specs"}
    assert len(pd.read_parquet(paths.planner_dir / "passings.parquet")) == con.execute(
        "SELECT count(*) FROM passings").fetchone()[0]  # passings are exported unfiltered
    assert con.execute("SELECT count(*) FROM dq_levels").fetchone()[0] > 0


def test_loads_stage_runs_riders_then_levels():
    from src.pipeline import run
    assert run.STAGES["loads"] == "src.pipeline.loads:run_loads"


def test_bound_uses_weekday_peak_cells_only(con, tmp_path, toy_gtfs_dir, monkeypatch):
    rows = [a2b(DAY, "08:00") for _ in range(40)] + [a2b(DAY, "14:00") for _ in range(35)]  # off-peak is heavier
    rows += [tk("Echo Depot", "Delta Metro", DAY, "10:00", route="101DOWN") for _ in range(10)]
    paths = build(con, tmp_path, toy_gtfs_dir, rows, published={"DTC": 3000.0, "DIMTS": 5.0}, monkeypatch=monkeypatch)
    loads.run_levels(con, paths)
    peak = cr(con, "route_id=101 AND day_type='weekday' AND tickets >= 30 AND window_start_min BETWEEN 420 AND 650")
    off = cr(con, "route_id=101 AND day_type='weekday' AND tickets >= 30 AND window_start_min BETWEEN 750 AND 900")
    assert len(peak) > 0 and len(off) > 0
    bound = 100 / np.quantile(peak.app_riders / peak.buses, 0.95)
    assert con.execute("SELECT bound FROM _er WHERE route_id=101").fetchone()[0] == pytest.approx(bound, rel=2e-3)


def test_corridor_zero_not_null_without_crowding(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = build(con, tmp_path, toy_gtfs_dir, [a2b(DAY, "08:00")], published={"DTC": 2.0, "DIMTS": 5.0},
                  monkeypatch=monkeypatch)
    loads.run_levels(con, paths)
    cv = pd.read_parquet(paths.processed / "corridor_values.parquet")
    assert len(cv) > 0 and cv.share_crowded.notna().all() and cv.crowded_rider_min.notna().all()
    assert (cv.share_crowded == 0).any() and (cv.crowded_rider_min == 0).any()
