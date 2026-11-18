import json

import pytest

from src.pipeline import network
from tests.test_network_clock import build, tk, sept


def run_assets(con, tmp_path, gtfs, rows):
    paths = build(con, tmp_path, gtfs, rows)
    network.run_network(con, paths)
    return paths


def mix(con, rid):
    return con.execute("SELECT share_9m, share_12m_ac, share_12m_nonac, basis FROM bus_mix WHERE route_id=?",
                       [rid]).fetchone()


def devi_rows(vehicles, n=5):
    return [tk("Alpha Terminal", "Charlie Chowk", "2026-09-01", f"08:{i:02d}", vehicle=v, route="D-005UP")
            for v in vehicles for i in range(n)]


def test_devi_name_route(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, devi_rows(["D1"]))
    assert mix(con, 301) == (1.0, 0.0, 0.0, "devi_name")


def vehicle_rows(n_devi, n_other):
    rows = devi_rows(["DEVI1"])
    rows += [tk("Delta Metro", "Echo Depot", "2026-09-01", f"09:{i:02d}", vehicle="DEVI1", route="909UP")
             for i in range(n_devi)]
    rows += [tk("Delta Metro", "Echo Depot", "2026-09-01", f"10:{i:02d}", vehicle=f"BUS{i}", route="909UP")
             for i in range(n_other)]
    return rows


def test_vehicle_rule_above_and_below_half(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, vehicle_rows(6, 4))
    assert con.execute("SELECT count(*) FROM devi_vehicles WHERE vehicle='DEVI1'").fetchone()[0] == 1
    s9, ac, nonac, basis = mix(con, 501)
    assert (s9, basis) == (pytest.approx(0.6), "vehicle_rule")
    assert ac + nonac == pytest.approx(0.4)


def test_vehicle_rule_below_threshold_is_12m(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, vehicle_rows(4, 6))
    assert mix(con, 501)[0] == 0
    assert mix(con, 501)[3] != "vehicle_rule"


def test_non_ac_tickets_raise_nonac_share(con, tmp_path, toy_gtfs_dir):
    rows = [{**tk("Delta Metro", "Echo Depot", "2026-09-01", f"09:{i:02d}", vehicle=f"B{i}", route="909UP"),
             "is_ac": i < 4} for i in range(8)]
    run_assets(con, tmp_path, toy_gtfs_dir, rows)
    s9, ac, nonac, basis = mix(con, 501)
    assert (s9, ac, nonac, basis) == (0, pytest.approx(0.5), pytest.approx(0.5), "is_ac")
    assert mix(con, 101) == (0, 1.0, 0, "default")


def test_route_specs_blend(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, vehicle_rows(5, 5))
    assert con.execute("SELECT seats, rated_total, crush FROM route_specs WHERE route_id=501").fetchone() == (
        pytest.approx(29.0), pytest.approx(49.5), pytest.approx(71.0))


def test_service_class(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, devi_rows(["D1"]))
    got = dict(con.execute('SELECT route_id, "class" FROM service_class').fetchall())
    assert got[601] == "office_special" and got[701] == "school"
    assert got[101] == "regular" and got[301] == "regular"


@pytest.mark.parametrize("name,cls", [("DAF-10DOWN", "daf"), ("MSB04UP", "school"), ("SPV10UP", "school"),
                                      ("DS-10UP", "office_special"), ("U-SPL-01UP", "office_special"),
                                      ("D-005UP", "regular"), ("ASD1UP", "regular")])
def test_service_class_patterns(name, cls):
    import re
    from src.pipeline.config import SERVICE_CLASS_PATTERNS
    got = next((c for c, p in SERVICE_CLASS_PATTERNS.items() if re.search(p, name, re.I)), "regular")
    assert got == cls


