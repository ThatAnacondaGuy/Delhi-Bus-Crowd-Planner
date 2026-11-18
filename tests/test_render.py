import json

import pytest

from src.pipeline import render
from src.pipeline.errors import RenderError
from src.pipeline.paths import Paths


def _tmpl(tmp_path, text):
    t = tmp_path / "A.tmpl.md"
    t.write_text(text, encoding="utf-8")
    return t, tmp_path / "A.md"


def test_formats_number(tmp_path):
    t, out = _tmpl(tmp_path, "Match rate {{match_rate:.1%}}; tickets {{n:,}}; plain {{ run_id }}.")
    render.render_file(t, out, {"match_rate": 0.9313, "n": 1234567, "run_id": "r1"})
    assert out.read_text(encoding="utf-8") == "Match rate 93.1%; tickets 1,234,567; plain r1."


def test_unknown_key_raises(tmp_path):
    t, out = _tmpl(tmp_path, "x {{nope}}")
    with pytest.raises(RenderError, match="nope"):
        render.render_file(t, out, {"a": 1})
    assert not out.exists()


def test_leftover_braces_raise(tmp_path):
    t, out = _tmpl(tmp_path, "x {{ not a name }} y")
    with pytest.raises(RenderError):
        render.render_file(t, out, {"a": 1})
    assert not out.exists()


def test_none_value_and_bad_format_raise(tmp_path):
    t, out = _tmpl(tmp_path, "{{a:.1%}}")
    with pytest.raises(RenderError, match="a"):
        render.render_file(t, out, {"a": None})
    with pytest.raises(RenderError, match="a"):
        render.render_file(t, out, {"a": "text"})   # '.1%' cannot format a str


def test_manifest_summary_is_flat(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"run_id": "20261118-2200-ab12cd34", "stages": {
        "validate": {"finished_at": "2026-11-18T22:03:14.070573+00:00",
                     "versions": {"code": "1d7db9f", "duckdb": "2.0.0", "pandas": "3.1.1"}},
        "clean": {"finished_at": "2026-11-18T21:59:57+00:00", "versions": {"code": "1d7db9f"}}}}))
    s = render.manifest_summary(m)
    assert s["run_id"] == "20261118-2200-ab12cd34"
    assert s["code_version"] == "1d7db9f"
    assert s["pipeline_finished_ist"] == "2026-11-19 03:33"
    assert all(not isinstance(v, (dict, list)) for v in s.values())


def test_manifest_summary_missing_run_id_raises(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"stages": {}}))
    with pytest.raises(RenderError, match="run_id"):
        render.manifest_summary(m)


def _paths(tmp_path):
    base = Paths.default()
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    proc = tmp_path / "out"
    proc.mkdir()
    (proc / "validation_report.json").write_text(json.dumps({"headline_numbers": {"match_rate": 0.9313}}))
    (proc / "manifest.json").write_text(json.dumps({"run_id": "rid", "stages": {}}))
    return Paths(repo, base.gtfs_dir, base.tickets_csv, base.gps_archive, base.gps_aggregates, proc)


def test_run_renders_every_template_and_says_so_when_none(tmp_path, capsys):
    paths = _paths(tmp_path)
    assert render.run(None, paths) == "no templates, nothing rendered"
    (paths.repo / "docs" / "TECHNICAL_NOTE.tmpl.md").write_text("{{match_rate:.1%}} / {{run_id}}")
    assert render.run(None, paths) == "1 file(s) rendered"
    assert (paths.repo / "docs" / "TECHNICAL_NOTE.md").read_text() == "93.1% / rid"
