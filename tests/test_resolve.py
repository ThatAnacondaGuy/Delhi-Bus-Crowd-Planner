import json
import shutil
from pathlib import Path

import pytest
from rapidfuzz import fuzz

from src.pipeline import clean, resolve
from src.pipeline.errors import GateError
from src.pipeline.paths import Paths
from tests.helpers import make_tickets


def ticket(route, start, end, minute=0, **extra):
    return {"route": route, "start_stop_name": start, "end_stop_name": end,
            "created_at": f"2026-10-05 08:{minute:02d}:00+05:30", **extra}


def run_resolve(con, tmp_path, gtfs_dir, rows, **kw):
    """Write the tickets, run clean, then resolve; return ResolveStats."""
    base = Paths.default()
    paths = Paths(base.repo, Path(gtfs_dir), make_tickets(tmp_path, rows), base.gps_archive,
                  base.gps_aggregates, tmp_path / "out")
    clean.run(con, paths)
    return resolve.run(con, paths, **kw)


def placed(con):
    return con.execute("SELECT route_id, orig_seq, dest_seq, how FROM tickets_resolved "
                       "ORDER BY ticket_id").fetchall()


def rejected(con):
    return con.execute("SELECT route_raw, reason FROM tickets_rejected ORDER BY ticket_id").fetchall()


def toy_with_routes(tmp_path, toy_gtfs_dir, extra, stops=()):
    """Copy the toy feed and add stops [(stop_id, name, lat, lon)] and routes
    [(route_id, short_name, [stop_ids])], one trip each."""
    d = tmp_path / "gtfs"
    shutil.copytree(toy_gtfs_dir, d)
    with open(d / "stops.txt", "a") as f:
        for sid, name, lat, lon in stops:
            f.write(f"{sid},{name},{lat},{lon}\n")
    with open(d / "routes.txt", "a") as r, open(d / "trips.txt", "a") as t, \
            open(d / "stop_times.txt", "a") as st:
        for rid, short, stops in extra:
            r.write(f"{rid},DTC,{short},{short},3\n")
            t.write(f"{rid},1,{rid}_0700,shp{rid}\n")
            for seq, s in enumerate(stops, 1):
                hms = f"07:{5 * (seq - 1):02d}:00"
                st.write(f"{rid}_0700,{hms},{hms},{s},{seq}\n")
    return d


def test_template_on_to_stop(con, tmp_path, toy_gtfs_dir):
    run_resolve(con, tmp_path, toy_gtfs_dir, [ticket("101UP", "Alpha Terminal", "Delta Metro")])
    rows = con.execute("SELECT seq, stop_id, stop_name, template_s, cum_template_s, operator "
                       "FROM canonical_stops WHERE short_name = '101UP' ORDER BY seq").fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5]
    assert [r[1] for r in rows] == ["1", "2", "3", "4", "5"]
    assert rows[0][2] == "Alpha Terminal" and rows[0][5] == "DTC"
    assert [r[3] for r in rows] == [0, 300, 300, 300, 300]
    assert rows[-1][4] == 1200
    ring = con.execute("SELECT template_s FROM canonical_stops WHERE route_id = 401 ORDER BY seq").fetchall()
    assert [r[0] for r in ring] == [0, 300, 300, 424]
    # every GTFS route gets a canonical sequence, ticketed or not
    assert con.execute("SELECT count(DISTINCT route_id) FROM canonical_stops").fetchone()[0] == 9


def test_forward(con, tmp_path, toy_gtfs_dir):
    run_resolve(con, tmp_path, toy_gtfs_dir, [ticket("101UP", "Alpha Terminal", "Delta Metro")])
    assert placed(con) == [(101, 1, 4, "forward")]
    got = con.execute("SELECT route_id, short_name, operator, direction, is_ring, is_devi, match_type "
                      "FROM route_map WHERE route_raw = '101UP'").fetchone()
    assert got == (101, "101UP", "DTC", "UP", False, False, "exact")


def test_reversed_remapped(con, tmp_path, toy_gtfs_dir):
    # R9: five forward tickets and one reversed ticket labelled 101UP. The minority rule sends the
    # reversed one to the opposite route (102, 101DOWN: Echo 1, Delta 2, ..., Alpha 5).
    rows = [ticket("101UP", "Alpha Terminal", "Delta Metro", i) for i in range(5)]
    rows.append(ticket("101UP", "Delta Metro", "Alpha Terminal", 9))
    stats = run_resolve(con, tmp_path, toy_gtfs_dir, rows)
    assert placed(con) == [(101, 1, 4, "forward")] * 5 + [(102, 2, 5, "remapped")]
    assert con.execute("SELECT route_id, match_type FROM route_map").fetchall() == [(101, "exact")]
    assert stats.remapped == 1 and stats.resolved_tickets == 6


