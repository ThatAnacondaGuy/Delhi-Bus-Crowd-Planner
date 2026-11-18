"""Package the Hugging Face Space: the API, the two screens and aggregate-only outputs.

    python -m deploy.package_bundle OUT_DIR            # the whole Space repo (Dockerfile, code, data/)
    python -m deploy.package_bundle OUT_DIR --data     # only the data folder

Only files on the allow-list are copied, so ticket-level and vehicle-level data (work.duckdb, resolved tickets,
per-vehicle GPS work files) can never reach the Space. `audit` re-checks any folder: every file name must be on
the allow-list and no table may carry a vehicle, registration, ticket id or timestamp column.
Build the bundle outside the repository (it is large and must never be committed).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.pipeline.config import PLANNER_TABLES
from src.pipeline.paths import REPO, Paths

TOP_LEVEL = ("stretch_crowding.parquet", "corridor_values.parquet", "corridor_geometry.geojson",
             "operator_trips.parquet", "route_hour_summary.csv", "coverage.csv", "validation_report.json",
             "validation_report.md", "data_quality.md", "manifest.json")
PLANNER = tuple(f"planner/{t}.parquet" for t in PLANNER_TABLES)
ALLOWED = frozenset(TOP_LEVEL + PLANNER)
# Without these the API cannot start (Planner.load, /v1/health); the rest are copied when present.
REQUIRED = frozenset({"stretch_crowding.parquet", "manifest.json"} | {
    f"planner/{t}.parquet" for t in ("canonical_stops", "runtime_factors", "places", "passings", "route_specs")})
FORBIDDEN_COLUMNS = frozenset({"vehicle", "vehicle_number", "vehicle_id", "registration", "ticket_id", "ts"})
CODE_DIRS = ("src", "frontend")
SPACE_FILES = {"Dockerfile": "Dockerfile", "README.md": "space_README.md"}
GITATTRIBUTES = "*.parquet filter=lfs diff=lfs merge=lfs -text\n*.geojson filter=lfs diff=lfs merge=lfs -text\n"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def _json_keys(node, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(str(k))
            _json_keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _json_keys(v, out)


def columns(path: Path) -> list[str]:
    """Column names of a parquet or CSV file, or every key of a JSON / GeoJSON file."""
    if path.suffix == ".parquet":
        return list(pq.read_schema(path).names)
    if path.suffix == ".csv":
        return [str(c) for c in pd.read_csv(path, nrows=0).columns]
    if path.suffix in (".json", ".geojson"):
        keys: set[str] = set()
        _json_keys(json.loads(path.read_text(encoding="utf-8")), keys)
        return sorted(keys)
    return []


def audit(data_dir: Path) -> list[str]:
    """Problems found in a bundle's data folder; an empty list means it is safe to publish."""
    data_dir = Path(data_dir)
    problems = []
    for p in sorted(x for x in data_dir.rglob("*") if x.is_file()):
        rel = p.relative_to(data_dir).as_posix()
        if rel not in ALLOWED:
            problems.append(f"{rel}: not on the allow-list")
            continue
        bad = [c for c in columns(p) if c.lower() in FORBIDDEN_COLUMNS]
        if bad:
            problems.append(f"{rel}: forbidden column(s) {', '.join(bad)}")
    return problems


def _clean_manifest(src: Path, dst: Path) -> None:
    """The run id and stage record, without the local paths and file hashes of the machine that built it."""
    m = json.loads(src.read_text(encoding="utf-8"))
    m.pop("hash_cache", None)
    for rec in m.get("stages", {}).values():
        rec["outputs"] = []
    dst.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")


def build(out_dir, processed=None) -> list[Path]:
    """Copy the allow-listed aggregates from `processed` (default data/processed) into `out_dir`; return the files.

    Raises FileNotFoundError when a file the API needs is missing and ValueError when the audit finds a problem."""
    src = Path(processed) if processed is not None else Paths.default().processed
    out = Path(out_dir)
    missing = sorted(r for r in REQUIRED if not (src / r).is_file())
    if missing:
        raise FileNotFoundError(f"{src}: missing {', '.join(missing)}")
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for rel in sorted(ALLOWED):
        s = src / rel
        if not s.is_file():
            continue
        d = out / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if rel == "manifest.json":
            _clean_manifest(s, d)
        else:
            shutil.copy2(s, d)
        copied.append(d)
    problems = audit(out)
    if problems:
        shutil.rmtree(out)
        raise ValueError("bundle refused: " + "; ".join(problems))
    return copied


def build_space(out_dir, processed=None, repo=None) -> list[Path]:
    """The whole Space repo: Dockerfile, README with the Space front matter, requirements.lock, src/, frontend/, data/."""
    repo = Path(repo) if repo is not None else REPO
    out = Path(out_dir)
    out_files = list(build(out / "data", processed))
    for name, source in SPACE_FILES.items():
        shutil.copy2(repo / "deploy" / source, out / name)
        out_files.append(out / name)
    shutil.copy2(repo / "requirements.lock", out / "requirements.lock")
    out_files.append(out / "requirements.lock")
    (out / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
    out_files.append(out / ".gitattributes")
    for d in CODE_DIRS:
        shutil.copytree(repo / d, out / d, ignore=IGNORE, dirs_exist_ok=True)
        out_files += [p for p in (out / d).rglob("*") if p.is_file()]
    return out_files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--data", action="store_true", help="only the data folder, not the whole Space repo")
    ap.add_argument("--processed", help="pipeline output folder (default data/processed)")
    a = ap.parse_args(argv)
    out = Path(a.out_dir).resolve()
    if REPO in (out, *out.parents):
        ap.error("build the bundle outside the repository")
    files = (build if a.data else build_space)(out, a.processed)
    total = sum(f.stat().st_size for f in files)
    for f in sorted(files):
        print(f"{f.stat().st_size / 1e6:9.2f} MB  {f.relative_to(out)}")
    print(f"{total / 1e6:9.2f} MB  total, {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
