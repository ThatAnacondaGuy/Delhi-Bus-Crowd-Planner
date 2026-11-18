"""Planner tests on the toy network with a hand-built stretch_crowding table."""
import json
import re

import numpy as np
import pandas as pd
import pytest

from src.pipeline import network
from src.pipeline.paths import Paths
from src.routing import planner as pl
from src.routing.planner import PlaceNotFound, Planner

WEEKDAY_WINDOWS = list(range(0, 1440, 30))
FORBIDDEN = re.compile(r"κ|kappa|mcraptor|pareto|sigmoid|\bscore\b", re.I)
CLASSES = {601: "office_special", 701: "school"}
SPECS = {301: (23.0, 36.0, 42.0)}
DEVI = {301}


def _hhmm(s):
    h, m = s.split(":")[:2]
    return int(h) * 60 + int(m)


def crowd(route_id, seq, low, mid, high, windows=None, day="weekday", flags=""):
    wins = WEEKDAY_WINDOWS if windows is None else windows
    return [dict(route_id=route_id, seq=seq, day_type=day, window_start_min=w, people_low=low, people_mid=mid,
                 people_high=high, flags=flags) for w in wins]


def build_export(tmp_path, gtfs_dir, con, rows, factors=None, rho=True):
    """Write toy planner/*.parquet and stretch_crowding.parquet; return Paths pointing at them."""
    g = pd.read_csv(gtfs_dir / "stops.txt", dtype={"stop_id": str})
    routes = pd.read_csv(gtfs_dir / "routes.txt")
    trips = pd.read_csv(gtfs_dir / "trips.txt")
    st = pd.read_csv(gtfs_dir / "stop_times.txt", dtype={"stop_id": str})
    st["minute"] = st.departure_time.map(_hhmm)
    st = st.merge(trips[["trip_id", "route_id"]], on="trip_id")
    stops = g.set_index("stop_id")
    canon, shapes, passings = [], [], []
    for _, r in routes.iterrows():
        rid = int(r.route_id)
        one = st[st.route_id == rid]
        first = one[one.trip_id == one.trip_id.iloc[0]].sort_values("stop_sequence")
        cum = 0
        prev = None
        for _, s in first.iterrows():
            tmpl = 0 if prev is None else (s.minute - prev) * 60
            if rid == 401 and s.stop_sequence == 4:
                tmpl = 424
            cum += tmpl
            sid = str(s.stop_id)
            canon.append(dict(route_id=rid, short_name=r.route_short_name, operator=r.agency_id, seq=int(s.stop_sequence),
                              stop_id=sid, stop_name=stops.loc[sid, "stop_name"], lat=float(stops.loc[sid, "stop_lat"]),
                              lon=float(stops.loc[sid, "stop_lon"]), template_s=tmpl, cum_template_s=cum))
            if prev is not None:
                a = canon[-2]
                shapes.append(dict(route_id=rid, seq=int(s.stop_sequence),
                                   coords=json.dumps([[a["lat"], a["lon"]], [canon[-1]["lat"], canon[-1]["lon"]]]),
                                   length_m=float(abs(a["lat"] - canon[-1]["lat"]) * 111_000 + abs(a["lon"] - canon[-1]["lon"]) * 98_000)))
            prev = s.minute
        passings.append(one[["route_id", "stop_sequence", "minute"]].rename(columns={"stop_sequence": "seq"}))
    pas = pd.concat(passings, ignore_index=True)
    out = tmp_path / "out"
    pdir = out / "planner"
    pdir.mkdir(parents=True)
    paths = Paths(Paths.default().repo, gtfs_dir, tmp_path / "t.csv", tmp_path / "g.7z", tmp_path / "ga", out)
    network.build_places(con, paths)
    ids = [int(x) for x in routes.route_id]

    def wr(name, df):
        df.to_parquet(pdir / f"{name}.parquet", index=False)

    wr("canonical_stops", pd.DataFrame(canon))
    wr("segment_shapes", pd.DataFrame(shapes))
    wr("places", con.execute("SELECT * FROM places").df())
    wr("hub_alias", con.execute("SELECT * FROM hub_alias").df())
    wr("passings", pas.astype({"route_id": "int64", "seq": "int32", "minute": "int32"}))
    sh = pas.groupby("route_id").minute.agg(first_min="min", last_min="max").reset_index()
    sh["ticket_hours"] = ""
    wr("service_hours", sh)
    wr("service_class", pd.DataFrame({"route_id": ids, "class": [CLASSES.get(i, "regular") for i in ids]}))
    fac = factors if factors is not None else pd.DataFrame(
        {"scope": pd.Series(dtype=str), "key": pd.Series(dtype=str), "hour": pd.Series(dtype=int),
         "factor": pd.Series(dtype=float), "n_pairs": pd.Series(dtype=int)})
    wr("runtime_factors", fac)
    wr("bus_mix", pd.DataFrame({"route_id": ids, "share_9m": [1.0 if i in DEVI else 0.0 for i in ids],
                                "share_12m_nonac": 0.0, "share_12m_ac": [0.0 if i in DEVI else 1.0 for i in ids],
                                "basis": "is_ac"}))
    sp = [(i,) + SPECS.get(i, (35.0, 63.0, 100.0)) for i in ids]
    wr("route_specs", pd.DataFrame(sp, columns=["route_id", "seats", "rated_total", "crush"]))
    if rho:
        wr("gps_rho_fill", pd.DataFrame([dict(route_id=i, hour=h, day_type=d, rho=1.0, rho_src="x")
                                         for i in ids for h in range(24) for d in ("weekday", "weekend")]))
    cdf = pd.DataFrame(rows)
    cdf["level"] = "x"
    cdf["evidence"] = "x"
    cdf.to_parquet(out / "stretch_crowding.parquet", index=False)
    return paths


