import subprocess
from pathlib import Path

from scripts.precommit_check import check_paths

ROOT = Path(__file__).resolve().parents[1]

IGNORED = ["data/processed_/x.parquet", "data/raw/gps/a.7z", "x.parquet", "x.pkl", "x.geojson", "x.db",
           "data/processed/stretch_crowding.parquet", "data/processed/work.duckdb"]
KEPT = ["tests/fixtures/toy_tickets.csv", "data/processed/validation_report.json",
        "data/processed/coverage.csv", "data/gps_aggregates/gps_route_hour.csv"]


def ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


def test_gitignore():
    assert all(ignored(p) for p in IGNORED) and not any(ignored(p) for p in KEPT)


def test_precommit_rejects(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * 5_000_001)
    errs = check_paths([str(big), "data/raw/x.csv", "docs/ok.md"])
    assert len(errs) == 2 and not any("docs/ok.md" in e for e in errs)


def test_imports():
    import pyarrow, rapidfuzz, fastapi, duckdb, yaml, httpx  # noqa
