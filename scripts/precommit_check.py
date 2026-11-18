"""Pre-commit guard: keep data and oversized files out of git."""
import os
import subprocess
import sys
from pathlib import PurePosixPath

MAX_BYTES = 5_000_000
PROCESSED_OK = {".json", ".md", ".csv"}


def _data_allowed(posix: str) -> bool:
    parts = PurePosixPath(posix).parts
    if "data" not in parts:
        return True
    rel = parts[parts.index("data") + 1:]
    if len(rel) == 2 and rel[0] == "processed":
        return PurePosixPath(rel[1]).suffix in PROCESSED_OK
    if len(rel) >= 2 and rel[0] == "gps_aggregates":
        return True
    return False


def check_paths(paths: list[str], max_bytes: int = MAX_BYTES) -> list[str]:
    errors = []
    for p in paths:
        posix = p.replace(os.sep, "/")
        if posix.startswith("data/") and not _data_allowed(posix):
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