STANDING_101 = [r for s in (1, 2, 3, 4) for r in crowd(101, s, 40, 45, 50)]


@pytest.fixture
def make(tmp_path, toy_gtfs_dir, con):
    def _make(rows, **kw):
        return Planner.load(build_export(tmp_path, toy_gtfs_dir, con, rows, **kw))
    return _make


def bus_legs(opt):
    return [x for x in opt["legs"] if x["mode"] == "bus"]


def by_role(res, role):
    got = [o for o in res["options"] if role in o["roles"]]
    return got[0] if got else None


def test_fastest_alpha_to_echo(make):
    p = make(STANDING_101)
    res = p.plan("Alpha Terminal", "Echo Depot", "08:00", "weekday")
    opt = by_role(res, "fastest")
    legs = bus_legs(opt)
    assert [l["route"] for l in legs] == ["101UP"]
    assert _hhmm(legs[0]["arrive"]) - _hhmm(legs[0]["depart"]) == 20
    assert 20 < opt["minutes"] <= 36
    assert opt["changes"] == 0 and opt["timetable_uncertain"] is False
    assert res["query"]["from"]["name"] == "Alpha Terminal" and res["query"]["depart"] == "08:00"
    assert res["query"]["day"] == "weekday" and res["data_version"]
    seg = legs[0]["segments"][0]
    assert set(seg) >= {"from_stop_id", "to_stop_id", "minutes", "level", "evidence", "people", "seats", "rated_total",
                        "flags", "coords"}
    assert seg["level"] == "standing" and seg["people"] == [40, 45, 50] and seg["seats"] == 35
    assert opt["fare_inr"] in (10, 15, 20, 25)
    assert opt["headline"]["level"] == "standing"


def bravo_charlie_rows(r101, r301):
    rows = crowd(101, 2, *r101) + crowd(301, 2, *r301)
    return rows


def test_less_crowded_alternative(make):
    p = make(bravo_charlie_rows((80, 90, 100), (20, 25, 30)))
    res = p.plan("Bravo Market", "Charlie Chowk", "08:00", "weekday")
    fastest, less = by_role(res, "fastest"), by_role(res, "less_crowded")
    assert bus_legs(fastest)[0]["route"] == "101UP" and fastest["headline"]["level"] == "crowded"
    assert bus_legs(less)[0]["route"] == "D-005UP" and less["headline"]["level"] == "standing"
    assert less["roles"] == ["less_crowded"]
    assert re.match(r"^\+\d+ min, no crowded stretch$", less["tradeoff"]), less["tradeoff"]
    assert fastest["tradeoff"] == "Fastest"


def test_less_crowded_ineligible_when_too_slow(make):
    fac = pd.DataFrame([dict(scope="route", key="301", hour=8, factor=5.0, n_pairs=100)])
    p = make(bravo_charlie_rows((80, 90, 100), (20, 25, 30)), factors=fac)
    res = p.plan("Bravo Market", "Charlie Chowk", "08:00", "weekday")
    assert by_role(res, "less_crowded") is None
    assert by_role(res, "fastest") is not None


