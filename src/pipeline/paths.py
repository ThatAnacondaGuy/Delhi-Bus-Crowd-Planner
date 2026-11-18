"""Filesystem layout for the pipeline."""
import os
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    repo: Path
    gtfs_dir: Path
    tickets_csv: Path
    gps_archive: Path
    gps_aggregates: Path
    processed: Path

    @property
    def planner_dir(self) -> Path:
        return self.processed / "planner"

    @property
    def work_db(self) -> Path:
        return self.processed / "work.duckdb"

    @property
    def manifest(self) -> Path:
        return self.processed / "manifest.json"

    @classmethod
    def default(cls) -> "Paths":
        raw = REPO / "data" / "raw"
        return cls(
            repo=REPO,
            gtfs_dir=raw / "gtfs" / "delhi_buses_static_gtfs_v1",
            tickets_csv=raw / "October-Delhi.csv",
            gps_archive=raw / "gps" / "delhi-dtc-bus-gtfs-rt-2026-10.7z",
            gps_aggregates=REPO / "data" / "gps_aggregates",
            processed=REPO / "data" / "processed",
        )

    @classmethod
    def from_env(cls) -> "Paths":
        """Like default(), but `processed` comes from DATA_DIR when set."""
        d = cls.default()
        env = os.environ.get("DATA_DIR")
        if not env:
            return d
        return cls(d.repo, d.gtfs_dir, d.tickets_csv, d.gps_archive, d.gps_aggregates, Path(env))
