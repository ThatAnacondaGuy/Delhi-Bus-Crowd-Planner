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

    def counting(con, paths, sample_routes=None):
        calls.append(1)
        return real(con, paths, sample_routes)

    monkeypatch.setattr(clean, "run", counting)

    assert run.main(["--until", "clean"], paths=paths) == 0
    m = json.loads((paths.processed / "manifest.json").read_text())
    assert m["stages"]["clean"]["done"] is True
    assert run.main(["--until", "clean"], paths=paths) == 0
    assert len(calls) == 1
    assert run.main(["--until", "clean", "--force"], paths=paths) == 0
    assert len(calls) == 2
    monkeypatch.setitem(run.STAGES, "resolve", "src.pipeline.no_such_stage_module:run")
    run.main(["--until", "resolve"], paths=paths)
    assert "stage resolve: not implemented yet, skipped" in capsys.readouterr().out


def test_paths_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    p = Paths.from_env()
    assert p.processed == tmp_path and p.work_db == tmp_path / "work.duckdb"
    assert p.planner_dir == tmp_path / "planner"


def test_kwargs_stage_gets_all_options(tmp_path, monkeypatch):
    csv = make_tickets(tmp_path, [{"created_at": "2026-10-05 08:00:00+05:30"}])
    base = Paths.default()
    paths = Paths(base.repo, base.gtfs_dir, csv, base.gps_archive, base.gps_aggregates, tmp_path / "out")
    seen = {}

    def kw_stage(con, paths, **kwargs):
        seen.update(kwargs)

    def narrow_stage(con, paths, force):
        seen["narrow_force"] = force

    monkeypatch.setattr(run, "_load", lambda spec: {"k": kw_stage, "n": narrow_stage}[spec])
    monkeypatch.setattr(run, "STAGES", {"a": "k", "b": "n"})
    run.main(["--until", "b", "--force", "--gps-raw"], paths=paths)
    assert seen["force"] is True and seen["gps_raw"] is True and "sample_routes" in seen
    assert seen["narrow_force"] is True


GTFS_NAMES = ("routes", "trips", "stop_times", "stops")


def test_stage_inputs_resolve_adds_gtfs():
    p = Paths.default()
    assert run.stage_inputs(p, "clean") == {"tickets_csv": str(p.tickets_csv)}
    ins = run.stage_inputs(p, "resolve")
    assert ins["tickets_csv"] == str(p.tickets_csv)
    assert {ins[f"gtfs_{n}"] for n in GTFS_NAMES} == {str(p.gtfs_dir / f"{n}.txt") for n in GTFS_NAMES}
    assert set(ins) <= set(run.stage_inputs(p, "network"))   # later stages inherit upstream inputs


def test_gtfs_change_reruns_resolve_only(tmp_path, monkeypatch):
    csv = make_tickets(tmp_path, [{"created_at": "2026-10-05 08:00:00+05:30"}])
    gtfs = tmp_path / "gtfs"
    gtfs.mkdir()
    for n in GTFS_NAMES:
        (gtfs / f"{n}.txt").write_text("x\n")
    base = Paths.default()
    paths = Paths(base.repo, gtfs, csv, base.gps_archive, base.gps_aggregates, tmp_path / "out")
    calls = []
    monkeypatch.setattr(run, "_load", lambda spec: (lambda con, paths: calls.append(spec)))
    monkeypatch.setattr(run, "STAGES", {"clean": "c", "resolve": "r"})
    run.main(["--until", "resolve"], paths=paths)
    run.main(["--until", "resolve"], paths=paths)
    assert calls == ["c", "r"]
    (gtfs / "stops.txt").write_text("changed\n")
    run.main(["--until", "resolve"], paths=paths)
    assert calls == ["c", "r", "r"]


def test_render_stage_is_stale_when_a_template_or_the_report_changes(tmp_path):
    base = Paths.default()
    paths = Paths(tmp_path, base.gtfs_dir, base.tickets_csv, base.gps_archive, base.gps_aggregates, tmp_path / "out")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "X.tmpl.md").write_text("{{run_id}}")
    ins = run.stage_inputs(paths, "render")
    assert ins["validation_report"] == str(paths.processed / "validation_report.json")
    assert ins["template_X.tmpl.md"] == str(tmp_path / "docs" / "X.tmpl.md")
    assert set(run.stage_inputs(paths, "validate")) <= set(ins)
