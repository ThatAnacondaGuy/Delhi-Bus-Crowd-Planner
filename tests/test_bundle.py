"""Hugging Face Space bundle: aggregates only, no ticket-level or vehicle-level data, API starts from it alone."""
import json
import re
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml
from fastapi.testclient import TestClient

from deploy import package_bundle
from src.api.main import create_app
from src.pipeline.config import PLANNER_TABLES
from tests.test_api import toy  # noqa: F401  (session fixture: a toy pipeline run)

FORBIDDEN_COLUMNS = {"vehicle", "vehicle_number", "vehicle_id", "registration", "ticket_id", "ts"}
REPO = Path(__file__).resolve().parents[1]
SOURCE_ONLY = ["work.duckdb", "resolved_tickets.parquet", "segment_crowding.parquet", "canonical_route_stops.parquet",
               "route_segment_shapes.pkl", "devi_vehicles.parquet", "tickets_resolved.parquet", "in.txt"]


@pytest.fixture(scope="module")
def processed(toy, tmp_path_factory):  # noqa: F811
    """The toy run's output folder plus the ticket-level and work files a real run leaves beside the aggregates."""
    src = tmp_path_factory.mktemp("src") / "processed"
    shutil.copytree(toy.processed, src)
    for name in SOURCE_ONLY:
        (src / name).write_bytes(b"ticket-level, must never be copied")
    (src / "gps_work").mkdir()
    (src / "gps_work" / "2026-10-03_trips.parquet").write_bytes(b"vehicle-level")
    (src / "planner" / "devi_vehicles.parquet").write_bytes(b"vehicle-level")
    return src


@pytest.fixture(scope="module")
def bundle(processed, tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle")
    package_bundle.build(out, processed)
    return out


def files(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file())


def columns(path: Path) -> set[str]:
    """Column names of a parquet or CSV file, or every key of a JSON / GeoJSON file, lower-cased."""
    if path.suffix == ".parquet":
        return {n.lower() for n in pq.read_schema(path).names}
    if path.suffix == ".csv":
        return {c.lower() for c in pd.read_csv(path, nrows=0).columns}
    if path.suffix in (".json", ".geojson"):
        keys: set[str] = set()

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    keys.add(str(k).lower())
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads(path.read_text()))
        return keys
    return set()


def test_bundle_has_no_ticket_or_vehicle_columns(bundle):
    seen = 0
    for p in files(bundle):
        bad = columns(p) & FORBIDDEN_COLUMNS
        assert not bad, f"{p.relative_to(bundle)} has forbidden columns {sorted(bad)}"
        seen += p.suffix in (".parquet", ".csv", ".json", ".geojson")
    assert seen >= 12


def test_bundle_files_are_on_the_allow_list(bundle, processed):
    allowed = package_bundle.ALLOWED
    got = {p.relative_to(bundle).as_posix() for p in files(bundle)}
    assert got <= allowed, sorted(got - allowed)
    assert {f"planner/{t}.parquet" for t in PLANNER_TABLES} <= got
    assert "stretch_crowding.parquet" in got and "manifest.json" in got
    for name in SOURCE_ONLY + ["gps_work", "planner/devi_vehicles.parquet"]:
        assert not (bundle / name).exists(), name
    assert not list(bundle.rglob("*.duckdb")) and not list(bundle.rglob("*.pkl"))
    assert not any(re.search(r"ticket|vehicle|devi", p.name, re.I) for p in files(bundle))


def test_total_size_under_500_mb(bundle):
    assert sum(p.stat().st_size for p in files(bundle)) < 500 * 1024 * 1024


def test_manifest_in_bundle_has_no_local_paths(bundle):
    text = (bundle / "manifest.json").read_text()
    m = json.loads(text)
    assert m["run_id"] and "hash_cache" not in m
    assert "/Users/" not in text and "work.duckdb" not in text
    assert all(v["outputs"] == [] for v in m["stages"].values())


def test_audit_catches_a_forbidden_column_and_a_stray_file(bundle, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(bundle, bad)
    assert package_bundle.audit(bad) == []
    pd.DataFrame({"route_id": [1], "Vehicle_Number": ["DL1"]}).to_parquet(bad / "operator_trips.parquet")
    (bad / "work.duckdb").write_bytes(b"x")
    problems = " ".join(package_bundle.audit(bad))
    assert "Vehicle_Number" in problems and "work.duckdb" in problems


def test_build_refuses_to_publish_a_forbidden_column(processed, tmp_path):
    src = tmp_path / "processed"
    shutil.copytree(processed, src)
    pd.DataFrame({"route_id": [1], "ticket_id": [7]}).to_parquet(src / "operator_trips.parquet")
    with pytest.raises(ValueError, match="ticket_id"):
        package_bundle.build(tmp_path / "out", src)


def test_api_starts_from_the_bundle_alone(bundle, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(bundle))
    with TestClient(create_app()) as c:
        r = c.get("/v1/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"
        assert r.json()["counts"]["stretch_rows"] > 0
        assert c.get("/").status_code == 200 and c.get("/operator").status_code == 200
        plan = c.get("/v1/plan", params={"from": "Alpha Terminal", "to": "Echo Depot", "depart": "08:00",
                                         "day": "weekday"})
        assert plan.status_code == 200 and plan.json()["options"]
        assert c.get("/v1/operator/trips", params={"day": "weekday"}).status_code == 200
        assert c.get("/v1/corridors", params={"day": "weekday", "window": "08:00"}).status_code == 200


def test_space_repo_layout(processed, tmp_path):
    out = tmp_path / "space"
    package_bundle.build_space(out, processed)
    for name in ("Dockerfile", "README.md", "requirements.lock", ".gitattributes", "src/api/main.py",
                 "frontend/index.html", "frontend/operator.html", "data/stretch_crowding.parquet",
                 "data/planner/canonical_stops.parquet"):
        assert (out / name).is_file(), name
    assert not list(out.rglob("__pycache__")) and not list(out.rglob("*.duckdb"))
    assert package_bundle.audit(out / "data") == []
    assert "*.parquet filter=lfs" in (out / ".gitattributes").read_text()
    # what is in the Space is exactly the allow-listed data plus code: nothing under data/ is stray
    assert all(p.relative_to(out / "data").as_posix() in package_bundle.ALLOWED for p in files(out / "data"))


def test_space_readme_front_matter_and_credit():
    text = (REPO / "deploy" / "space_README.md").read_text()
    head = text.split("---")[1]
    meta = yaml.safe_load(head)
    assert meta["sdk"] == "docker" and meta["app_port"] == 7860
    assert all(meta.get(k) for k in ("title", "emoji", "colorFrom", "colorTo", "short_description"))
    assert "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing." in text
    assert "aggregate" in text.lower()
    assert not re.search(r"κ|kappa|mcraptor|pareto|sigmoid|\bscore\b", text, re.I)


def test_dockerfile_contract():
    d = (REPO / "deploy" / "Dockerfile").read_text()
    assert d.startswith("FROM python:3.12-slim")
    assert "requirements.lock" in d and re.search(r"^ENV\b[^\n]*(\\\n[^\n]*)*\bDATA_DIR=/app/data", d, re.M)
    assert re.search(r"^USER\s+(user|1000)", d, re.M) and "WORKDIR /app" in d and "1000" in d
    assert 'CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]' in d
    assert all(re.search(rf"^COPY .*{s}", d, re.M) for s in ("src ./src", "frontend ./frontend", "data /app/data"))
