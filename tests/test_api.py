"""API v1 on a toy run: planner/*.parquet, stretch_crowding, corridors, operator trips, manifest."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.pipeline import manifest
from src.pipeline.db import connect
from tests.test_planner import STANDING_101, build_export, crowd

FIXTURE = Path(__file__).parent / "fixtures" / "plan_example.json"
FORBIDDEN = re.compile(r"κ|kappa|mcraptor|pareto|sigmoid|\bscore\b", re.I)
PRESET = {"from": "Alpha Terminal", "to": "Echo Depot", "depart": "08:00", "day": "weekday"}


@pytest.fixture(scope="session")
def toy(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    con = connect()
    gtfs = Path(__file__).parent / "fixtures" / "toy_gtfs"
    rows = STANDING_101 + crowd(101, 2, 80, 90, 100) + crowd(301, 2, 20, 25, 30)
    paths = build_export(tmp, gtfs, con, STANDING_101 + crowd(301, 2, 20, 25, 30))
    con.close()
    out = paths.processed
    canon = pd.read_parquet(out / "planner" / "canonical_stops.parquet")
    nxt = canon.assign(seq=canon.seq - 1)[["route_id", "seq", "stop_id", "stop_name"]]
    nxt.columns = ["route_id", "seq", "to_stop_id", "to_name"]
    sc = pd.read_parquet(out / "stretch_crowding.parquet")
    sc = sc.merge(canon[["route_id", "seq", "short_name", "operator", "stop_id", "stop_name"]]
                  .rename(columns={"stop_id": "from_stop_id", "stop_name": "from_name"}), on=["route_id", "seq"])
    sc = sc.merge(nxt, on=["route_id", "seq"])
    sc["direction"] = "UP"
    sc["level"], sc["evidence"] = "standing", "rough"
    sc["seats"], sc["rated_total"], sc["crush"] = 35.0, 63.0, 100.0
    sc.to_parquet(out / "stretch_crowding.parquet", index=False)
    pid = f"{sc.from_stop_id.iloc[0]}-{sc.to_stop_id.iloc[0]}"
    pd.DataFrame([dict(pair_id=pid, from_stop_id="1", to_stop_id="2", day_type="weekday", window_start_min=480,
                       load_ratio=1.2, share_crowded=0.5, crowded_rider_min=900.0, buses=3.0, routes=2),
                  dict(pair_id="2-3", from_stop_id="2", to_stop_id="3", day_type="weekday", window_start_min=480,
                       load_ratio=0.4, share_crowded=0.0, crowded_rider_min=0.0, buses=2.0, routes=1)]
                 ).to_parquet(out / "corridor_values.parquet", index=False)
    (out / "corridor_geometry.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": pid, "properties": {"id": pid},
         "geometry": {"type": "LineString", "coordinates": [[77.0, 28.0], [77.1, 28.1]]}}]}))
    ops = [("DTC", "weekday", 480, 50.0), ("DTC", "weekday", 540, 90.0), ("DIMTS", "weekday", 600, 70.0),
           ("DTC", "weekend", 480, 999.0)]
    pd.DataFrame([dict(route_id=101, short_name="101UP", operator=o, direction="UP", day_type=d, depart_min=t,
                       crowded_rider_min_removed=v, riders_moved_down=5.0, max_load_section="A to B",
                       peak_load_factor=1.1, evidence_share=0.2, flags="") for o, d, t, v in ops]
                 ).to_parquet(out / "operator_trips.parquet", index=False)
    (out / "validation_report.json").write_text(json.dumps({"headline_numbers": {"clean_days": 29,
                                                                                  "tickets_resolved": 1234}}))
    f = out / "in.txt"
    f.write_text("x")
    manifest.mark_done("loads", {"x": str(f)}, [], path=out / "manifest.json")
    return paths


@pytest.fixture(scope="session")
def client(toy):
    with TestClient(create_app(toy)) as c:
        yield c


def test_every_200_has_data_version(client):
    mfst = json.loads((Path(client.app.state.s.processed) / "manifest.json").read_text())
    urls = ["/v1/health", "/v1/plan?from=Alpha Terminal&to=Echo Depot&depart=08:00&day=weekday",
            "/v1/places/search?q=alpha", "/v1/crowding?route_id=101&day=weekday&window=08:10",
            "/v1/crowding/stretch?from=1&to=2&day=weekday", "/v1/corridors?day=weekday&window=08:00",
            "/v1/operator/trips?day=weekday"]
    for u in urls:
        r = client.get(u)
        assert r.status_code == 200, (u, r.text)
        assert r.json()["data_version"] == mfst["run_id"], u


def test_plan_bad_depart_422(client):
    for d in ("9am", "25:00", "08:75", ""):
        assert client.get("/v1/plan", params={**PRESET, "depart": d}).status_code == 422, d


def test_plan_bad_day_422(client):
    assert client.get("/v1/plan", params={**PRESET, "day": "sunday"}).status_code == 422
    assert client.get("/v1/plan", params={"from": "Alpha Terminal", "to": "Echo Depot"}).status_code == 422


def test_plan_unknown_place_404(client):
    r = client.get("/v1/plan", params={**PRESET, "from": "zzzz"})
    assert r.status_code == 404
    assert isinstance(r.json()["suggestions"], list) and r.json()["detail"]


def test_plan_matches_frozen_example(client):
    got = client.get("/v1/plan", params=PRESET).json()
    ex = json.loads(FIXTURE.read_text())
    assert set(got) == set(ex) and set(got["query"]) == set(ex["query"])
    assert set(got["options"][0]) == set(ex["options"][0])
    seg = lambda o: o["legs"][[l["mode"] for l in o["legs"]].index("bus")]["segments"][0]
    assert set(seg(got["options"][0])) == set(seg(ex["options"][0]))
    assert got["options"][0]["minutes"] == ex["options"][0]["minutes"]


def test_places_search(client):
    r = client.get("/v1/places/search", params={"q": "alpha"}).json()
    assert r["places"] and r["places"][0]["name"]
    assert client.get("/v1/places/search", params={"q": ""}).status_code == 422


def test_crowding_route_and_window_floor(client):
    r = client.get("/v1/crowding", params={"route_id": 101, "day": "weekday", "window": "08:10"}).json()
    assert r["window"]["start"] == "08:00" and r["stretches"][0]["level"] == "standing"
    assert r["stretches"][0]["people"] == [40, 45, 50]
    assert client.get("/v1/crowding", params={"route_id": 999, "day": "weekday", "window": "08:00"}).status_code == 404
    assert client.get("/v1/crowding", params={"route_id": 101, "day": "weekday"}).status_code == 422


def test_crowding_stretch(client):
    r = client.get("/v1/crowding/stretch", params={"from": "1", "to": "2", "day": "weekday"}).json()
    assert r["windows"] and r["windows"][0]["routes"][0]["route"]
    assert client.get("/v1/crowding/stretch", params={"from": "x", "to": "y", "day": "weekday"}).status_code == 404


def test_corridors_geojson(client):
    r = client.get("/v1/corridors", params={"day": "weekday", "window": "08:20"}).json()
    assert r["type"] == "FeatureCollection" and len(r["features"]) == 2
    top = r["features"][0]
    assert top["properties"]["crowded_rider_min"] == 900.0 and top["geometry"]["type"] == "LineString"
    assert len(client.get("/v1/corridors", params={"day": "weekday", "window": "08:00", "limit": 1}).json()["features"]) == 1


def test_operator_trips_day_required_and_ranked_within_day(client):
    assert client.get("/v1/operator/trips").status_code == 422
    assert client.get("/v1/operator/trips", params={"day": "holiday"}).status_code == 422
    wd = client.get("/v1/operator/trips", params={"day": "weekday"}).json()["trips"]
    assert [t["crowded_rider_min_removed"] for t in wd] == [90.0, 70.0, 50.0]
    we = client.get("/v1/operator/trips", params={"day": "weekend"}).json()["trips"]
    assert [t["crowded_rider_min_removed"] for t in we] == [999.0]
    dm = client.get("/v1/operator/trips", params={"day": "weekday", "operator": "dimts"}).json()["trips"]
    assert [t["depart"] for t in dm] == ["10:00"]


def test_operator_trips_csv(client):
    r = client.get("/v1/operator/trips.csv", params={"day": "weekday"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("route_id,short_name,operator") and len(lines) == 4
    assert client.get("/v1/operator/trips.csv").status_code == 422


def test_no_ticket_or_vehicle_fields(client):
    body = client.get("/v1/operator/trips", params={"day": "weekday"}).text
    assert "vehicle" not in body.lower() and "ticket" not in body.lower()


def test_health_counts_match_outputs(client, toy):
    h = client.get("/v1/health").json()
    sc = pd.read_parquet(toy.processed / "stretch_crowding.parquet")
    assert h["counts"]["stretch_rows"] == len(sc)
    assert h["counts"]["operator_trips"] == 4
    assert h["counts"]["routes"] == pd.read_parquet(toy.processed / "planner" / "route_specs.parquet").shape[0]
    assert h["stages_done"] == ["loads"] and h["data"]["ticket_days"] == 29


def test_cors_get_any_origin_no_credentials(client):
    r = client.get("/v1/health", headers={"Origin": "https://example.org"})
    assert r.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in r.headers
    pre = client.options("/v1/plan", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200 and "GET" in pre.headers["access-control-allow-methods"]


def test_pages_served(client):
    for u in ("/", "/operator"):
        r = client.get(u)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")


def test_placeholder_has_credit(toy, monkeypatch):
    import src.api.main as m
    monkeypatch.setattr(m, "FRONTEND", Path("/nonexistent"))
    with TestClient(m.create_app(toy)) as c:
        for u in ("/", "/operator"):
            assert "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing." in c.get(u).text


def test_no_forbidden_words_in_responses(client):
    for u in ("/v1/health", "/v1/plan?from=Alpha Terminal&to=Echo Depot&depart=08:00&day=weekday",
              "/v1/places/search?q=alpha", "/openapi.json"):
        assert not FORBIDDEN.search(client.get(u).text), u
    assert not FORBIDDEN.search(Path("src/api/main.py").read_text())