def test_places_group_by_stem_and_distance(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, devi_rows(["D1"]))
    pid = dict(con.execute("SELECT stop_id, place_id FROM places").fetchall())
    assert pid["3"] == pid["7"] and pid["6"] != pid["3"]
    assert con.execute("SELECT DISTINCT name FROM places WHERE place_id=?", [pid["3"]]).fetchall() == [("Charlie Chowk",)]


def test_hub_alias_and_stems(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, devi_rows(["D1"]))
    pid = dict(con.execute("SELECT stop_id, place_id FROM places").fetchall())
    alias = dict(con.execute("SELECT alias, place_id FROM hub_alias").fetchall())
    assert alias["cp"] == alias["connaught place"] == pid["8"]
    assert alias["isbt av"] == pid["9"]
    assert network.name_stem("Charlie Chowk Opp") == "charlie chowk"
    assert network.name_stem("Foo Terminal (T)") == "foo"


def test_hub_match_uses_word_boundaries_and_prefers_bus_stops():
    stops = [("1", "Quito Market", 28.0, 77.0), ("2", "Anand Vihar Metro Station", 28.1, 77.1),
             ("3", "ISBT Anand Vihar", 28.1, 77.12), ("4", "ITO", 28.2, 77.2)]
    place_of = network._group_places(stops)
    assert network._hub_place(["ito"], stops, place_of) == place_of["4"]
    assert network._hub_place(["isbt anand vihar", "anand vihar"], stops, place_of) == place_of["3"]


def test_segment_shape(con, tmp_path, toy_gtfs_dir):
    run_assets(con, tmp_path, toy_gtfs_dir, devi_rows(["D1"]))
    coords, length = con.execute("SELECT coords, length_m FROM segment_shapes WHERE route_id=101 AND seq=2").fetchone()
    c = json.loads(coords)
    assert c[0] == pytest.approx([28.6, 77.2], abs=1e-5) and c[-1] == pytest.approx([28.61349, 77.2], abs=1e-5)
    assert length == pytest.approx(1500, rel=0.01)
    assert con.execute("SELECT count(*) FROM segment_shapes WHERE route_id=101").fetchone()[0] == 4


def test_slice_never_moves_backwards():
    import numpy as np
    shape = np.array([[28.0, 77.0], [28.01, 77.0], [28.02, 77.0], [28.01, 77.001], [28.0, 77.001]])
    stops = np.array([[28.0, 77.0], [28.02, 77.0], [28.0, 77.001]])
    segs = network.slice_segments(shape, stops)
    assert segs[0][0] == [28.0, 77.0] and segs[0][-1] == [28.02, 77.0]
    assert segs[1][0] == [28.02, 77.0] and segs[1][-1] == [28.0, 77.001]
    assert len(segs[1]) == 3


def test_hub_matches_name_inside_parentheses():
    stops = [("1", "Shivaji Stadium Terminal ( Connaught Place )", 28.63, 77.21),
             ("2", "Rajiv Chowk Metro Station", 28.63, 77.22)]
    place_of = network._group_places(stops)
    assert network._hub_place(["connaught place"], stops, place_of) == place_of["1"]


def test_hub_prefers_most_specific_stem():
    stops = [("1", "Anand Vihar", 28.0, 77.0), ("2", "Anand Vihar ISBT Terminal", 28.1, 77.1)]
    place_of = network._group_places(stops)
    assert network._hub_place(["isbt anand vihar", "anand vihar isbt", "anand vihar"], stops, place_of) == place_of["2"]


def test_vehicle_rule_needs_min_linked_tickets(con, tmp_path, toy_gtfs_dir):
    rows = devi_rows(["DEVI1"]) + [tk("Delta Metro", "Echo Depot", "2026-09-01", f"09:{i:02d}", vehicle="DEVI1",
                                      route="909UP") for i in range(4)]
    run_assets(con, tmp_path, toy_gtfs_dir, rows)
    s9, _, _, basis = mix(con, 501)
    assert s9 == 0 and basis != "vehicle_rule"
