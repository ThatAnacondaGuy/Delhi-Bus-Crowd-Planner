"""Pre-commit guard: keep data and oversized files out of git."""
import os
import posixpath
import subprocess
import sys
from pathlib import Path, PurePosixPath

MAX_BYTES = 5_000_000
PROCESSED_OK = {".json", ".md", ".csv"}
BANNED_SUFFIXES = {".parquet", ".pkl", ".geojson", ".7z", ".db", ".duckdb"}
ROOT = Path(__file__).resolve().parents[1]


def _normalise(p: str) -> str:
    """Repo-relative posix path with leading './' and '..' segments resolved."""
    path = Path(p)
    if path.is_absolute():
        try:
            path = path.relative_to(ROOT)
        except ValueError:
            return path.as_posix()
    return posixpath.normpath(path.as_posix())


def _data_allowed(posix: str) -> bool:
    parts = PurePosixPath(posix).parts[1:]  # drop leading "data"
    if len(parts) == 2 and parts[0] == "processed":
        return PurePosixPath(parts[1]).suffix in PROCESSED_OK
    return len(parts) >= 2 and parts[0] == "gps_aggregates"


def check_paths(paths: list[str], max_bytes: int = MAX_BYTES) -> list[str]:
    errors = []
    for p in paths:
        posix = _normalise(p)
        suffix = PurePosixPath(posix).suffix.lower()
        if suffix in BANNED_SUFFIXES:
            errors.append(f"{p}: binary artifact ({suffix}) must never be committed")
        elif (posix == "data" or posix.startswith("data/")) and not _data_allowed(posix):
            errors.append(f"{p}: not allowed under data/ (only data/processed/*.json|md|csv and data/gps_aggregates/*)")
        if os.path.isfile(p) and os.path.getsize(p) > max_bytes:
            errors.append(f"{p}: larger than {max_bytes} bytes")
    return errors


def main(argv: list[str]) -> int:
    paths = argv or subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=True).stdout.split("\n")
    errors = check_paths([p for p in paths if p])
    for e in errors:
        print(f"precommit: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
