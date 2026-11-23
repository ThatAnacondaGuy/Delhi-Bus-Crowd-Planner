"""Build the free static demo (a Hugging Face `sdk: static` Space): the two screens plus precomputed JSON.

    python -m deploy.build_static OUT_DIR [--processed DIR]

Judges pick from a menu of places and departure times instead of typing; every answer was computed ahead of time by
the same planner and written by the API's own code, so the files have exactly the shape the API returns. The full
planner (any place, any time) still runs from the repo. OUT_DIR becomes the Space repo root:

    index.html operator.html app.css app.js operator.css operator.js data.js config.js README.md [.gitattributes]
    static-data/places.json  health.json
    static-data/plans/<from>/<to>.json        7 departure slots per ordered pair of places
    static-data/operator/trips-<day>.json|csv top trips per operator
    static-data/corridors/<day>-<hhmm>.json   busiest corridor stretches per window
    static-data/crowding/<day>/<route>.json   every window of each route shown in the operator tables

Every JSON and CSV written is audited with the same column rules as deploy/package_bundle.py, and the build fails if a
vehicle, registration, ticket id or timestamp key turns up. Build outside the repository (the output is large and is
never committed).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import shutil
import sys
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from deploy.package_bundle import FORBIDDEN_COLUMNS, columns
from src.api.main import create_app
from src.pipeline.config import WINDOWS
from src.pipeline.paths import REPO, Paths
from src.routing.planner import PlaceNotFound

GITHUB = "https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner"
SLOTS = (("weekday", "08:00"), ("weekday", "09:00"), ("weekday", "13:00"), ("weekday", "18:00"),
         ("weekday", "21:00"), ("weekend", "10:00"), ("weekend", "18:00"))
DAYS = ("weekday", "weekend")
OPERATORS = ("DTC", "DIMTS")
TOP_PER_OPERATOR = 100        # rows per operator in the operator JSON and CSV
SHOWN_PER_OPERATOR = 20       # rows the operator screen draws; their routes get a heat strip
CORRIDOR_LIMIT = 1000         # busiest corridor stretches per window (the API allows 5,000; the 200 MB budget decides)
LFS_BYTES = 10 * 1024 * 1024  # Hugging Face wants Git LFS above this size
# The five demo journeys (frontend/app.js PRESETS) use these; all are also hubs in src/pipeline/hubs.yaml.
DEMO_PLACES = ("ISBT Anand Vihar", "Connaught Place", "Ambedkar Nagar", "ITO", "Mandi House", "Laxmi Nagar", "AIIMS")
# Well-known places beyond the hubs; each is a GTFS place name that the planner resolves on its own.
EXTRA_PLACES = ("Lajpat Nagar", "Rajouri Garden", "Hauz Khas", "Nangloi", "Jhandewalan", "Old Delhi Railway Station",
                "Jama Masjid", "Peeragarhi", "Nizamuddin Railway Station", "Azadpur Terminal")
PAGES = ("index.html", "operator.html")
ASSETS = ("app.css", "app.js", "operator.css", "operator.js", "data.js")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}{minute % 60:02d}"


def default_places(repo: Path = REPO) -> list[str]:
    hubs = list(yaml.safe_load((repo / "src" / "pipeline" / "hubs.yaml").read_text(encoding="utf-8")))
    return list(dict.fromkeys([*hubs, *DEMO_PLACES, *EXTRA_PLACES]))


def _round_coords(x):
    if isinstance(x, float):
        return round(x, 5)
    if isinstance(x, list):
        return [_round_coords(v) for v in x]
    return x


def _round_plan(node):
    """Coordinates to 5 decimals (about a metre) wherever a plan carries them; nothing else is touched."""
    if isinstance(node, dict):
        return {k: _round_coords(v) if k == "coords" else _round_plan(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_round_plan(v) for v in node]
    return node


def _write_json(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False), encoding="utf-8")


def audit_static(root: Path) -> list[str]:
    """Problems in the JSON and CSV files under `root`: a vehicle, registration, ticket id or timestamp key or column."""
    problems = []
    for p in sorted(x for x in Path(root).rglob("*") if x.is_file() and x.suffix in (".json", ".csv", ".geojson")):
        bad = [c for c in columns(p) if c.lower() in FORBIDDEN_COLUMNS]
        if bad:
            problems.append(f"{p.relative_to(root).as_posix()}: forbidden column(s) {', '.join(bad)}")
    return problems


def for_space(html: str) -> str:
    """The pages as the API serves them use /static/ paths, a / link and an API link for the CSV; at the Space root all are relative."""
    out = (html.replace('"/static/', '"').replace('href="/"', 'href="index.html"')
           .replace('href="/v1/operator/trips.csv?day=weekday"', 'href="static-data/operator/trips-weekday.csv"'))
    if "/static/" in out or 'href="/' in out:
        raise ValueError("a page still has a root-relative path after rewriting")
    return out


class _Run:
    """One build: the API in-process, the files written, and a record of what was skipped."""

    def __init__(self, out: Path, client: TestClient, slots, corridor_limit: int, log):
        self.out, self.c, self.slots, self.corridor_limit, self.log = out, client, slots, corridor_limit, log
        self.data = out / "static-data"
        self.files: list[Path] = []
        self.report: dict = {"skipped_places": [], "missing_slots": [], "plans": 0}

    def put(self, path: Path, body) -> None:
        _write_json(path, body)
        self.files.append(path)

    def get(self, url: str, **params):
        r = self.c.get(url, params=params)
        return r.status_code, r

    def places(self, names) -> list[dict]:
        planner, seen, out = self.c.app.state.s.planner, {}, []
        for name in names:
            try:
                place = planner._resolve(name, [])           # the same resolution /v1/plan does
            except PlaceNotFound as e:
                self.report["skipped_places"].append(f"{name}: {e.message}")
                continue
            if place.id in seen:
                self.report["skipped_places"].append(f"{name}: same place as {seen[place.id]}")
                continue
            seen[place.id] = name
            out.append({"name": name, "slug": slug(name)})
        return sorted(out, key=lambda p: p["name"].lower())

    def plans(self, places: list[dict]) -> None:
        t0 = time.time()
        for a in places:
            for b in places:
                if a is b:
                    continue
                slots = {}
                for day, depart in self.slots:
                    status, r = self.get("/v1/plan", **{"from": a["name"], "to": b["name"], "depart": depart, "day": day})
                    if status != 200:
                        self.report["missing_slots"].append(f"{a['name']} -> {b['name']} {day} {depart}: {status}")
                        continue
                    slots[f"{day}-{depart.replace(':', '')}"] = _round_plan(r.json())
                if slots:
                    self.put(self.data / "plans" / a["slug"] / f"{b['slug']}.json", {"slots": slots})
                    self.report["plans"] += len(slots)
            self.log(f"plans from {a['name']} done ({time.time() - t0:.0f}s)")

    def operator(self) -> dict[str, list[int]]:
        """Trips per day (top rows per operator), the CSVs, and the routes the screen shows a heat strip for."""
        shown: dict[str, list[int]] = {}
        for day in DAYS:
            rows, csv_parts, route_ids = [], [], []
            head = {}
            for op in OPERATORS:
                _, r = self.get("/v1/operator/trips", day=day, operator=op, limit=TOP_PER_OPERATOR)
                body = r.json()
                head = {"data_version": body["data_version"], "day": day}
                rows += body["trips"]
                route_ids += [t["route_id"] for t in body["trips"][:SHOWN_PER_OPERATOR]]
                _, c = self.get("/v1/operator/trips.csv", day=day, operator=op, limit=TOP_PER_OPERATOR)
                csv_parts.append(c.text if not csv_parts else c.text.split("\n", 1)[1])
            self.put(self.data / "operator" / f"trips-{day}.json", {**head, "operator": None, "count": len(rows), "trips": rows})
            csv = self.data / "operator" / f"trips-{day}.csv"
            csv.write_text("".join(csv_parts), encoding="utf-8", newline="")
            self.files.append(csv)
            shown[day] = list(dict.fromkeys(route_ids))
        return shown

    def corridors(self) -> None:
        for day in DAYS:
            step = WINDOWS[day].step_min
            for start in range(0, 1440, step):
                _, r = self.get("/v1/corridors", day=day, window=f"{start // 60:02d}:{start % 60:02d}", limit=self.corridor_limit)
                body = r.json()
                for f in body["features"]:
                    g = f.get("geometry")
                    if g and "coordinates" in g:
                        g["coordinates"] = _round_coords(g["coordinates"])
                self.put(self.data / "corridors" / f"{day}-{_hhmm(start)}.json", body)
            self.log(f"corridors {day} done")

    def crowding(self, routes: dict[str, list[int]]) -> None:
        for day, ids in routes.items():
            for rid in ids:
                status, r = self.get("/v1/crowding", route_id=rid, day=day)
                if status == 200:
                    self.put(self.data / "crowding" / day / f"{rid}.json", r.json())
                else:
                    self.report.setdefault("no_crowding", []).append(f"{day} route {rid}: {status}")


def build_with_report(out_dir, processed=None, places=None, slots=SLOTS, repo=None, corridor_limit=CORRIDOR_LIMIT,
                      log=lambda m: None) -> tuple[list[Path], dict]:
    """Write the static Space into `out_dir` (must not exist or be empty); return (files, report).

    `places` is a list of place names to offer (default: the hubs, the demo journeys and some well-known extras);
    names the planner cannot resolve are skipped and listed in report["skipped_places"]. A failure removes only what
    this call created."""
    repo = Path(repo) if repo is not None else REPO
    paths = Paths.default()
    if processed is not None:
        paths = dataclasses.replace(paths, processed=Path(processed))
    out = Path(out_dir)
    existed = out.exists()
    if existed and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"{out}: not empty; give an empty or new folder")
    out.mkdir(parents=True, exist_ok=True)
    try:
        with TestClient(create_app(paths)) as client:
            run = _Run(out, client, tuple(slots), corridor_limit, log)
            health = client.get("/v1/health")
            if health.status_code != 200:
                raise RuntimeError("/v1/health failed")
            menu = run.places(default_places(repo) if places is None else list(places))
            if len(menu) < 2:
                raise ValueError("fewer than two places resolve; nothing to plan between")
            version = health.json()["data_version"]
            run.put(run.data / "places.json", {"data_version": version, "places": menu,
                                              "slots": [{"day": d, "depart": t} for d, t in run.slots]})
            run.put(run.data / "health.json", health.json())
            run.plans(menu)
            run.crowding(run.operator())
            run.corridors()
        files = run.files
        for page in PAGES:
            (out / page).write_text(for_space((repo / "frontend" / page).read_text(encoding="utf-8")), encoding="utf-8")
            files.append(out / page)
        for name in ASSETS:
            shutil.copy2(repo / "frontend" / name, out / name)
            files.append(out / name)
        (out / "config.js").write_text(
            "/* Static demo: the screens read the precomputed files in static-data/ instead of the API. */\n"
            f"window.CROWD_STATIC = {json.dumps({'data': 'static-data/', 'github': GITHUB})};\n", encoding="utf-8")
        shutil.copy2(repo / "deploy" / "static_README.md", out / "README.md")
        files += [out / "config.js", out / "README.md"]
        problems = audit_static(out)
        if problems:
            raise ValueError("static build refused: " + "; ".join(problems))
        big = sorted(p.relative_to(out).as_posix() for p in files if p.stat().st_size > LFS_BYTES)
        if big:
            (out / ".gitattributes").write_text(
                "".join(f"{b} filter=lfs diff=lfs merge=lfs -text\n" for b in big), encoding="utf-8")
            files.append(out / ".gitattributes")
        run.report["places"] = [p["name"] for p in menu]
        run.report["lfs_files"] = big
        return files, run.report
    except BaseException:
        for child in out.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        if not existed:
            out.rmdir()
        raise


def build(out_dir, processed=None, **kw) -> list[Path]:
    return build_with_report(out_dir, processed, **kw)[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--processed", help="pipeline output folder (default data/processed)")
    a = ap.parse_args(argv)
    out = Path(a.out_dir).resolve()
    if REPO in (out, *out.parents):
        ap.error("build the static site outside the repository")
    files, rep = build_with_report(out, a.processed, log=lambda m: print(m, file=sys.stderr, flush=True))
    total = sum(f.stat().st_size for f in files)
    biggest = max(files, key=lambda f: f.stat().st_size)
    print(f"{len(files)} files, {total / 1e6:.1f} MB; largest {biggest.relative_to(out)} {biggest.stat().st_size / 1e6:.2f} MB")
    print(f"{len(rep['places'])} places: {', '.join(rep['places'])}")
    print(f"{rep['plans']} plan slots written; {len(rep['missing_slots'])} slots without an answer; "
          f"{len(rep['skipped_places'])} places skipped")
    for s in rep["skipped_places"] + rep["missing_slots"][:20]:
        print("  skipped:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
