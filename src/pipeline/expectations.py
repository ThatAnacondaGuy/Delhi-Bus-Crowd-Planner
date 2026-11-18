"""Pre-registered validation expectations (loaded from validation/expectations.yaml)."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Corridor:
    name: str
    grade: str
    peak: list[str]
    direction: str | None
    gtfs_stop_names: list[str]
    sources: list[str]


@dataclass(frozen=True)
class Expectations:
    peaks: dict
    weekend: dict
    radial: dict
    corridors: list[Corridor]
    gps_stoptime_rho_min: float
    dtc_bus_km: tuple[float, float]
    load_factor_band: tuple[float, float]


GRADES = {"strong", "moderate", "weak"}
PEAKS = {"am", "pm"}


def load_expectations(path) -> Expectations:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for c in d["corridors"]:
        if c["grade"] not in GRADES:
            raise ValueError(f"corridor {c['name']!r}: bad grade {c['grade']!r}")
        bad = [p for p in c["peak"] if p not in PEAKS]
        if bad:
            raise ValueError(f"corridor {c['name']!r}: bad peak {bad!r}")
    corridors = [Corridor(c["name"], c["grade"], list(c["peak"]), c["direction"],
                          list(c["gtfs_stop_names"]), list(c["sources"]))
                 for c in d["corridors"]]
    pc = d["published_checks"]
    return Expectations(
        peaks=d["peaks"], weekend=d["weekend"], radial=d["radial"], corridors=corridors,
        gps_stoptime_rho_min=float(d["gps_stoptime"]["rho_min"]),
        dtc_bus_km=tuple(pc["dtc_bus_km"]["band"]),
        load_factor_band=tuple(pc["load_factor"]["band"]))