def test_majority_reversed_swaps_route(con, tmp_path, toy_gtfs_dir):
    rows = [ticket("101UP", "Delta Metro", "Alpha Terminal", i) for i in range(6)]
    stats = run_resolve(con, tmp_path, toy_gtfs_dir, rows)
    route_id, short, match_type, evidence = con.execute(
        "SELECT route_id, short_name, match_type, evidence FROM route_map WHERE route_raw = '101UP'").fetchone()
    assert (route_id, short, match_type) == (102, "101DOWN", "remap")
    ev = json.loads(evidence)
    assert ev["from_route_id"] == 101 and ev["reversed"] == 6 and ev["resolvable"] == 6
    assert placed(con) == [(102, 2, 5, "forward")] * 6
    assert stats.routes_remapped == 1 and stats.remapped == 0


def test_reversed_without_opposite_rejected(con, tmp_path, toy_gtfs_dir):
    # 909UP has no 909DOWN in the toy feed.
    run_resolve(con, tmp_path, toy_gtfs_dir, [ticket("909UP", "Echo Depot", "Delta Metro")])
    assert placed(con) == []
    assert rejected(con) == [("909UP", "reversed")]


def test_ring_wrap(con, tmp_path, toy_gtfs_dir):
    # OMS(+)UP runs stops 2 -> 3 -> 6 -> 2 (seq 1..4). Foxtrot (seq 3) -> Charlie wraps: seq 4 is
    # stop 2 again and seq 5 is stop 3 on the second lap.
    run_resolve(con, tmp_path, toy_gtfs_dir, [
        ticket("OMS(+)UP", "Foxtrot Nagar", "Charlie Chowk"),
        ticket("OMS(+)UP", "Foxtrot Nagar", "Bravo Market", 1),   # ends at the closing stop, no wrap
        ticket("OMS(+)UP", "Bravo Market", "Charlie Chowk", 2),
    ])
    assert placed(con) == [(401, 3, 5, "ring_wrap"), (401, 3, 4, "forward"), (401, 1, 2, "forward")]
    assert con.execute("SELECT is_ring, direction FROM route_map").fetchone() == (True, "CW")
    meta = dict(con.execute("SELECT route_id, is_ring FROM route_meta").fetchall())
    assert meta[401] is True and meta[101] is False


def test_route_meta_opposites(con, tmp_path, toy_gtfs_dir):
    run_resolve(con, tmp_path, toy_gtfs_dir, [ticket("101UP", "Alpha Terminal", "Delta Metro")])
    opp = dict(con.execute("SELECT route_id, opposite_route_id FROM route_meta").fetchall())
    assert opp[101] == 102 and opp[102] == 101 and opp[201] == 202 and opp[501] is None
    n = dict(con.execute("SELECT route_id, n_stops FROM route_meta").fetchall())
    assert n[101] == 5 and n[401] == 4


def test_alias_needs_overlap(con, tmp_path, toy_gtfs_dir):
    # Ticket strings ML96UP / ML97UP have no exact GTFS short name; alias_key finds ML-96UP / ML-97UP.
    # The alias stands only when >= 80% of the string's tickets resolve in stop order on the route.
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(801, "ML-96UP", [1, 2, 3, 4, 5]),
                                                    (802, "ML-97UP", [1, 2, 3, 4, 5])])
    rows = [ticket("ML96UP", "Alpha Terminal", "Delta Metro", i) for i in range(8)]
    rows += [ticket("ML96UP", "Delta Metro", "Alpha Terminal", 10 + i) for i in range(2)]   # 8/10 in order
    rows += [ticket("ML97UP", "Alpha Terminal", "Delta Metro", 20 + i) for i in range(7)]
    rows += [ticket("ML97UP", "Delta Metro", "Alpha Terminal", 30 + i) for i in range(3)]   # 7/10 in order
    stats = run_resolve(con, tmp_path, gtfs, rows)
    rm = {r[0]: r[1:] for r in con.execute(
        "SELECT route_raw, route_id, short_name, match_type, evidence FROM route_map").fetchall()}
    assert rm["ML96UP"][:3] == (801, "ML-96UP", "alias")
    ev = json.loads(rm["ML96UP"][3])
    assert ev["candidates"][0]["short_name"] == "ML-96UP" and ev["candidates"][0]["share"] == pytest.approx(0.8)
    assert rm["ML97UP"][:3] == (None, None, "unmatched")
    assert json.loads(rm["ML97UP"][3])["alias_key_step"]["candidates"][0]["share"] == pytest.approx(0.7)
    assert placed(con) == [(801, 1, 4, "forward")] * 8
    assert rejected(con) == [("ML96UP", "reversed")] * 2 + [("ML97UP", "unmatched_route")] * 10
    assert stats.aliases == 1


