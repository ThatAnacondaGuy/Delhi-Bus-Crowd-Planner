"""Free static demo: the build writes precomputed JSON in the API's own shape; the two screens read it in static mode."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from deploy import build_static
from src.api.main import OPERATOR_COLUMNS, create_app
from tests.test_api import toy  # noqa: F401  (session fixture: a toy pipeline run)

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN_WORDS = re.compile(r"κ|kappa|mcraptor|pareto|sigmoid|\bscore\b", re.I)
CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing."
PLACES = ["Alpha Terminal", "Echo Depot", "Nowhere At All"]


@pytest.fixture(scope="module")
def built(toy, tmp_path_factory):  # noqa: F811
    out = tmp_path_factory.mktemp("space") / "out"
    files, report = build_static.build_with_report(out, toy.processed, places=PLACES, corridor_limit=50)
    return out, files, report


@pytest.fixture(scope="module")
def api(toy):  # noqa: F811
    with TestClient(create_app(toy)) as c:
        yield c


def load(out: Path, rel: str):
    return json.loads((out / "static-data" / rel).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- what is written

def test_layout_and_files_returned(built):
    out, files, _ = built
    for name in ("index.html", "operator.html", "app.css", "app.js", "operator.css", "operator.js", "data.js",
                 "config.js", "README.md", "static-data/places.json", "static-data/health.json",
                 "static-data/operator/trips-weekday.json", "static-data/operator/trips-weekend.json",
                 "static-data/operator/trips-weekday.csv", "static-data/operator/trips-weekend.csv",
                 "static-data/plans/alpha-terminal/echo-depot.json", "static-data/plans/echo-depot/alpha-terminal.json"):
        assert (out / name).is_file(), name
    assert {p.resolve() for p in files} == {p.resolve() for p in out.rglob("*") if p.is_file()}


def test_places_resolve_and_unresolved_are_reported(built):
    out, _, report = built
    meta = load(out, "places.json")
    assert [p["name"] for p in meta["places"]] == ["Alpha Terminal", "Echo Depot"]
    assert all(p["slug"] for p in meta["places"])
    assert any("Nowhere At All" in s for s in report["skipped_places"])
    assert [(s["day"], s["depart"]) for s in meta["slots"]] == list(build_static.SLOTS)


def test_default_menu_is_hubs_plus_demo_journeys():
    names = build_static.default_places()
    hubs = list(yaml.safe_load((REPO / "src" / "pipeline" / "hubs.yaml").read_text(encoding="utf-8")))
    assert set(hubs) <= set(names) and set(build_static.DEMO_PLACES) <= set(names)
    assert len(names) == len(set(names)) and 24 <= len(names) <= 32
    js = (REPO / "frontend" / "app.js").read_text(encoding="utf-8")
    for p in ("ISBT Anand Vihar", "Connaught Place", "Ambedkar Nagar", "ITO", "Mandi House", "Laxmi Nagar", "AIIMS"):
        assert f'"{p}"' in js and p in names


def test_plan_slots_match_the_api_after_rounding(built, api):
    out, _, _ = built
    body = load(out, "plans/alpha-terminal/echo-depot.json")
    assert set(body["slots"]) == {f"{d}-{t.replace(':', '')}" for d, t in build_static.SLOTS}
    for day, depart in build_static.SLOTS:
        want = build_static._round_plan(api.get("/v1/plan", params={"from": "Alpha Terminal", "to": "Echo Depot",
                                                                  "depart": depart, "day": day}).json())
        assert body["slots"][f"{day}-{depart.replace(':', '')}"] == want


def test_plan_coordinates_have_at_most_five_decimals(built):
    out, _, _ = built
    seen = 0
    for p in (out / "static-data" / "plans").rglob("*.json"):
        for m in re.finditer(r'"coords":(\[\[.*?\]\])', p.read_text(encoding="utf-8")):
            for num in re.findall(r"-?\d+\.\d+", m.group(1)):
                assert len(num.split(".")[1]) <= 5, num
                seen += 1
    assert seen > 0


def test_round_plan_touches_only_coords():
    node = {"a": 1.123456789, "legs": [{"coords": [[28.123456789, 77.987654321]], "minutes": 3.14159265}]}
    got = build_static._round_plan(node)
    assert got == {"a": 1.123456789, "legs": [{"coords": [[28.12346, 77.98765]], "minutes": 3.14159265}]}


def test_health_is_the_api_body(built, api):
    out, _, _ = built
    assert load(out, "health.json") == api.get("/v1/health").json()
    assert load(out, "health.json")["app_riders_one_in"] and load(out, "places.json")["data_version"]


def test_operator_files_match_the_api(built, api):
    out, _, _ = built
    day = "weekday"
    body = load(out, f"operator/trips-{day}.json")
    for op in build_static.OPERATORS:
        want = api.get("/v1/operator/trips", params={"day": day, "operator": op, "limit": 100}).json()["trips"]
        assert [t for t in body["trips"] if t["operator"] == op] == want
    csv = (out / "static-data" / "operator" / f"trips-{day}.csv").read_text(encoding="utf-8").splitlines()
    assert csv[0] == ",".join(OPERATOR_COLUMNS)
    assert len(csv) == 1 + len(body["trips"])
    assert load(out, "operator/trips-weekend.json")["day"] == "weekend"


def test_corridors_per_window_in_the_api_shape(built, api):
    out, _, _ = built
    day_files = sorted((out / "static-data" / "corridors").glob("weekday-*.json"))
    assert len(day_files) == 48 and len(list((out / "static-data" / "corridors").glob("weekend-*.json"))) == 24
    got = load(out, "corridors/weekday-0800.json")
    want = api.get("/v1/corridors", params={"day": "weekday", "window": "08:00", "limit": 50}).json()
    assert got["type"] == "FeatureCollection" and got["window"] == want["window"] and got["day"] == "weekday"
    assert [f["id"] for f in got["features"]] == [f["id"] for f in want["features"]]
    assert got["features"][0]["properties"].keys() == want["features"][0]["properties"].keys()


def test_crowding_for_routes_in_the_operator_tables(built, api):
    out, _, _ = built
    ids = {t["route_id"] for t in load(out, "operator/trips-weekday.json")["trips"]}
    for rid in ids:
        got = load(out, f"crowding/weekday/{rid}.json")
        assert got == api.get("/v1/crowding", params={"route_id": rid, "day": "weekday"}).json()
        assert "windows" in got                           # every window, for the heat strip


# ---------------------------------------------------------------- privacy

def test_no_vehicle_or_ticket_keys_anywhere(built):
    out, _, _ = built
    assert build_static.audit_static(out) == []
    for p in out.rglob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r'"(vehicle|vehicle_number|vehicle_id|registration|ticket_id|ts)"\s*:', text), p


def test_audit_catches_forbidden_keys_and_columns(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"ok": [{"Vehicle_Number": "DL1"}]}))
    (tmp_path / "b.csv").write_text("route_id,ticket_id\n1,2\n")
    (tmp_path / "c.json").write_text(json.dumps({"fine": 1}))
    problems = build_static.audit_static(tmp_path)
    assert len(problems) == 2 and any("a.json" in p for p in problems) and any("b.csv" in p for p in problems)


def test_build_refuses_a_forbidden_key_and_cleans_up(toy, tmp_path, monkeypatch):  # noqa: F811
    real = build_static._Run.operator

    def leaky(self):
        out = real(self)
        build_static._write_json(self.data / "operator" / "leak.json", {"rows": [{"ticket_id": 7}]})
        return out

    monkeypatch.setattr(build_static._Run, "operator", leaky)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="ticket_id"):
        build_static.build(out, toy.processed, places=PLACES, corridor_limit=5)
    assert not out.exists()


def test_build_refuses_a_non_empty_folder(toy, tmp_path):  # noqa: F811
    (tmp_path / "x.txt").write_text("keep me")
    with pytest.raises(ValueError, match="not empty"):
        build_static.build(tmp_path, toy.processed, places=PLACES)
    assert (tmp_path / "x.txt").read_text() == "keep me"


def test_build_needs_two_places(toy, tmp_path):  # noqa: F811
    with pytest.raises(ValueError, match="two places"):
        build_static.build(tmp_path / "out", toy.processed, places=["Alpha Terminal", "Nowhere At All"])
    assert not (tmp_path / "out").exists()


def test_big_files_get_gitattributes(toy, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(build_static, "LFS_BYTES", 1)
    out = tmp_path / "out"
    build_static.build(out, toy.processed, places=PLACES, corridor_limit=5)
    attrs = (out / ".gitattributes").read_text()
    assert "static-data/places.json filter=lfs" in attrs


def test_no_gitattributes_when_every_file_is_small(built):
    out, _, report = built
    assert not (out / ".gitattributes").exists() and report["lfs_files"] == []


# ---------------------------------------------------------------- the pages

def test_pages_use_paths_that_work_at_the_space_root(built):
    out, _, _ = built
    idx, op = (out / "index.html").read_text(encoding="utf-8"), (out / "operator.html").read_text(encoding="utf-8")
    for html in (idx, op):
        assert "/static/" not in html and 'href="/' not in html and 'src="/' not in html
        assert 'src="config.js"' in html and 'src="data.js"' in html and 'id="demo-banner"' in html
        assert CREDIT in html
    assert 'href="app.css"' in idx and 'src="app.js"' in idx
    assert 'href="index.html"' in op and 'src="operator.js"' in op
    cfg = (out / "config.js").read_text(encoding="utf-8")
    assert "CROWD_STATIC" in cfg and '"static-data/"' in cfg and "github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner" in cfg


def test_api_mode_config_is_empty_and_loaded_before_the_scripts():
    assert re.search(r"CROWD_STATIC\s*=\s*null", (REPO / "frontend" / "config.js").read_text(encoding="utf-8"))
    for page, script in (("index.html", "app.js"), ("operator.html", "operator.js")):
        html = (REPO / "frontend" / page).read_text(encoding="utf-8")
        order = [html.index(f'/static/{n}"') for n in ("config.js", "data.js", script)]
        assert order == sorted(order)


def test_api_serves_the_new_frontend_files(toy):  # noqa: F811
    with TestClient(create_app(toy)) as c:
        assert c.get("/static/config.js").status_code == 200 and c.get("/static/data.js").status_code == 200
        assert 'src="/static/data.js"' in c.get("/").text


def test_space_readme_front_matter_and_credit(built):
    out, _, _ = built
    text = (out / "README.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---")[1])
    assert meta["sdk"] == "static" and meta["app_file"] == "index.html" and meta["pinned"] is False
    assert all(meta.get(k) for k in ("title", "emoji", "colorFrom", "colorTo", "short_description"))
    assert CREDIT in text and "github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner" in text
    assert "aggregate" in text.lower() and not FORBIDDEN_WORDS.search(text)


def test_new_frontend_files_are_clean():
    for name in ("data.js", "config.js"):
        text = (REPO / "frontend" / name).read_text(encoding="utf-8")
        assert not FORBIDDEN_WORDS.search(text), name
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text and "document.write" not in text


def test_banner_wording_comes_from_the_data_files():
    js = (REPO / "frontend" / "data.js").read_text(encoding="utf-8")
    assert ("Live demo: ready-made answers for ${(meta.places || []).length} places at ${(meta.slots || []).length} "
            "departure times, computed by the same model. The full planner (any place, any time) runs from the code on ") in js
    assert not re.search(r"\b\d+ places\b", js)


# ---------------------------------------------------------------- data.js in a JS engine (skipped without node)

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_data_js_answers_api_urls_from_the_files(built, tmp_path):
    out, _, _ = built
    script = tmp_path / "t.js"
    script.write_text(r"""