def test_less_crowded_ineligible_when_mostly_no_data(make):
    p = make(crowd(101, 2, 80, 90, 100))  # D-005UP and 202UP have no rows at all
    res = p.plan("Bravo Market", "Charlie Chowk", "08:00", "weekday")
    assert by_role(res, "less_crowded") is None
    assert by_role(res, "fastest")["headline"]["level"] == "crowded"


def test_merged_roles_when_fastest_is_also_least_crowded(make, monkeypatch):
    p = make(bravo_charlie_rows((5, 6, 8), (20, 25, 30)))
    legs = {rid: [("bus", p.route_ri[rid], 1, 2, p.stop_idx["2"], p.stop_idx["3"])] for rid in (101, 301)}
    # the label search rarely returns a slower trip that is also more crowded, so feed both candidates in
    monkeypatch.setattr(Planner, "_raptor", lambda self, o, d, dep, day, beta: [legs[101]] if beta == 0 else [legs[301]])
    res = p.plan("Bravo Market", "Charlie Chowk", "08:00", "weekday")
    merged = [o for o in res["options"] if "fastest" in o["roles"]]
    assert len(merged) == 1 and merged[0]["roles"] == ["fastest", "less_crowded"]
    assert len(res["options"]) == 1 and merged[0]["tradeoff"] == "Fastest and least crowded"


def later_rows(first_seats_window, low, mid, high):
    rows = []
    for s in (1, 2, 3, 4):
        rows += crowd(101, s, 80, 80, 80, windows=[w for w in WEEKDAY_WINDOWS if w < first_seats_window])
        rows += crowd(101, s, low, mid, high, windows=[w for w in WEEKDAY_WINDOWS if w >= first_seats_window])
    return rows


def test_leave_later_offered_when_whole_range_is_seats(make):
    p = make(later_rows(510, 8, 8, 8))
    res = p.plan("Alpha Terminal", "Echo Depot", "08:00", "weekday")
    assert by_role(res, "fastest")["headline"]["level"] == "standing"
    later = by_role(res, "leave_later")
    assert later is not None and later["roles"] == ["leave_later"]
    assert later["depart"] == "08:20"
    assert later["headline"]["level"] == "seats"
    assert later["tradeoff"].startswith("Leave 08:20 · usually seats · arrive ")
    assert later["tradeoff"].endswith(later["arrive"])


def test_leave_later_not_offered_when_range_spans_two_levels(make):
    p = make(later_rows(510, 20, 25, 30))
    res = p.plan("Alpha Terminal", "Echo Depot", "08:00", "weekday")
    assert by_role(res, "leave_later") is None


def seg(minutes, level, ev="many_tickets", a="A", b="B"):
    return dict(minutes=minutes, lvl=level, lvl_lo=level, lvl_hi=level, evidence=ev, from_name=a, to_name=b, leg=0)


def test_headline_rules():
    four_crowded = [seg(10, "standing", a="X", b="Y"), seg(4, "crowded", a="Y", b="Z")]
    h = pl.headline_of(four_crowded, "lvl")
    assert h["level"] == "standing"
    six = [seg(10, "standing", a="X", b="Y"), seg(6, "crowded", a="Y", b="Z")]
    h = pl.headline_of(six, "lvl")
    assert h["level"] == "crowded" and h["stretch"] == {"from": "Y", "to": "Z", "minutes": 6}
    assert pl.headline_of([seg(8, "no_data", "none")], "lvl")["level"] == "no_data"
    assert pl.headline_of([seg(8, "seats")], "lvl")["stretch"] is None


def test_night_departure_is_flagged_never_empty(make):
    p = make(STANDING_101)
    res = p.plan("Alpha Terminal", "Echo Depot", "23:40", "weekday")
    assert res["options"] or res["notes"]
    assert all(o["timetable_uncertain"] for o in res["options"])
    if not res["options"]:
        assert any("No scheduled service" in n for n in res["notes"])


def test_walk_only_trip(make):
    p = make(STANDING_101)
    res = p.plan("Charlie Chowk", "Charlie Chowk Opp", "08:00", "weekday")
    assert len(res["options"]) == 1
    assert all(l["mode"] == "walk" for l in res["options"][0]["legs"])
    assert res["options"][0]["changes"] == 0 and res["options"][0]["fare_inr"] == 0