def test_alias_only_without_exact_name(con, tmp_path, toy_gtfs_dir):
    # 101UP is an exact short name, so it never goes through alias matching even though
    # alias_key("101UP") would also match a GTFS route 0101UP.
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(901, "0101UP", [1, 2, 3, 4, 5])])
    run_resolve(con, tmp_path, gtfs, [ticket("101UP", "Alpha Terminal", "Delta Metro")])
    assert con.execute("SELECT route_id, match_type FROM route_map").fetchall() == [(101, "exact")]


def test_merge_rule():
    a = ["alpha terminal", "bravo market", "charlie chowk", "delta metro", "echo depot"]
    assert resolve.mergeable(a, a)[0]
    assert not resolve.mergeable(a, a[:-1])[0]                       # different termini
    assert not resolve.mergeable(a, list(reversed(a)))[0]             # opposite direction
    long = a[:1] + [f"stop {i}" for i in range(10)] + a[1:]
    ok, ev = resolve.mergeable(a, long)
    assert not ok and ev["ordered_match"] < 0.9                      # same termini, too few shared stops


def test_rejection_reasons_and_dq(con, tmp_path, toy_gtfs_dir):
    stats = run_resolve(con, tmp_path, toy_gtfs_dir, [
        ticket("101UP", "Alpha Terminal", "Delta Metro", passenger_count=2),
        ticket("NOPE99UP", "Alpha Terminal", "Delta Metro", 1),        # no GTFS route
        ticket("101UP", "Xyzzy Qwerty", "Delta Metro", 2),             # stop not on the route
        ticket("101UP", "Charlie Chowk", "Charlie Chowk", 3),          # same stop
    ])
    assert rejected(con) == [("NOPE99UP", "unmatched_route"), ("101UP", "unmatched_stop"),
                             ("101UP", "same_stop")]
    dq = {r[0]: r[1:] for r in con.execute("SELECT reason, tickets, pax FROM dq_resolve").fetchall()}
    assert dq["unmatched_route"] == (1, 1) and dq["unmatched_stop"] == (1, 1)
    assert dq["same_stop"] == (1, 1) and dq["reversed"] == (0, 0) and dq["ambiguous_stop"] == (0, 0)
    assert stats.tickets == 4 and stats.pax == 5 and stats.resolved_pax == 2
    assert stats.match_rate == pytest.approx(0.4)
    assert stats.rejected == {"unmatched_route": 1, "unmatched_stop": 1, "ambiguous_stop": 0, "same_stop": 1,
                              "reversed": 0}
    assert con.execute("SELECT match_type FROM route_map WHERE route_raw = 'NOPE99UP'").fetchone() == ("unmatched",)


def test_sample_routes_restrict(con, tmp_path, toy_gtfs_dir):
    stats = run_resolve(con, tmp_path, toy_gtfs_dir, [
        ticket("101UP", "Alpha Terminal", "Delta Metro"),
        ticket("909UP", "Delta Metro", "Echo Depot", 1),
    ], sample_routes=["909UP"])
    assert placed(con) == [(501, 1, 2, "forward")]
    assert con.execute("SELECT route_raw FROM route_map").fetchall() == [("909UP",)]
    assert stats.tickets == 1


def test_conservation_gate(con, tmp_path, toy_gtfs_dir):
    run_resolve(con, tmp_path, toy_gtfs_dir, [
        ticket("101UP", "Alpha Terminal", "Delta Metro"),
        ticket("909UP", "Delta Metro", "Echo Depot", 1),
        ticket("NOPE99UP", "Alpha Terminal", "Delta Metro", 2),
    ])
    resolve.check_conservation(con)
    con.execute("DELETE FROM tickets_resolved WHERE route_id = 101")
    with pytest.raises(GateError, match="101UP"):
        resolve.check_conservation(con)


