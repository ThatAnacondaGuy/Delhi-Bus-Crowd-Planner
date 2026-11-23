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


def test_run_also_renders_the_root_readme_template(tmp_path):
    paths = _paths(tmp_path)
    (paths.repo / "docs" / "TECHNICAL_NOTE.tmpl.md").write_text("note {{match_rate:.1%}}")
    (paths.repo / "README.tmpl.md").write_text("readme {{match_rate:.1%}} {{run_id}}")
    assert render.run(None, paths) == "2 file(s) rendered"
    assert (paths.repo / "README.md").read_text() == "readme 93.1% rid"
    assert (paths.repo / "docs" / "TECHNICAL_NOTE.md").read_text() == "note 93.1%"


def test_readme_template_alone_is_enough(tmp_path):
    paths = _paths(tmp_path)
    (paths.repo / "README.tmpl.md").write_text("{{match_rate:.0%}}")
    assert render.run(None, paths) == "1 file(s) rendered"
    assert (paths.repo / "README.md").read_text() == "93%"


def test_render_stage_input_list_names_the_root_template(tmp_path):
    from src.pipeline import run as run_mod
    paths = _paths(tmp_path)
    (paths.repo / "README.tmpl.md").write_text("x")
    (paths.repo / "docs" / "A.tmpl.md").write_text("x")
    names = run_mod.STAGE_INPUTS["render"](paths)
    assert "template_README.tmpl.md" in names and "template_A.tmpl.md" in names


def test_config_numbers_come_from_config_and_fill_templates(tmp_path):
    from src.pipeline.config import BUS_SPECS, E_SCALE_CEILING_MULT, SCALE_RANGE, SEATS_FRACTION
    n = render.config_numbers()
    assert n["seats_12m_ac"] == BUS_SPECS["12m_ac"].seats and n["crush_9m_devi"] == BUS_SPECS["9m_devi"].crush
    assert n["rated_12m_nonac"] == BUS_SPECS["12m_nonac"].rated_total
    assert n["seats_fraction"] == SEATS_FRACTION and (n["scale_low"], n["scale_high"]) == SCALE_RANGE
    assert n["e_scale_ceiling"] == E_SCALE_CEILING_MULT
    assert n["gps_sample_days"] == 10 and n["min_daily_trips"] == 3 and n["no_data_cutoff"] == 0.5
    t, out = _tmpl(tmp_path, "{{seats_12m_ac}}/{{rated_12m_ac}}/{{crush_12m_ac}} x{{scale_low:.1f}}-{{scale_high:.1f}}")
    render.render_file(t, out, n)
    assert out.read_text() == "35/63/100 x0.7-1.3"
    assert all(not isinstance(v, (dict, list)) for v in n.values())


def test_run_fills_config_numbers_without_the_report(tmp_path):
    paths = _paths(tmp_path)
    (paths.repo / "README.tmpl.md").write_text("{{seats_12m_ac}} seats, ran {{run_id}}")
    render.run(None, paths)
    assert (paths.repo / "README.md").read_text() == "35 seats, ran rid"
