from pathlib import Path

import pytest

from src.pipeline import clean, loads, network, resolve
from src.pipeline.errors import GateError
from src.pipeline.paths import Paths
from tests.helpers import make_tickets


def tk(start, end, day, hhmm, vehicle="DL1X", route="101UP", amount=9.0):
    return {"route": route, "start_stop_name": start, "end_stop_name": end, "vehicle_number": vehicle,
            "created_at": f"{day} {hhmm}:00+05:30", "amount": amount}


def build(con, tmp_path, gtfs_dir, rows):
    base = Paths.default()
    paths = Paths(base.repo, Path(gtfs_dir), make_tickets(tmp_path, rows), base.gps_archive,
                  base.gps_aggregates, tmp_path / "out")
    clean.run(con, paths)
    resolve.run(con, paths)
    network.run_clock(con, paths)
    return paths


def stretch_totals(con, route_id=101):
    return dict(con.execute("SELECT seq, sum(pax) FROM stretch_riders WHERE route_id=? GROUP BY seq ORDER BY seq",
                            [route_id]).fetchall())


DAY = "2026-10-14"


def test_placement_on_stretches(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [tk("Alpha Terminal", "Delta Metro", DAY, "08:00")])
    loads.run_riders(con, paths)
    rows = con.execute("SELECT seq, minute, pax, tickets, corrected FROM stretch_riders WHERE route_id=101 "
                       "ORDER BY seq").fetchall()
    assert rows == [(1, 480, 1.0, 1, False), (2, 485, 1.0, 1, False), (3, 490, 1.0, 1, False)]


def test_exclusion_in_on_board_time(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, [tk("Alpha Terminal", "Echo Depot", "2026-10-06", "09:05")])
    stats = loads.run_riders(con, paths)
    # stretches at 09:05 and 09:10 stay; 09:15 (window start, half-open) and 09:20 are dropped
    assert con.execute("SELECT seq, minute FROM stretch_riders ORDER BY seq").fetchall() == [(1, 545), (2, 550)]
    assert stats.excluded_rm == pytest.approx(10.0)  # two 5-minute stretches, one rider
    loads.check_rider_gate(con)  # still balances
    # the reverse route has no tickets at all: no correction, route flagged
    assert con.execute("SELECT alighting_sensitive, moved_pax FROM terminal_asymmetry WHERE route_id=101"
                       ).fetchall() == [(True, 0.0)]


def alight_rows(day=DAY):
    rows = [tk("Alpha Terminal", "Echo Depot", day, f"08:{i:02d}") for i in range(10)]
    rows += [tk("Alpha Terminal", "Bravo Market", day, "09:00")]
    rows += [tk("Alpha Terminal", "Delta Metro", day, f"09:0{i}") for i in range(1, 4)]
    r = "101DOWN"
    rows += [tk("Echo Depot", "Alpha Terminal", day, f"10:0{i}", route=r) for i in range(2)]
    rows += [tk("Delta Metro", "Alpha Terminal", day, f"10:1{i}", route=r) for i in range(3)]
    rows += [tk("Bravo Market", "Alpha Terminal", day, "10:20", route=r)]
    return rows


def test_alighting_correction(con, tmp_path, toy_gtfs_dir, monkeypatch):
    monkeypatch.setattr(loads, "ALIGHTING_MIN_REVERSE_BOARD", 1)  # the toy reverse has only 2 terminal boardings
    paths = build(con, tmp_path, toy_gtfs_dir, alight_rows())
    stats = loads.run_riders(con, paths, correct_alighting=True)
    assert con.execute("SELECT route_id, terminal_alight, reverse_terminal_board, ratio, moved_pax "
                       "FROM terminal_asymmetry WHERE route_id=101").fetchall() == [(101, 10.0, 2.0, 1.0, 8.0)]
    # terminal alightings 10 -> 2; 8 move to Bravo (1/4) and Delta (3/4); Charlie has no reverse boardings
    assert stretch_totals(con) == {1: pytest.approx(14), 2: pytest.approx(11), 3: pytest.approx(11),
                                   4: pytest.approx(2)}
    assert con.execute("SELECT bool_or(corrected) FROM stretch_riders WHERE route_id=101 AND seq=4").fetchone()[0]
    assert stats.moved_pax == pytest.approx(8.0)
    loads.check_rider_gate(con)


def test_alighting_correction_off_moves_nothing(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, alight_rows())
    stats = loads.run_riders(con, paths, correct_alighting=False)
    assert stretch_totals(con) == {1: pytest.approx(14), 2: pytest.approx(13), 3: pytest.approx(13),
                                   4: pytest.approx(10)}
    assert con.execute("SELECT moved_pax FROM terminal_asymmetry WHERE route_id=101").fetchone()[0] == 0
    assert stats.moved_pax == 0
    assert not con.execute("SELECT bool_or(corrected) FROM stretch_riders").fetchone()[0]
    loads.check_rider_gate(con)


def test_unknown_reverse_is_flagged_not_corrected(con, tmp_path, toy_gtfs_dir):
    rows = [tk("Alpha Terminal", "Charlie Chowk", DAY, "08:00", route="D-005UP") for _ in range(3)]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    stats = loads.run_riders(con, paths)
    assert con.execute("SELECT terminal_alight, reverse_terminal_board, moved_pax, alighting_sensitive "
                       "FROM terminal_asymmetry WHERE route_id=301").fetchall() == [(3.0, None, 0.0, True)]
    assert stats.alighting_sensitive == 1 and stats.moved_pax == 0
    assert stretch_totals(con, 301) == {1: 3, 2: 3}


def test_ring_stretches_wrap_into_range(con, tmp_path, toy_gtfs_dir):
    rows = [tk("Foxtrot Nagar", "Charlie Chowk", DAY, "08:00", route="OMS(+)UP")]
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    assert con.execute("SELECT dest_seq FROM tickets_resolved").fetchone()[0] == 5  # wraps past N=4
    loads.run_riders(con, paths)
    assert con.execute("SELECT seq, minute FROM stretch_riders WHERE route_id=401 ORDER BY minute").fetchall() \
        == [(3, 480), (1, 487)]  # 3->4 takes 424 s


def test_gate_raises_on_corrupted_pax(con, tmp_path, toy_gtfs_dir):
    paths = build(con, tmp_path, toy_gtfs_dir, alight_rows())
    loads.run_riders(con, paths)
    loads.check_rider_gate(con)
    con.execute("UPDATE stretch_riders SET pax = pax + 100 WHERE route_id=101 AND seq=1 AND minute=480")
    with pytest.raises(GateError):
        loads.check_rider_gate(con)


def test_uninformative_reverse_moves_nothing(con, tmp_path, toy_gtfs_dir):
    rows = [tk("Alpha Terminal", "Echo Depot", DAY, f"08:0{i}") for i in range(6)]
    rows += [tk("Delta Metro", "Alpha Terminal", DAY, "10:00", route="101DOWN")]  # reverse: 0 terminal boardings
    paths = build(con, tmp_path, toy_gtfs_dir, rows)
    stats = loads.run_riders(con, paths)
    assert con.execute("SELECT moved_pax, alighting_sensitive FROM terminal_asymmetry WHERE route_id=101"
                       ).fetchall() == [(0.0, True)]
    assert stretch_totals(con)[4] == 6 and stats.moved_pax == 0