def test_conservation_gate_catches_double_count(con, tmp_path, toy_gtfs_dir):
    run_resolve(con, tmp_path, toy_gtfs_dir, [ticket("101UP", "Alpha Terminal", "Delta Metro"),
                                              ticket("101UP", "Bravo Market", "Delta Metro", 1)])
    first = con.execute("SELECT min(ticket_id) FROM tickets_resolved").fetchone()[0]
    con.execute("DELETE FROM tickets_resolved WHERE ticket_id <> ?", [first])
    con.execute("INSERT INTO tickets_rejected VALUES (?, '101UP', 'same_stop')", [first])
    with pytest.raises(GateError, match="101UP"):
        resolve.check_conservation(con)


def test_normalize_transit_text():
    assert resolve.normalize_transit_text("Rohini Sec-22 (T)") == "rohini sector 22 terminal"
    assert resolve.normalize_transit_text("Mayur Vihar Ph-II") == "mayur vihar phase 2"
    assert resolve.normalize_transit_text("Nehru Place Mkt.") == "nehru place market"
    assert resolve.normalize_transit_text(None) == ""


def test_route_scoped_matcher():
    idx = resolve.build_stop_index([(1, "Alpha Terminal"), (2, "Bravo Market / Bravo Bazar"),
                                    (3, "Charlie Chowk"), (4, "Alpha Terminal")])
    key, score, method = resolve.match_stop("Alpha Terminal", idx)
    assert method == "exact" and score == 100.0 and idx.keys[key] == (1, 4)
    key, score, method = resolve.match_stop("Charli Chowk", idx)
    assert method == "fuzzy" and score >= 78 and idx.keys[key] == (3,)
    assert idx.keys[resolve.match_stop("Bravo Bazar", idx)[0]] == (2,)   # slash token
    assert resolve.match_stop("Zzyzx Qwv", idx) is None


# ---- R14: WRatio ties break by token_sort_ratio, then partial_ratio; a remaining tie is ambiguous

def test_tie_break_prefers_shared_words(con, tmp_path, toy_gtfs_dir):
    # WRatio gives both stops exactly 85.5 for "Isbt Anand Vihar": one shared word is enough once the
    # lengths differ by 1.5x. token_sort_ratio picks the stop that really is Anand Vihar ISBT.
    q = "isbt anand vihar"
    assert fuzz.WRatio(q, "c block yamuna vihar / c4 yamuna vihar") == fuzz.WRatio(q, "anand vihar isbt main road")
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(811, "AV-1UP", [1, 10, 11, 4])],
                           stops=[(10, "C-Block Yamuna Vihar / C4 YAMUNA VIHAR", 28.6200, 77.2000),
                                  (11, "Anand Vihar ISBT Main Road", 28.6300, 77.2000)])
    run_resolve(con, tmp_path, gtfs, [ticket("AV-1UP", "Isbt Anand Vihar", "Delta Metro"),
                                      ticket("AV-1UP", "Alpha Terminal", "Isbt Anand Vihar", 1)])
    assert placed(con) == [(811, 3, 4, "forward"), (811, 1, 3, "forward")]


def test_ambiguous_stop_rejected(con, tmp_path, toy_gtfs_dir):
    idx = resolve.build_stop_index([(1, "Alpha Vihar"), (2, "Bravo Vihar")])
    m = resolve.match_stop("Vihar", idx)
    assert m.method == "ambiguous" and m.key is None
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(812, "VH-1UP", [12, 13, 4])],
                           stops=[(12, "Alpha Vihar", 28.6200, 77.2100), (13, "Bravo Vihar", 28.6300, 77.2100)])
    run_resolve(con, tmp_path, gtfs, [ticket("VH-1UP", "Vihar", "Delta Metro"),
                                      ticket("VH-1UP", "Alpha Vihar", "Delta Metro", 1)])
    assert rejected(con) == [("VH-1UP", "ambiguous_stop")]
    assert placed(con) == [(812, 1, 3, "forward")]
    assert con.execute("SELECT tickets, pax FROM dq_resolve WHERE reason = 'ambiguous_stop'").fetchone() == (1, 1)


# ---- R15: a route is a ring when its first and last stops are the same stop or within PLACE_RADIUS_M

