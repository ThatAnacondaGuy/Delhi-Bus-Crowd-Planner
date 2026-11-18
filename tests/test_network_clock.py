from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import clean, network, resolve
from src.pipeline.errors import GateError
from src.pipeline.paths import Paths
from tests.helpers import make_tickets


def tk(start, end, day, hhmm, vehicle="DL1X", route="101UP"):
    return {"route": route, "start_stop_name": start, "end_stop_name": end, "vehicle_number": vehicle,
            "created_at": f"{day} {hhmm}:00+05:30"}


def build(con, tmp_path, gtfs_dir, rows):
    base = Paths.default()
    paths = Paths(base.repo, Path(gtfs_dir), make_tickets(tmp_path, rows), base.gps_archive,
                  base.gps_aggregates, tmp_path / "out")
    clean.run(con, paths)
    resolve.run(con, paths)
    return paths


def pair_rows(days, gap_min=21, route="101UP"):
    rows = []
    for d in days:
        rows.append(tk("Alpha Terminal", "Echo Depot", d, "18:00", route=route))
        rows.append(tk("Delta Metro", "Echo Depot", d, f"18:{gap_min:02d}", route=route))
    return rows


def sept(n):
    return [str(date(2026, 9, 1) + timedelta(days=i)) for i in range(n)]


def test_factor_from_pairs(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, pair_rows(sept(1)))
    stats = network.run_clock(con, paths)
    assert stats.pairs == 1
    op = con.execute("SELECT factor, n_pairs FROM runtime_factors WHERE scope='operator' AND key='DTC' "
                     "AND hour=18").fetchall()
    assert op == [(pytest.approx(1.4), 1)]
    assert con.execute("SELECT count(*) FROM runtime_factors WHERE scope='route'").fetchone()[0] == 1
    clock = network.Clock.load(con)
    assert clock.factor(101, 18) == pytest.approx(1.4)  # one pair: falls back to the operator factor


def test_route_factor_with_30_pairs(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, pair_rows(sept(30)))
    network.run_clock(con, paths)
    assert con.execute("SELECT factor, n_pairs FROM runtime_factors WHERE scope='route' AND key='101' "
                       "AND hour=18").fetchall() == [(pytest.approx(1.4), 30)]
    assert network.Clock.load(con).factor(101, 18) == pytest.approx(1.4)


def test_short_pairs_ignored(con, tmp_path, toy_gtfs_dir):
    rows = []
    for d in sept(3):  # seq 1 -> 2 is only 300 template seconds
        rows += [tk("Alpha Terminal", "Echo Depot", d, "18:00"), tk("Bravo Market", "Echo Depot", d, "18:09")]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    assert network.run_clock(con, paths).pairs == 0


def frames(factors):
    canon = pd.DataFrame({"route_id": [101] * 3, "seq": [1, 2, 3], "template_s": [0, 300, 300],
                          "operator": ["DTC"] * 3})
    fac = pd.DataFrame([("operator", "DTC", h, f, 100) for h, f in factors.items()],
                       columns=["scope", "key", "hour", "factor", "n_pairs"])
    return network.Clock.from_frames(canon, fac)


def test_travel_seconds_advances_hour():
    clock = frames({7: 1.0, 8: 2.0})
    assert clock.travel_seconds(101, 1, 3, 7 * 60 + 55) == pytest.approx(900)
    assert clock.travel_seconds(101, 2, 2, 480) == 0


def test_missing_hour_falls_back_to_nearest():
    clock = frames({7: 1.5, 12: 2.0})
    assert clock.factor(101, 8) == 1.5 and clock.factor(101, 11) == 2.0 and clock.factor(101, 3) == 1.5
    assert clock.fallbacks == 22
    assert frames({}).factor(101, 9) == 1.0


def test_route_factor_needs_30_pairs():
    canon = pd.DataFrame({"route_id": [101, 101], "seq": [1, 2], "template_s": [0, 300], "operator": ["DTC"] * 2})
    fac = pd.DataFrame([("operator", "DTC", 9, 1.2, 500), ("route", "101", 9, 3.0, 29),
                        ("route", "101", 10, 3.0, 30)], columns=["scope", "key", "hour", "factor", "n_pairs"])
    clock = network.Clock.from_frames(canon, fac)
    assert clock.factor(101, 9) == 1.2 and clock.factor(101, 10) == 3.0


def test_passings(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [tk("Alpha Terminal", "Echo Depot", "2026-09-01", "08:00")])
    network.run_clock(con, paths)
    rows = con.execute("SELECT minute FROM passings WHERE route_id=101 AND seq=3 ORDER BY minute").fetchall()
    assert len(rows) == 64 and rows[0][0] == 6 * 60 + 10
    sh = con.execute("SELECT first_min, last_min FROM service_hours WHERE route_id=101").fetchone()
    assert sh[0] == 360 and sh[1] > 21 * 60


def test_service_hours_adds_ticket_hours(con, tmp_path, toy_gtfs_dir):
    rows = [tk("Alpha Terminal", "Echo Depot", d, "23:10", vehicle="NULL") for d in sept(3)]
    rows += [tk("Alpha Terminal", "Echo Depot", d, "05:10", vehicle="NULL") for d in sept(2)]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    network.run_clock(con, paths)
    got = con.execute("SELECT ticket_hours FROM service_hours WHERE route_id=101").fetchone()[0]
    assert got == "23"


def test_gate_raises_when_model_off(con, tmp_path, toy_gtfs_dir, monkeypatch):
    paths = build(con, tmp_path, toy_gtfs_dir, pair_rows(sept(40)))
    monkeypatch.setattr(network, "GATE_TOLERANCE", -1.0)
    with pytest.raises(GateError):
        network.run_clock(con, paths)


def test_stats_and_dq(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, pair_rows(sept(2)))
    network.run_clock(con, paths)
    dq = dict(con.execute("SELECT name, value FROM dq_clock").fetchall())
    assert dq["pairs"] == 2 and dq["fallback_cells"] > 0