def test_places_search_aliases(make):
    p = make(STANDING_101)
    ids = {}
    for q in ("cp", "Rajiv Chowk", "anand vihar isbt", "ISBT AV", "Connaught-Place", "C.P."):
        ids[q] = p.search_places(q)[0]
    assert ids["cp"]["id"] == ids["Rajiv Chowk"]["id"] == ids["Connaught-Place"]["id"] == ids["C.P."]["id"]
    assert ids["cp"]["name"] == "Connaught Place"
    assert ids["anand vihar isbt"]["id"] == ids["ISBT AV"]["id"]
    assert ids["ISBT AV"]["name"] == "ISBT Anand Vihar"
    with pytest.raises(PlaceNotFound) as e:
        p.plan("zzzz", "Echo Depot", "08:00", "weekday")
    assert isinstance(e.value.suggestions, list) and e.value.suggestions
    assert p.search_places("zzzz") == [] or p.search_places("zzzz")[0]["match"] == "fuzzy"
    for bad in ("", "   ", "###", "देहली"):
        with pytest.raises(PlaceNotFound):
            p.plan(bad, "Echo Depot", "08:00", "weekday")


def test_typed_forms_resolve_right_place(make):
    p = make(STANDING_101)
    for typed in ("alpha terminal", "ALPHA TERMINAL", "  Alpha   Terminal ", "alpha-terminal", "Alpha Termnal"):
        res = p.plan(typed, "Echo Depot", "08:00", "weekday")
        assert res["query"]["from"]["name"] == "Alpha Terminal", typed
    res = p.plan("place:1", "stop:5", "08:00", "weekday")
    assert res["query"]["from"]["id"] == "place:1" and res["query"]["to"]["name"] == "Echo Depot"
    with pytest.raises(PlaceNotFound):
        p.plan("place:99999", "Echo Depot", "08:00", "weekday")


def test_cp_to_isbt_toy_walk_only_or_no_service_never_500(make):
    p = make(STANDING_101)
    res = p.plan("CP", "ISBT AV", "18:00", "weekday")
    assert res["options"] or res["notes"]


def test_excluded_routes_and_day_rules(make):
    p = make(STANDING_101)
    wd, we = p.routes_for_day("weekday"), p.routes_for_day("weekend")
    assert "SPL-1UP" not in wd and "SPL-1UP" not in we
    assert "DS-12DOWN" in wd and "DS-12DOWN" not in we


def test_bad_input_raises_value_error(make):
    p = make(STANDING_101)
    for depart, day in (("25:00", "weekday"), ("8am", "weekday"), ("08:00", "friday")):
        with pytest.raises(ValueError):
            p.plan("Alpha Terminal", "Echo Depot", depart, day)


def test_no_forbidden_words_in_responses(make):
    p = make(bravo_charlie_rows((80, 90, 100), (20, 25, 30)) + STANDING_101)
    for args in (("Bravo Market", "Charlie Chowk", "08:00"), ("Alpha Terminal", "Echo Depot", "08:00"),
                 ("Alpha Terminal", "Echo Depot", "23:40")):
        text = json.dumps(p.plan(*args, "weekday"), ensure_ascii=False)
        assert not FORBIDDEN.search(text)


def test_interpolation_between_window_centres(make):
    rows = []
    for s in (1, 2, 3, 4):
        rows += crowd(101, s, 10, 20, 30, windows=[480]) + crowd(101, s, 50, 60, 70, windows=[510])
    p = make(rows)
    low, mid, high, _ = p.crowd_at(101, 1, 495.0, "weekday")
    assert (low, mid, high) == pytest.approx((30, 40, 50))
    assert p.crowd_at(101, 1, 600.0, "weekday") is None  # outside any known window: unknown, never a number


def test_load_does_not_need_work_db(make, tmp_path):
    p = make(STANDING_101)
    assert not (tmp_path / "out" / "work.duckdb").exists()
    assert p.search_places("alpha")


def test_missing_rho_falls_back_with_note(make):
    p = make(STANDING_101, rho=False)
    res = p.plan("Alpha Terminal", "Echo Depot", "08:00", "weekday")
    assert by_role(res, "fastest") is not None
    assert any("frequency" in n for n in res["notes"])