def test_near_closed_loop_wraps(con, tmp_path, toy_gtfs_dir):
    # LOOP-1UP ends at Bravo Gate, a different stop about 100 m from its first stop Bravo Market: a ring,
    # so Foxtrot -> Charlie wraps. LOOP-2UP ends about 600 m away: not a ring, so the same ticket is reversed.
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(821, "LOOP-1UP", [2, 3, 6, 14]), (822, "LOOP-2UP", [2, 3, 6, 15])],
                           stops=[(14, "Bravo Gate", 28.61439, 77.2000), (15, "Golf Links", 28.61889, 77.2000)])
    run_resolve(con, tmp_path, gtfs, [ticket("LOOP-1UP", "Foxtrot Nagar", "Charlie Chowk"),
                                      ticket("LOOP-2UP", "Foxtrot Nagar", "Charlie Chowk", 1)])
    assert placed(con) == [(821, 3, 5, "ring_wrap")]
    assert rejected(con) == [("LOOP-2UP", "reversed")]
    ring = dict(con.execute("SELECT route_id, is_ring FROM route_meta").fetchall())
    assert ring[821] is True and ring[822] is False and ring[401] is True and ring[101] is False


def test_swap_onto_ring_keeps_forward_minority(con, tmp_path, toy_gtfs_dir):
    # OMS(-)DOWN (added; Bravo, Foxtrot, Charlie, Echo; not a ring): 4 of 5 tickets reversed, so the string
    # swaps to its opposite, the OMS(+)UP ring. The fifth ticket runs forward on OMS(-)DOWN and stays there
    # as remapped instead of wrapping the wrong way round the ring.
    gtfs = toy_with_routes(tmp_path, toy_gtfs_dir, [(402, "OMS(-)DOWN", [2, 6, 3, 5])])
    rows = [ticket("OMS(-)DOWN", "Charlie Chowk", "Foxtrot Nagar", i) for i in range(4)]
    rows.append(ticket("OMS(-)DOWN", "Foxtrot Nagar", "Charlie Chowk", 9))
    run_resolve(con, tmp_path, gtfs, rows)
    assert con.execute("SELECT route_id, match_type FROM route_map").fetchall() == [(401, "remap")]
    assert placed(con) == [(401, 2, 3, "forward")] * 4 + [(402, 2, 3, "remapped")]


# ---- R16: aliases by removing variant tokens (STL, EXT, EXP, SPL) when alias_key finds nothing

def test_variant_key():
    vk = resolve.variant_key
    assert vk("101STLUP") == vk("101UP") and vk("588LSTLDOWN") == vk("588DOWN")
    assert vk("118EXTNDOWN") == vk("118EXTDOWN") == vk("118DOWN") and vk("BPEXPUP") == vk("BPUP")
    assert vk("529SPLDOWN") == vk("529DOWN") and vk("567BSTLUP") != vk("567BSTLDOWN")


def test_variant_token_alias(con, tmp_path, toy_gtfs_dir):
    # 101STLUP: no exact name, no alias_key match; without STL it keys to 101UP and its tickets run in
    # order there. 202STLUP keys to 202UP, but its tickets' stops are not on that route: unmatched.
    stats = run_resolve(con, tmp_path, toy_gtfs_dir, [
        ticket("101STLUP", "Alpha Terminal", "Delta Metro"),
        ticket("101STLUP", "Bravo Market", "Charlie Chowk", 1, passenger_count=2),
        ticket("202STLUP", "Alpha Terminal", "Delta Metro", 2),
    ])
    rm = {r[0]: r[1:] for r in con.execute(
        "SELECT route_raw, route_id, short_name, match_type, evidence FROM route_map").fetchall()}
    assert rm["101STLUP"][:3] == (101, "101UP", "alias")
    ev = json.loads(rm["101STLUP"][3])
    assert ev["rule"] == "variant_tokens" and ev["candidates"][0]["short_name"] == "101UP"
    assert ev["candidates"][0]["share"] == 1.0 and ev["alias_key_step"]["candidates"] == []
    assert rm["202STLUP"][:3] == (None, None, "unmatched")
    assert json.loads(rm["202STLUP"][3])["variant_step"]["candidates"][0]["share"] == 0.0
    assert placed(con) == [(101, 1, 4, "forward"), (101, 2, 3, "forward")]
    assert rejected(con) == [("202STLUP", "unmatched_route")]
    assert stats.variant_aliases == 1 and stats.variant_alias_pax == 3
