import sqlite3

import pandas as pd

from src.pipeline import gps
from src.pipeline.db import connect
from src.pipeline.paths import Paths
from tests.fixtures.build_toy_gps import BASE_TS, DAY, build_toy_gps, ping, toy_stops


def _trips(tmp_path, extra=()):
    db = build_toy_gps(tmp_path / "bus_movements_2026_10_15.db", extra)
    con = connect()
    n = gps.load_pings(con, db, DAY)
    return con, n, gps.find_trips(con, toy_stops())


def test_duplicate_polls_dropped(tmp_path):
    con, n, _ = _trips(tmp_path)
    total = sqlite3.connect(tmp_path / "bus_movements_2026_10_15.db").execute("SELECT count(*) FROM vehicle_feed").fetchone()[0]
    assert n == total - 1
    assert con.execute("SELECT count(*) FROM pings").fetchone()[0] == n


def test_trip_needs_80_percent_of_stops_in_order(tmp_path):
    _, _, t = _trips(tmp_path)
    ran = dict(zip(t["vehicle"], t["ran"]))
    assert ran["A"] and ran["B"]          # 5 of 5 and 4 of 5
    assert not ran["C"]                   # 3 of 5
    assert not ran["D"]                   # reverse order: chain of 1
    assert "E" not in ran                 # 300 m away: no ping matches a stop


def test_speed_column_never_read(tmp_path):
    _, _, t1 = _trips(tmp_path)
    db = build_toy_gps(tmp_path / "g.db")
    c = sqlite3.connect(db)
    c.execute("UPDATE vehicle_feed SET speed = random() * 1e6")
    c.commit()
    c.close()
    con = connect()
    gps.load_pings(con, db, DAY)
    t3 = gps.find_trips(con, toy_stops())
    pd.testing.assert_frame_equal(t1.reset_index(drop=True), t3.reset_index(drop=True))
    assert "speed" not in {r[0] for r in con.execute("DESCRIBE pings").fetchall()}


def test_coverage_and_rho():
    trips = pd.DataFrame({"route_id": [101] * 4, "hour": [9] * 4, "ran": [True] * 4,
                          "in_first": [True] * 4, "in_mid": [True] * 4, "in_last": [True] * 4,
                          "run_ratio": [1.0] * 4})
    sched = pd.DataFrame({"route_id": [101], "hour": [9], "scheduled_trips": [8]})
    day = {"2026-10-15": "weekday"}
    full = pd.DataFrame({"route_id": [101], "date": ["2026-10-15"], "linked": [5], "seen": [4]})
    out = gps.combine({"2026-10-15": trips}, {"2026-10-15": full}, sched, day).iloc[0]
    assert out["coverage"] == 0.8 and out["source"] == "gps"
    assert abs(out["rho"] - 4 / (8 * 0.8)) < 1e-9
    low = full.assign(seen=3)
    out = gps.combine({"2026-10-15": trips}, {"2026-10-15": low}, sched, day).iloc[0]
    assert out["coverage"] == 0.6 and out["source"] == "schedule_only" and pd.isna(out["rho"])


def test_load_aggregates_missing_csv(tmp_path):
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, base.tickets_csv, base.gps_archive, tmp_path / "none", tmp_path)
    con = connect()
    assert gps.load_aggregates(con, paths) is False
    assert con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'gps_route_hour'").fetchone()[0] == 0


def test_load_aggregates_reads_csv(tmp_path):
    d = tmp_path / "agg"
    d.mkdir()
    (d / "gps_route_hour.csv").write_text(
        "route_id,hour,day_type,observed_trips,scheduled_trips,coverage,rho,rho_first,rho_mid,rho_last,runtime_ratio,source\n"
        "101,9,weekday,4,8,0.9,0.55,,,,1.1,gps\n")
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, base.tickets_csv, base.gps_archive, d, tmp_path)
    con = connect()
    assert gps.load_aggregates(con, paths) is True
    assert con.execute("SELECT rho FROM gps_route_hour").fetchone()[0] == 0.55


def test_rho_model_shrinks_small_cells_and_caps(tmp_path):
    d = tmp_path / "agg"
    d.mkdir()
    head = "route_id,hour,day_type,observed_trips,scheduled_trips,coverage,rho,rho_first,rho_mid,rho_last,runtime_ratio,source\n"
    (d / "gps_route_hour.csv").write_text(head +
        "101,9,weekday,0,1,1.0,0.0,,,,,gps\n"            # one scheduled trip, none seen
        "101,10,weekday,8,4,1.0,2.0,,,,,gps\n"           # more seen than scheduled
        "101,11,weekday,4,8,1.0,0.5,,,,,gps\n"
        "102,9,weekday,,5,0.5,,,,,,schedule_only\n")
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, base.tickets_csv, base.gps_archive, d, tmp_path)
    con = connect()
    assert gps.load_aggregates(con, paths)
    rm = dict(con.execute("SELECT route_id * 100 + hour, rho_model FROM gps_route_hour").fetchall())
    route_rho = (0 + 8 + 4) / (1 + 4 + 8)
    assert abs(rm[10109] - 3 * route_rho / 4) < 1e-9       # pulled up from 0 toward the route's rho
    assert rm[10110] == 1.0                                # capped
    assert rm[10209] is None                               # schedule only: no rho


def test_fill_order_cell_route_operator(tmp_path):
    d = tmp_path / "agg"
    d.mkdir()
    head = "route_id,hour,day_type,observed_trips,scheduled_trips,coverage,rho,rho_first,rho_mid,rho_last,runtime_ratio,source\n"
    (d / "gps_route_hour.csv").write_text(head +
        "101,9,weekday,4,8,1.0,0.5,,,,,gps\n"
        "101,10,weekday,0,0,1.0,,,,,,gps\n"
        "102,9,weekday,2,8,1.0,0.25,,,,,gps\n"
        "103,9,weekday,,5,0.5,,,,,,schedule_only\n")
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, base.tickets_csv, base.gps_archive, d, tmp_path)
    con = connect()
    con.execute("CREATE TABLE route_meta AS SELECT * FROM (VALUES (101::BIGINT,'DTC'),(102,'DTC'),(103,'DTC'),(104,'DIMTS')) t(route_id, operator)")
    assert gps.load_aggregates(con, paths)
    f = {(r, h): (rho, s) for r, h, rho, s in con.execute(
        "SELECT route_id, hour, rho, rho_src FROM gps_rho_fill WHERE day_type = 'weekday'").fetchall()}
    assert f[(101, 9)][1] == "cell"
    assert f[(101, 10)][1] == "route" and abs(f[(101, 10)][0] - 0.5) < 0.2
    op_hour = (4 + 2) / 16
    assert f[(103, 9)][1] == "op_hour" and abs(f[(103, 9)][0] - op_hour) < 1e-9
    assert f[(103, 3)][1] == "op_day" and abs(f[(103, 3)][0] - op_hour) < 1e-9
    assert f[(104, 9)][1] == "none" and f[(104, 9)][0] == 1.0