const fs = require("fs"), path = require("path");
const out = process.argv[2];
global.window = { CROWD_STATIC: { data: "static-data/", github: "https://example.test/gh" }, fetch: async (u) => {
  const f = path.join(out, String(u));
  if (!fs.existsSync(f)) return new Response("nope", { status: 404 });
  return new Response(fs.readFileSync(f), { status: 200 });
} };
global.location = { href: "http://localhost/index.html" };
global.document = { createElement: () => ({ set textContent(v) { this.t = v; } }) };
require(path.join(process.argv[3], "frontend", "data.js"));
(async () => {
  const D = window.CrowdData, res = {};
  res.static = D.static;
  let r = await D.fetch("/v1/plan?from=alpha%20terminal&to=Echo+Depot&depart=8:00&day=weekday");
  res.plan = [r.status, (await r.json()).query.depart];
  r = await D.fetch("/v1/plan?from=zzz&to=Echo+Depot&depart=08:00&day=weekday");
  res.unknown = [r.status, (await r.json()).suggestions.length > 0];
  r = await D.fetch("/v1/plan?from=Echo+Depot&to=Alpha+Terminal&depart=03:00&day=weekday");
  res.badTime = r.status;
  r = await D.fetch("/v1/plan?from=Echo+Depot&to=Echo+Depot&depart=08:00&day=weekday");
  res.same = r.status;
  r = await D.fetch("/v1/health"); res.oneIn = (await r.json()).app_riders_one_in;
  r = await D.fetch("/v1/operator/trips?day=weekday&operator=DIMTS&limit=1"); const t = await r.json();
  res.ops = [t.count, t.trips.map((x) => x.operator)];
  r = await D.fetch("/v1/corridors?day=weekday&window=08:10&limit=1"); const c = await r.json();
  res.corr = [c.window.start, c.features.length];
  r = await D.fetch("/v1/crowding?route_id=101&day=weekday"); res.crowd = [r.status, Array.isArray((await r.json()).windows)];
  r = await D.fetch("/v1/crowding?route_id=99999&day=weekday"); res.noCrowd = r.status;
  res.csv = D.link("/v1/operator/trips.csv?day=weekend&operator=DTC&limit=1000");
  console.log(JSON.stringify(res));
})();
""", encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(out), str(REPO)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["static"] is True and got["plan"] == [200, "08:00"]
    assert got["unknown"] == [404, True] and got["badTime"] == 404 and got["same"] == 422
    assert got["oneIn"] and got["ops"][0] == 1 and got["ops"][1] == ["DIMTS"]
    assert got["corr"][0] == "08:00" and got["corr"][1] <= 1
    assert got["crowd"] == [200, True] and got["noCrowd"] == 404
    assert got["csv"] == "static-data/operator/trips-weekend.csv"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_data_js_is_a_no_op_in_api_mode(tmp_path):
    script = tmp_path / "t.js"
    script.write_text(r"""
global.window = { CROWD_STATIC: null, fetch: async () => "native" };
require(process.argv[2] + "/frontend/data.js");
(async () => {
  const D = window.CrowdData;
  console.log(JSON.stringify([D.static, await D.fetch("/v1/plan"), D.link("/v1/operator/trips.csv?day=weekday")]));
})();
""", encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(REPO)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [False, "native", "/v1/operator/trips.csv?day=weekday"]
