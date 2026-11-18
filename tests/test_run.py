import json

from src.pipeline import clean, run
from src.pipeline.paths import Paths
from tests.helpers import make_tickets


def test_run_until_clean_and_resume(tmp_path, monkeypatch, capsys):
    csv = make_tickets(tmp_path, [{"created_at": "2026-10-05 08:00:00+05:30"}])
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, csv, base.gps_archive, base.gps_aggregates, tmp_path / "out")
    calls = []
    real = clean.run
    monkeypatch.setattr(clean, "run", lambda *a, **k: calls.append(1) or real(*a, **k))

    assert run.main(["--until", "clean"], paths=paths) == 0
    m = json.loads((paths.processed / "manifest.json").read_text())
    assert m["stages"]["clean"]["done"] is True
    assert run.main(["--until", "clean"], paths=paths) == 0
    assert len(calls) == 1
    assert run.main(["--until", "clean", "--force"], paths=paths) == 0
    assert len(calls) == 2
    run.main(["--until", "resolve"], paths=paths)
    assert "stage resolve: not implemented yet, skipped" in capsys.readouterr().out


def test_paths_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    p = Paths.from_env()
    assert p.processed == tmp_path and p.work_db == tmp_path / "work.duckdb"
    assert p.planner_dir == tmp_path / "planner"
