"""Resumable-run manifest: which stages are done, against which inputs and code."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .paths import REPO, Paths


def _manifest_path(path) -> Path:
    return Path(path) if path is not None else Paths.from_env().processed / "manifest.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"stages": {}, "hash_cache": {}}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def code_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=10)
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def versions() -> dict:
    out = {"code": code_version()}
    for pkg in ("duckdb", "pandas"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "unknown"
    return out


def _sha256(path: str, data: dict) -> str:
    """SHA-256 of a file, cached by size+mtime inside the manifest."""
    p = Path(path)
    if not p.exists():
        return "missing"
    st = p.stat()
    cache = data.setdefault("hash_cache", {})
    hit = cache.get(str(p.resolve()))
    if hit and hit["size"] == st.st_size and hit["mtime_ns"] == st.st_mtime_ns:
        return hit["sha256"]
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    cache[str(p.resolve())] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": h.hexdigest()}
    return h.hexdigest()


def mark_done(stage: str, inputs: dict[str, str], outputs: list[str], params: dict | None = None,
              path=None) -> None:
    mp = _manifest_path(path)
    data = _load(mp)
    data.setdefault("stages", {})[stage] = {
        "done": True,
        "inputs": {k: _sha256(v, data) for k, v in inputs.items()},
        "params": params or {},
        "versions": versions(),
        "outputs": [str(o) for o in outputs],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(mp, data)


def is_done(stage: str, inputs: dict[str, str], params: dict | None = None, path=None) -> bool:
    mp = _manifest_path(path)
    data = _load(mp)
    rec = data.get("stages", {}).get(stage)
    if not rec or not rec.get("done"):
        return False
    if rec.get("versions") != versions() or rec.get("params", {}) != (params or {}):
        return False
    current = {k: _sha256(v, data) for k, v in inputs.items()}
    if rec.get("inputs") != current:
        return False
    return all(Path(o).exists() for o in rec.get("outputs", []))
