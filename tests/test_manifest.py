import json
import re

from src.pipeline import manifest


def test_run_id_written_and_stable_for_same_inputs(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("a")
    mp = tmp_path / "manifest.json"
    manifest.mark_done("clean", {"x": str(f)}, [], path=mp)
    rid = json.loads(mp.read_text())["run_id"]
    assert re.fullmatch(r"\d{8}-\d{4}-[0-9a-f]{8}", rid)
    manifest.mark_done("clean", {"x": str(f)}, [], path=mp)
    rid2 = json.loads(mp.read_text())["run_id"]
    assert rid2.split("-")[2] == rid.split("-")[2]  # same inputs, same hash part
    f.write_text("b")
    manifest.mark_done("clean", {"x": str(f)}, [], path=mp)
    rid3 = json.loads(mp.read_text())["run_id"]
    assert rid3.split("-")[2] != rid.split("-")[2]
